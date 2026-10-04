from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .domain.errors import DomainError
from .main import DB, Actor, Storage
from .models import (
    InterviewerProfile,
    StyleJob,
    StylePattern,
    StyleVersion,
    TranscriptArchive,
    TranscriptTurn,
)
from .services import archive, projects, style
from .style_schemas import (
    JobCreate,
    PatternReview,
    ProfileCreate,
    Publish,
    SourceCreate,
    SpeakerRole,
    TurnInput,
)

router = APIRouter(prefix="/api")


@router.get("/profiles")
def profiles(db: DB, user: Actor):
    return [
        {"id": p.id, "name": p.name, "project_id": p.project_id, "description": p.description}
        for p in db.scalars(
            select(InterviewerProfile)
            .where(InterviewerProfile.owner_id == user.id)
            .order_by(InterviewerProfile.created_at.desc())
        )
    ]


@router.post("/profiles", status_code=201)
def create_profile(body: ProfileCreate, db: DB, user: Actor):
    projects.access(db, body.project_id, user, owner=True)
    p = InterviewerProfile(owner_id=user.id, **body.model_dump())
    db.add(p)
    db.flush()
    projects.audit(db, p.project_id, user.id, "style.profile_created", p.id)
    db.commit()
    return style.details(db, p)


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str, db: DB, user: Actor):
    return style.details(db, style.profile(db, profile_id, user))


@router.post("/profiles/{profile_id}/assets", status_code=201)
def add_source(profile_id: str, body: SourceCreate, db: DB, user: Actor):
    return style.attach(db, style.profile(db, profile_id, user, True), body.asset_id)


