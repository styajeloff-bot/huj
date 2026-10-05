"""application vehicle markup

Revision ID: 093
Revises: 092
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "093"
down_revision: str | None = "092"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "application_vehicles",
        sa.Column("markup_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "application_vehicles",
        sa.Column("markup_value", sa.Numeric(15, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_vehicles", "markup_value")
    op.drop_column("application_vehicles", "markup_type")
