"""application vehicle catalog price visibility

Revision ID: 095
Revises: 094
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "095"
down_revision: str | None = "094"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "application_vehicles",
        sa.Column(
            "discount_show_catalog_price",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "application_vehicles",
        sa.Column(
            "markup_show_catalog_price",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "application_vehicles",
        "markup_show_catalog_price",
    )
    op.drop_column(
        "application_vehicles",
        "discount_show_catalog_price",
    )