@router.get("/profiles/{profile_id}/sources/{source_id}/turns")
def turns(
    profile_id: str,
    source_id: str,
    db: DB,
    user: Actor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    p = style.profile(db, profile_id, user)
    s = style.source(db, p, source_id)
    query = (
        select(TranscriptTurn)
        .where(TranscriptTurn.source_id == s.id)
        .order_by(TranscriptTurn.start_ms, TranscriptTurn.id)
    )
    return {
        "items": [style.turn_dict(t) for t in db.scalars(query.offset(offset).limit(limit))],
        "total": db.scalar(
            select(func.count()).select_from(TranscriptTurn).where(TranscriptTurn.source_id == s.id)
        ),
    }


@router.post("/profiles/{profile_id}/sources/{source_id}/turns", status_code=201)
def add_turn(profile_id: str, source_id: str, body: TurnInput, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    return style.edit_turn(db, p, style.source(db, p, source_id), body)


@router.patch("/profiles/{profile_id}/sources/{source_id}/turns/{turn_id}")
def edit_turn(profile_id: str, source_id: str, turn_id: str, body: TurnInput, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    return style.edit_turn(db, p, style.source(db, p, source_id), body, turn_id)


@router.post("/profiles/{profile_id}/sources/{source_id}/review", status_code=204)
def review_source(profile_id: str, source_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    style.review_source(db, p, style.source(db, p, source_id))


@router.post("/profiles/{profile_id}/sources/{source_id}/transcribe", status_code=202)
def transcribe(profile_id: str, source_id: str, body: JobCreate, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    return style.enqueue(db, p, body, "transcribe", style.source(db, p, source_id))


@router.post("/profiles/{profile_id}/analyze", status_code=202)
def analyze(profile_id: str, body: JobCreate, db: DB, user: Actor):
    return style.enqueue(db, style.profile(db, profile_id, user, True), body, "analyze")


@router.post("/profiles/{profile_id}/patterns", status_code=201)
def add_pattern(profile_id: str, body: PatternReview, db: DB, user: Actor):
    return style.save_pattern(db, style.profile(db, profile_id, user, True), body)


@router.patch("/profiles/{profile_id}/style-drafts/{pattern_id}")
def edit_pattern(profile_id: str, pattern_id: str, body: PatternReview, db: DB, user: Actor):
    return style.save_pattern(db, style.profile(db, profile_id, user, True), body, pattern_id)


@router.get("/profiles/{profile_id}/patterns/{pattern_id}/evidence")
def pattern_evidence(profile_id: str, pattern_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user)
    pat = db.scalar(
        select(StylePattern).where(StylePattern.profile_id == p.id, StylePattern.id == pattern_id)
    )
    if not pat:
        raise DomainError(404, "Pattern not found")
    return style.evidence(db, p, pat.evidence_ids, require_reviewed=False)


@router.post("/profiles/{profile_id}/versions", status_code=201)
def publish(profile_id: str, body: Publish, db: DB, user: Actor):
    return style.publish(db, style.profile(db, profile_id, user, True), body.request_id)


@router.get("/profiles/{profile_id}/versions/{version_id}")
def version(profile_id: str, version_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user)
    v = db.scalar(select(StyleVersion).where(StyleVersion.profile_id == p.id, StyleVersion.id == version_id))
    if not v:
        raise DomainError(404, "Version not found")
    return {"id": v.id, "number": v.number, "snapshot": v.snapshot}


@router.get("/jobs/{job_id}")
def job(job_id: str, db: DB, user: Actor):
    j = db.get(StyleJob, job_id)
    if not j:
        raise DomainError(404, "Job not found")
    style.profile(db, j.profile_id, user)
    return style.job_dict(j)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: str, db: DB, user: Actor):
    j = db.get(StyleJob, job_id)
    if not j:
        raise DomainError(404, "Job not found")
    p = style.profile(db, j.profile_id, user, True)
    style.idle(db, p)
    db.refresh(j, with_for_update=True)
    if j.state not in {"failed", "cancelled"}:
        raise DomainError(409, "Only failed or stopped jobs can be resumed")
    # A fresh Temporal execution keeps DB checkpoints from the failed execution.
    j.state, j.error = "pending", None
    j.generation += 1
    if j.kind == "analyze":
        j.completed, j.total, j.checkpoint = 0, 0, []
    projects.audit(db, p.project_id, user.id, "style.job_retried", j.id)
    db.commit()
    return style.job_dict(j)


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: str, db: DB, user: Actor):
    from .models import StyleSource

    p = style.profile(db, profile_id, user, True)
    style.idle(db, p)
    source_ids = list(db.scalars(select(StyleSource.id).where(StyleSource.profile_id == p.id)))
    db.query(StyleJob).filter(StyleJob.profile_id == p.id).delete(synchronize_session=False)
    db.query(StyleVersion).filter(StyleVersion.profile_id == p.id).delete(synchronize_session=False)
    db.query(StylePattern).filter(StylePattern.profile_id == p.id).delete(synchronize_session=False)
    db.query(TranscriptTurn).filter(TranscriptTurn.source_id.in_(source_ids)).delete(
        synchronize_session=False
    )
    db.query(StyleSource).filter(StyleSource.profile_id == p.id).delete(synchronize_session=False)
    projects.audit(db, p.project_id, user.id, "style.profile_deleted", p.id)
    db.delete(p)
    db.commit()


@router.patch("/profiles/{profile_id}/sources/{source_id}/speakers", status_code=204)
def identify_speaker(profile_id: str, source_id: str, body: SpeakerRole, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    style.idle(db, p)
    s = style.source(db, p, source_id)
    if db.scalar(
        select(StyleJob.id).where(
            StyleJob.source_id == s.id,
            StyleJob.kind == "transcribe",
            StyleJob.state.in_(("failed", "cancelled")),
        )
    ):
        raise DomainError(409, "Resume failed transcription before identifying speakers")
    turns = list(db.scalars(select(TranscriptTurn).where(TranscriptTurn.source_id == s.id)))
    turns = [
        t
        for t in turns
        if (
            style.speaker_group(t.speaker) == style.speaker_group(body.speaker)
            if body.across_sections
            else t.speaker == body.speaker
        )
    ]
    if not turns:
        raise DomainError(404, "Speaker not found in this recording")
    style.invalidate(db, p, s)
    for label in {t.speaker for t in turns}:
        style.apply_speaker_role(db, s, label, body.role)
    projects.audit(db, p.project_id, user.id, "style.speaker_identified", s.id)
    db.commit()


@router.post("/jobs/{job_id}/stop", status_code=202)
def stop_job(job_id: str, db: DB, user: Actor):
    j = db.get(StyleJob, job_id)
    if not j:
        raise DomainError(404, "Job not found")
    p = style.profile(db, j.profile_id, user, True)
    db.refresh(j, with_for_update=True)
    if j.state in {"pending", "failed"}:
        j.state, j.error = "cancelled", None
    elif j.state in {"running", "dispatched"}:
        j.state, j.error = "stopping", None
    projects.audit(db, p.project_id, user.id, "style.job_stop_requested", j.id)
    db.commit()
    return style.job_dict(j)


@router.delete("/profiles/{profile_id}/sources/{source_id}", status_code=204)
def delete_recording(profile_id: str, source_id: str, db: DB, user: Actor, storage: Storage):
    p = style.profile(db, profile_id, user, True)
    style.delete_recording(db, p, source_id, user, storage)


class ArchivePrepare(BaseModel):
    revision: int = Field(ge=0)


class ArchiveSaved(BaseModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    folder_label: str = Field(min_length=1, max_length=255)


@router.post("/profiles/{profile_id}/sources/{source_id}/archives")
def prepare_archive(profile_id: str, source_id: str, body: ArchivePrepare, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    return archive.prepare(db, p, style.source(db, p, source_id), body.revision)


@router.get("/profiles/{profile_id}/sources/{source_id}/archives")
def list_archives(profile_id: str, source_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user)
    s = style.source(db, p, source_id)
    return [
        archive.result(a)
        for a in db.scalars(
            select(TranscriptArchive)
            .where(TranscriptArchive.source_id == s.id)
            .order_by(TranscriptArchive.revision.desc())
        )
    ]


@router.get("/profiles/{profile_id}/archives/{archive_id}")
def get_archive(profile_id: str, archive_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user)
    return archive.export(archive.get(db, p, archive_id))


@router.post("/profiles/{profile_id}/archives/{archive_id}/saved")
def archive_saved(profile_id: str, archive_id: str, body: ArchiveSaved, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    return archive.saved(db, p, archive.get(db, p, archive_id), body.sha256, body.folder_label)


@router.get("/profiles/{profile_id}/memory")
def search_memory(
    profile_id: str,
    db: DB,
    user: Actor,
    q: str = Query(min_length=1, max_length=300),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    p = style.profile(db, profile_id, user)
    return archive.search(db, p, q, offset, limit)


@router.get("/profiles/{profile_id}/sources/{source_id}/speakers")
def speaker_roles(profile_id: str, source_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user)
    return style.speaker_summary(db, style.source(db, p, source_id))


@router.delete("/profiles/{profile_id}/sources/{source_id}/script", status_code=204)
def delete_script(profile_id: str, source_id: str, db: DB, user: Actor):
    p = style.profile(db, profile_id, user, True)
    style.delete_script(db, p, style.source(db, p, source_id))


@router.delete("/jobs/{job_id}", status_code=204)
def delete_processing(job_id: str, db: DB, user: Actor):
    j = db.get(StyleJob, job_id)
    if not j:
        raise DomainError(404, "Job not found")
    p = style.profile(db, j.profile_id, user, True)
    style.idle(db, p)
    db.refresh(j, with_for_update=True)
    if j.state not in {"failed", "cancelled", "completed"}:
        raise DomainError(409, "Stop processing and wait for it to finish stopping before deleting")
    if j.kind == "transcribe" and j.source_id:
        style.delete_script(db, p, style.source(db, p, j.source_id))
    else:
        projects.audit(db, p.project_id, user.id, "style.processing_deleted", j.id)
        db.delete(j)
        db.commit()
