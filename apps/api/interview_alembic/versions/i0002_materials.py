"""Optional upload requests and immutable session-owned material copies."""

import sqlalchemy as sa

from alembic import op

revision = "i0002"
down_revision = "i0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "interview_upload_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id", sa.String(36), sa.ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "turn_id", name="uq_interview_upload_turn"),
    )
    op.create_index("ix_interview_upload_requests_session_id", "interview_upload_requests", ["session_id"])
    op.create_table(
        "interview_materials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column(
            "request_id", sa.String(36), sa.ForeignKey("interview_upload_requests.id", ondelete="SET NULL")
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("storage_key", sa.String(500), unique=True, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "asset_id", name="uq_interview_material_asset"),
    )
    op.create_index("ix_interview_materials_session_id", "interview_materials", ["session_id"])


def downgrade():
    op.drop_table("interview_materials")
    op.drop_table("interview_upload_requests")
