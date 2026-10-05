"""Add draft status for unassigned leasing-company applications.

Revision ID: 062
Revises: 061
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE leasing_company_application_status "
        "ADD VALUE IF NOT EXISTS 'draft' BEFORE 'submitted'"
    )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values without recreating the type.
    pass
