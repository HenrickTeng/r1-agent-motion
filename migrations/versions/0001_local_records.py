"""Create local approval and execution records."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from apps.teacher_bridge.database import Base

    Base.metadata.create_all(op.get_bind())


def downgrade():
    from apps.teacher_bridge.database import Base

    Base.metadata.drop_all(op.get_bind())
