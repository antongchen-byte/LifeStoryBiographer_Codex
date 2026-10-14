"""Owner-scoped screenplay editing and durable generation."""

import hashlib
import json
import re
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import delete, select

from .cinema_models import CinemaProduction
from .config import settings
from .domain.errors import DomainError
from .domain.processing import checksum
from .interview_models import (
    InterviewApproval,
    InterviewMaterial,
    InterviewTurn,
    Screenplay,
    ScreenplaySection,
    ScreenplaySubsection,
)
from .interview_routes import IDB, material_record, put_bytes, session_access
from .main import DB, Actor, Storage
from .models import MediaAsset, MediaStatus, new_id
from .schemas import Boundary
from .screenplay_schemas import SaveScreenplay, SectionContent, source_hash
from .services import projects

router = APIRouter(prefix="/api/interviews/screenplays", tags=["screenplays"])
ACTIVE = {"pending", "dispatched", "running"}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def content_hash(content):
    return digest(json.dumps(content, sort_keys=True, ensure_ascii=False))


def access(main, db, user, identifier, lock=False):
    s = db.scalar(
        select(Screenplay)
        .where(Screenplay.id == identifier, Screenplay.owner_id == user.id)
        .with_for_update()
        if lock
        else select(Screenplay).where(Screenplay.id == identifier, Screenplay.owner_id == user.id)
    )
    if not s:
        raise DomainError(404, "Screenplay not found")
    projects.access(main, s.project_id, user, owner=True)
    return s


def editable(s, revision=None):
    if s.state in ACTIVE:
        raise DomainError(409, "Wait for generation to finish or stop it before editing")
    if revision is not None and revision != s.revision:
        raise DomainError(409, "This screenplay changed. Reload the saved version before editing")


def detail(db, s):
    sections = []
    for page in db.scalars(
        select(ScreenplaySection)
        .where(ScreenplaySection.screenplay_id == s.id)
        .order_by(ScreenplaySection.position)
    ):
        subs = []
        start = 0
        for sub in db.scalars(
            select(ScreenplaySubsection)
            .where(ScreenplaySubsection.section_id == page.id)
            .order_by(ScreenplaySubsection.position)
        ):
            subs.append(
                {
                    "id": sub.id,
                    "section_id": page.id,
                    "interview_uid": s.interview_uid,
                    "position": sub.position,
                    "start_seconds": start,
                    "seconds": sub.seconds,
                    "content": sub.content,
                }
            )
            start += sub.seconds
        sections.append(
            {
                "id": page.id,
                "position": page.position,
                "seconds": 60,
                "content": page.content,
                "subsections": subs,
                "breakdown_stale": bool(subs)
                and s.source.get("breakdown_hashes", {}).get(page.id) != content_hash(page.content),
            }
        )
    return {
        "id": s.id,
        "project_id": s.project_id,
        "session_id": s.session_id,
        "interview_uid": s.interview_uid,
        "title": s.title,
        "source": s.source,
        "reviewed_markdown": s.reviewed_markdown,
        "materials": s.materials,
        "sections": sections,
        "revision": s.revision,
        "state": s.state,
        "error": s.error,
        "progress": s.job.get("progress", 0),
        "job_kind": s.job.get("kind"),
        "draft_stale": bool(sections)
        and s.source.get("draft_source_sha256") != source_hash(s.reviewed_markdown, s.materials),
        "exports": s.exports,
    }


class Create(Boundary):
    session_id: str | None = None
    project_id: str | None = None
    markdown: str | None = Field(default=None, min_length=1, max_length=200000)
    filename: str = Field(default="interview.md", max_length=255)
    interview_uid: str | None = None


