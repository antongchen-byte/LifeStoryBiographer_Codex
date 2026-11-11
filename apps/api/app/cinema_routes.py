"""Owner scoped video generation, review and archive endpoints."""

from .services import production_context as production

import tempfile
from pathlib import Path

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from .cinema_models import CinemaJob, CinemaProduction
from .domain.errors import DomainError
from .interview_routes import IDB
from .main import DB, Actor, Storage
from .models import MediaAsset, MediaStatus, new_id
from .schemas import Boundary
from .screenplay_routes import access, detail, markdown_export, render_content

router = APIRouter(prefix="/api/cinema", tags=["cinema"])
ACTIVE = {"pending", "dispatched", "running", "submitting", "polling", "processing"}
MODEL = "gemini-omni-1.1-flash"


def refresh_editor_photos(main, db, user, p):
    if not user.production_editor:
        return
    from .interview_models import InterviewMaterial, InterviewSession
    from .interview_routes import material_record
    materials = list(p.snapshot["materials"])
    seen = {m.get("asset_id") for m in materials}
    candidates = [material_record(m) for m in db.scalars(
        select(InterviewMaterial).join(InterviewSession, InterviewMaterial.session_id == InterviewSession.id)
        .where(InterviewSession.project_id == p.snapshot["project_id"], InterviewMaterial.mime_type.like("image/%"))
    )]
    candidates += [{"id": a.id, "asset_id": a.id, "filename": a.original_filename,
        "mime_type": a.mime_type, "storage_key": a.storage_key, "sha256": a.checksum_sha256}
        for a in main.scalars(select(MediaAsset).where(
            MediaAsset.project_id == p.snapshot["project_id"], MediaAsset.status == MediaStatus.ready,
            MediaAsset.mime_type.like("image/%"))) if not a.details.get("crop_source")]
    for record in candidates:
        if record.get("asset_id") not in seen:
            materials.append(record)
            seen.add(record.get("asset_id"))
    if materials != p.snapshot["materials"]:
        p.snapshot = {**p.snapshot, "materials": materials}
        db.flush()


def production_access(main, db, user, identifier, lock=False):
    p = db.scalar(
        select(CinemaProduction)
        .where(CinemaProduction.id == identifier, CinemaProduction.owner_id == production.owner_id(user))
        .with_for_update()
        if lock
        else select(CinemaProduction).where(
            CinemaProduction.id == identifier, CinemaProduction.owner_id == production.owner_id(user)
        )
    )
    if not p:
        raise DomainError(404, "Cinema production not found")
    access(main, db, user, p.screenplay_id)
    refresh_editor_photos(main, db, user, p)
    return p


def units(p):
    return [
        {**sub, "section_position": page["position"], "section_id": page["id"]}
        for page in p.snapshot["sections"]
        for sub in page["subsections"]
    ]


def jobs_for(db, p):
    return list(
        db.scalars(
            select(CinemaJob)
            .where(CinemaJob.production_id == p.id)
            .order_by(CinemaJob.created_at, CinemaJob.id)
        )
    )


def sequence(db, p):
    jobs = jobs_for(db, p)
    latest = {j.subsection_id: j for j in jobs if j.kind == "clip"}
    rows, previous, chain_valid = [], None, True
    for unit in units(p):
        job = latest.get(unit["id"])
        stale = bool(
            job
            and job.request.get("previous_id")
            and (not previous or job.request["previous_id"] != previous.id or not chain_valid)
        )
        chain_valid = bool(job and job.state == "ready" and not stale)
        rows.append((unit, job, stale))
        previous = job
    return rows


def job_data(job, storage):
    return {
        "id": job.id,
        "kind": job.kind,
        "state": job.state,
        "request": job.request,
        "duration": job.duration,
        "previewed": job.previewed,
        "approved": job.approved,
        "frame_ready": bool(job.frame_key),
        "error": job.error,
        "sha256": job.sha256,
        "recoverable": bool(job.operation) and job.state == "failed",
        "preview_url": storage.sign_download(job.output_key)
        if job.output_key and job.kind != "bundle"
        else None,
        "download_url": storage.sign_download(
            job.output_key, f"{job.kind}-{job.id}.{'zip' if job.kind == 'bundle' else 'mp4'}"
        )
        if job.output_key
        else None,
    }


def view(db, p, storage, all_project_photos=False):
    rows = sequence(db, p)
    ids = [j.id for _, j, stale in rows if j and j.state == "ready" and j.approved and not stale]
    return {
        "id": p.id,
        "screenplay_id": p.screenplay_id,
        "revision": p.source_revision,
        "interview_uid": p.interview_uid,
        "title": p.snapshot["title"],
        "model": MODEL,
        "all_project_photos": all_project_photos,
        "materials": [
            {"id": m["id"], "filename": m["filename"], "mime_type": m.get("mime_type", "")}
            for m in p.snapshot["materials"]
        ],
        "all_approved": bool(rows) and len(ids) == len(rows),
        "units": [
            {
                **unit,
                "prompt": render_content(unit["content"]),
                "stale": stale,
                "clip": job_data(job, storage) if job else None,
            }
            for unit, job, stale in rows
        ],
        "renders": [
            job_data(j, storage) for j in jobs_for(db, p) if j.kind != "clip" and j.request["clip_ids"] == ids
        ],
    }


