"""Add special-equipment trims.

Revision ID: 089
Revises: 088_special_equipment_colors
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "089"
down_revision: str | None = "088_special_equipment_colors"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "special_equipment_trims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("lock_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("lock_version >= 1", name="ck_se_trims_lock_version"),
        sa.CheckConstraint("sort_order >= 0", name="ck_se_trims_sort_order"),
        sa.ForeignKeyConstraint(
            ["modification_id"],
            ["special_equipment_modifications.id"],
            name="fk_se_trims_modification",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_trims"),
        sa.UniqueConstraint("id", "modification_id", name="uq_se_trims_id_modification"),
    )
    op.create_index("idx_se_trims_modification_active_sort", "special_equipment_trims", ["modification_id", "is_active", "sort_order", "name", "id"])
    op.create_index("uq_se_trims_modification_code_normalized", "special_equipment_trims", ["modification_id", sa.text("lower(btrim(code))")], unique=True)
    op.create_index("uq_se_trims_modification_name_normalized", "special_equipment_trims", ["modification_id", sa.text("lower(btrim(name))")], unique=True)
    op.create_index("uq_se_trims_modification_slug_normalized", "special_equipment_trims", ["modification_id", sa.text("lower(btrim(slug))")], unique=True)

    op.create_table(
        "special_equipment_trim_attributes",
        sa.Column("trim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_filterable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_se_trim_attributes_sort_order"),
        sa.ForeignKeyConstraint(["attribute_id"], ["special_equipment_attributes.id"], name="fk_se_trim_attributes_attribute", onupdate="CASCADE", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["group_id"], ["special_equipment_attribute_groups.id"], name="fk_se_trim_attributes_group", onupdate="CASCADE", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trim_id"], ["special_equipment_trims.id"], name="fk_se_trim_attributes_trim", onupdate="CASCADE", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trim_id", "attribute_id", name="pk_special_equipment_trim_attributes"),
        sa.UniqueConstraint("trim_id", "attribute_id", name="uq_se_trim_attributes_trim_attribute"),
    )

    op.create_unique_constraint("uq_se_attribute_options_attribute_id_id", "special_equipment_attribute_options", ["attribute_id", "id"])
    op.create_table(
        "special_equipment_trim_attribute_values",
        sa.Column("trim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("value_number", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.CheckConstraint("num_nonnulls(value_number, value_text, value_boolean, option_id) = 1", name="ck_se_trim_attribute_values_one_value"),
        sa.CheckConstraint("value_text IS NULL OR octet_length(value_text) <= 2000", name="ck_se_trim_attribute_values_text_size"),
        sa.ForeignKeyConstraint(["trim_id", "attribute_id"], ["special_equipment_trim_attributes.trim_id", "special_equipment_trim_attributes.attribute_id"], name="fk_se_trim_attribute_values_assignment", onupdate="CASCADE", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["attribute_id", "option_id"], ["special_equipment_attribute_options.attribute_id", "special_equipment_attribute_options.id"], name="fk_se_trim_attribute_values_option_attribute", onupdate="CASCADE", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("trim_id", "attribute_id", name="pk_special_equipment_trim_attribute_values"),
    )
    op.create_index("idx_se_trim_attribute_values_number", "special_equipment_trim_attribute_values", ["attribute_id", "value_number", "trim_id"], postgresql_where=sa.text("value_number IS NOT NULL"))
    op.create_index("idx_se_trim_attribute_values_option", "special_equipment_trim_attribute_values", ["attribute_id", "option_id", "trim_id"], postgresql_where=sa.text("option_id IS NOT NULL"))
    op.create_index("idx_se_trim_attribute_values_text_search", "special_equipment_trim_attribute_values", [sa.text("lower(value_text) gin_trgm_ops")], postgresql_using="gin", postgresql_where=sa.text("value_text IS NOT NULL"))

    op.add_column("special_equipment_products", sa.Column("trim_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_se_products_trim", "special_equipment_products", "special_equipment_trims", ["trim_id"], ["id"], onupdate="CASCADE", ondelete="RESTRICT")
    op.create_foreign_key("fk_se_products_trim_modification", "special_equipment_products", "special_equipment_trims", ["trim_id", "modification_id"], ["id", "modification_id"], onupdate="CASCADE", ondelete="RESTRICT")
    op.create_index("idx_se_products_trim", "special_equipment_products", ["trim_id", sa.text("updated_at DESC"), sa.text("id DESC")])


def downgrade() -> None:
    op.drop_index("idx_se_products_trim", table_name="special_equipment_products")
    op.drop_constraint("fk_se_products_trim_modification", "special_equipment_products", type_="foreignkey")
    op.drop_constraint("fk_se_products_trim", "special_equipment_products", type_="foreignkey")
    op.drop_column("special_equipment_products", "trim_id")
    op.drop_index("idx_se_trim_attribute_values_text_search", table_name="special_equipment_trim_attribute_values", postgresql_using="gin")
    op.drop_index("idx_se_trim_attribute_values_option", table_name="special_equipment_trim_attribute_values")
    op.drop_index("idx_se_trim_attribute_values_number", table_name="special_equipment_trim_attribute_values")
    op.drop_table("special_equipment_trim_attribute_values")
    op.drop_constraint("uq_se_attribute_options_attribute_id_id", "special_equipment_attribute_options", type_="unique")
    op.drop_table("special_equipment_trim_attributes")
    op.drop_index("uq_se_trims_modification_slug_normalized", table_name="special_equipment_trims")
    op.drop_index("uq_se_trims_modification_name_normalized", table_name="special_equipment_trims")
    op.drop_index("uq_se_trims_modification_code_normalized", table_name="special_equipment_trims")
    op.drop_index("idx_se_trims_modification_active_sort", table_name="special_equipment_trims")
    op.drop_table("special_equipment_trims")
