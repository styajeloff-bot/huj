"""Add special-equipment colors.

Revision ID: 088_special_equipment_colors
Revises: 087
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "088_special_equipment_colors"
down_revision = "087"
branch_labels = None
depends_on = None

_RECEIPT_CHECK = "ck_se_catalog_mutation_receipts_resource_type"


def upgrade() -> None:
    op.create_table(
        "special_equipment_colors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("applicability", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("lock_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("applicability IN ('body', 'interior', 'both')", name="ck_special_equipment_colors_applicability"),
        sa.CheckConstraint("lock_version >= 1", name="ck_special_equipment_colors_lock_version"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_special_equipment_colors_code_norm", "special_equipment_colors", [sa.text("lower(trim(code))")], unique=True)
    op.create_index("uq_special_equipment_colors_name_norm", "special_equipment_colors", [sa.text("lower(trim(name))")], unique=True)
    op.create_index(
        "idx_special_equipment_colors_active_select",
        "special_equipment_colors",
        ["is_active", "applicability", sa.text("lower(name)"), "id"],
        unique=False,
    )
    op.add_column("special_equipment_products", sa.Column("body_color_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("special_equipment_products", sa.Column("interior_color_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_special_equipment_products_body_color",
        "special_equipment_products",
        "special_equipment_colors",
        ["body_color_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_foreign_key(
        "fk_special_equipment_products_interior_color",
        "special_equipment_products",
        "special_equipment_colors",
        ["interior_color_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_index("idx_se_products_body_color", "special_equipment_products", ["body_color_id"], unique=False, postgresql_where=sa.text("body_color_id IS NOT NULL"))
    op.create_index("idx_se_products_interior_color", "special_equipment_products", ["interior_color_id"], unique=False, postgresql_where=sa.text("interior_color_id IS NOT NULL"))
    op.drop_constraint(_RECEIPT_CHECK, "special_equipment_catalog_mutation_receipts", type_="check")
    op.create_check_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        "resource_type IN ('category', 'mark', 'model', 'modification', 'attribute_group', 'attribute', 'attribute_option', 'product', 'color')",
    )


def downgrade() -> None:
    op.drop_constraint(_RECEIPT_CHECK, "special_equipment_catalog_mutation_receipts", type_="check")
    op.create_check_constraint(
        _RECEIPT_CHECK,
        "special_equipment_catalog_mutation_receipts",
        "resource_type IN ('category', 'mark', 'model', 'modification', 'attribute_group', 'attribute', 'attribute_option', 'product')",
    )
    op.drop_index("idx_se_products_interior_color", table_name="special_equipment_products")
    op.drop_index("idx_se_products_body_color", table_name="special_equipment_products")
    op.drop_constraint("fk_special_equipment_products_interior_color", "special_equipment_products", type_="foreignkey")
    op.drop_constraint("fk_special_equipment_products_body_color", "special_equipment_products", type_="foreignkey")
    op.drop_column("special_equipment_products", "interior_color_id")
    op.drop_column("special_equipment_products", "body_color_id")
    op.drop_index("idx_special_equipment_colors_active_select", table_name="special_equipment_colors")
    op.drop_index("uq_special_equipment_colors_name_norm", table_name="special_equipment_colors")
    op.drop_index("uq_special_equipment_colors_code_norm", table_name="special_equipment_colors")
    op.drop_table("special_equipment_colors")
