"""Scope business-role section visibility by catalog storefront.

Revision ID: 103
Revises: 102
Create Date: 2026-08-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "103"
down_revision: str | None = "102"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "section_visibility"
_DEFAULT_ID = "00000000-0000-0000-0000-000000000001"
_BUSINESS_SCOPES_SQL = "'leasing_company', 'dealer', 'distributor'"
_STOREFRONT_SCOPES_SQL = (
    "'public', 'leasing_company', 'dealer', 'distributor'"
)


def upgrade() -> None:
    """Upgrade revision 102 data and constraints."""
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
    op.execute(
        sa.text(
            "UPDATE section_visibility "
            "SET storefront_id = CAST(:default_id AS uuid) "
            f"WHERE scope IN ({_BUSINESS_SCOPES_SQL}) "
            "AND storefront_id IS NULL"
        ).bindparams(default_id=_DEFAULT_ID)
    )
    op.execute(
        sa.text(
            "WITH defaults(scope, section_key, is_visible) AS ("
            "VALUES "
            "('leasing_company', 'leasing_applications', TRUE), "
            "('leasing_company', 'documents', TRUE), "
            "('leasing_company', 'document_requirements', TRUE), "
            "('leasing_company', 'compensations', TRUE), "
            "('leasing_company', 'exchange', TRUE), "
            "('leasing_company', 'leasing_analytics', TRUE), "
            "('leasing_company', 'security', TRUE), "
            "('leasing_company', 'employees', TRUE), "
            "('dealer', 'applications', TRUE), "
            "('dealer', 'clients', TRUE), "
            "('dealer', 'inventory', TRUE), "
            "('dealer', 'reports', TRUE), "
            "('dealer', 'distributor_analytics', TRUE), "
            "('dealer', 'exchange', TRUE), "
            "('dealer', 'compensations', TRUE), "
            "('dealer', 'employees', TRUE), "
            "('distributor', 'applications', TRUE), "
            "('distributor', 'warehouses', TRUE), "
            "('distributor', 'distributor_analytics', TRUE), "
            "('distributor', 'dealers', TRUE), "
            "('distributor', 'companies', TRUE), "
            "('distributor', 'support', TRUE), "
            "('distributor', 'compensations', TRUE), "
            "('distributor', 'catalog', TRUE), "
            "('distributor', 'employees', TRUE)"
            "), effective_default AS ("
            "SELECT defaults.scope, defaults.section_key, "
            "COALESCE(root.is_visible, defaults.is_visible) AS is_visible, "
            "root.updated_by "
            "FROM defaults "
            "LEFT JOIN section_visibility AS root "
            "ON root.scope = defaults.scope "
            "AND root.storefront_id = CAST(:default_id AS uuid) "
            "AND root.section_key = defaults.section_key"
            ") "
            "INSERT INTO section_visibility "
            "(id, scope, storefront_id, section_key, is_visible, updated_by) "
            "SELECT gen_random_uuid(), effective.scope, storefront.id, "
            "effective.section_key, effective.is_visible, effective.updated_by "
            "FROM catalog_storefronts AS storefront "
            "CROSS JOIN effective_default AS effective "
            "WHERE NOT storefront.is_default"
        ).bindparams(default_id=_DEFAULT_ID)
    )
    op.create_check_constraint(
        "ck_section_visibility_storefront_target",
        _TABLE,
        f"(scope IN ({_STOREFRONT_SCOPES_SQL}) "
        "AND storefront_id IS NOT NULL) OR "
        "(scope = 'carcraft_employee' AND storefront_id IS NULL)",
    )
    op.create_index(
        "uq_section_visibility_storefront_scope_section",
        _TABLE,
        ["storefront_id", "scope", "section_key"],
        unique=True,
        postgresql_where=sa.text(
            f"scope IN ({_STOREFRONT_SCOPES_SQL}) "
            "AND storefront_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_section_visibility_global_scope_section",
        _TABLE,
        ["scope", "section_key"],
        unique=True,
        postgresql_where=sa.text(
            "scope = 'carcraft_employee' AND storefront_id IS NULL"
        ),
    )


def downgrade() -> None:
    """Restore the revision 102 representation."""
    op.drop_index(
        "uq_section_visibility_global_scope_section",
        table_name=_TABLE,
    )
    op.drop_index(
        "uq_section_visibility_storefront_scope_section",
        table_name=_TABLE,
    )
    op.drop_constraint(
        "ck_section_visibility_storefront_target",
        _TABLE,
        type_="check",
    )
    op.execute(
        sa.text(
            "DELETE FROM section_visibility "
            f"WHERE scope IN ({_BUSINESS_SCOPES_SQL}) "
            "AND storefront_id <> CAST(:default_id AS uuid)"
        ).bindparams(default_id=_DEFAULT_ID)
    )
    op.execute(
        sa.text(
            "UPDATE section_visibility SET storefront_id = NULL "
            f"WHERE scope IN ({_BUSINESS_SCOPES_SQL}) "
            "AND storefront_id = CAST(:default_id AS uuid)"
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
