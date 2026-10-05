"""Scope public section visibility by catalog storefront.

Revision ID: 102
Revises: 101
Create Date: 2026-08-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "102"
down_revision: str | None = "101"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "section_visibility"
_DEFAULT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "storefront_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_section_visibility_storefront_id",
        _TABLE,
        "catalog_storefronts",
        ["storefront_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "uq_section_visibility_scope_section_key",
        _TABLE,
        type_="unique",
    )
    op.execute(
        sa.text(
            "UPDATE section_visibility "
            "SET storefront_id = CAST(:default_id AS uuid) "
            "WHERE scope = 'public'"
        ).bindparams(default_id=_DEFAULT_ID)
    )
    op.execute(
        sa.text(
            "WITH defaults(section_key, is_visible) AS ("
            "VALUES "
            "('about', TRUE), "
            "('catalog', TRUE), "
            "('models', FALSE), "
            "('special_equipment_catalog', FALSE)"
            "), effective_default AS ("
            "SELECT defaults.section_key, "
            "CASE "
            "WHEN defaults.section_key = 'special_equipment_catalog' THEN FALSE "
            "ELSE COALESCE(root.is_visible, defaults.is_visible) "
            "END AS is_visible, "
            "root.updated_by "
            "FROM defaults "
            "LEFT JOIN section_visibility AS root "
            "ON root.scope = 'public' "
            "AND root.storefront_id = CAST(:default_id AS uuid) "
            "AND root.section_key = defaults.section_key"
            ") "
            "INSERT INTO section_visibility "
            "(id, scope, storefront_id, section_key, is_visible, updated_by) "
            "SELECT gen_random_uuid(), 'public', storefront.id, "
            "effective.section_key, effective.is_visible, effective.updated_by "
            "FROM catalog_storefronts AS storefront "
            "CROSS JOIN effective_default AS effective "
            "WHERE NOT storefront.is_default"
        ).bindparams(default_id=_DEFAULT_ID)
    )
    op.create_check_constraint(
        "ck_section_visibility_storefront_target",
        _TABLE,
        "(scope = 'public' AND storefront_id IS NOT NULL) OR "
        "(scope <> 'public' AND storefront_id IS NULL)",
    )
    op.create_index(
        "uq_section_visibility_public_storefront_section",
        _TABLE,
        ["storefront_id", "section_key"],
        unique=True,
        postgresql_where=sa.text(
            "scope = 'public' AND storefront_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_section_visibility_global_scope_section",
        _TABLE,
        ["scope", "section_key"],
        unique=True,
        postgresql_where=sa.text(
            "scope <> 'public' AND storefront_id IS NULL"
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM section_visibility "
            "WHERE scope = 'public' "
            "AND storefront_id <> CAST(:default_id AS uuid)"
        ).bindparams(default_id=_DEFAULT_ID)
    )
    op.drop_index(
        "uq_section_visibility_global_scope_section",
        table_name=_TABLE,
    )
    op.drop_index(
        "uq_section_visibility_public_storefront_section",
        table_name=_TABLE,
    )
    op.drop_constraint(
        "ck_section_visibility_storefront_target",
        _TABLE,
        type_="check",
    )
    op.drop_constraint(
        "fk_section_visibility_storefront_id",
        _TABLE,
        type_="foreignkey",
    )
    op.drop_column(_TABLE, "storefront_id")
    op.create_unique_constraint(
        "uq_section_visibility_scope_section_key",
        _TABLE,
        ["scope", "section_key"],
    )
