"""Sequential bounded audio processing inspired by VocalExtract-Pro (see docs/style-lab.md)."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from temporalio import activity

from ..ai.style_provider import PROMPT_VERSION, GeminiStyleProvider, ProcessingStopped, ProviderFailure
from ..database import SessionLocal
from ..models import InterviewerProfile, MediaAsset, StyleJob, StylePattern, StyleSource, TranscriptTurn
from ..services.style import evidence, turn_dict
from ..storage import get_storage

CHUNK_MS = 30_000
BATCH_TURNS = 80


def chunk_ranges(duration_ms: int):
    if not 0 < duration_ms <= 4 * 60 * 60 * 1000:
        raise ValueError("Recording must be between zero and four hours")
    return [(start, min(CHUNK_MS, duration_ms - start)) for start in range(0, duration_ms, CHUNK_MS)]


def extract_segment(source: Path, target: Path, start_ms: int, duration_ms: int):
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-ss",
            str(start_ms / 1000),
            "-i",
            str(source),
            "-t",
            str(duration_ms / 1000),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(target),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )


def stop_requested(job_id, generation):
    with SessionLocal() as check:
        current = check.get(StyleJob, job_id)
        return (
            current is None or current.generation != generation or current.state in {"stopping", "cancelled"}
        )


def check_execution(db, job, generation):
    db.refresh(job)
    if job.generation != generation or job.state in {"stopping", "cancelled"}:
        raise ProcessingStopped()
    # Release the read transaction before the slow external request.
    db.commit()


def fence(db, job, generation):
    db.refresh(job, with_for_update=True)
    if job.generation != generation or job.state in {"stopping", "cancelled"}:
        raise ProcessingStopped()
    if job.state not in {"running", "dispatched", "pending"}:
        raise ProviderFailure("This worker execution is no longer active")


def transcribe(db, job, provider, storage, heartbeat):
    generation = job.generation
    source = db.get(StyleSource, job.source_id)
    asset = db.get(MediaAsset, source.asset_id)
    ranges = chunk_ranges(asset.duration_ms)
    check_execution(db, job, generation)
    job.total = len(ranges)
    db.commit()
    with TemporaryDirectory(prefix="style-audio-") as directory:
        local = Path(directory) / ("recording" + Path(asset.original_filename).suffix)
        heartbeat("downloading")
        storage.download(asset.storage_key, local)
        target = Path(directory) / "segment.mp3"
        for index in range(job.completed, len(ranges)):
            start, length = ranges[index]
            heartbeat(index)
            extract_segment(local, target, start, length)
            check_execution(db, job, generation)
            result = provider.transcribe(target.read_bytes(), length)
            fence(db, job, generation)
            if job.completed > index:
                db.commit()
                continue
            for t in result.turns:
                if t.end_ms > length:
                    raise ProviderFailure(
                        "Transcript timestamps exceeded their audio segment; retry required"
                    )
                db.add(
                    TranscriptTurn(
                        source_id=source.id,
                        chunk_index=index,
                        speaker=f"{index + 1}: {t.speaker}"[:80],
                        role="unknown",
                        start_ms=start + t.start_ms,
                        end_ms=start + t.end_ms,
                        text=t.text,
                    )
                )
            # Turns and checkpoint commit atomically. Retries never duplicate a saved segment.
            job.completed = index + 1
            db.commit()
            target.unlink(missing_ok=True)
            heartbeat(index + 1)
    source.revision += 1
    source.reviewed = False


def analyze(db, job, provider, heartbeat):
    generation = job.generation
    p = db.get(InterviewerProfile, job.profile_id)
    turns = list(
        db.scalars(
            select(TranscriptTurn)
            .join(StyleSource)
            .where(StyleSource.profile_id == p.id)
            .order_by(StyleSource.id, TranscriptTurn.start_ms, TranscriptTurn.id)
        )
    )
    sources = list(db.scalars(select(StyleSource).where(StyleSource.profile_id == p.id)))
    if not sources or any(not s.reviewed for s in sources):
        raise ProviderFailure("Source review changed; approve all transcripts before analyzing")
    # At most 80 turns / ~640k characters per extraction. Include two previous turns for boundaries.
    batches = [turns[max(0, i - 2) : i + BATCH_TURNS] for i in range(0, len(turns), BATCH_TURNS)]
    job.total = len(batches) + 1
    db.commit()
    for index in range(job.completed, len(batches)):
        heartbeat(index)
        batch = batches[index]
        check_execution(db, job, generation)
        result = provider.analyze([turn_dict(t) for t in batch])
        allowed = {t.id for t in batch}
        candidates = []
        for pattern in result.patterns:
            if not set(pattern.evidence_ids).issubset(allowed):
                raise ProviderFailure("Style analysis cited an unknown transcript turn")
            ev = evidence(db, p, pattern.evidence_ids)
            candidates.append({**pattern.model_dump(), "source_ids": sorted({e["source_id"] for e in ev})})
        fence(db, job, generation)
        if job.completed > index:
            db.commit()
            continue
        job.checkpoint = [*job.checkpoint, *candidates]
        job.completed = index + 1
        db.commit()
    # Hierarchical reduction bounds requests for multi-hour/multiple recordings.
    candidates = list(job.checkpoint)
    while len(candidates) > 60:
        reduced = []
        for offset in range(0, len(candidates), 60):
            heartbeat("comparing")
            check_execution(db, job, generation)
            reduced.extend(consolidate_validated(db, p, provider, candidates[offset : offset + 60]))
        candidates = reduced
    heartbeat("finalizing")
    check_execution(db, job, generation)
    results = consolidate_validated(db, p, provider, candidates) if candidates else []
    fence(db, job, generation)
    for data in results:
        db.add(
            StylePattern(
                profile_id=p.id,
                **{k: v for k, v in data.items() if k != "source_ids"},
                review_status="pending",
                origin=f"gemini:{PROMPT_VERSION}",
            )
        )
    job.completed = job.total


def consolidate_validated(db, p, provider, candidates):
    allowed = {identifier for c in candidates for identifier in c["evidence_ids"]}
    output = provider.consolidate(candidates)
    result = []
    for pattern in output.patterns:
        if not set(pattern.evidence_ids).issubset(allowed):
            raise ProviderFailure("Style comparison cited unsupported evidence")
        ev = evidence(db, p, pattern.evidence_ids)
        result.append({**pattern.model_dump(), "source_ids": sorted({e["source_id"] for e in ev})})
    return result


@activity.defn
def process_style(job_id: str):
    with SessionLocal() as db:
        job = db.get(StyleJob, job_id, with_for_update=True)
        if not job or job.state in {"completed", "failed", "cancelled"}:
            return
        if job.state == "stopping":
            job.state = "cancelled"
            db.commit()
            return
        generation = job.generation
        job.state, job.error = "running", None
        db.commit()
        try:
            provider = GeminiStyleProvider(job.model)
            provider.should_stop = lambda: stop_requested(job_id, generation)
            if job.kind == "transcribe":
                transcribe(db, job, provider, get_storage(), activity.heartbeat)
            else:
                analyze(db, job, provider, activity.heartbeat)
            fence(db, job, generation)
            job.state = "completed"
            db.commit()
        except ProcessingStopped:
            db.rollback()
            job = db.get(StyleJob, job_id)
            if job and job.generation == generation and job.state == "stopping":
                job.state, job.error = "cancelled", None
                db.commit()
            return
        except Exception as error:
            db.rollback()
            job = db.get(StyleJob, job_id)
            if not job or job.generation != generation or job.state in {"completed", "failed", "cancelled"}:
                return
            if job.state == "stopping":
                job.state, job.error = "cancelled", None
                db.commit()
                return
            job.error = (
                str(error)
                if isinstance(error, ProviderFailure)
                else "Processing failed; retry to resume saved progress"
            )
            db.commit()
            # Do not place raw provider, storage, or transcript details in workflow histories.
            raise RuntimeError("Style processing failed; see job status") from None


@activity.defn
def mark_style_failed(job_id: str):
    with SessionLocal() as db:
        job = db.get(StyleJob, job_id)
        if job and job.state == "stopping":
            job.state, job.error = "cancelled", None
            db.commit()
        elif job and job.state not in {"completed", "cancelled"}:
            job.state = "failed"
            job.error = job.error or "Worker interrupted; retry to resume saved progress"
            db.commit()
