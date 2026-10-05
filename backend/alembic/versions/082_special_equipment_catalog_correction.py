"""Replace the special-equipment catalog with the approved correction.

Revision ID: 082
Revises: 081
Create Date: 2026-07-28

The task explicitly permits a clean database and rejects compatibility/data
copying.  This migration therefore replaces the old catalog tables atomically.
Commerce tables keep their product foreign keys.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "082"
down_revision: str | None = "081"
branch_labels: str | None = None
depends_on: str | None = None

_COMMERCE_PRODUCT_FOREIGN_KEYS = (
    (
        "special_equipment_favorites",
        "special_equipment_favorites_product_id_fkey",
        "CASCADE",
    ),
    (
        "special_equipment_cart_items",
        "special_equipment_cart_items_product_id_fkey",
        "RESTRICT",
    ),
    (
        "special_equipment_application_items",
        "special_equipment_application_items_product_id_fkey",
        "RESTRICT",
    ),
    (
        "special_equipment_purchase_orders",
        "special_equipment_purchase_orders_product_id_fkey",
        "RESTRICT",
    ),
)


def _directory_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "lock_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def _drop_legacy_catalog() -> None:
    for table_name, constraint_name, _ondelete in _COMMERCE_PRODUCT_FOREIGN_KEYS:
        op.drop_constraint(
            constraint_name,
            table_name,
            type_="foreignkey",
        )

    for table_name in (
        "special_equipment_product_images",
        "special_equipment_product_attribute_values",
        "special_equipment_category_attributes",
        "special_equipment_product_categories",
        "special_equipment_products",
        "special_equipment_attributes",
        "special_equipment_manufacturers",
        "special_equipment_categories",
    ):
        op.drop_table(table_name)


def _create_directories() -> None:
    op.create_table(
        "special_equipment_categories",
        *_directory_columns(),
        sa.Column("usage_metric", sa.String(20), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "usage_metric IN ('mileage_km', 'engine_hours')",
            name="ck_special_equipment_categories_usage_metric",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_categories_sort_order_nonnegative",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_categories_lock_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_special_equipment_categories_code"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_categories_slug"),
    )
    op.create_index(
        "idx_special_equipment_categories_active_sort",
        "special_equipment_categories",
        ["is_active", "sort_order", "id"],
    )
    op.create_table(
        "special_equipment_category_relations",
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "parent_id <> child_id",
            name="ck_special_equipment_category_relations_not_self",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_category_relations_sort_order",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_category_relations_parent",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_category_relations_child",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("parent_id", "child_id"),
    )
    op.create_index(
        "idx_special_equipment_category_relations_child_parent",
        "special_equipment_category_relations",
        ["child_id", "parent_id"],
    )

    op.create_table(
        "special_equipment_marks",
        *_directory_columns(),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_special_equipment_marks_lock_version"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_special_equipment_marks_code"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_marks_slug"),
        sa.UniqueConstraint("name", name="uq_special_equipment_marks_name"),
    )
    op.create_table(
        "special_equipment_models",
        *_directory_columns(),
        sa.Column("mark_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "lock_version >= 1", name="ck_special_equipment_models_lock_version"
        ),
        sa.ForeignKeyConstraint(
            ["mark_id"],
            ["special_equipment_marks.id"],
            name="fk_special_equipment_models_mark",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_special_equipment_models_code"),
        sa.UniqueConstraint(
            "mark_id", "slug", name="uq_special_equipment_models_mark_slug"
        ),
        sa.UniqueConstraint(
            "mark_id", "name", name="uq_special_equipment_models_mark_name"
        ),
    )
    op.create_index(
        "idx_special_equipment_models_mark",
        "special_equipment_models",
        ["mark_id", "name", "id"],
    )
    op.create_table(
        "special_equipment_modifications",
        *_directory_columns(),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year_from", sa.SmallInteger(), nullable=True),
        sa.Column("year_to", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_modifications_lock_version",
        ),
        sa.CheckConstraint(
            "year_from IS NULL OR year_from BETWEEN 1900 AND 2200",
            name="ck_special_equipment_modifications_year_from",
        ),
        sa.CheckConstraint(
            "year_to IS NULL OR year_to BETWEEN 1900 AND 2200",
            name="ck_special_equipment_modifications_year_to",
        ),
        sa.CheckConstraint(
            "year_from IS NULL OR year_to IS NULL OR year_from <= year_to",
            name="ck_special_equipment_modifications_year_range",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["special_equipment_models.id"],
            name="fk_special_equipment_modifications_model",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "code", name="uq_special_equipment_modifications_code"
        ),
        sa.UniqueConstraint(
            "model_id",
            "slug",
            name="uq_special_equipment_modifications_model_slug",
        ),
        sa.UniqueConstraint(
            "model_id",
            "name",
            name="uq_special_equipment_modifications_model_name",
        ),
    )
    op.create_index(
        "idx_special_equipment_modifications_model",
        "special_equipment_modifications",
        ["model_id", "name", "id"],
    )
    op.create_table(
        "special_equipment_modification_categories",
        sa.Column("modification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["modification_id"],
            ["special_equipment_modifications.id"],
            name="fk_special_equipment_modification_categories_modification",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_modification_categories_category",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("modification_id", "category_id"),
    )


def _create_attributes() -> None:
    op.create_table(
        "special_equipment_attribute_groups",
        *_directory_columns(),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_attribute_groups_sort_order",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_attribute_groups_lock_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "code", name="uq_special_equipment_attribute_groups_code"
        ),
        sa.UniqueConstraint(
            "slug", name="uq_special_equipment_attribute_groups_slug"
        ),
    )
    op.create_table(
        "special_equipment_attributes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("filter_kind", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "lock_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "data_type IN ('number', 'text', 'boolean', 'select')",
            name="ck_special_equipment_attributes_data_type",
        ),
        sa.CheckConstraint(
            "filter_kind IN ('exact', 'range', 'search')",
            name="ck_special_equipment_attributes_filter_kind",
        ),
        sa.CheckConstraint(
            "filter_kind <> 'range' OR data_type = 'number'",
            name="ck_special_equipment_attributes_range_number",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_attributes_lock_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_special_equipment_attributes_code"),
    )
    op.create_table(
        "special_equipment_attribute_options",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "lock_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_attribute_options_sort_order",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_attribute_options_lock_version",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id"],
            ["special_equipment_attributes.id"],
            name="fk_special_equipment_attribute_options_attribute",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attribute_id",
            "code",
            name="uq_special_equipment_attribute_options_attribute_code",
        ),
    )
    op.create_index(
        "idx_special_equipment_attribute_options_attribute",
        "special_equipment_attribute_options",
        ["attribute_id", "sort_order", "id"],
    )
    op.create_table(
        "special_equipment_category_attributes",
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_filterable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_category_attributes_sort_order",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_category_attributes_category",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id"],
            ["special_equipment_attributes.id"],
            name="fk_special_equipment_category_attributes_attribute",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["special_equipment_attribute_groups.id"],
            name="fk_special_equipment_category_attributes_group",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("category_id", "attribute_id"),
    )
    op.create_table(
        "special_equipment_modification_attribute_values",
        sa.Column("modification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("option_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("value_number", sa.Numeric(20, 4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_modification_attribute_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_modification_attribute_values_text_size",
        ),
        sa.ForeignKeyConstraint(
            ["modification_id"],
            ["special_equipment_modifications.id"],
            name="fk_se_modification_attribute_values_modification",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id"],
            ["special_equipment_attributes.id"],
            name="fk_se_modification_attribute_values_attribute",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["option_id"],
            ["special_equipment_attribute_options.id"],
            name="fk_se_modification_attribute_values_option",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("modification_id", "attribute_id"),
    )
    op.create_index(
        "idx_se_modification_attribute_values_number",
        "special_equipment_modification_attribute_values",
        ["attribute_id", "value_number", "modification_id"],
        postgresql_where=sa.text("value_number IS NOT NULL"),
    )
    op.create_index(
        "idx_se_modification_attribute_values_option",
        "special_equipment_modification_attribute_values",
        ["attribute_id", "option_id", "modification_id"],
        postgresql_where=sa.text("option_id IS NOT NULL"),
    )


def _create_products() -> None:
    op.create_table(
        "special_equipment_products",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("modification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "currency_code",
            sa.CHAR(3),
            server_default=sa.text("'RUB'"),
            nullable=False,
        ),
        sa.Column("manufacture_year", sa.SmallInteger(), nullable=True),
        sa.Column("vin", sa.String(32), nullable=True),
        sa.Column("condition", sa.String(10), nullable=False),
        sa.Column("mileage_km", sa.BigInteger(), nullable=True),
        sa.Column("engine_hours", sa.BigInteger(), nullable=True),
        sa.Column(
            "publication_status",
            sa.String(20),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "sale_status",
            sa.String(20),
            server_default=sa.text("'unavailable'"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "lock_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_special_equipment_products_price_nonnegative",
        ),
        sa.CheckConstraint(
            "mileage_km IS NULL OR mileage_km >= 0",
            name="ck_special_equipment_products_mileage_nonnegative",
        ),
        sa.CheckConstraint(
            "engine_hours IS NULL OR engine_hours >= 0",
            name="ck_special_equipment_products_engine_hours_nonnegative",
        ),
        sa.CheckConstraint(
            "currency_code = 'RUB'",
            name="ck_special_equipment_products_currency_rub",
        ),
        sa.CheckConstraint(
            "manufacture_year IS NULL OR manufacture_year BETWEEN 1900 AND 2200",
            name="ck_special_equipment_products_manufacture_year",
        ),
        sa.CheckConstraint(
            "condition IN ('new', 'used')",
            name="ck_special_equipment_products_condition",
        ),
        sa.CheckConstraint(
            "(condition = 'new' AND mileage_km IS NULL AND engine_hours IS NULL) "
            "OR (condition = 'used' AND num_nonnulls(mileage_km, engine_hours) = 1)",
            name="ck_special_equipment_products_condition_usage",
        ),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'published', 'archived')",
            name="ck_special_equipment_products_publication_status",
        ),
        sa.CheckConstraint(
            "sale_status IN ('available', 'reserved', 'sold', 'unavailable')",
            name="ck_special_equipment_products_sale_status",
        ),
        sa.CheckConstraint(
            "publication_status <> 'published' OR published_at IS NOT NULL",
            name="ck_special_equipment_products_published_at",
        ),
        sa.CheckConstraint(
            "publication_status <> 'published' OR seller_company_id IS NOT NULL",
            name="ck_special_equipment_products_published_seller",
        ),
        sa.CheckConstraint(
            "sale_status NOT IN ('reserved', 'sold') OR price IS NOT NULL",
            name="ck_special_equipment_products_claimed_price",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_products_lock_version",
        ),
        sa.ForeignKeyConstraint(
            ["modification_id"],
            ["special_equipment_modifications.id"],
            name="fk_special_equipment_products_modification",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seller_company_id"],
            ["companies.id"],
            name="fk_special_equipment_products_seller_company",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_special_equipment_products_code"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_products_slug"),
    )
    op.create_index(
        "idx_special_equipment_products_modification",
        "special_equipment_products",
        ["modification_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_special_equipment_products_published",
        "special_equipment_products",
        [sa.text("published_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_price_published",
        "special_equipment_products",
        ["price", "id"],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_se_products_claimed_seller",
        "special_equipment_products",
        ["seller_company_id", "id"],
        postgresql_where=sa.text(
            "seller_company_id IS NOT NULL "
            "AND sale_status IN ('reserved', 'sold')"
        ),
    )
    op.create_index(
        "uq_special_equipment_products_vin",
        "special_equipment_products",
        [sa.text("upper(vin)")],
        unique=True,
        postgresql_where=sa.text("vin IS NOT NULL"),
    )
    op.create_table(
        "special_equipment_product_categories",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            name="fk_special_equipment_product_categories_product",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_product_categories_category",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("product_id", "category_id"),
    )
    op.create_index(
        "idx_special_equipment_product_categories_category",
        "special_equipment_product_categories",
        ["category_id", "product_id"],
    )
    op.create_table(
        "special_equipment_product_images",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_product_images_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            name="fk_special_equipment_product_images_product",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key", name="uq_special_equipment_product_images_storage_key"
        ),
    )
    op.create_index(
        "uq_special_equipment_product_image_order",
        "special_equipment_product_images",
        ["product_id", "sort_order"],
        unique=True,
    )
    op.create_index(
        "uq_special_equipment_product_primary_image",
        "special_equipment_product_images",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def _restore_commerce_foreign_keys() -> None:
    for table_name, constraint_name, ondelete in _COMMERCE_PRODUCT_FOREIGN_KEYS:
        op.create_foreign_key(
            constraint_name,
            table_name,
            "special_equipment_products",
            ["product_id"],
            ["id"],
            ondelete=ondelete,
        )


def upgrade() -> None:
    _drop_legacy_catalog()
    _create_directories()
    _create_attributes()
    _create_products()
    _restore_commerce_foreign_keys()

    op.drop_constraint(
        "ck_se_catalog_mutation_receipts_resource_type",
        "special_equipment_catalog_mutation_receipts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_se_catalog_mutation_receipts_resource_type",
        "special_equipment_catalog_mutation_receipts",
        "resource_type IN ("
        "'category', 'mark', 'model', 'modification', "
        "'attribute_group', 'attribute', 'attribute_option', 'product')",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Revision 082 is intentionally irreversible: task 21808 requires "
        "a clean database and explicitly rejects compatibility/data copying"
    )
