"""Fix leasing proposal database defaults.

Revision ID: 044
Revises: 043
Create Date: 2026-06-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "leasing_proposals",
        "position",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )
    op.alter_column(
        "leasing_proposals",
        "kind",
        existing_type=postgresql.ENUM(
            "preliminary",
            "final",
            name="leasing_proposal_kind",
            create_type=False,
        ),
        nullable=False,
        server_default=sa.text("'preliminary'::leasing_proposal_kind"),
    )
    op.alter_column(
        "leasing_proposals",
        "buyout_amount",
        existing_type=sa.Numeric(15, 2),
        nullable=True,
        server_default=sa.text("0"),
    )


def downgrade() -> None:
    op.alter_column(
        "leasing_proposals",
        "buyout_amount",
        existing_type=sa.Numeric(15, 2),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "leasing_proposals",
        "kind",
        existing_type=postgresql.ENUM(
            "preliminary",
            "final",
            name="leasing_proposal_kind",
            create_type=False,
        ),
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "leasing_proposals",
        "position",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=None,
    )