@router.post("", status_code=201)
def create(body: Create, main: DB, db: IDB, user: Actor):
    if bool(body.session_id) == bool(body.markdown):
        raise DomainError(422, "Select one database interview or one Markdown source")
    materials = []
    if body.session_id:
        interview = session_access(db, main, user, body.session_id, True)
        if interview.status == "active":
            raise DomainError(409, "Save the conversation for review before opening Screenplay Editor")
        approval = db.scalar(
            select(InterviewApproval)
            .where(InterviewApproval.session_id == interview.id)
            .order_by(InterviewApproval.created_at.desc())
        )
        markdown = (
            approval.script
            if approval
            else (
                f"# {interview.title}\n\nInterview UID: {interview.id}\n\n"
                + "\n\n".join(
                    f"## {t.sequence}. {t.role}\n\n{t.text}"
                    for t in db.scalars(
                        select(InterviewTurn)
                        .where(InterviewTurn.session_id == interview.id)
                        .order_by(InterviewTurn.sequence)
                    )
                )
            )
        )
        if len(markdown) > 200000:
            raise DomainError(
                422, "This interview exceeds the editor source limit; import a selected excerpt"
            )
        materials = [
            material_record(m)
            for m in db.scalars(select(InterviewMaterial).where(InterviewMaterial.session_id == interview.id))
        ]
        project_id, uid, title, model = interview.project_id, interview.id, interview.title, interview.model
        source = {
            "kind": "database",
            "interview_revision": interview.revision,
            "approval_id": approval.id if approval else None,
        }
    else:
        if not body.project_id:
            raise DomainError(422, "Choose a biography workspace for the imported file")
        projects.access(main, body.project_id, user, owner=True)
        if not body.filename.lower().endswith(".md"):
            raise DomainError(422, "Choose a .md file")
        markdown = body.markdown
        embedded = re.search(r"(?mi)^(?:Interview UID|Session):\s*([a-f0-9-]{36})\s*$", markdown)
        uid = body.interview_uid or (embedded.group(1) if embedded else new_id())
        try:
            uid = str(UUID(uid))
        except ValueError:
            raise DomainError(422, "Interview UID must be a UUID") from None
        project_id, title, model = body.project_id, Path(body.filename).stem, settings.gemini_model
        source = {
            "kind": "markdown",
            "filename": body.filename,
            "uid_origin": "imported" if embedded or body.interview_uid else "assigned",
            "notice": "Local filenames and links do not import materials. Attach files below or load the database interview.",
        }
    source["original_sha256"] = digest(markdown)
    s = Screenplay(
        owner_id=user.id,
        project_id=project_id,
        session_id=body.session_id,
        interview_uid=uid,
        title=title[:200],
        source=source,
        model=model,
        original_markdown=markdown,
        reviewed_markdown=markdown,
        materials=materials,
    )
    db.add(s)
    db.commit()
    return detail(db, s)


@router.get("")
def listing(main: DB, db: IDB, user: Actor):
    result = []
    for s in db.scalars(
        select(Screenplay).where(Screenplay.owner_id == user.id).order_by(Screenplay.created_at.desc())
    ):
        projects.access(main, s.project_id, user, owner=True)
        result.append(
            {
                "id": s.id,
                "title": s.title,
                "interview_uid": s.interview_uid,
                "state": s.state,
                "revision": s.revision,
            }
        )
    return result


@router.get("/{identifier}")
def get(identifier: str, main: DB, db: IDB, user: Actor):
    return detail(db, access(main, db, user, identifier))


@router.put("/{identifier}")
def save(identifier: str, body: SaveScreenplay, main: DB, db: IDB, user: Actor):
    s = access(main, db, user, identifier, True)
    editable(s, body.revision)
    pages = list(db.scalars(select(ScreenplaySection).where(ScreenplaySection.screenplay_id == s.id)))
    if {p.id for p in pages} != {p.id for p in body.sections} or len(pages) != len(body.sections):
        raise DomainError(422, "Section IDs must match this screenplay")
    allowed = {m["id"] for m in s.materials}
    for edit in body.sections:
        page = next(p for p in pages if p.id == edit.id)
        subs = list(
            db.scalars(select(ScreenplaySubsection).where(ScreenplaySubsection.section_id == page.id))
        )
        if {p.id for p in subs} != {p.id for p in edit.subsections} or len(subs) != len(edit.subsections):
            raise DomainError(422, "Subsection IDs must match their parent section")
        for content in [edit.content] + [p.content for p in edit.subsections]:
            if not set(content.material_ids).issubset(allowed):
                raise DomainError(422, "A section references unavailable material")
        if edit.content.elements[0].kind != "scene":
            raise DomainError(422, "Each 60-second section must begin with a scene heading")
        requested = {item.id: item for item in edit.subsections}
        children_changed = any(
            sub.content != requested[sub.id].content.model_dump() or sub.seconds != requested[sub.id].seconds
            for sub in subs
        )
        parent_content = edit.content.model_dump()
        if children_changed:
            hashes = dict(s.source.get("breakdown_hashes", {}))
            if parent_content != page.content or hashes.get(page.id) != content_hash(page.content):
                raise DomainError(
                    409,
                    "The parent section has separate edits. Save the section and regenerate "
                    "its subsections before editing them together.",
                )
            ordered = [requested[sub.id].content for sub in sorted(subs, key=lambda sub: sub.position)]
            elements = [element.model_dump() for content in ordered for element in content.elements]
            if elements[0]["kind"] != "scene":
                elements.insert(0, parent_content["elements"][0])
            # Keep section notes; subsection-specific notes remain with their own timing.
            parent_content = SectionContent(
                elements=elements,
                material_ids=list(
                    dict.fromkeys(
                        parent_content["material_ids"]
                        + [mid for content in ordered for mid in content.material_ids]
                    )
                ),
                notes=parent_content["notes"],
            ).model_dump()
            hashes[page.id] = content_hash(parent_content)
            s.source = {**s.source, "breakdown_hashes": hashes}
        page.content = parent_content
        for sub_edit in edit.subsections:
            sub = next(p for p in subs if p.id == sub_edit.id)
            sub.content, sub.seconds = sub_edit.content.model_dump(), sub_edit.seconds
    if not set(body.material_notes).issubset(allowed) or any(
        len(note) > 4000 for note in body.material_notes.values()
    ):
        raise DomainError(422, "Material notes must reference available material and fit 4000 characters")
    s.materials = [
        {**m, "editor_notes": body.material_notes.get(m["id"], m.get("editor_notes", ""))}
        for m in s.materials
    ]
    s.title, s.reviewed_markdown = body.title, body.reviewed_markdown
    s.revision += 1
    db.commit()
    return detail(db, s)


