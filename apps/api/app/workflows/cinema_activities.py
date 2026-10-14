import hashlib
import json
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import select
from temporalio import activity

from ..ai.veo_provider import VeoProvider, VideoFailure
from ..cinema_models import CinemaJob, CinemaProduction
from ..interview_database import SessionLocal
from ..storage import get_storage


def command(args, heartbeat=lambda: None, timeout=900):
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors)
        start = time.monotonic()
        try:
            while process.poll() is None:
                heartbeat()
                if time.monotonic() - start > timeout:
                    raise VideoFailure("Video processing timed out")
                time.sleep(1)
            if process.returncode:
                raise VideoFailure("Video processing failed. The generated file could not be decoded")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        timeout=30,
        check=True,
    )
    data = json.loads(result.stdout)
    if not any(s["codec_type"] == "video" for s in data["streams"]):
        raise VideoFailure("Generated file contains no video")
    duration = float(data["format"]["duration"])
    if not 0 < duration < 3600:
        raise VideoFailure("Generated clip duration is invalid")
    return duration, any(s["codec_type"] == "audio" for s in data["streams"])


def photo(storage, key, target):
    original = target.with_suffix(".source")
    storage.download(key, original)
    with Image.open(original) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1920, 1920))
        image.save(target, "PNG")


