import logging
import uuid
from typing import Annotated

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import get_db
from .domain.errors import DomainError
from .interview_database import get_interview_db
from .interview_models import InterviewConfig
from .models import AuditEvent, InterviewerProfile, MediaAsset, MediaStatus, Project, ProjectMember, User
from .schemas import (
    Login,
    LoginRead,
    MediaRead,
    MediaUpdate,
    MemberCreate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    Register,
    UploadComplete,
    UploadCreate,
    UploadStarted,
    UserRead,
)
from .services import auth, media, projects
from .storage import ObjectStorage, get_storage

app = FastAPI(title="AI Biographer API", version="0.2.0")
logger = logging.getLogger("biographer.api")
security = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]
Storage = Annotated[ObjectStorage, Depends(get_storage)]


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.trace_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(DomainError)
async def domain_error(request: Request, error: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status, content={"detail": error.message, "request_id": request.state.trace_id}
    )


async def dependency_error(request: Request, error: Exception) -> JSONResponse:
    logger.error("Dependency unavailable trace=%s type=%s", request.state.trace_id, type(error).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "A required service is unavailable. Please retry.",
            "request_id": request.state.trace_id,
        },
    )


for exception_type in (BotoCoreError, ClientError, RedisError, SQLAlchemyError):
    app.add_exception_handler(exception_type, dependency_error)


def token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]) -> str:
    if not credentials:
        raise DomainError(401, "Please sign in")
    return credentials.credentials


def current_user(db: DB, bearer: Annotated[str, Depends(token)]) -> User:
    return auth.authenticate(db, bearer)


Actor = Annotated[User, Depends(current_user)]


@app.get("/health")
def health(db: DB) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=UserRead, status_code=201)
def register(body: Register, db: DB, request: Request) -> User:
    auth.rate_limit(f"register:{request.client.host if request.client else 'unknown'}")
    return auth.register(db, body)


@app.post("/api/auth/login", response_model=LoginRead)
def login(body: Login, db: DB) -> dict:
    auth.rate_limit("login:" + body.email)
    bearer, user = auth.login(db, body)
    return {"token": bearer, "user": user}


@app.get("/api/auth/me", response_model=UserRead)
def me(user: Actor) -> User:
    return user


@app.post("/api/auth/logout", status_code=204)
def logout(db: DB, bearer: Annotated[str, Depends(token)]) -> Response:
    auth.logout(db, bearer)
    return Response(status_code=204)


@app.post("/api/projects", response_model=ProjectRead, status_code=201)
def create_project(body: ProjectCreate, db: DB, user: Actor) -> ProjectRead:
    return projects.create(db, user, body)


@app.get("/api/projects", response_model=list[ProjectRead])
def list_projects(
    db: DB, user: Actor, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
) -> list:
    rows = db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [projects.present(db, p, role) for p, role in rows]


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, db: DB, user: Actor) -> ProjectRead:
    project, member = projects.access(db, project_id, user)
    return projects.present(db, project, member.role)