class Generate(Boundary):
    revision: int
    kind: str = Field(pattern="^(draft|breakdown)$")
    sections: int = Field(default=3, ge=1, le=30)
    seconds: int = Field(default=10)
    consent: bool = False


@router.post("/{identifier}/generate")
def generate(identifier: str, body: Generate, main: DB, db: IDB, user: Actor):
    s = access(main, db, user, identifier, True)
    editable(s, body.revision)
    if not body.consent:
        raise DomainError(422, "Consent to sending the reviewed source and material context to Gemini")
    if body.seconds not in {10, 15}:
        raise DomainError(422, "Choose 10- or 15-second subsections")
    data = detail(db, s)
    if body.kind == "breakdown" and (not data["sections"] or data["draft_stale"]):
        raise DomainError(409, "Generate a draft from the current reviewed conversation first")
    s.generation += 1
    s.state, s.error = "pending", None
    s.job = {"kind": body.kind, "count": body.sections, "seconds": body.seconds, "progress": 0, "results": []}
    s.revision += 1
    db.commit()
    return detail(db, s)


@router.post("/{identifier}/stop")
def stop(identifier: str, main: DB, db: IDB, user: Actor):
    s = access(main, db, user, identifier, True)
    if s.state in ACTIVE:
        s.generation += 1
        s.state, s.error = "idle", None
        s.revision += 1
        db.commit()
    return detail(db, s)


class Attach(Boundary):
    asset_ids: list[str] = Field(min_length=1, max_length=12)
    revision: int


@router.post("/{identifier}/materials")
def attach(identifier: str, body: Attach, main: DB, db: IDB, user: Actor, storage: Storage):
    s = access(main, db, user, identifier, True)
    editable(s, body.revision)
    result = list(s.materials)
    copied = []
    try:
        for aid in dict.fromkeys(body.asset_ids):
            if any(m["asset_id"] == aid for m in result):
                continue
            a = main.get(MediaAsset, aid)
            if not a or a.project_id != s.project_id or a.status != MediaStatus.ready:
                raise DomainError(422, "Select processed materials from this biography workspace")
            mid = new_id()
            filename = re.sub(r"[^a-zA-Z0-9._-]+", "_", a.original_filename).strip(".") or "material"
            key = f"interviews/{user.id}/{s.interview_uid}/screenplays/{s.id}/materials/{mid}/{filename}"
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "source"
                storage.download(a.storage_key, path)
                sha = checksum(path)
                if path.stat().st_size != a.size_bytes or (a.checksum_sha256 and a.checksum_sha256 != sha):
                    raise DomainError(409, "Material integrity check failed")
                copied.append(key)
                storage.put(key, path, a.mime_type)
            result.append(
                {
                    "id": mid,
                    "session_id": s.interview_uid,
                    "asset_id": aid,
                    "filename": a.original_filename,
                    "mime_type": a.mime_type,
                    "storage_key": key,
                    "sha256": sha,
                    "owned_copy": True,
                }
            )
        s.materials = result
        s.revision += 1
        db.commit()
    except Exception:
        db.rollback()
        for key in copied:
            storage.delete(key)
        raise
    return detail(db, s)


