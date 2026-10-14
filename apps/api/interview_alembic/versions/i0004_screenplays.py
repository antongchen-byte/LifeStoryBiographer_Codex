"""Screenplay sources, timed sections, and generation subsections."""

import sqlalchemy as sa

from alembic import op

revision = "i0004"
down_revision = "i0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "screenplays",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("interview_sessions.id")),
        sa.Column("interview_uid", sa.String(36), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("original_markdown", sa.Text(), nullable=False),
        sa.Column("reviewed_markdown", sa.Text(), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("job", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("exports", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ["owner_id", "project_id", "session_id", "interview_uid"]:
        op.create_index("ix_screenplays_" + field, "screenplays", [field])
    op.create_table(
        "screenplay_sections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "screenplay_id",
            sa.String(36),
            sa.ForeignKey("screenplays.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.UniqueConstraint("screenplay_id", "position", name="uq_screenplay_section"),
    )
    op.create_index("ix_screenplay_sections_screenplay_id", "screenplay_sections", ["screenplay_id"])
    op.create_table(
        "screenplay_subsections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "section_id",
            sa.String(36),
            sa.ForeignKey("screenplay_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.UniqueConstraint("section_id", "position", name="uq_screenplay_subsection"),
    )
    op.create_index("ix_screenplay_subsections_section_id", "screenplay_subsections", ["section_id"])


def downgrade():
    op.drop_table("screenplay_subsections")
    op.drop_table("screenplay_sections")
    op.drop_table("screenplays")
