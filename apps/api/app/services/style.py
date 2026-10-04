"""Owner-scoped review state. Profile row locks serialize all draft mutations."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.errors import DomainError
from ..models import (
    InterviewerProfile,
    MediaAsset,
    MediaStatus,
    StyleJob,
    StylePattern,
    StyleSource,
    StyleVersion,
    TranscriptTurn,
    User,
)
from ..style_schemas import JobCreate, PatternReview, TurnInput
from .projects import access, audit

ACTIVE = ("pending", "dispatched", "running", "stopping")


def profile(db: Session, identifier: str, user: User, lock=False):
    query = select(InterviewerProfile).where(
        InterviewerProfile.id == identifier, InterviewerProfile.owner_id == user.id
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if not row:
        raise DomainError(404, "Interviewer profile not found")
    access(db, row.project_id, user, owner=True)
    return row


def idle(db, p):
    if db.scalar(select(StyleJob.id).where(StyleJob.profile_id == p.id, StyleJob.state.in_(ACTIVE))):
        raise DomainError(409, "Wait for the current Style Lab job to finish before editing")


def source(db, p, identifier):
    s = db.scalar(select(StyleSource).where(StyleSource.id == identifier, StyleSource.profile_id == p.id))
    if not s:
        raise DomainError(404, "Recording not found")
    return s


def turn_dict(t):
    return {
        k: getattr(t, k)
        for k in (
            "id",
            "source_id",
            "chunk_index",
            "speaker",
            "role",
            "role_override",
            "start_ms",
            "end_ms",
            "text",
        )
    }


def pattern_dict(p):
    return {
        k: getattr(p, k)
        for k in (
            "id",
            "category",
            "instruction",
            "example",
            "confidence",
            "evidence_ids",
            "review_status",
            "origin",
        )
    }


def job_dict(j):
    return {
        k: getattr(j, k)
        for k in (
            "id",
            "profile_id",
            "source_id",
            "kind",
            "state",
            "completed",
            "total",
            "model",
            "error",
            "created_at",
        )
    }


def details(db, p):
    sources = []
    for s, a in db.execute(
        select(StyleSource, MediaAsset)
        .join(MediaAsset)
        .where(StyleSource.profile_id == p.id)
        .order_by(StyleSource.created_at)
    ):
        sources.append(
            {
                "id": s.id,
                "asset_id": a.id,
                "filename": a.original_filename,
                "mime_type": a.mime_type,
                "duration_ms": a.duration_ms,
                "reviewed": s.reviewed,
                "revision": s.revision,
                "turn_count": db.scalar(
                    select(func.count()).select_from(TranscriptTurn).where(TranscriptTurn.source_id == s.id)
                ),
            }
        )
    return {
        "id": p.id,
        "project_id": p.project_id,
        "name": p.name,
        "description": p.description,
        "sources": sources,
        "patterns": [
            pattern_dict(r)
            for r in db.scalars(
                select(StylePattern).where(StylePattern.profile_id == p.id).order_by(StylePattern.id)
            )
        ],
        "versions": [
            {
                "id": v.id,
                "number": v.number,
                "created_at": v.created_at,
                "pattern_count": len(v.snapshot["patterns"]),
            }
            for v in db.scalars(
                select(StyleVersion)
                .where(StyleVersion.profile_id == p.id)
                .order_by(StyleVersion.number.desc())
            )
        ],
        "jobs": [
            job_dict(j)
            for j in db.scalars(
                select(StyleJob)
                .where(StyleJob.profile_id == p.id)
                .order_by(StyleJob.created_at.desc())
                .limit(20)
            )
        ],
        "provider_ready": bool(settings.gemini_api_key and settings.gemini_model),
        "question_plan_status": "awaiting_reference_questions",
    }


def attach(db, p, asset_id):
    idle(db, p)
    a = db.scalar(
        select(MediaAsset)
        .where(MediaAsset.id == asset_id, MediaAsset.project_id == p.project_id)
        .with_for_update()
    )
    if not a:
        raise DomainError(404, "Recording not found in this project")
    if a.status != MediaStatus.ready or not a.mime_type.startswith(("audio/", "video/")) or not a.duration_ms:
        raise DomainError(422, "Choose a processed audio or video recording with a valid duration")
    s = db.scalar(select(StyleSource).where(StyleSource.profile_id == p.id, StyleSource.asset_id == a.id))
    if not s:
        s = StyleSource(profile_id=p.id, asset_id=a.id)
        db.add(s)
        audit(db, p.project_id, p.owner_id, "style.source_added", a.id)
        db.commit()
    return {"id": s.id}


def invalidate(db, p, s):
    s.reviewed = False
    s.revision += 1
    ids = set(db.scalars(select(TranscriptTurn.id).where(TranscriptTurn.source_id == s.id)))
    for pat in db.scalars(select(StylePattern).where(StylePattern.profile_id == p.id)):
        if ids.intersection(pat.evidence_ids):
            pat.review_status = "pending"


def speaker_group(label):
    label = re.sub(r"^\d+:\s*", "", label).strip()
    return re.sub(r"^Speaker\s+", "", label, flags=re.IGNORECASE)


def speaker_summary(db, s):
    turns = list(db.scalars(select(TranscriptTurn).where(TranscriptTurn.source_id == s.id)))
    groups = {}
    for t in turns:
        name = speaker_group(t.speaker)
        g = groups.setdefault(
            name,
            {
                "speaker": name,
                "labels": set(),
                "roles": set(),
                "turn_count": 0,
                "unassigned": 0,
                "overrides": 0,
            },
        )
        g["labels"].add(t.speaker)
        g["turn_count"] += 1
        g["unassigned"] += t.role == "unknown"
        g["overrides"] += bool(t.role_override)
        if not t.role_override:
            g["roles"].add(t.role)
    roles = {t.role for t in turns}
    return {
        "items": [
            {**g, "labels": sorted(g["labels"]), "roles": sorted(g["roles"])}
            for g in sorted(groups.values(), key=lambda g: g["speaker"])
        ],
        "unassigned": sum(t.role == "unknown" for t in turns),
        "missing_roles": [role for role in ("interviewer", "participant") if role not in roles],
    }


def apply_speaker_role(db, s, speaker, role):
    # Explicit local corrections survive later changes to the speaker default.
    for turn in db.scalars(
        select(TranscriptTurn).where(
            TranscriptTurn.source_id == s.id,
            TranscriptTurn.speaker == speaker,
            TranscriptTurn.role_override.is_(False),
        )
    ):
        turn.role = role


def edit_turn(db, p, s, data: TurnInput, identifier=None):
    idle(db, p)
    # A failed transcript must be resumed before manual editing, so retries cannot overwrite reviews.
    if db.scalar(
        select(StyleJob.id).where(
            StyleJob.source_id == s.id,
            StyleJob.kind == "transcribe",
            StyleJob.state.in_(("failed", "cancelled")),
        )
    ):
        raise DomainError(409, "Resume the failed transcription before editing this recording")
    asset = db.get(MediaAsset, s.asset_id)
    if data.end_ms > asset.duration_ms:
        raise DomainError(422, "Transcript timestamps exceed the recording duration")
    t = (
        db.scalar(
            select(TranscriptTurn).where(TranscriptTurn.id == identifier, TranscriptTurn.source_id == s.id)
        )
        if identifier
        else None
    )
    if identifier and not t:
        raise DomainError(404, "Transcript turn not found")
    invalidate(db, p, s)
    if t is None:
        t = TranscriptTurn(source_id=s.id, **data.model_dump(exclude={"role_scope"}))
        db.add(t)
    else:
        for key, value in data.model_dump(exclude={"role_scope"}).items():
            setattr(t, key, value)
    if data.role_scope == "speaker":
        t.role_override = False
        apply_speaker_role(db, s, data.speaker, data.role)
    elif data.role_scope == "turn":
        t.role_override = True
    audit(db, p.project_id, p.owner_id, "style.transcript_edited", s.id)
    db.commit()
    return turn_dict(t)


def review_source(db, p, s, commit=True):
    idle(db, p)
    if db.scalar(
        select(StyleJob.id).where(
            StyleJob.source_id == s.id, StyleJob.kind == "transcribe", StyleJob.state != "completed"
        )
    ):
        raise DomainError(409, "Finish transcription before approving it")
    roles = list(db.scalars(select(TranscriptTurn.role).where(TranscriptTurn.source_id == s.id)))
    if "interviewer" not in roles or "participant" not in roles or "unknown" in roles:
        raise DomainError(
            422, "Identify all speakers, including an interviewer and participant, before approving"
        )
    s.reviewed = True
    audit(db, p.project_id, p.owner_id, "style.transcript_reviewed", s.id)
    if commit:
        db.commit()


def evidence(db, p, ids, require_reviewed=True):
    rows = list(
        db.execute(
            select(TranscriptTurn, StyleSource, MediaAsset)
            .join(StyleSource, TranscriptTurn.source_id == StyleSource.id)
            .join(MediaAsset, StyleSource.asset_id == MediaAsset.id)
            .where(TranscriptTurn.id.in_(ids), StyleSource.profile_id == p.id)
            .order_by(StyleSource.id, TranscriptTurn.start_ms, TranscriptTurn.id)
        )
    )
    if len({r[0].id for r in rows}) != len(set(ids)) or not any(t.role == "interviewer" for t, _, _ in rows):
        raise DomainError(
            422, "Evidence must cite this profile's transcript and include interviewer behavior"
        )
    if require_reviewed and any(not s.reviewed for _, s, _ in rows):
        raise DomainError(422, "Approve the source transcripts before using their evidence")
    return [
        {**turn_dict(t), "filename": a.original_filename, "asset_id": a.id, "source_revision": s.revision}
        for t, s, a in rows
    ]


def save_pattern(db, p, data: PatternReview, identifier=None):
    idle(db, p)
    evidence(db, p, data.evidence_ids)
    if data.review_status == "approved" and not data.anonymized_confirmed:
        raise DomainError(
            422,
            "Confirm that the rule and example contain no identifying source facts or unconfirmed intentions",
        )
    pat = (
        db.scalar(select(StylePattern).where(StylePattern.id == identifier, StylePattern.profile_id == p.id))
        if identifier
        else None
    )
    if identifier and not pat:
        raise DomainError(404, "Style pattern not found")
    values = data.model_dump(exclude={"anonymized_confirmed"})
    values["evidence_ids"] = list(dict.fromkeys(data.evidence_ids))
    if pat is None:
        pat = StylePattern(profile_id=p.id, **values)
        db.add(pat)
    else:
        for key, value in values.items():
            setattr(pat, key, value)
    audit(db, p.project_id, p.owner_id, "style.pattern_reviewed", p.id)
    db.commit()
    return pattern_dict(pat)


def enqueue(db, p, data: JobCreate, kind, s=None):
    old = db.scalar(
        select(StyleJob).where(StyleJob.profile_id == p.id, StyleJob.request_id == data.request_id)
    )
    if old:
        if old.kind != kind or old.source_id != (s.id if s else None):
            raise DomainError(409, "Request ID already used for a different job")
        return job_dict(old)
    idle(db, p)
    if not settings.gemini_api_key or not settings.gemini_model:
        raise DomainError(503, "Set GEMINI_API_KEY and GEMINI_MODEL on the server to enable AI processing")
    if kind == "transcribe":
        old_source_job = db.scalar(select(StyleJob).where(StyleJob.source_id == s.id, StyleJob.kind == kind))
        if old_source_job:
            raise DomainError(409, "This recording already has a transcription job; resume it if it failed")
        if db.scalar(select(TranscriptTurn.id).where(TranscriptTurn.source_id == s.id)):
            raise DomainError(409, "This recording already has a manual transcript")
    else:
        sources = list(db.scalars(select(StyleSource).where(StyleSource.profile_id == p.id)))
        if not sources or any(not source.reviewed for source in sources):
            raise DomainError(422, "Approve every recording's transcript before analyzing style")
    job = StyleJob(
        profile_id=p.id,
        source_id=s.id if s else None,
        kind=kind,
        request_id=data.request_id,
        model=settings.gemini_model,
    )
    db.add(job)
    audit(db, p.project_id, p.owner_id, "style.provider_processing_requested", p.id)
    db.commit()
    return job_dict(job)


def publish(db, p, request_id):
    old = db.scalar(
        select(StyleVersion).where(StyleVersion.profile_id == p.id, StyleVersion.request_id == request_id)
    )
    if old:
        return {"id": old.id, "number": old.number, "snapshot": old.snapshot}
    idle(db, p)
    patterns = list(
        db.scalars(
            select(StylePattern)
            .where(StylePattern.profile_id == p.id, StylePattern.review_status == "approved")
            .order_by(StylePattern.id)
        )
    )
    if not patterns:
        raise DomainError(422, "Approve at least one evidence-backed pattern before publishing")
    snapshot = {
        "profile_name": p.name,
        "patterns": [
            {**pattern_dict(pat), "evidence": evidence(db, p, pat.evidence_ids)} for pat in patterns
        ],
        "scope": "private",
        "question_plan_status": "awaiting_reference_questions",
    }
    number = (
        db.scalar(select(func.max(StyleVersion.number)).where(StyleVersion.profile_id == p.id)) or 0
    ) + 1
    v = StyleVersion(profile_id=p.id, number=number, request_id=request_id, snapshot=snapshot)
    db.add(v)
    audit(db, p.project_id, p.owner_id, "style.published", p.id)
    db.commit()
    return {"id": v.id, "number": v.number, "snapshot": v.snapshot}


def delete_recording(db, p, source_id, user, storage):
    from ..models import TranscriptArchive
    from . import media

    idle(db, p)
    s = source(db, p, source_id)
    if db.scalar(select(TranscriptArchive.id).where(TranscriptArchive.source_id == s.id)):
        raise DomainError(
            409, "This recording supports an approved script archive and must be retained as evidence"
        )
    asset = media.find(db, p.project_id, s.asset_id, lock=True)
    if db.scalar(select(StyleSource.id).where(StyleSource.asset_id == s.asset_id, StyleSource.id != s.id)):
        raise DomainError(
            409, "This recording is also used by another Style Lab profile; it cannot be deleted here"
        )
    for version in db.scalars(select(StyleVersion).where(StyleVersion.profile_id == p.id)):
        if any(
            e.get("asset_id") == asset.id
            for pattern in version.snapshot.get("patterns", [])
            for e in pattern.get("evidence", [])
        ):
            raise DomainError(
                409, "This recording supports a published style version and must be retained as evidence"
            )
    turn_ids = set(db.scalars(select(TranscriptTurn.id).where(TranscriptTurn.source_id == s.id)))
    for pattern in db.scalars(select(StylePattern).where(StylePattern.profile_id == p.id)):
        if turn_ids.intersection(pattern.evidence_ids):
            db.delete(pattern)
    db.query(StyleJob).filter(StyleJob.source_id == s.id).delete(synchronize_session=False)
    db.query(TranscriptTurn).filter(TranscriptTurn.source_id == s.id).delete(synchronize_session=False)
    db.delete(s)
    db.flush()
    # Existing deletion removes original/proxies and commits references atomically in the DB.
    media.remove(db, asset, user, storage)


def delete_script(db, p, s):
    from ..models import TranscriptArchive

    idle(db, p)
    turn_ids = set(db.scalars(select(TranscriptTurn.id).where(TranscriptTurn.source_id == s.id)))
    for pattern in db.scalars(select(StylePattern).where(StylePattern.profile_id == p.id)):
        if turn_ids.intersection(pattern.evidence_ids):
            db.delete(pattern)
    # Published snapshots contain copies of the deleted text; remove affected versions too.
    for version in db.scalars(select(StyleVersion).where(StyleVersion.profile_id == p.id)):
        if any(
            e.get("source_id") == s.id or e.get("asset_id") == s.asset_id
            for pattern in version.snapshot.get("patterns", [])
            for e in pattern.get("evidence", [])
        ):
            db.delete(version)
    db.query(TranscriptArchive).filter(TranscriptArchive.source_id == s.id).delete(synchronize_session=False)
    # Analysis checkpoints can contain derived copies of this script.
    db.query(StyleJob).filter(
        StyleJob.profile_id == p.id, (StyleJob.source_id == s.id) | (StyleJob.kind == "analyze")
    ).delete(synchronize_session=False)
    db.query(TranscriptTurn).filter(TranscriptTurn.source_id == s.id).delete(synchronize_session=False)
    s.reviewed = False
    s.revision += 1
    audit(db, p.project_id, p.owner_id, "style.script_deleted", s.id)
    db.commit()
