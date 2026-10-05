"""Persist immutable responses for special-equipment idempotent creates.

Revision ID: 087
Revises: 086
Create Date: 2026-08-10
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "087"
down_revision: str | None = "086"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "special_equipment_catalog_mutation_receipts",
        sa.Column(
            "response_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Tagged immutable create response; NULL marks a legacy receipt "
                "that must replay from the current resource"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "special_equipment_catalog_mutation_receipts",
        "response_snapshot",
    )
