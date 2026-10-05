"""Drop legacy catalog_blocks JSONB column from catalog_storefronts.

Revision ID: 126
Revises: 125
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "126"
down_revision: str | None = "125"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_catalog_storefronts_catalog_blocks",
        "catalog_storefronts",
        type_="check",
    )
    op.drop_column("catalog_storefronts", "catalog_blocks")


def downgrade() -> None:
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "catalog_blocks",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                "'{\"special_offers\": {\"title\": "
                "\"Выбрать автомобиль по специальной цене\", \"is_visible\": true}, "
                "\"all_vehicles\": {\"title\": "
                "\"Выбрать автомобиль из каталога\", \"is_visible\": true}}'::jsonb"
            ),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_catalog_blocks",
        "catalog_storefronts",
        "jsonb_typeof(catalog_blocks) = 'object' "
        "AND catalog_blocks ?& ARRAY['special_offers', 'all_vehicles'] "
        "AND (catalog_blocks - ARRAY['special_offers', 'all_vehicles']) "
        "= '{}'::jsonb "
        "AND jsonb_typeof(catalog_blocks -> 'special_offers') = 'object' "
        "AND jsonb_typeof(catalog_blocks -> 'special_offers' -> "
        "'title') = 'string' "
        "AND jsonb_typeof(catalog_blocks -> 'special_offers' -> "
        "'is_visible') = 'boolean' "
        "AND jsonb_typeof(catalog_blocks -> 'all_vehicles') = 'object' "
        "AND jsonb_typeof(catalog_blocks -> 'all_vehicles' -> "
        "'title') = 'string' "
        "AND jsonb_typeof(catalog_blocks -> 'all_vehicles' -> "
        "'is_visible') = 'boolean'",
    )
