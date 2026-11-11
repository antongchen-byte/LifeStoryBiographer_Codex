from alembic import op
import sqlalchemy as sa
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("production_reviews", sa.Column("project_snapshot", sa.JSON(), nullable=True))
    op.add_column("production_reviews", sa.Column("working_project_id", sa.String(36), nullable=True))

def downgrade():
    op.drop_column("production_reviews", "working_project_id")
    op.drop_column("production_reviews", "project_snapshot")
