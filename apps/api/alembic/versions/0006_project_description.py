"""Editable biography descriptions."""
import sqlalchemy as sa
from alembic import op
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("projects", sa.Column("description", sa.Text(), nullable=True))

def downgrade():
    op.drop_column("projects", "description")
