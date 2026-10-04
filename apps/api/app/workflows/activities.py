import tempfile
from pathlib import Path

from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ..database import SessionLocal
from ..domain.errors import InvalidMedia
from ..domain.processing import process
from ..domain.scanning import get_scanner
from ..models import MediaAsset, MediaStatus, ProcessingJob
from ..storage import get_storage


@activity.defn
def process_media(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if not job or job.state == "completed":
            return
        asset = db.scalar(select(MediaAsset).where(MediaAsset.id == job.asset_id).with_for_update())
        if not asset:
            return
        if asset.status == MediaStatus.ready:
            job.state = "completed"
            db.commit()
            return
        asset.status = MediaStatus.processing
        job.state, job.attempts = "running", activity.info().attempt
        asset_id, key, mime, expected_size, project_id = (
            asset.id,
            asset.storage_key,
            asset.mime_type,
            asset.size_bytes,
            asset.project_id,
        )
        db.commit()
    try:
        with tempfile.TemporaryDirectory(prefix="biographer-") as directory:
            folder = Path(directory)
            original = folder / "original"
            storage = get_storage()
            head = storage.head(key)
            if not head or head["ContentLength"] != expected_size:
                raise InvalidMedia("The stored original is missing or its size changed")
            storage.download(key, original)
            if original.stat().st_size != expected_size:
                raise InvalidMedia("The downloaded original has an unexpected size")
            scan = get_scanner().scan(original)
            result = process(original, mime, folder)
            result["details"]["security_scan"] = scan
            for kind in ("thumbnail", "proxy"):
                artifact = result.pop(kind, None)
                if artifact:
                    derived_key = f"projects/{project_id}/processed/{asset_id}/{kind}{artifact.suffix}"
                    derived_mime = {".jpg": "image/jpeg", ".mp4": "video/mp4", ".mp3": "audio/mpeg"}[
                        artifact.suffix
                    ]
                    storage.put(derived_key, artifact, derived_mime)
                    result[kind + "_key"] = derived_key
            with SessionLocal() as db:
                asset = db.get(MediaAsset, asset_id)
                job = db.get(ProcessingJob, job_id)
                if asset and job:
                    for field, value in result.items():
                        setattr(asset, field, value)
                    asset.status, asset.error = MediaStatus.ready, None
                    job.state = "completed"
                    db.commit()
    except InvalidMedia as error:
        with SessionLocal() as db:
            asset = db.get(MediaAsset, asset_id)
            if asset:
                asset.error = str(error)
                db.commit()
        raise ApplicationError(str(error), non_retryable=True) from error


@activity.defn
def mark_media_failed(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if not job or job.state == "completed":
            return
        asset = db.get(MediaAsset, job.asset_id)
        if asset:
            asset.status = MediaStatus.failed
            asset.error = asset.error or "Processing could not finish after three attempts. Please retry."
        job.state = "failed"
        db.commit()
