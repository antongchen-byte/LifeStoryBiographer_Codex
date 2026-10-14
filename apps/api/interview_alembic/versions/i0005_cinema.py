"""Cinema snapshots and versioned generation jobs."""

import sqlalchemy as sa

from alembic import op

revision = "i0005"
down_revision = "i0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cinema_productions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("screenplay_id", sa.String(36), sa.ForeignKey("screenplays.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("interview_uid", sa.String(36), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("screenplay_id", "source_revision", name="uq_cinema_source"),
    )
    for name in ["screenplay_id", "owner_id", "interview_uid"]:
        op.create_index("ix_cinema_productions_" + name, "cinema_productions", [name])
    op.create_table(
        "cinema_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("production_id", sa.String(36), sa.ForeignKey("cinema_productions.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("subsection_id", sa.String(36)),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("operation", sa.String(300)),
        sa.Column("output_key", sa.String(700)),
        sa.Column("frame_key", sa.String(700)),
        sa.Column("duration", sa.Float()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("previewed", sa.Boolean(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ["production_id", "subsection_id", "state"]:
        op.create_index("ix_cinema_jobs_" + name, "cinema_jobs", [name])


def downgrade():
    op.drop_table("cinema_jobs")
    op.drop_table("cinema_productions")
