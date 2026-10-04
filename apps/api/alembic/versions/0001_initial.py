"""Initial project and media tables.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    project_status = sa.Enum(
        "intake", "story_development", "screenplay", "production", "completed", name="projectstatus"
    )
    media_status = sa.Enum("uploading", "uploaded", "processing", "ready", "failed", name="mediastatus")
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_name", sa.String(200), nullable=False),
        sa.Column("title", sa.String(250)),
        sa.Column("default_language", sa.String(16), nullable=False),
        sa.Column("status", project_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("multipart_upload_id", sa.String(500)),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("thumbnail_key", sa.String(500)),
        sa.Column("error", sa.Text()),
        sa.Column("status", media_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_media_assets_project_id", "media_assets", ["project_id"])


def downgrade():
    op.drop_table("media_assets")
    op.drop_table("projects")
    sa.Enum(name="mediastatus").drop(op.get_bind())
    sa.Enum(name="projectstatus").drop(op.get_bind())
