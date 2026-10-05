"""Fix exchange bid database defaults.

Revision ID: 072
Revises: 071
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "072"
down_revision: str | None = "071"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "exchange_bids",
        "is_accepted",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
    op.alter_column(
        "exchange_bids",
        "kp_status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=sa.text("'none'"),
    )
    op.alter_column(
        "exchange_bids",
        "quantity",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )


def downgrade() -> None:
    op.alter_column(
        "exchange_bids",
        "quantity",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "exchange_bids",
        "kp_status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "exchange_bids",
        "is_accepted",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None,
    )
