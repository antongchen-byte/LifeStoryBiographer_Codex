"""Create the local interview DB and apply its independent migration history."""

from alembic.config import Config
from sqlalchemy import text

from alembic import command

from .config import settings
from .database import engine as main_engine
from .interview_database import url


def main():
    if not settings.interview_database_url:
        with main_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if not conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            ):
                conn.execute(text('CREATE DATABASE "biographer_interviews"'))
    command.upgrade(Config("interview_alembic.ini"), "head")


if __name__ == "__main__":
    main()
