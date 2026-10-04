from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.errors import DomainError
from ..models import AuditEvent, MediaAsset, Project, ProjectMember, User
from ..schemas import MemberCreate, ProjectCreate, ProjectRead, ProjectUpdate

WRITE_ROLES = {"OWNER", "SUBJECT", "EDITOR"}


def access(
    db: Session, project_id: str, user: User, write: bool = False, owner: bool = False
) -> tuple[Project, ProjectMember]:
    member = db.get(ProjectMember, (project_id, user.id))
    project = db.get(Project, project_id) if member else None
    if not project or not member:
        raise DomainError(404, "Project not found")
    if (write and member.role not in WRITE_ROLES) or (owner and member.role != "OWNER"):
        raise DomainError(403, "Your role does not allow this action")
    return project, member


def audit(db: Session, project_id: str, actor_id: str, action: str, target_id: str) -> None:
    db.add(AuditEvent(project_id=project_id, actor_id=actor_id, action=action, target_id=target_id))


def present(db: Session, project: Project, role: str) -> ProjectRead:
    result = ProjectRead.model_validate(project)
    result.role = role
    result.media_count = (
        db.scalar(select(func.count()).select_from(MediaAsset).where(MediaAsset.project_id == project.id))
        or 0
    )
    return result


def create(db: Session, user: User, data: ProjectCreate) -> ProjectRead:
    project = Project(**data.model_dump())
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="OWNER"))
    audit(db, project.id, user.id, "project.created", project.id)
    db.commit()
    return present(db, project, "OWNER")


def update(db: Session, project: Project, user: User, data: ProjectUpdate) -> None:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    audit(db, project.id, user.id, "project.updated", project.id)
    db.commit()


def add_member(db: Session, project: Project, actor: User, data: MemberCreate) -> None:
    user = db.scalar(select(User).where(User.email == data.email.casefold()))
    if not user:
        raise DomainError(404, "Ask this collaborator to create an account first")
    member = db.get(ProjectMember, (project.id, user.id))
    if member and member.role == "OWNER":
        raise DomainError(409, "The owner role cannot be changed")
    if member:
        member.role = data.role
    else:
        db.add(ProjectMember(project_id=project.id, user_id=user.id, role=data.role))
    audit(db, project.id, actor.id, "member.updated", user.id)
    db.commit()
