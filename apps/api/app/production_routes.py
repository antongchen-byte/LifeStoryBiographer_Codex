"""Production-only capabilities: explicit project scope, versioned drafts and releases."""
from copy import deepcopy
from typing import Literal
from uuid import UUID
from .models import ProductionReview
import json
from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select, func, or_, and_
from .main import DB, Actor, Storage
from .interview_routes import IDB
from .domain.errors import DomainError
from .models import User, Project, ProjectMember, MediaAsset, ProductionRevision, ProductionRelease
from .interview_models import Screenplay, ScreenplaySection, ScreenplaySubsection, InterviewSession, InterviewConfig, InterviewApproval, InterviewMaterial, InterviewTurn
from .cinema_models import CinemaProduction, CinemaJob
from .schemas import Boundary
from .services import projects, production_context as context

from .services.owner_email import enqueue

router = APIRouter(prefix="/api/production", tags=["production"])


def editor(user):
    if not user.production_editor:
        raise DomainError(403, "Production editor access required")


def selected(user, project_id):
    editor(user)
    if context.scope(user) != project_id:
        raise DomainError(403, "Open this project in the production workspace first")


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def checkpoint(main, db, user, action):
    project_id = context.scope(user)
    if not project_id:
        raise DomainError(403, "Select a production project")
    from .screenplay_routes import detail
    p = main.get(Project, project_id)
    sessions = list(db.scalars(select(InterviewSession).where(InterviewSession.project_id == project_id)))
    ids = [s.id for s in sessions]
    snapshot = {
        "project": serialize(p),
        "materials": [serialize(m) for m in main.scalars(select(MediaAsset).where(MediaAsset.project_id == project_id))],
        "screenplays": [detail(db, s) for s in db.scalars(select(Screenplay).where(Screenplay.project_id == project_id))],
        "sessions": [serialize(s) for s in sessions],
        "turns": [serialize(t) for t in db.scalars(select(InterviewTurn).where(InterviewTurn.session_id.in_(ids)))],
        "interview_materials": [serialize(m) for m in db.scalars(select(InterviewMaterial).where(InterviewMaterial.session_id.in_(ids)))],
    }
    row = ProductionRevision(project_id=project_id, actor_id=user.id, action=action[:300],
        snapshot=json.loads(json.dumps(snapshot, default=str)))
    main.add(row)
    main.flush()  # Assign the revision ID before linking the audit event.
    # AuditEvent.action is a bounded event name. Full request details live in
    # the linked revision, not in this 80-character column.
    projects.audit(main, project_id, user.id, "production.checkpoint", row.id)
    main.commit()
    return row


def fork(db, user, source):
    from .screenplay_routes import content_hash
    from .config import settings
    metadata = deepcopy(source["source"])
    metadata.update(production_draft=True, editor_id=user.id, based_on_screenplay=source["id"], based_on_revision=source["revision"])
    # Derived sections remain editable; final export is always a new explicit action.
    forked = Screenplay(owner_id=context.owner_id(user), project_id=context.scope(user),
        session_id=source.get("session_id"), interview_uid=source["interview_uid"], title=source["title"],
        source=metadata, original_markdown=source["reviewed_markdown"], reviewed_markdown=source["reviewed_markdown"],
        materials=deepcopy(source["materials"]), model=settings.gemini_model)
    db.add(forked); db.flush()
    hashes = {}
    subsection_ids = {}
    for section in source["sections"]:
        page = ScreenplaySection(screenplay_id=forked.id, position=section["position"], content=deepcopy(section["content"]))
        db.add(page); db.flush()
        for sub in section["subsections"]:
            copied = ScreenplaySubsection(section_id=page.id, position=sub["position"], seconds=sub["seconds"], content=deepcopy(sub["content"]))
            db.add(copied); db.flush()
            subsection_ids[sub["id"]] = copied.id
        if not section.get("breakdown_stale"):
            hashes[page.id] = content_hash(page.content)
    forked.source = {**metadata, "breakdown_hashes": hashes}
    from .config import settings
    forked.model = settings.gemini_model
    forked.revision = source["revision"]
    forked.exports = deepcopy(source.get("exports", []))
    db.flush()
    previous = db.scalar(select(CinemaProduction).where(CinemaProduction.screenplay_id == source["id"], CinemaProduction.source_revision == source["revision"]))
    if previous:
        from .screenplay_routes import detail
        copied_production = CinemaProduction(screenplay_id=forked.id, owner_id=forked.owner_id,
            interview_uid=forked.interview_uid, source_revision=forked.revision, snapshot=detail(db, forked))
        db.add(copied_production); db.flush()
        old_jobs = list(db.scalars(select(CinemaJob).where(CinemaJob.production_id == previous.id).order_by(CinemaJob.created_at, CinemaJob.id)))
        if any(j.state not in {"ready", "failed", "cancelled"} for j in old_jobs):
            raise DomainError(409, "Wait for existing video jobs to finish before copying this production")
        from .models import new_id
        job_ids = {j.id:new_id() for j in old_jobs}
        for old in old_jobs:
            payload = deepcopy(old.request)
            if payload.get("previous_id"): payload["previous_id"] = job_ids.get(payload["previous_id"], payload["previous_id"])
            if "clip_ids" in payload: payload["clip_ids"] = [job_ids.get(i,i) for i in payload["clip_ids"]]
            payload.update(actor_id=user.id, project_id=forked.project_id, copied_from_job=old.id)
            db.add(CinemaJob(id=job_ids[old.id], production_id=copied_production.id, kind=old.kind,
                subsection_id=subsection_ids.get(old.subsection_id), state=old.state, request=payload,
                output_key=old.output_key, frame_key=old.frame_key, duration=old.duration, sha256=old.sha256,
                previewed=old.previewed, approved=old.approved, error=old.error, created_at=old.created_at))
    db.commit()
    return forked


