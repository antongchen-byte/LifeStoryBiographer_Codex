from contextlib import nullcontext

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from app.models import MediaAsset, MediaStatus, ProcessingJob, Project
from app.workflows import activities


def setup_job(db, storage, monkeypatch, content, mime):
    project = Project(subject_name="Worker Test")
    db.add(project)
    db.flush()
    asset = MediaAsset(
        project_id=project.id,
        original_filename="test.txt",
        mime_type=mime,
        size_bytes=len(content),
        storage_key="test-original",
        status=MediaStatus.uploaded,
    )
    db.add(asset)
    db.flush()
    job = ProcessingJob(asset_id=asset.id)
    db.add(job)
    db.commit()
    storage.objects[asset.storage_key] = content
    monkeypatch.setattr(activities, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(activities, "get_storage", lambda: storage)
    return asset, job


def test_activity_is_idempotent(db, storage, monkeypatch):
    asset, job = setup_job(db, storage, monkeypatch, b"A synthetic memory.", "text/plain")
    environment = ActivityEnvironment()
    environment.run(activities.process_media, job.id)
    assert asset.status == MediaStatus.ready
    assert job.state == "completed"
    assert len(asset.checksum_sha256) == 64

    def unexpected_download(key, path):
        raise AssertionError("Completed jobs must not process a second time")

    monkeypatch.setattr(storage, "download", unexpected_download)
    environment.run(activities.process_media, job.id)


def test_invalid_media_reaches_a_visible_terminal_state(db, storage, monkeypatch):
    asset, job = setup_job(db, storage, monkeypatch, b"Not an image.", "image/jpeg")
    environment = ActivityEnvironment()
    with pytest.raises(ApplicationError) as failure:
        environment.run(activities.process_media, job.id)
    assert failure.value.non_retryable
    environment.run(activities.mark_media_failed, job.id)
    assert asset.status == MediaStatus.failed
    assert job.state == "failed"
    assert asset.error
