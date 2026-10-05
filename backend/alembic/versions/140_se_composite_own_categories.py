"""Composite products own categories flag.

Revision ID: 140
Revises: 139
Create Date: 2026-09-29 10:35:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "140"
down_revision = "139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "has_own_categories",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("special_equipment_products", "has_own_categories")
