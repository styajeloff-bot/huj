"""Add independent semantic storefront color overrides.

Revision ID: 114
Revises: 113
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "114"
down_revision: str | None = "113"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "appearance_color_overrides", postgresql.JSONB(),
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_appearance_color_overrides",
        "catalog_storefronts",
        "jsonb_typeof(appearance_color_overrides) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_catalog_storefronts_appearance_color_overrides",
        "catalog_storefronts", type_="check",
    )
    op.drop_column("catalog_storefronts", "appearance_color_overrides")
