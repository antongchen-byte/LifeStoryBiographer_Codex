"""Versioned archive: local write acknowledgement precedes searchable indexing."""

import hashlib
import json

from sqlalchemy import func, literal_column, select

from ..domain.errors import DomainError
from ..models import ConversationMemoryTurn, MediaAsset, TranscriptArchive, TranscriptTurn, now
from . import style
from .projects import audit


def content(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def result(a):
    return {
        "id": a.id,
        "revision": a.revision,
        "sha256": a.sha256,
        "created_at": a.created_at,
        "saved_at": a.saved_at,
        "folder_label": a.folder_label,
    }


def export(a):
    snap = a.snapshot
    lines = [snap["filename"], f"Approved transcript · revision {a.revision}", ""]
    for t in snap["turns"]:
        lines.append(
            f"[{t['start_ms'] / 1000:.3f}–{t['end_ms'] / 1000:.3f}s] {t['speaker']} ({t['role']})\n{t['text']}\n"
        )
    return {
        **result(a),
        "filename": f"transcript-{a.source_id}-r{a.revision}-{a.id}",
        "json": content(snap),
        "text": "\n".join(lines),
    }


def prepare(db, p, s, revision):
    style.idle(db, p)
    if s.revision != revision:
        raise DomainError(409, "Transcript changed. Reload and review the current revision.")
    style.review_source(db, p, s, commit=False)
    a = db.scalar(
        select(TranscriptArchive).where(
            TranscriptArchive.source_id == s.id, TranscriptArchive.revision == revision
        )
    )
    if not a:
        asset = db.get(MediaAsset, s.asset_id)
        snapshot = {
            "schema_version": 1,
            "scope": "reference_interview",
            "project_id": p.project_id,
            "profile_id": p.id,
            "source_id": s.id,
            "asset_id": asset.id,
            "filename": asset.original_filename,
            "revision": revision,
            "approved_at": now().isoformat(),
            "approved_by": p.owner_id,
            "turns": [
                style.turn_dict(t)
                for t in db.scalars(
                    select(TranscriptTurn)
                    .where(TranscriptTurn.source_id == s.id)
                    .order_by(TranscriptTurn.start_ms, TranscriptTurn.id)
                )
            ],
        }
        a = TranscriptArchive(
            profile_id=p.id,
            source_id=s.id,
            revision=revision,
            snapshot=snapshot,
            sha256=hashlib.sha256(content(snapshot).encode()).hexdigest(),
        )
        db.add(a)
    db.commit()
    return export(a)


def get(db, p, archive_id):
    a = db.scalar(
        select(TranscriptArchive).where(
            TranscriptArchive.id == archive_id, TranscriptArchive.profile_id == p.id
        )
    )
    if not a:
        raise DomainError(404, "Archived script not found")
    return a


def saved(db, p, a, sha256, folder_label):
    if sha256 != a.sha256:
        raise DomainError(409, "Saved script checksum does not match the approved version")
    if a.saved_at is None:
        for t in a.snapshot["turns"]:
            db.add(
                ConversationMemoryTurn(
                    archive_id=a.id,
                    turn_id=t["id"],
                    **{k: t[k] for k in ("speaker", "role", "start_ms", "end_ms", "text")},
                )
            )
        a.saved_at, a.folder_label = now(), folder_label
        audit(db, p.project_id, p.owner_id, "style.script_saved_and_indexed", a.id)
        db.commit()
    return result(a)


def search(db, p, q, offset, limit):
    # Only the latest locally saved revision per recording; draft edits do not erase history.
    latest = (
        select(TranscriptArchive.source_id, func.max(TranscriptArchive.revision).label("revision"))
        .where(TranscriptArchive.profile_id == p.id, TranscriptArchive.saved_at.is_not(None))
        .group_by(TranscriptArchive.source_id)
        .subquery()
    )
    stmt = (
        select(ConversationMemoryTurn, TranscriptArchive)
        .join(TranscriptArchive)
        .join(
            latest,
            (TranscriptArchive.source_id == latest.c.source_id)
            & (TranscriptArchive.revision == latest.c.revision),
        )
        .where(TranscriptArchive.profile_id == p.id)
    )
    if db.bind.dialect.name == "postgresql":
        stmt = stmt.where(
            func.to_tsvector(literal_column("'simple'"), ConversationMemoryTurn.text).op("@@")(
                func.plainto_tsquery(literal_column("'simple'"), q)
            )
        )
    else:
        stmt = stmt.where(ConversationMemoryTurn.text.icontains(q, autoescape=True))
    rows = db.execute(
        stmt.order_by(TranscriptArchive.source_id, ConversationMemoryTurn.start_ms, ConversationMemoryTurn.id)
        .offset(offset)
        .limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "archive_id": a.id,
                "source_id": a.source_id,
                "revision": a.revision,
                "filename": a.snapshot["filename"],
                "turn_id": t.turn_id,
                "speaker": t.speaker,
                "role": t.role,
                "start_ms": t.start_ms,
                "end_ms": t.end_ms,
                "text": t.text,
            }
            for t, a in rows[:limit]
        ],
        "has_more": len(rows) > limit,
    }
