"""Point exchange dealer request links to companies.

Revision ID: 061
Revises: 060
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "061"
down_revision: str | None = "060"
branch_labels: str | None = None
depends_on: str | None = None


_TARGET_TABLES = (
    "exchange_cart_item_dealer_comments",
    "exchange_request_dealer_comments",
    "exchange_request_warehouses",
)


def _drop_dealer_fk(table_name: str) -> None:
    op.drop_constraint(
        f"{table_name}_dealer_id_fkey",
        table_name,
        type_="foreignkey",
    )


def _create_dealer_fk(table_name: str, target_table: str) -> None:
    op.create_foreign_key(
        f"{table_name}_dealer_id_fkey",
        table_name,
        target_table,
        ["dealer_id"],
        ["id"],
        ondelete="CASCADE" if table_name != "exchange_request_warehouses" else None,
    )


def upgrade() -> None:
    bind = op.get_bind()

    for table_name in _TARGET_TABLES:
        _drop_dealer_fk(table_name)

    # Old data may store dealer user ids. Convert them to the user's company id
    # before enforcing company-level foreign keys.
    for table_name in _TARGET_TABLES:
        bind.execute(sa.text(f"""
            UPDATE {table_name} AS target
            SET dealer_id = users.company_id
            FROM users
            WHERE target.dealer_id = users.id
              AND users.company_id IS NOT NULL
        """))

    # For request warehouses, the selected warehouse is authoritative. If an old
    # row did not resolve through users, use the warehouse owner company.
    bind.execute(sa.text("""
        UPDATE exchange_request_warehouses AS target
        SET dealer_id = COALESCE(warehouses.dealer_id, warehouses.company_id)
        FROM warehouses
        WHERE target.warehouse_id = warehouses.id
          AND NOT EXISTS (
              SELECT 1 FROM companies WHERE companies.id = target.dealer_id
          )
          AND COALESCE(warehouses.dealer_id, warehouses.company_id) IS NOT NULL
    """))

    for table_name in _TARGET_TABLES:
        _create_dealer_fk(table_name, "companies")


def downgrade() -> None:
    bind = op.get_bind()

    for table_name in _TARGET_TABLES:
        _drop_dealer_fk(table_name)

    # Best-effort downgrade: map company-level dealer ids back to the first
    # active dealer user in that company.
    for table_name in _TARGET_TABLES:
        bind.execute(sa.text(f"""
            UPDATE {table_name} AS target
            SET dealer_id = dealer_users.id
            FROM (
                SELECT DISTINCT ON (company_id) company_id, id
                FROM users
                WHERE company_id IS NOT NULL
                  AND role = 'dealer'
                  AND is_active IS TRUE
                  AND deleted_at IS NULL
                ORDER BY company_id, created_at ASC, id ASC
            ) AS dealer_users
            WHERE target.dealer_id = dealer_users.company_id
        """))

    for table_name in _TARGET_TABLES:
        _create_dealer_fk(table_name, "users")