@app.patch("/api/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, body: ProjectUpdate, db: DB, user: Actor) -> ProjectRead:
    project, member = projects.access(db, project_id, user, write=True)
    projects.update(db, project, user, body)
    return projects.present(db, project, member.role)


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(
    project_id: str, db: DB, user: Actor, interviews: Annotated[Session, Depends(get_interview_db)]
) -> Response:
    project, _ = projects.access(db, project_id, user, owner=True)
    if db.scalar(select(func.count()).select_from(MediaAsset).where(MediaAsset.project_id == project_id)):
        raise DomainError(409, "Delete the project's media before deleting the project")
    if db.scalar(select(InterviewerProfile.id).where(InterviewerProfile.project_id == project_id)):
        raise DomainError(409, "This project contains an interviewer profile and its evidence")
    if interviews.scalar(select(InterviewConfig.id).where(InterviewConfig.project_id == project_id)):
        raise DomainError(409, "Delete this project's Interview Studio sessions and configurations first")
    db.query(AuditEvent).filter(AuditEvent.project_id == project_id).delete()
    db.delete(project)
    db.commit()
    return Response(status_code=204)


@app.post("/api/projects/{project_id}/members", status_code=204)
def add_member(project_id: str, body: MemberCreate, db: DB, user: Actor) -> Response:
    project, _ = projects.access(db, project_id, user, owner=True)
    projects.add_member(db, project, user, body)
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/audit")
def audit_trail(project_id: str, db: DB, user: Actor) -> list:
    projects.access(db, project_id, user, owner=True)
    return [
        {"action": e.action, "actor_id": e.actor_id, "target_id": e.target_id, "created_at": e.created_at}
        for e in db.scalars(
            select(AuditEvent)
            .where(AuditEvent.project_id == project_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
    ]


@app.post("/api/projects/{project_id}/media/duplicates")
def check_duplicate_upload(project_id: str, body: UploadCreate, db: DB, user: Actor):
    project, _ = projects.access(db, project_id, user, write=True)
    return media.duplicates(db, project, user, body)


@app.post("/api/projects/{project_id}/media/uploads", response_model=UploadStarted, status_code=201)
def create_upload(
    project_id: str, body: UploadCreate, db: DB, user: Actor, storage: Storage
) -> UploadStarted:
    project, _ = projects.access(db, project_id, user, write=True)
    return media.start(db, project, user, body, storage)


@app.get("/api/projects/{project_id}/media/{asset_id}/upload", response_model=UploadStarted)
def resume_upload(project_id: str, asset_id: str, db: DB, user: Actor, storage: Storage) -> UploadStarted:
    projects.access(db, project_id, user, write=True)
    return media.resume(media.find(db, project_id, asset_id), storage)


@app.post("/api/projects/{project_id}/media/{asset_id}/complete", response_model=MediaRead)
def finish_upload(
    project_id: str, asset_id: str, body: UploadComplete, db: DB, user: Actor, storage: Storage
) -> MediaRead:
    projects.access(db, project_id, user, write=True)
    return media.complete(db, media.find(db, project_id, asset_id, lock=True), user, body, storage)


@app.post("/api/projects/{project_id}/media/{asset_id}/retry", response_model=MediaRead)
def retry_media(project_id: str, asset_id: str, db: DB, user: Actor) -> MediaRead:
    projects.access(db, project_id, user, write=True)
    return media.retry(db, media.find(db, project_id, asset_id, lock=True), user)


@app.get("/api/projects/{project_id}/media", response_model=list[MediaRead])
def list_media(
    project_id: str, db: DB, user: Actor, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)
) -> list:
    projects.access(db, project_id, user)
    return [
        media.present(a)
        for a in db.scalars(
            select(MediaAsset)
            .where(MediaAsset.project_id == project_id)
            .order_by(MediaAsset.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ]


@app.get("/api/projects/{project_id}/media/{asset_id}", response_model=MediaRead)
def get_media(project_id: str, asset_id: str, db: DB, user: Actor) -> MediaRead:
    projects.access(db, project_id, user)
    return media.present(media.find(db, project_id, asset_id))


@app.patch("/api/projects/{project_id}/media/{asset_id}", response_model=MediaRead)
def update_media(project_id: str, asset_id: str, body: MediaUpdate, db: DB, user: Actor) -> MediaRead:
    projects.access(db, project_id, user, write=True)
    asset = media.find(db, project_id, asset_id, lock=True)
    asset.description = body.description
    projects.audit(db, project_id, user.id, "media.updated", asset.id)
    db.commit()
    return media.present(asset)


@app.get("/api/projects/{project_id}/media/{asset_id}/download")
def download_media(
    project_id: str, asset_id: str, db: DB, user: Actor, storage: Storage, kind: str = "original"
) -> dict:
    projects.access(db, project_id, user)
    asset = media.find(db, project_id, asset_id)
    if asset.status != MediaStatus.ready:
        raise DomainError(409, "Media is not ready for download")
    key = {"original": asset.storage_key, "thumbnail": asset.thumbnail_key, "proxy": asset.proxy_key}.get(
        kind
    )
    if not key:
        raise DomainError(404, "This media version does not exist")
    return {"url": storage.sign_download(key, asset.original_filename if kind == "original" else None)}


@app.delete("/api/projects/{project_id}/media/{asset_id}", status_code=204)
def delete_media(project_id: str, asset_id: str, db: DB, user: Actor, storage: Storage) -> Response:
    projects.access(db, project_id, user, write=True)
    media.remove(db, media.find(db, project_id, asset_id, lock=True), user, storage)
    return Response(status_code=204)


from .style_routes import router as style_router  # noqa: E402

app.include_router(style_router)

from .interview_routes import router as interview_router  # noqa: E402

app.include_router(interview_router)
