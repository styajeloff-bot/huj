"""Init ClickHouse

Revision ID: 001
Revises:
Create Date: 2026-05-14 17:53:21

"""
from alembic import op
from infrastructure.models.clickhouse import ClickHouseBase

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    ClickHouseBase.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    ClickHouseBase.metadata.drop_all(bind=op.get_bind())
