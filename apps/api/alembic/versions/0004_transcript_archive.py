"""Immutable approved scripts and locally saved conversation memory."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transcript_archives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("interviewer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id", sa.String(36), sa.ForeignKey("style_sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True)),
        sa.Column("folder_label", sa.String(255)),
        sa.UniqueConstraint("source_id", "revision", name="uq_transcript_archive_revision"),
    )
    op.create_table(
        "conversation_memory_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "archive_id",
            sa.String(36),
            sa.ForeignKey("transcript_archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_id", sa.String(36), nullable=False),
        sa.Column("speaker", sa.String(80), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("archive_id", "turn_id", name="uq_memory_archive_turn"),
    )
    for table, cols in {
        "transcript_archives": ["profile_id", "source_id"],
        "conversation_memory_turns": ["archive_id"],
    }.items():
        for col in cols:
            op.create_index(f"ix_{table}_{col}", table, [col])
    op.execute(
        "CREATE INDEX ix_memory_text_search ON conversation_memory_turns USING gin (to_tsvector('simple', text))"
    )


def downgrade():
    op.drop_table("conversation_memory_turns")
    op.drop_table("transcript_archives")
