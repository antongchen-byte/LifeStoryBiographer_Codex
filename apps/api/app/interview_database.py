"""New interviews live in a separate PostgreSQL database, not the style library."""

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class InterviewBase(DeclarativeBase):
    pass


url = make_url(settings.interview_database_url or settings.database_url)
if not settings.interview_database_url:
    url = url.set(database="biographer_interviews")
engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_interview_db():
    with SessionLocal() as session:
        yield session