@router.get("/me")
def capabilities(user: Actor):
    return {"production_editor": bool(user.production_editor), "actor_id": user.id}


@router.get("/projects")
def listing(main: DB, db: IDB, user: Actor, q: str = Query("", max_length=200)):
    editor(user)
    query = select(Project, User).join(ProjectMember, ProjectMember.project_id == Project.id).join(User, User.id == ProjectMember.user_id).where(ProjectMember.role == "OWNER")
    if q:
        query = query.where(User.email.ilike(f"%{q}%") | User.name.ilike(f"%{q}%") | Project.title.ilike(f"%{q}%"))
    result = []
    for p, owner in main.execute(query.order_by(Project.created_at.desc()).limit(100)):
        has_script = db.scalar(select(InterviewApproval.id).where(InterviewApproval.project_id == p.id).limit(1))
        screenplay = db.scalar(select(Screenplay).where(Screenplay.project_id == p.id).order_by(Screenplay.created_at.desc()).limit(1))
        result.append({"id":p.id,"title":p.title or p.subject_name,"owner_id":owner.id,"owner_name":owner.name,"owner_email":owner.email,
            "readiness":"Screenplay available" if screenplay else "Approved interview ready" if has_script else "Collecting source material"})
    return result


@router.post("/projects/{project_id}/open")
def open_project(project_id: str, main: DB, db: IDB, user: Actor):
    selected(user, project_id)
    checkpoint(main, db, user, "opened")
    p, _ = projects.access(main, project_id, user, write=True)
    owner = main.get(User, context.owner_id(user))
    drafts = list(db.scalars(select(Screenplay).where(Screenplay.project_id == project_id).order_by(Screenplay.created_at.desc())))
    draft = next((s for s in drafts if s.source.get("production_draft") and s.source.get("editor_id") == user.id), None)
    if not draft and drafts:
        original = next((s for s in drafts if not s.source.get("production_draft")), None)
        if original:
            from .screenplay_routes import detail, ACTIVE
            if original.state in ACTIVE:
                raise DomainError(409, "Wait for screenplay generation to finish before opening this production")
            draft = fork(db, user, detail(db, original))
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id, InterviewSession.status != "active").order_by(InterviewSession.created_at.desc()).limit(1))
    config = db.scalar(select(InterviewConfig).where(InterviewConfig.project_id == project_id, InterviewConfig.owner_id == owner.id).order_by(InterviewConfig.created_at.desc()).limit(1))
    return {"id":p.id,"title":p.title or p.subject_name,"owner_name":owner.name,"owner_email":owner.email,
        "config_id":config.id if config else None,
        "screenplay_id":draft.id if draft else None,"session_id":session.id if session else None,"actor_id":user.id}


@router.get("/projects/{project_id}/versions")
def versions(project_id: str, main: DB, user: Actor):
    selected(user, project_id)
    return [{"id":r.id,"actor_id":r.actor_id,"action":r.action,"created_at":r.created_at}
            for r in main.scalars(select(ProductionRevision).where(ProductionRevision.project_id == project_id).order_by(ProductionRevision.created_at.desc()).limit(100))]


@router.get("/projects/{project_id}/versions/{revision_id}")
def version(project_id: str, revision_id: str, main: DB, user: Actor):
    selected(user, project_id)
    row = main.get(ProductionRevision, revision_id)
    if not row or row.project_id != project_id:
        raise DomainError(404, "Version not found")
    return row.snapshot


class Restore(Boundary):
    screenplay_id: str


