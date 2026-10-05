"""Add an independent optional modification filter to monetization conditions.

Revision ID: 166
Revises: 165
"""

import sqlalchemy as sa
from alembic import op

revision = "166"
down_revision = "165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("monetization_programs", sa.Column("modification", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("monetization_programs", "modification")
