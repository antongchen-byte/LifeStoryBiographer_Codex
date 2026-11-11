"""The authenticated actor is never replaced by the project owner."""
from sqlalchemy import select
from ..models import ProjectMember
from ..domain.errors import DomainError

def scope(user):
    return getattr(user, "production_project_id", None)

def owner_id(user):
    return getattr(user, "production_owner_id", user.id)

def project_owner(db, project_id):
    result = db.scalar(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id, ProjectMember.role == "OWNER"))
    if not result:
        raise DomainError(404, "Project owner not found")
    return result

def project_ids(db, user):
    if scope(user):
        return [scope(user)]
    if getattr(user, "workspace_project_id", None):
        return [user.workspace_project_id]
    return list(db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id, ProjectMember.role == "OWNER")))

def strict_owner(db, project_id, user):
    if project_owner(db, project_id) != user.id:
        raise DomainError(403, "Only the project owner can manage membership or delete the project")