def run_cinema(
    identifier,
    factory=SessionLocal,
    storage=None,
    provider_factory=VeoProvider,
    heartbeat=lambda: None,
    pause=time.sleep,
):
    storage = storage or get_storage()
    with factory() as db:
        job = db.get(CinemaJob, identifier, with_for_update=True)
        if not job or job.state in {"ready", "failed"}:
            return
        p = db.get(CinemaProduction, job.production_id)
        payload, kind, operation = dict(job.request), job.kind, job.operation
        snapshot, interview_uid, owner_id, production_id = p.snapshot, p.interview_uid, p.owner_id, p.id
        if kind == "clip" and job.state == "submitting" and not operation:
            job.state, job.error = (
                "failed",
                "Submission was interrupted before its operation ID was saved. Check Gemini usage before manually regenerating; it may have been billed.",
            )
            db.commit()
            return
        job.state = "polling" if operation else "running"
        db.commit()
    prefix = f"interviews/{owner_id}/{interview_uid}/cinema/{production_id}/{identifier}"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            output = work / ("clips.zip" if kind == "bundle" else "video.mp4")
            frame_key, duration = None, None
            if kind == "clip":
                provider = provider_factory()
                if not operation:
                    refs = []
                    materials = {m["id"]: m for m in snapshot["materials"]}
                    for index, mid in enumerate(payload["material_ids"]):
                        heartbeat()
                        path = work / f"photo-{index}.png"
                        photo(
                            storage,
                            payload.get("reference_keys", {}).get(mid, materials[mid]["storage_key"]),
                            path,
                        )
                        refs.append(path)
                    first = None
                    if payload["previous_frame_key"]:
                        first = work / "first.png"
                        storage.download(payload["previous_frame_key"], first)
                    with factory() as db:
                        j = db.get(CinemaJob, identifier, with_for_update=True)
                        j.state = "submitting"
                        db.commit()
                    heartbeat()
                    operation = provider.submit(payload["prompt"], payload["continuity"], first, refs)
                    with factory() as db:
                        j = db.get(CinemaJob, identifier, with_for_update=True)
                        j.operation, j.state = operation, "polling"
                        db.commit()
                uri = None
                for _ in range(720):
                    heartbeat()
                    uri = provider.poll(operation)
                    if uri:
                        break
                    pause(10)
                if not uri:
                    raise VideoFailure(
                        "Veo is taking longer than two hours. The operation ID is saved; use Resume generation to recover it"
                    )
                provider.download(uri, output)
                with factory() as db:
                    j = db.get(CinemaJob, identifier, with_for_update=True)
                    j.state = "processing"
                    db.commit()
                duration, _ = probe(output)
                frame = work / "last.png"
                # Decode the tail and overwrite one image through the final decoded frame.
                command(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-sseof",
                        "-2",
                        "-i",
                        str(output),
                        "-map",
                        "0:v:0",
                        "-an",
                        "-fps_mode",
                        "passthrough",
                        "-update",
                        "1",
                        str(frame),
                    ],
                    heartbeat,
                )
                if not frame.exists():
                    raise VideoFailure("Could not extract the final video frame")
                frame_key = prefix + "/last-frame.png"
                storage.put(frame_key, frame, "image/png")
            else:
                with factory() as db:
                    records = {
                        j.id: j
                        for j in db.scalars(select(CinemaJob).where(CinemaJob.id.in_(payload["clip_ids"])))
                    }
                clips, manifest = (
                    [],
                    {
                        "interview_uid": interview_uid,
                        "screenplay_id": snapshot["id"],
                        "screenplay_revision": snapshot["revision"],
                        "production_id": production_id,
                        "clips": [],
                    },
                )
                for index, cid in enumerate(payload["clip_ids"]):
                    heartbeat()
                    clip = records[cid]
                    if clip.production_id != production_id or not clip.output_key:
                        raise VideoFailure("An approved source clip is missing")
                    path = work / f"{index + 1:03d}-{clip.subsection_id}.mp4"
                    storage.download(clip.output_key, path)
                    clips.append(path)
                    manifest["clips"].append(
                        {
                            "id": cid,
                            "subsection_id": clip.subsection_id,
                            "filename": path.name,
                            "prompt": clip.request,
                            "duration": clip.duration,
                            "sha256": clip.sha256,
                        }
                    )
                if kind == "bundle":
                    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                        for clip in clips:
                            archive.write(clip, "clips/" + clip.name)
                else:
                    normalized = []
                    for index, clip in enumerate(clips):
                        length, audio = probe(clip)
                        target = work / f"normalized-{index}.mp4"
                        args = ["ffmpeg", "-y", "-v", "error", "-i", str(clip)]
                        if not audio:
                            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                        args += [
                            "-map",
                            "0:v:0",
                            "-map",
                            "0:a:0" if audio else "1:a:0",
                            "-t",
                            str(length),
                            "-vf",
                            "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-pix_fmt",
                            "yuv420p",
                            "-c:a",
                            "aac",
                            "-ar",
                            "48000",
                            "-ac",
                            "2",
                            str(target),
                        ]
                        command(args, heartbeat)
                        normalized.append(target)
                    listing = work / "concat.txt"
                    listing.write_text("\n".join(f"file '{path.name}'" for path in normalized))
                    command(
                        [
                            "ffmpeg",
                            "-y",
                            "-v",
                            "error",
                            "-f",
                            "concat",
                            "-safe",
                            "1",
                            "-i",
                            str(listing),
                            "-c",
                            "copy",
                            "-movflags",
                            "+faststart",
                            str(output),
                        ],
                        heartbeat,
                    )
                    duration, _ = probe(output)
            key = prefix + "/" + output.name
            with output.open("rb") as source:
                checksum = hashlib.file_digest(source, "sha256").hexdigest()
            storage.put(key, output, "application/zip" if kind == "bundle" else "video/mp4")
            with factory() as db:
                j = db.get(CinemaJob, identifier, with_for_update=True)
                j.output_key, j.frame_key, j.duration, j.sha256 = key, frame_key, duration, checksum
                j.state, j.error = "ready", None
                db.commit()
    except Exception as error:
        with factory() as db:
            j = db.get(CinemaJob, identifier, with_for_update=True)
            if j and j.state != "ready":
                j.state = "failed"
                j.error = (
                    str(error)
                    if isinstance(error, VideoFailure)
                    else "Video processing failed. Saved clips are retained. Retry or resume the saved operation."
                )
                db.commit()


@activity.defn
def process_cinema(identifier: str):
    run_cinema(identifier, heartbeat=lambda: activity.heartbeat())


@activity.defn
def fail_cinema(identifier: str):
    with SessionLocal() as db:
        j = db.get(CinemaJob, identifier, with_for_update=True)
        if j and j.state != "ready":
            j.state, j.error = (
                "failed",
                "Video job interrupted. Resume the saved operation if available; otherwise check Gemini usage before regenerating.",
            )
            db.commit()
