"""Production editing capability, recoverable snapshots and explicit releases."""
from alembic import op
import sqlalchemy as sa
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("production_editor", sa.Boolean(), nullable=False, server_default=sa.false()))
    from app.models import ProductionRevision, ProductionRelease
    ProductionRevision.__table__.create(op.get_bind())
    ProductionRelease.__table__.create(op.get_bind())

def downgrade():
    op.drop_table("production_releases")
    op.drop_table("production_revisions")
    op.drop_column("users", "production_editor")