@router.post("/screenplays/{identifier}")
def load(identifier: str, main: DB, db: IDB, user: Actor, storage: Storage):
    s = access(main, db, user, identifier, True)
    snapshot = detail(db, s)
    if (
        s.state in ACTIVE
        or not s.exports
        or not any(e["revision"] == s.revision for e in s.exports)
        or snapshot["draft_stale"]
        or not snapshot["sections"]
        or any(not p["subsections"] or p["breakdown_stale"] for p in snapshot["sections"])
    ):
        raise DomainError(
            409, "Save the final screenplay and current subsections in the Screenplay Editor first"
        )
    p = db.scalar(
        select(CinemaProduction).where(
            CinemaProduction.screenplay_id == s.id, CinemaProduction.source_revision == s.revision
        )
    )
    if not p:
        p = CinemaProduction(
            screenplay_id=s.id,
            owner_id=production.owner_id(user),
            interview_uid=s.interview_uid,
            source_revision=s.revision,
            snapshot=snapshot,
        )
        db.add(p)
        db.commit()
    refresh_editor_photos(main, db, user, p)
    db.commit()
    return view(db, p, storage, user.production_editor)


@router.get("/{identifier}")
def get(identifier: str, main: DB, db: IDB, user: Actor, storage: Storage):
    p = production_access(main, db, user, identifier)
    db.commit()
    return view(db, p, storage, user.production_editor)


class GenerateClip(Boundary):
    prompt: str = Field(min_length=1, max_length=12000)
    continuity: str = Field(default="", max_length=4000)
    previous_frame: bool = False
    material_ids: list[str] = Field(default_factory=list, max_length=3)
    material_variants: dict[str, str] = Field(default_factory=dict, max_length=3)
    consent: bool = False
    expected_clip_id: str | None = None


@router.post("/{identifier}/subsections/{subsection}/generate", status_code=202)
def generate(
    identifier: str, subsection: str, body: GenerateClip, main: DB, db: IDB, user: Actor, storage: Storage
):
    p = production_access(main, db, user, identifier, True)
    rows = sequence(db, p)
    index = next((i for i, (unit, _, _) in enumerate(rows) if unit["id"] == subsection), None)
    if index is None:
        raise DomainError(404, "Subsection not found")
    unit, current, _ = rows[index]
    seconds = unit["seconds"]
    if seconds not in {4, 6, 8}:
        raise DomainError(422, "Rebuild this legacy screenplay into 4-, 6- or 8-second subsections in Screenplay Editor and save a new final revision")
    if (current and current.state in ACTIVE) or body.expected_clip_id != (current.id if current else None):
        raise DomainError(409, "This clip changed or is generating. Reload before generating again")
    if not body.consent:
        raise DomainError(422, "Confirm sending the prompt and selected photos to Gemini Omni for paid generation")
    previous = None
    continuity = body.continuity
    if body.previous_frame and body.material_ids:
        raise DomainError(422, "Choose either the previous clip's final frame or reference photos, not both")
    if body.previous_frame:
        if index == 0:
            raise DomainError(422, "The first subsection has no previous clip")
        _, previous, stale = rows[index - 1]
        if not previous or previous.state != "ready" or stale or not previous.frame_key:
            raise DomainError(
                409,
                "Generate the previous clip and resolve any stale continuity first; its final frame must be available",
            )
        continuity = previous.request["continuity"]
    allowed = set(unit["content"]["material_ids"])
    materials = {m["id"]: m for m in p.snapshot["materials"]}
    if user.production_editor:
        allowed = set(materials)
    if len(set(body.material_ids)) != len(body.material_ids) or not set(body.material_ids).issubset(allowed):
        raise DomainError(422, "Choose only photos checked for this subsection in the Screenplay Editor")
    if any(
        mid not in materials or not materials[mid].get("mime_type", "").startswith("image/")
        for mid in body.material_ids
    ):
        raise DomainError(422, "Gemini Omni references must be uploaded photo materials")
    if not set(body.material_variants).issubset(body.material_ids):
        raise DomainError(422, "Crop selections must belong to selected photo references")
    variants = {}
    for mid, aid in body.material_variants.items():
        asset = main.get(MediaAsset, aid)
        if (
            not asset
            or asset.project_id != p.snapshot["project_id"]
            or asset.status != MediaStatus.ready
            or asset.details.get("crop_source") != {"scope": "cinema", "container": p.id, "id": mid}
        ):
            raise DomainError(422, "This cropped photo does not belong to this Cinema Studio material")
        variants[mid] = asset.storage_key
    job_id = new_id()
    reference_keys = {}
    # Freeze selected cropped bytes with the generation attempt so later media deletion cannot alter it.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for mid in body.material_ids:
                key = variants.get(mid, materials[mid]["storage_key"])
                path = Path(tmp) / "reference.jpg"
                storage.download(key, path)
                frozen = f"interviews/{production.owner_id(user)}/{p.interview_uid}/cinema/{p.id}/{job_id}/references/{mid}.jpg"
                storage.put(frozen, path, "image/jpeg" if mid in variants else materials[mid]["mime_type"])
                reference_keys[mid] = frozen
    except Exception:
        for key in reference_keys.values():
            storage.delete(key)
        raise
    job = CinemaJob(
        id=job_id,
        production_id=p.id,
        kind="clip",
        subsection_id=subsection,
        request={
            "actor_id": user.id, "project_id": p.snapshot["project_id"],
            "prompt": body.prompt,
            "continuity": continuity,
            "model": MODEL,
            "seconds": seconds,
            "material_ids": body.material_ids,
            "material_variants": body.material_variants,
            "reference_keys": reference_keys,
            "previous_id": previous.id if previous else None,
            "previous_frame_key": previous.frame_key if previous else None,
        },
    )
    try:
        db.add(job)
        db.commit()
    except Exception:
        db.rollback()
        for key in reference_keys.values():
            storage.delete(key)
        raise
    return view(db, p, storage, user.production_editor)


