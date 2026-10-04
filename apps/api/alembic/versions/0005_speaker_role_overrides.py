"""Preserve explicit turn-local speaker role corrections."""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "transcript_turns",
        sa.Column("role_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("transcript_turns", "role_override")
