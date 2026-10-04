"""Reviewed interviewer style profiles and durable jobs."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interviewer_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "style_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("interviewer_profiles.id"), nullable=False),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("media_assets.id"), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "asset_id", name="uq_style_source"),
    )
    op.create_table(
        "transcript_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("style_sources.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(80), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_table(
        "style_patterns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("interviewer_profiles.id"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("origin", sa.String(80), nullable=False),
    )
    op.create_table(
        "style_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("interviewer_profiles.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "number", name="uq_style_version_number"),
        sa.UniqueConstraint("profile_id", "request_id", name="uq_style_publish_request"),
    )
    op.create_table(
        "style_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("interviewer_profiles.id"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("style_sources.id")),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "request_id", name="uq_style_job_request"),
    )
    for table, columns in {
        "interviewer_profiles": ["owner_id", "project_id"],
        "style_sources": ["profile_id", "asset_id"],
        "transcript_turns": ["source_id"],
        "style_patterns": ["profile_id"],
        "style_versions": ["profile_id"],
        "style_jobs": ["profile_id", "state"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in [
        "style_jobs",
        "style_versions",
        "style_patterns",
        "transcript_turns",
        "style_sources",
        "interviewer_profiles",
    ]:
        op.drop_table(table)
