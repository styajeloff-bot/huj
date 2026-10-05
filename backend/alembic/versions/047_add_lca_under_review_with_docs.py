"""add lca under_review_with_docs status

Revision ID: 047
Revises: 046
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op

revision: str = "047"
down_revision: str | None = "046"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE leasing_company_application_status "
        "ADD VALUE IF NOT EXISTS 'under_review_with_docs'"
    )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding the
    # type and rewriting dependent columns. Keep downgrade intentionally empty.
    pass
