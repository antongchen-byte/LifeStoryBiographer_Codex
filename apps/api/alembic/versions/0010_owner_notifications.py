"""Durable owner email notifications."""
from alembic import op
import sqlalchemy as sa
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("owner_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_key", sa.String(200), nullable=False, unique=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False))

def downgrade():
    op.drop_table("owner_notifications")
