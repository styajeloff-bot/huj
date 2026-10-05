"""clear bad catalog facets snapshots

Revision ID: 050
Revises: 049
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM catalog_facets_snapshot")


def downgrade() -> None:
    pass
