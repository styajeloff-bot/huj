"""Backfill vehicles status/is_available and add DB defaults.

Revision ID: 003
Revises: 002
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Set missing status/is_available and add column defaults."""
    op.execute(
        "UPDATE vehicles SET status = 'available' WHERE status IS NULL"
    )
    op.execute(
        "UPDATE vehicles SET is_available = true WHERE is_available IS NULL"
    )
    op.execute(
        "ALTER TABLE vehicles "
        "ALTER COLUMN status SET DEFAULT 'available', "
        "ALTER COLUMN is_available SET DEFAULT true"
    )


def downgrade() -> None:
    """Drop the defaults; leave data as-is."""
    op.execute(
        "ALTER TABLE vehicles "
        "ALTER COLUMN status DROP DEFAULT, "
        "ALTER COLUMN is_available DROP DEFAULT"
    )
