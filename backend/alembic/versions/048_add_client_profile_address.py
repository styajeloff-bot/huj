"""add client profile registration address

Revision ID: 048
Revises: 047
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "048"
down_revision: str | None = "047"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("client_profiles", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("client_profiles", "address")