@router.post("/projects/{project_id}/versions/{revision_id}/restore")
def restore(project_id: str, revision_id: str, body: Restore, main: DB, db: IDB, user: Actor):
    snapshot = version(project_id, revision_id, main, user)
    source = next((s for s in snapshot["screenplays"] if s["id"] == body.screenplay_id), None)
    if not source:
        raise DomainError(404, "Screenplay is not part of this version")
    checkpoint(main, db, user, "restore screenplay")
    return {"screenplay_id":fork(db, user, source).id}


class Publish(Boundary):
    job_id: str
    preview_confirmed: bool = False


@router.post("/projects/{project_id}/publish")
def publish(project_id: str, body: Publish, main: DB, db: IDB, user: Actor):
    selected(user, project_id)
    if not body.preview_confirmed:
        raise DomainError(422, "Preview the finished video and confirm publication")
    from .cinema_routes import production_access, sequence
    job = db.get(CinemaJob, body.job_id)
    if not job or job.kind != "stitch" or job.state != "ready" or not job.output_key or not job.sha256:
        raise DomainError(409, "A completed stitched video is required")
    p = production_access(main, db, user, job.production_id)
    rows = sequence(db, p)
    ids = [j.id for _, j, stale in rows if j and j.state == "ready" and j.approved and not stale]
    if not rows or len(ids) != len(rows) or ids != job.request.get("clip_ids"):
        raise DomainError(409, "Review and approve all current clips before publishing")
    existing = main.scalar(select(ProductionRelease).where(ProductionRelease.job_id == job.id))
    if not existing:
        existing = ProductionRelease(project_id=project_id, owner_id=context.owner_id(user), actor_id=user.id,
            job_id=job.id, title=p.snapshot["title"], storage_key=job.output_key, sha256=job.sha256)
        main.add(existing)
        enqueue(main, context.owner_id(user), project_id, "film:" + job.id)
        projects.audit(main, project_id, user.id, "production.published", job.id)
        main.commit()
    return {"id":existing.id,"published":True}


class PublishClips(Boundary):
    production_id: str


@router.post("/projects/{project_id}/publish-clips")
def publish_clips(project_id: str, body: PublishClips, main: DB, db: IDB, user: Actor):
    selected(user, project_id)
    from .cinema_routes import production_access, sequence
    p = production_access(main, db, user, body.production_id, True)
    rows = sequence(db, p)
    if not rows or any(not j or j.state != "ready" or not j.approved or not j.previewed or stale or not j.output_key or not j.sha256 for _,j,stale in rows):
        raise DomainError(409, "Preview and approve all current clips before sharing them with the owner")
    new_clip_ids = []
    for unit,job,_ in rows:
        if not main.scalar(select(ProductionRelease).where(ProductionRelease.job_id == job.id)):
            main.add(ProductionRelease(project_id=project_id,owner_id=context.owner_id(user),actor_id=user.id,
                job_id=job.id,title=f"{p.snapshot['title']} — Clip {unit['section_position']}.{unit['position']}"[:200],
                storage_key=job.output_key,sha256=job.sha256))
            new_clip_ids.append(job.id)
            projects.audit(main,project_id,user.id,"production.clip_shared",job.id)
    if new_clip_ids:
        from hashlib import sha256
        enqueue(main, context.owner_id(user), project_id, "clips:" + sha256(",".join(sorted(new_clip_ids)).encode()).hexdigest())
    main.commit()
    return {"published":True,"count":len(rows)}


def snapshot_videos(snapshot):
    tables=(snapshot or {}).get("tables",{})
    for p in tables.get("cinema_productions",[]):
        jobs=sorted([j for j in tables.get("cinema_jobs",[]) if j['production_id']==p['id']],key=lambda j:(j['created_at'],j['id']))
        latest={j['subsection_id']:j for j in jobs if j['kind']=='clip'}
        ids=[]
        previous=None
        valid=True
        units=[(section,sub) for section in p['snapshot'].get('sections',[]) for sub in section.get('subsections',[])]
        for section,sub in units:
            job=latest.get(sub['id'])
            ready=bool(job and job['state']=='ready' and job.get('approved') and job.get('previewed') and job.get('output_key'))
            if ready and job['request'].get('previous_id') and (not valid or not previous or job['request']['previous_id']!=previous['id']):ready=False
            valid=valid and ready
            if ready:
                ids.append(job['id'])
                yield job,f"{p['snapshot']['title']} — Clip {section['position']}.{sub['position']}"
            previous=job
        if units and valid:
            for job in jobs:
                if job['kind']=='stitch' and job['state']=='ready' and job.get('output_key') and job['request'].get('clip_ids')==ids:
                    yield job,p['snapshot']['title']


