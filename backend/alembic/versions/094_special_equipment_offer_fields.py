"""Add special-equipment warehouse and special price.

Revision ID: 094
Revises: 093
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "094"
down_revision: str | None = "093"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "special_equipment_products",
        sa.Column("special_price", sa.Numeric(precision=15, scale=2), nullable=True),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_se_products_special_price_valid",
        "special_equipment_products",
        "special_price IS NULL OR (price IS NOT NULL "
        "AND special_price > 0 AND special_price < price)",
    )
    op.create_foreign_key(
        "fk_se_products_warehouse",
        "special_equipment_products",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_se_products_effective_price_published",
        "special_equipment_products",
        [sa.text("COALESCE(special_price, price)"), "id"],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_se_products_warehouse",
        "special_equipment_products",
        ["warehouse_id", "id"],
        postgresql_where=sa.text("warehouse_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_se_products_warehouse",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_se_products_effective_price_published",
        table_name="special_equipment_products",
    )
    op.drop_constraint(
        "fk_se_products_warehouse",
        "special_equipment_products",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_se_products_special_price_valid",
        "special_equipment_products",
        type_="check",
    )
    op.drop_column("special_equipment_products", "warehouse_id")
    op.drop_column("special_equipment_products", "special_price")
