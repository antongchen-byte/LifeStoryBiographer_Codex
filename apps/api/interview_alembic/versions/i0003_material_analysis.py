"""Durable material interpretation and interviewee confirmation."""

import sqlalchemy as sa

from alembic import op

revision = "i0003"
down_revision = "i0002"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("analysis_state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("analysis_generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("analysis", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("analysis_error", sa.Text()),
        sa.Column("analysis_progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discussion_turn_id", sa.String(36)),
        sa.Column("confirmation", sa.JSON(), nullable=False, server_default="{}"),
    ]:
        op.add_column("interview_materials", column)
    # Do not send historical attachments to a provider without a new user action.
    op.execute("UPDATE interview_materials SET analysis_state = 'not_started'")


def downgrade():
    for name in [
        "confirmation",
        "discussion_turn_id",
        "analysis_progress",
        "analysis_error",
        "analysis",
        "analysis_generation",
        "analysis_state",
    ]:
        op.drop_column("interview_materials", name)