@router.get("/{identifier}/materials/{material_id}")
def material_url(identifier: str, material_id: str, main: DB, db: IDB, user: Actor, storage: Storage):
    s = access(main, db, user, identifier)
    m = next((m for m in s.materials if m["id"] == material_id), None)
    if not m:
        raise DomainError(404, "Material not found")
    return {"url": storage.sign_download(m["storage_key"], m["filename"])}


def render_content(content):
    lines = []
    for e in content["elements"]:
        indent = {"character": 22, "parenthetical": 16, "dialogue": 10, "transition": 40}.get(e["kind"], 0)
        lines.append(" " * indent + e["text"].replace("\n", "\n" + " " * indent))
    return "\n".join(lines)


def fenced_content(content):
    text = render_content(content)
    # Use a fence longer than any backtick run in the script, preserving its text.
    length = max([2] + [len(run) for run in re.findall(r"`+", text)]) + 1
    fence = "`" * length
    return f"{fence}text\n{text}\n{fence}"


def markdown_export(data):
    lines = [
        f"# {data['title']}",
        f"Interview UID: {data['interview_uid']}",
        f"Screenplay UID: {data['id']}",
        f"Revision: {data['revision']}",
        "Timing is estimated; validate with a read-through.",
    ]
    for page in data["sections"]:
        lines += [
            f"## Section {page['position']} — ~60 seconds",
            f"Section UID: {page['id']}",
            fenced_content(page["content"]),
            "Production notes: " + page["content"]["notes"],
            "Material UIDs: " + ", ".join(page["content"]["material_ids"]),
        ]
        for sub in page["subsections"]:
            lines += [
                f"### {page['position']}.{sub['position']} — {sub['start_seconds']}–{sub['start_seconds'] + sub['seconds']} seconds",
                f"Subsection UID: {sub['id']} | Section UID: {page['id']} | Interview UID: {data['interview_uid']}",
                fenced_content(sub["content"]),
                "Production notes: " + sub["content"]["notes"],
                "Material UIDs: " + ", ".join(sub["content"]["material_ids"]),
            ]
    lines += ["## Source materials"] + [
        f"- {m['filename']} | Material UID: {m['id']} | Interview UID: {data['interview_uid']} | Storage key: {m['storage_key']} | SHA-256: {m['sha256']}"
        for m in data["materials"]
    ]
    return "\n\n".join(lines) + "\n"


@router.post("/{identifier}/export")
def export(identifier: str, main: DB, db: IDB, user: Actor, storage: Storage):
    s = access(main, db, user, identifier, True)
    editable(s)
    data = detail(db, s)
    if (
        not data["sections"]
        or data["draft_stale"]
        or any(not p["subsections"] or p["breakdown_stale"] for p in data["sections"])
    ):
        raise DomainError(409, "Generate current subsections and save your edits before exporting")
    text = markdown_export(data)
    key = f"interviews/{user.id}/{s.interview_uid}/screenplays/{s.id}/revision-{s.revision}/screenplay.md"
    put_bytes(storage, key, text.encode(), "text/markdown")
    entry = {"revision": s.revision, "storage_key": key, "sha256": digest(text)}
    s.exports = [e for e in s.exports if e["revision"] != s.revision] + [entry]
    db.commit()
    return {"filename": f"screenplay-{s.interview_uid}-{s.id}.md", "markdown": text, **entry}


@router.delete("/{identifier}", status_code=204)
def remove(identifier: str, main: DB, db: IDB, user: Actor, storage: Storage):
    s = access(main, db, user, identifier, True)
    editable(s)
    if db.scalar(select(CinemaProduction.id).where(CinemaProduction.screenplay_id == s.id).limit(1)):
        raise DomainError(
            409, "This screenplay is used by Cinema Studio; retain it with its video provenance"
        )
    for m in s.materials:
        if m.get("owned_copy"):
            storage.delete(m["storage_key"])
    for item in s.exports:
        storage.delete(item["storage_key"])
    db.execute(
        delete(ScreenplaySubsection).where(
            ScreenplaySubsection.section_id.in_(
                select(ScreenplaySection.id).where(ScreenplaySection.screenplay_id == s.id)
            )
        )
    )
    db.execute(delete(ScreenplaySection).where(ScreenplaySection.screenplay_id == s.id))
    db.delete(s)
    db.commit()
