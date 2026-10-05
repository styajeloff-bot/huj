"""Confirm active application vehicles with saved discounts.

Revision ID: 098
Revises: 097
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "098"
down_revision: str | None = "097"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Repair the rows that unambiguously completed the discount flow."""

    op.execute(
        sa.text(
            """
            UPDATE application_vehicles
            SET car_status = 'confirmed'
            WHERE car_status = 'active'
              AND discount_type IS NOT NULL
              AND discount_value IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    """The data correction intentionally has no destructive downgrade."""