@router.get("/projects/{project_id}/releases")
def releases(project_id: str, main: DB, db: IDB, user: Actor, storage: Storage, review_id: str | None = None):
    projects.access(main, project_id, user)
    result=[]
    seen=set()
    if not review_id:
        for r in main.scalars(select(ProductionRelease).where(ProductionRelease.project_id == project_id).order_by(ProductionRelease.created_at.desc())):
            job=db.get(CinemaJob,r.job_id)
            result.append({"id":r.id,"title":r.title,"created_at":r.created_at,"editor_id":r.actor_id,
                "kind":job.kind if job else "stitch","url":storage.sign_download(r.storage_key,r.title+'.mp4')})
            seen.add(r.job_id)
    query=select(ProductionReview).where(ProductionReview.project_id==project_id).order_by(ProductionReview.created_at.desc())
    if review_id:query=query.where(ProductionReview.id==review_id)
    for review in main.scalars(query):
        for job,title in snapshot_videos(review.project_snapshot):
            if job['id'] in seen:continue
            seen.add(job['id'])
            result.append({"id":review.id+':'+job['id'],"title":title,"kind":job['kind'],"review_id":review.id,
                "created_at":review.created_at,"editor_id":review.actor_id,
                "url":storage.sign_download(job['output_key'],title+'.mp4')})
    return result


class ShareReview(Boundary):
    session_id: str | None = Field(default=None, max_length=36)
    screenplay_revision: int | None = Field(default=None, ge=0)
    screenplay_id: str | None = Field(default=None, max_length=36)
    module: Literal["biography", "style", "interview", "screenplay", "cinema"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1500000)
    request_id: UUID


def review_access(main, project_id, user):
    if context.scope(user):
        selected(user, project_id)
    else:
        projects.access(main, project_id, user, owner=True)


def review_summary(row, main):
    number = main.scalar(select(func.count()).select_from(ProductionReview).where(
        ProductionReview.project_id == row.project_id, ProductionReview.module == row.module,
        or_(ProductionReview.created_at < row.created_at,
            and_(ProductionReview.created_at == row.created_at, ProductionReview.id <= row.id))))
    actor = main.get(User, row.actor_id)
    return {"id":row.id, "project_id":row.project_id, "module":row.module,
            "title":row.title, "editor_id":row.actor_id, "editor_name":actor.name if actor else "Production Editor",
            "version_number":number, "created_at":row.created_at, "can_create_project":bool(row.project_snapshot)}


@router.post("/projects/{project_id}/reviews", status_code=201)
def share_review(project_id: str, body: ShareReview, main: DB, db: IDB, user: Actor, storage: Storage):
    selected(user, project_id)
    existing = main.scalar(select(ProductionReview).where(ProductionReview.request_id == str(body.request_id)))
    if existing:
        if existing.project_id != project_id or existing.actor_id != user.id:
            raise DomainError(409, "This save request belongs to another version")
        return review_summary(existing, main)
    from .services.review_projects import capture, copy_objects
    snapshot = capture(main, db, project_id, body.screenplay_id, body.session_id, body.screenplay_revision)
    snapshot, copied_keys = copy_objects(snapshot, storage, f"editor-versions/{body.request_id}")
    row = ProductionReview(project_id=project_id, owner_id=context.owner_id(user), actor_id=user.id,
        project_snapshot=snapshot,
        request_id=str(body.request_id), module=body.module, title=(body.title if body.title.startswith("Editor-") else "Editor-"+body.title)[:200], content=body.content)
    try:
        main.add(row)
        main.flush()
        enqueue(main, context.owner_id(user), project_id, "review:" + row.id)
        projects.audit(main, project_id, user.id, "production.review_shared", row.id)
        main.commit()
    except Exception:
        main.rollback()
        for key in copied_keys: storage.delete(key)
        raise
    return review_summary(row, main)


@router.get("/projects/{project_id}/reviews")
def list_reviews(project_id: str, main: DB, user: Actor):
    review_access(main, project_id, user)
    return [review_summary(r, main) for r in main.scalars(select(ProductionReview)
        .where(ProductionReview.project_id == project_id).order_by(ProductionReview.created_at.desc()))]


@router.get("/projects/{project_id}/reviews/{review_id}")
def read_review(project_id: str, review_id: str, main: DB, user: Actor):
    review_access(main, project_id, user)
    row = main.get(ProductionReview, review_id)
    if not row or row.project_id != project_id:
        raise DomainError(404, "Editor version not found")
    return {**review_summary(row, main), "content":row.content}


@router.post("/projects/{project_id}/reviews/{review_id}/open-project")
def open_review_project(project_id: str, review_id: str, main: DB, db: IDB, user: Actor, storage: Storage):
    context.strict_owner(main, project_id, user)
    row = main.scalar(select(ProductionReview).where(ProductionReview.id == review_id,
        ProductionReview.project_id == project_id).with_for_update())
    if not row:
        raise DomainError(404, "Editor version not found")
    from .services.review_projects import materialize
    return materialize(main, db, row, user, storage)
