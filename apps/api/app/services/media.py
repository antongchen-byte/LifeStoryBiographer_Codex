from pathlib import PurePath

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.errors import DomainError
from ..domain.formats import part_size, part_sizes, validate_upload
from ..models import (
    AuditEvent,
    MediaAsset,
    MediaStatus,
    ProcessingJob,
    Project,
    ProjectMember,
    StyleSource,
    User,
    new_id,
)
from ..schemas import MediaRead, UploadComplete, UploadCreate, UploadPart, UploadStarted
from ..storage import ObjectStorage
from .projects import audit


def find(db: Session, project_id: str, asset_id: str, lock: bool = False) -> MediaAsset:
    query = select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.project_id == project_id)
    if lock:
        query = query.with_for_update()
    asset = db.scalar(query)
    if not asset:
        raise DomainError(404, "Media asset not found")
    return asset


def present(asset: MediaAsset) -> MediaRead:
    result = MediaRead.model_validate(asset)
    result.has_thumbnail = bool(asset.thumbnail_key)
    result.has_proxy = bool(asset.proxy_key)
    return result


def resume(asset: MediaAsset, storage: ObjectStorage) -> UploadStarted:
    urls, parts = [], []
    if (
        asset.status == MediaStatus.uploading
        and asset.multipart_upload_id
        and not storage.head(asset.storage_key)
    ):
        parts = [
            UploadPart(part_number=p["PartNumber"], etag=p["ETag"])
            for p in storage.parts(asset.storage_key, asset.multipart_upload_id)
        ]
        urls = [
            storage.sign_part(asset.storage_key, asset.multipart_upload_id, i + 1, size)
            for i, size in enumerate(part_sizes(asset.size_bytes))
        ]
    return UploadStarted(
        asset_id=asset.id,
        status=asset.status,
        part_size=part_size(asset.size_bytes),
        part_urls=urls,
        uploaded_parts=parts,
    )


def duplicates(db, project, user, data):
    # Existing audit events provide uploader identity for old as well as new assets.
    uploaded_by_user = select(AuditEvent.target_id).where(
        AuditEvent.actor_id == user.id, AuditEvent.action == "media.upload_started"
    )
    rows = db.execute(
        select(MediaAsset, Project.title)
        .join(Project, MediaAsset.project_id == Project.id)
        .join(ProjectMember, (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user.id))
        .where(
            MediaAsset.id.in_(uploaded_by_user),
            func.lower(MediaAsset.original_filename) == data.filename.lower(),
            MediaAsset.size_bytes == data.size_bytes,
            or_(
                MediaAsset.project_id != project.id,
                MediaAsset.idempotency_key != data.idempotency_key,
                MediaAsset.idempotency_key.is_(None),
            ),
        )
        .order_by(MediaAsset.created_at.desc())
        .limit(10)
    )
    return [
        {
            "asset_id": a.id,
            "project_id": a.project_id,
            "project_title": title,
            "filename": a.original_filename,
            "status": a.status.value,
        }
        for a, title in rows
    ]


def start(
    db: Session, project: Project, user: User, data: UploadCreate, storage: ObjectStorage
) -> UploadStarted:
    validate_upload(data.filename, data.mime_type, data.size_bytes)
    existing = db.scalar(
        select(MediaAsset).where(
            MediaAsset.project_id == project.id, MediaAsset.idempotency_key == data.idempotency_key
        )
    )
    if existing:
        if (existing.original_filename, existing.mime_type, existing.size_bytes) != (
            data.filename,
            data.mime_type,
            data.size_bytes,
        ):
            raise DomainError(409, "This upload key belongs to a different file")
        return resume(existing, storage)
    if not data.allow_duplicate and duplicates(db, project, user, data):
        raise DomainError(
            409,
            "You already uploaded a file with this name and size. Check your existing materials, or confirm that another copy is necessary.",
        )
    identifier = new_id()
    key = f"projects/{project.id}/originals/{identifier}{PurePath(data.filename).suffix.lower()}"
    upload_id = storage.begin(key, data.mime_type)
    asset = MediaAsset(
        id=identifier,
        project_id=project.id,
        original_filename=data.filename,
        mime_type=data.mime_type,
        size_bytes=data.size_bytes,
        storage_key=key,
        multipart_upload_id=upload_id,
        idempotency_key=data.idempotency_key,
        ownership_declared=True,
    )
    db.add(asset)
    audit(db, project.id, user.id, "media.upload_started", identifier)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.abort(key, upload_id)
        existing = db.scalar(
            select(MediaAsset).where(
                MediaAsset.project_id == project.id, MediaAsset.idempotency_key == data.idempotency_key
            )
        )
        if existing:
            return resume(existing, storage)
        raise DomainError(409, "The project changed during upload. Please retry.") from None
    except Exception:
        db.rollback()
        storage.abort(key, upload_id)
        raise
    return resume(asset, storage)