class Review(Boundary):
    approved: bool


@router.post("/{identifier}/clips/{clip_id}/previewed")
def previewed(identifier: str, clip_id: str, main: DB, db: IDB, user: Actor):
    p = production_access(main, db, user, identifier, True)
    job = db.get(CinemaJob, clip_id)
    if not job or job.production_id != p.id or job.kind != "clip" or job.state != "ready":
        raise DomainError(404, "Ready clip not found")
    job.previewed = True
    db.commit()
    return {"previewed": True}


@router.post("/{identifier}/clips/{clip_id}/review")
def review(identifier: str, clip_id: str, body: Review, main: DB, db: IDB, user: Actor, storage: Storage):
    p = production_access(main, db, user, identifier, True)
    row = next(((j, stale) for _, j, stale in sequence(db, p) if j and j.id == clip_id), None)
    if not row:
        raise DomainError(404, "Current clip not found")
    job, stale = row
    if job.state != "ready" or not job.previewed or (body.approved and stale):
        raise DomainError(409, "Preview the current clip and resolve continuity changes before approval")
    job.approved = body.approved
    db.commit()
    return view(db, p, storage, user.production_editor)


@router.post("/{identifier}/renders/{kind}", status_code=202)
def render(identifier: str, kind: str, main: DB, db: IDB, user: Actor, storage: Storage):
    if kind not in {"bundle", "stitch"}:
        raise DomainError(404, "Render type not found")
    p = production_access(main, db, user, identifier, True)
    rows = sequence(db, p)
    if not rows or any(not j or j.state != "ready" or not j.approved or stale for _, j, stale in rows):
        raise DomainError(409, "Preview and approve every current clip first")
    ids = [j.id for _, j, _ in rows]
    jobs = jobs_for(db, p)
    if kind == "stitch" and not any(
        j.kind == "bundle" and j.state == "ready" and j.request["clip_ids"] == ids for j in jobs
    ):
        raise DomainError(409, "Save the approved clips before stitching")
    existing = next(
        (
            j
            for j in reversed(jobs)
            if j.kind == kind and j.request["clip_ids"] == ids and j.state != "failed"
        ),
        None,
    )
    if not existing:
        db.add(CinemaJob(production_id=p.id, kind=kind, request={"clip_ids": ids, "actor_id": user.id, "project_id": p.snapshot["project_id"]}))
        db.commit()
    return view(db, p, storage, user.production_editor)


@router.post("/{identifier}/clips/{clip_id}/resume", status_code=202)
def resume(identifier: str, clip_id: str, main: DB, db: IDB, user: Actor, storage: Storage):
    p = production_access(main, db, user, identifier, True)
    job = next((j for _, j, _ in sequence(db, p) if j and j.id == clip_id), None)
    if not job or job.state != "failed" or not job.operation:
        raise DomainError(409, "Only a failed current clip with a saved operation can be resumed")
    db.add(
        CinemaJob(
            production_id=p.id,
            kind="clip",
            subsection_id=job.subsection_id,
            request=job.request,
            operation=job.operation,
        )
    )
    db.commit()
    return view(db, p, storage, user.production_editor)


@router.get("/{identifier}/screenplay")
def source_markdown(identifier: str, main: DB, db: IDB, user: Actor):
    p = production_access(main, db, user, identifier)
    return {
        "filename": f"screenplay-{p.screenplay_id}-revision-{p.source_revision}.md",
        "markdown": markdown_export(p.snapshot),
    }
