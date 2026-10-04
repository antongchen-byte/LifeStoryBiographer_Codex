"""Accounts, access control, durable jobs, and media metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "project_members",
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
    )
    op.add_column("media_assets", sa.Column("idempotency_key", sa.String(64)))
    op.add_column("media_assets", sa.Column("proxy_key", sa.String(500)))
    op.add_column("media_assets", sa.Column("description", sa.Text()))
    op.add_column("media_assets", sa.Column("details", sa.JSON(), server_default="{}", nullable=False))
    op.add_column(
        "media_assets",
        sa.Column("ownership_declared", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_unique_constraint("uq_media_upload_request", "media_assets", ["project_id", "idempotency_key"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "asset_id", sa.String(36), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processing_jobs_asset_id", "processing_jobs", ["asset_id"])
    op.create_index("ix_processing_jobs_state", "processing_jobs", ["state"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_project_id", "audit_events", ["project_id"])


def downgrade() -> None:
    for table in ("audit_events", "processing_jobs", "project_members", "auth_sessions", "users"):
        op.drop_table(table)
    op.drop_constraint("uq_media_upload_request", "media_assets", type_="unique")
    for column in ("ownership_declared", "details", "description", "proxy_key", "idempotency_key"):
        op.drop_column("media_assets", column)
