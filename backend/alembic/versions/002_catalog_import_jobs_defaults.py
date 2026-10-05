"""Add missing DEFAULT 0 to catalog_import_jobs counters.

Revision ID: 002
Revises: 001
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Set DEFAULT 0 for integer counter columns."""
    op.execute(
        "ALTER TABLE catalog_import_jobs "
        "ALTER COLUMN rows_total SET DEFAULT 0, "
        "ALTER COLUMN rows_done SET DEFAULT 0, "
        "ALTER COLUMN images_total SET DEFAULT 0, "
        "ALTER COLUMN images_done SET DEFAULT 0, "
        "ALTER COLUMN images_failed SET DEFAULT 0"
    )


def downgrade() -> None:
    """Drop the defaults."""
    op.execute(
        "ALTER TABLE catalog_import_jobs "
        "ALTER COLUMN rows_total DROP DEFAULT, "
        "ALTER COLUMN rows_done DROP DEFAULT, "
        "ALTER COLUMN images_total DROP DEFAULT, "
        "ALTER COLUMN images_done DROP DEFAULT, "
        "ALTER COLUMN images_failed DROP DEFAULT"
    )