def complete(
    db: Session, asset: MediaAsset, user: User, body: UploadComplete, storage: ObjectStorage
) -> MediaRead:
    if asset.status != MediaStatus.uploading:
        return present(asset)
    sizes = part_sizes(asset.size_bytes)
    head = storage.head(asset.storage_key)
    if head is None:
        if [p.part_number for p in body.parts] != list(range(1, len(sizes) + 1)):
            raise DomainError(422, "All upload parts must be consecutive and ordered")
        if not asset.multipart_upload_id:
            raise DomainError(409, "This upload is no longer active")
        stored = storage.parts(asset.storage_key, asset.multipart_upload_id)
        if len(stored) != len(sizes) or any(
            p["PartNumber"] != i + 1
            or p["Size"] != size
            or p["ETag"].strip('"') != body.parts[i].etag.strip('"')
            for i, (p, size) in enumerate(zip(stored, sizes))
        ):
            raise DomainError(422, "Uploaded parts do not match the expected sizes and checksums")
        storage.complete(
            asset.storage_key,
            asset.multipart_upload_id,
            [{"PartNumber": p.part_number, "ETag": p.etag} for p in body.parts],
        )
        head = storage.head(asset.storage_key)
    if not head or head["ContentLength"] != asset.size_bytes:
        asset.status, asset.error = MediaStatus.failed, "Uploaded size does not match declared size"
        db.commit()
        raise DomainError(422, asset.error)
    asset.status, asset.multipart_upload_id = MediaStatus.uploaded, None
    db.add(ProcessingJob(asset_id=asset.id))
    audit(db, asset.project_id, user.id, "media.upload_completed", asset.id)
    db.commit()
    return present(asset)


def retry(db: Session, asset: MediaAsset, user: User) -> MediaRead:
    if asset.status != MediaStatus.failed:
        raise DomainError(409, "Only failed processing jobs can be retried")
    asset.status, asset.error = MediaStatus.uploaded, None
    db.add(ProcessingJob(asset_id=asset.id))
    audit(db, asset.project_id, user.id, "media.processing_retried", asset.id)
    db.commit()
    return present(asset)


def remove(db: Session, asset: MediaAsset, user: User, storage: ObjectStorage) -> None:
    if db.scalar(select(StyleSource.id).where(StyleSource.asset_id == asset.id)):
        raise DomainError(409, "This recording is retained as Style Lab evidence")
    if asset.status in {MediaStatus.uploaded, MediaStatus.processing}:
        raise DomainError(409, "Wait for processing to finish before deleting this file")
    if asset.multipart_upload_id:
        storage.abort(asset.storage_key, asset.multipart_upload_id)
    derived = f"projects/{asset.project_id}/processed/{asset.id}"
    for key in {
        asset.storage_key,
        asset.thumbnail_key,
        asset.proxy_key,
        f"{derived}/thumbnail.jpg",
        f"{derived}/proxy.mp4",
        f"{derived}/proxy.mp3",
    }:
        if key:
            storage.delete(key)
    audit(db, asset.project_id, user.id, "media.deleted", asset.id)
    db.delete(asset)
    db.commit()
