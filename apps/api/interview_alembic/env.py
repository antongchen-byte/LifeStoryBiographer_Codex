from alembic import context
from app import interview_models  # noqa: F401
from app.interview_database import InterviewBase, engine

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=InterviewBase.metadata)
    with context.begin_transaction():
        context.run_migrations()
