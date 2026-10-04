"""Separate database for interview configuration, recordings and approved scripts."""

import sqlalchemy as sa

from alembic import op

revision = "i0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_configs",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("avatar_id", sa.String(36), nullable=False),
        sa.Column("avatar", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("genre", sa.String(40), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interview_configs_owner_id", "interview_configs", ["owner_id"])
    op.create_index("ix_interview_configs_project_id", "interview_configs", ["project_id"])
    op.create_table(
        "interview_context_chunks",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column(
            "config_id",
            sa.String(36),
            sa.ForeignKey("interview_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
    )
    op.create_index("ix_interview_context_chunks_config_id", "interview_context_chunks", ["config_id"])
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("config_id", sa.String(36), sa.ForeignKey("interview_configs.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("active_token", sa.String(36), nullable=True),
        sa.Column("busy_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interview_sessions_config_id", "interview_sessions", ["config_id"])
    op.create_index("ix_interview_sessions_owner_id", "interview_sessions", ["owner_id"])
    op.create_index("ix_interview_sessions_project_id", "interview_sessions", ["project_id"])
    op.create_table(
        "interview_turns",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("audio_key", sa.String(500), nullable=True),
        sa.Column("audio_mime", sa.String(100), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "request_id", "role", name="uq_interview_request_role"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_interview_sequence"),
    )
    op.create_index("ix_interview_turns_session_id", "interview_turns", ["session_id"])
    op.create_table(
        "approved_interviews",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "revision", name="uq_interview_approval"),
    )
    op.create_index("ix_approved_interviews_session_id", "approved_interviews", ["session_id"])
    op.create_index("ix_approved_interviews_owner_id", "approved_interviews", ["owner_id"])
    op.create_index("ix_approved_interviews_project_id", "approved_interviews", ["project_id"])
    op.execute(
        "CREATE INDEX ix_interview_context_search ON interview_context_chunks USING gin (to_tsvector('simple', text))"
    )
    op.execute(
        "CREATE INDEX ix_approved_interview_search ON approved_interviews USING gin (to_tsvector('simple', script))"
    )


def downgrade():
    op.drop_table("approved_interviews")
    op.drop_table("interview_turns")
    op.drop_table("interview_sessions")
    op.drop_table("interview_context_chunks")
    op.drop_table("interview_configs")
