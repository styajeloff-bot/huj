"""Create the isolated special-equipment catalog core.

Revision ID: 073
Revises: 072
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "073"
down_revision: str | None = "072"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "special_equipment_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="ck_special_equipment_categories_not_self_parent",
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_categories_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_categories_parent",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_categories"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_categories_slug"),
    )
    op.create_index(
        "idx_special_equipment_categories_parent_sort",
        "special_equipment_categories",
        ["parent_id", "sort_order", "id"],
    )

    op.create_table(
        "special_equipment_manufacturers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_manufacturers"),
        sa.UniqueConstraint(
            "slug", name="uq_special_equipment_manufacturers_slug"
        ),
    )
    op.create_index(
        "uq_special_equipment_manufacturers_name_ci",
        "special_equipment_manufacturers",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "special_equipment_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manufacturer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("modification", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column(
            "currency_code",
            sa.CHAR(length=3),
            server_default=sa.text("'RUB'"),
            nullable=False,
        ),
        sa.Column("manufacture_year", sa.SmallInteger(), nullable=True),
        sa.Column("vin", sa.String(length=32), nullable=True),
        sa.Column(
            "publication_status",
            sa.String(length=20),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "sale_status",
            sa.String(length=20),
            server_default=sa.text("'unavailable'"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_document",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('russian'::regconfig, "
                "coalesce(model, '') || ' ' || coalesce(modification, '') || ' ' || "
                "coalesce(description, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "price IS NULL OR price >= 0",
            name="ck_special_equipment_products_price_nonnegative",
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
        sa.ForeignKeyConstraint(
            ["manufacturer_id"],
            ["special_equipment_manufacturers.id"],
            name="fk_special_equipment_products_manufacturer",
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
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_products"),
        sa.UniqueConstraint("slug", name="uq_special_equipment_products_slug"),
    )
    op.create_index(
        "idx_special_equipment_products_published",
        "special_equipment_products",
        [sa.text("published_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_manufacturer_published",
        "special_equipment_products",
        ["manufacturer_id", sa.text("published_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_seller_published",
        "special_equipment_products",
        ["seller_company_id", sa.text("published_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_available",
        "special_equipment_products",
        [sa.text("published_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text(
            "publication_status = 'published' AND sale_status = 'available'"
        ),
    )
    op.create_index(
        "idx_special_equipment_products_price_asc_published",
        "special_equipment_products",
        [sa.text("price ASC NULLS LAST"), sa.text("id ASC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_price_desc_published",
        "special_equipment_products",
        [sa.text("price DESC NULLS LAST"), sa.text("id DESC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_name_published",
        "special_equipment_products",
        [sa.text("lower(model)"), sa.text("id ASC")],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
    op.create_index(
        "idx_special_equipment_products_search",
        "special_equipment_products",
        ["search_document"],
        postgresql_using="gin",
    )
    op.create_index(
        "uq_special_equipment_products_vin",
        "special_equipment_products",
        [sa.text("upper(vin)")],
        unique=True,
        postgresql_where=sa.text("vin IS NOT NULL"),
    )

    op.create_table(
        "special_equipment_attributes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("filter_kind", sa.String(length=20), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
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
            "(data_type = 'select' AND options IS NOT NULL) OR "
            "(data_type <> 'select' AND options IS NULL)",
            name="ck_special_equipment_attributes_options",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_attributes"),
        sa.UniqueConstraint("code", name="uq_special_equipment_attributes_code"),
    )

    op.create_table(
        "special_equipment_product_categories",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_product_categories_category",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            name="fk_special_equipment_product_categories_product",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id",
            "category_id",
            name="pk_special_equipment_product_categories",
        ),
    )
    op.create_index(
        "idx_special_equipment_product_categories_category",
        "special_equipment_product_categories",
        ["category_id", "product_id"],
    )
    op.create_index(
        "uq_special_equipment_product_primary_category",
        "special_equipment_product_categories",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    op.create_table(
        "special_equipment_category_attributes",
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_filterable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_special_equipment_category_attributes_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id"],
            ["special_equipment_attributes.id"],
            name="fk_special_equipment_category_attributes_attribute",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["special_equipment_categories.id"],
            name="fk_special_equipment_category_attributes_category",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "category_id",
            "attribute_id",
            name="pk_special_equipment_category_attributes",
        ),
    )
    op.create_index(
        "idx_special_equipment_category_attributes_attribute",
        "special_equipment_category_attributes",
        ["attribute_id", "category_id"],
    )

    op.create_table(
        "special_equipment_product_attribute_values",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attribute_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value_number", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean) = 1",
            name="ck_special_equipment_product_attribute_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_special_equipment_product_attribute_values_text_size",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id"],
            ["special_equipment_attributes.id"],
            name="fk_special_equipment_product_attribute_values_attribute",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            name="fk_special_equipment_product_attribute_values_product",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "product_id",
            "attribute_id",
            name="pk_special_equipment_product_attribute_values",
        ),
    )
    op.create_index(
        "idx_special_equipment_attribute_values_number",
        "special_equipment_product_attribute_values",
        ["attribute_id", "value_number", "product_id"],
        postgresql_where=sa.text("value_number IS NOT NULL"),
    )
    op.create_index(
        "idx_special_equipment_attribute_values_text",
        "special_equipment_product_attribute_values",
        ["attribute_id", "value_text", "product_id"],
        postgresql_where=sa.text("value_text IS NOT NULL"),
    )
    op.create_index(
        "idx_special_equipment_attribute_values_boolean",
        "special_equipment_product_attribute_values",
        ["attribute_id", "value_boolean", "product_id"],
        postgresql_where=sa.text("value_boolean IS NOT NULL"),
    )

    op.create_table(
        "special_equipment_product_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
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
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_product_images"),
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


def downgrade() -> None:
    op.drop_index(
        "uq_special_equipment_product_primary_image",
        table_name="special_equipment_product_images",
    )
    op.drop_index(
        "uq_special_equipment_product_image_order",
        table_name="special_equipment_product_images",
    )
    op.drop_table("special_equipment_product_images")

    op.drop_index(
        "idx_special_equipment_attribute_values_boolean",
        table_name="special_equipment_product_attribute_values",
    )
    op.drop_index(
        "idx_special_equipment_attribute_values_text",
        table_name="special_equipment_product_attribute_values",
    )
    op.drop_index(
        "idx_special_equipment_attribute_values_number",
        table_name="special_equipment_product_attribute_values",
    )
    op.drop_table("special_equipment_product_attribute_values")

    op.drop_index(
        "idx_special_equipment_category_attributes_attribute",
        table_name="special_equipment_category_attributes",
    )
    op.drop_table("special_equipment_category_attributes")

    op.drop_index(
        "uq_special_equipment_product_primary_category",
        table_name="special_equipment_product_categories",
    )
    op.drop_index(
        "idx_special_equipment_product_categories_category",
        table_name="special_equipment_product_categories",
    )
    op.drop_table("special_equipment_product_categories")

    op.drop_table("special_equipment_attributes")

    op.drop_index(
        "uq_special_equipment_products_vin",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_special_equipment_products_search",
        table_name="special_equipment_products",
        postgresql_using="gin",
    )
    op.drop_index(
        "idx_special_equipment_products_available",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_special_equipment_products_seller_published",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_special_equipment_products_manufacturer_published",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_special_equipment_products_published",
        table_name="special_equipment_products",
    )
    op.drop_table("special_equipment_products")

    op.drop_index(
        "uq_special_equipment_manufacturers_name_ci",
        table_name="special_equipment_manufacturers",
    )
    op.drop_table("special_equipment_manufacturers")

    op.drop_index(
        "idx_special_equipment_categories_parent_sort",
        table_name="special_equipment_categories",
    )
    op.drop_table("special_equipment_categories")
