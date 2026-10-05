"""Add typed public UI configuration to catalog storefronts.

Revision ID: 109
Revises: 108
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "109"
down_revision: str | None = "108"
branch_labels: str | None = None
depends_on: str | None = None

_PAGE_TITLES_DEFAULT = sa.text(
    "'{\"home\": \"Главная\", \"about\": \"О нас\", "
    "\"catalog\": \"Каталог\", \"models\": \"Модели\", "
    "\"special_equipment_catalog\": \"Спецтехника\"}'::jsonb"
)
_CATALOG_BLOCKS_DEFAULT = sa.text(
    "'{\"special_offers\": {\"title\": "
    "\"Выбрать автомобиль по специальной цене\", \"is_visible\": true}, "
    "\"all_vehicles\": {\"title\": "
    "\"Выбрать автомобиль из каталога\", \"is_visible\": true}}'::jsonb"
)


def upgrade() -> None:
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "home_page_key",
            sa.String(length=64),
            nullable=False,
            server_default="home",
        ),
    )
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "public_page_titles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_PAGE_TITLES_DEFAULT,
        ),
    )
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "catalog_blocks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_CATALOG_BLOCKS_DEFAULT,
        ),
    )
    op.add_column(
        "catalog_storefronts",
        sa.Column("public_ui_updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "catalog_storefronts",
        sa.Column(
            "public_ui_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_foreign_key(
        "fk_catalog_storefronts_public_ui_updated_by",
        "catalog_storefronts",
        "users",
        ["public_ui_updated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_home_page_key",
        "catalog_storefronts",
        "home_page_key IN ('home', 'about', 'catalog', 'models', "
        "'special_equipment_catalog')",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_public_page_titles",
        "catalog_storefronts",
        "jsonb_typeof(public_page_titles) = 'object' "
        "AND public_page_titles ?& ARRAY['home', 'about', 'catalog', 'models', "
        "'special_equipment_catalog'] "
        "AND (public_page_titles - ARRAY['home', 'about', 'catalog', 'models', "
        "'special_equipment_catalog']) = '{}'::jsonb "
        "AND jsonb_typeof(public_page_titles -> 'home') = 'string' "
        "AND jsonb_typeof(public_page_titles -> 'about') = 'string' "
        "AND jsonb_typeof(public_page_titles -> 'catalog') = 'string' "
        "AND jsonb_typeof(public_page_titles -> 'models') = 'string' "
        "AND jsonb_typeof(public_page_titles -> 'special_equipment_catalog') = 'string'",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_catalog_blocks",
        "catalog_storefronts",
        "jsonb_typeof(catalog_blocks) = 'object' "
        "AND catalog_blocks ?& ARRAY['special_offers', 'all_vehicles'] "
        "AND (catalog_blocks - ARRAY['special_offers', 'all_vehicles']) "
        "= '{}'::jsonb "
        "AND jsonb_typeof(catalog_blocks -> 'special_offers') = 'object' "
        "AND jsonb_typeof(catalog_blocks -> 'special_offers' -> 'title') = 'string' "
        "AND jsonb_typeof(catalog_blocks -> 'special_offers' -> 'is_visible') = 'boolean' "
        "AND jsonb_typeof(catalog_blocks -> 'all_vehicles') = 'object' "
        "AND jsonb_typeof(catalog_blocks -> 'all_vehicles' -> 'title') = 'string' "
        "AND jsonb_typeof(catalog_blocks -> 'all_vehicles' -> 'is_visible') = 'boolean'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_catalog_storefronts_catalog_blocks",
        "catalog_storefronts",
        type_="check",
    )
    op.drop_constraint(
        "ck_catalog_storefronts_public_page_titles",
        "catalog_storefronts",
        type_="check",
    )
    op.drop_constraint(
        "ck_catalog_storefronts_home_page_key",
        "catalog_storefronts",
        type_="check",
    )
    op.drop_constraint(
        "fk_catalog_storefronts_public_ui_updated_by",
        "catalog_storefronts",
        type_="foreignkey",
    )
    op.drop_column("catalog_storefronts", "public_ui_updated_at")
    op.drop_column("catalog_storefronts", "public_ui_updated_by")
    op.drop_column("catalog_storefronts", "catalog_blocks")
    op.drop_column("catalog_storefronts", "public_page_titles")
    op.drop_column("catalog_storefronts", "home_page_key")
