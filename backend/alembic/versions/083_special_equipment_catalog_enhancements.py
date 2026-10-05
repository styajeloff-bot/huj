"""Complete the task 21940 special-equipment catalog contract.

Revision ID: 083
Revises: 082
Create Date: 2026-07-29

Revision 082 already introduced the normalized Mark -> Model -> Modification
catalog.  This revision only adds the missing group defaults, ordered primary
categories, product identity fields, on-order availability and preorder
commerce states.

The product ownership and VIN checks are installed as ``NOT VALID``.  This is
intentional: PostgreSQL still enforces them for every new or updated row while
allowing an existing row created before task 21940 to remain readable until it
is edited and completed through the management UI.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "083"
down_revision: str | None = "082"
branch_labels: str | None = None
depends_on: str | None = None


def _add_attribute_group_defaults() -> None:
    # Existing rows may predate the task 21940 contract. PostgreSQL will
    # enforce this check for new and updated rows, while legacy violations
    # remain readable until they are corrected.
    op.create_check_constraint(
        "ck_special_equipment_attributes_search_text",
        "special_equipment_attributes",
        "filter_kind IS DISTINCT FROM 'search' "
        "OR data_type IS NOT DISTINCT FROM 'text'",
        postgresql_not_valid=True,
    )
    op.add_column(
        "special_equipment_attributes",
        sa.Column(
            "attribute_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_special_equipment_attributes_group",
        "special_equipment_attributes",
        "special_equipment_attribute_groups",
        ["attribute_group_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_special_equipment_attributes_group",
        "special_equipment_attributes",
        ["attribute_group_id", "name", "id"],
    )
    op.alter_column(
        "special_equipment_category_attributes",
        "group_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        nullable=True,
    )


def _add_ordered_modification_categories() -> None:
    op.add_column(
        "special_equipment_modification_categories",
        sa.Column("sort_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "special_equipment_modification_categories",
        sa.Column("is_primary", sa.Boolean(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT modification_id,
                       category_id,
                       row_number() OVER (
                           PARTITION BY modification_id
                           ORDER BY category_id
                       ) - 1 AS position
                FROM special_equipment_modification_categories
            )
            UPDATE special_equipment_modification_categories AS target
            SET sort_order = ranked.position,
                is_primary = ranked.position = 0
            FROM ranked
            WHERE target.modification_id = ranked.modification_id
              AND target.category_id = ranked.category_id
            """
        )
    )
    op.alter_column(
        "special_equipment_modification_categories",
        "sort_order",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.alter_column(
        "special_equipment_modification_categories",
        "is_primary",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )
    op.create_check_constraint(
        "ck_se_modification_categories_sort_order",
        "special_equipment_modification_categories",
        "sort_order >= 0",
    )
    op.create_unique_constraint(
        "uq_se_modification_categories_order",
        "special_equipment_modification_categories",
        ["modification_id", "sort_order"],
    )
    op.create_index(
        "uq_se_modification_categories_primary",
        "special_equipment_modification_categories",
        ["modification_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def _add_product_contract() -> None:
    op.add_column(
        "special_equipment_products",
        sa.Column("owners_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column("no_vin", sa.Boolean(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE special_equipment_products "
            "SET no_vin = (vin IS NULL) "
            "WHERE no_vin IS NULL"
        )
    )
    op.alter_column(
        "special_equipment_products",
        "no_vin",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )

    # NOT VALID preserves pre-21940 rows while enforcing the contract for all
    # new rows and for an old row as soon as it is edited.
    op.create_check_constraint(
        "ck_special_equipment_products_owners_count_positive",
        "special_equipment_products",
        "owners_count IS NULL OR owners_count >= 1",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_special_equipment_products_condition_owners",
        "special_equipment_products",
        "(condition = 'new' AND owners_count IS NULL) OR "
        "(condition = 'used' AND owners_count IS NOT NULL AND owners_count >= 1)",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_special_equipment_products_vin_choice",
        "special_equipment_products",
        "(no_vin AND vin IS NULL) OR "
        "(NOT no_vin AND vin IS NOT NULL AND btrim(vin) <> '' "
        "AND char_length(vin) <= 17)",
        postgresql_not_valid=True,
    )

    op.drop_constraint(
        "ck_special_equipment_products_sale_status",
        "special_equipment_products",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_sale_status",
        "special_equipment_products",
        "sale_status IN ("
        "'available', 'on_order', 'reserved', 'sold', 'unavailable')",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_on_order_price",
        "special_equipment_products",
        "sale_status <> 'on_order' OR price > 0",
    )
    op.create_index(
        "idx_se_products_public_availability",
        "special_equipment_products",
        ["sale_status", sa.text("published_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text(
            "publication_status = 'published' "
            "AND sale_status IN ('available', 'on_order')"
        ),
    )


def _add_text_search_indexes() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for index_name, table_name, expression, where in (
        (
            "idx_se_marks_name_search",
            "special_equipment_marks",
            "lower(name) gin_trgm_ops",
            None,
        ),
        (
            "idx_se_models_name_search",
            "special_equipment_models",
            "lower(name) gin_trgm_ops",
            None,
        ),
        (
            "idx_se_modifications_name_search",
            "special_equipment_modifications",
            "lower(name) gin_trgm_ops",
            None,
        ),
        (
            "idx_se_products_description_search",
            "special_equipment_products",
            "lower(description) gin_trgm_ops",
            sa.text("description IS NOT NULL"),
        ),
    ):
        op.create_index(
            index_name,
            table_name,
            [sa.text(expression)],
            postgresql_using="gin",
            postgresql_where=where,
        )
    op.create_index(
        "idx_se_modification_attribute_values_text_search",
        "special_equipment_modification_attribute_values",
        [sa.text("lower(value_text) gin_trgm_ops")],
        postgresql_using="gin",
        postgresql_where=sa.text("value_text IS NOT NULL"),
    )


def _stale_pre_v4_import_previews() -> None:
    # Revision 082 did not persist the normalized artifact schema version on
    # the job row, so SQL cannot distinguish an old v3 archive from a v4 one.
    # Conservatively invalidate every unfinished archive present at migration
    # time. Preview/apply is retryable; applying an unauthenticated v3 plan is
    # not. Fresh v4 previews generated after this migration are unaffected.
    op.execute(
        sa.text(
            """
            UPDATE special_equipment_import_jobs
            SET status = 'preview_stale',
                phase = 'preview_stale',
                error_code = 'PREVIEW_STALE',
                error_detail =
                    'Предпросмотр создан устаревшей версией нормализатора; '
                    'запустите проверку файла повторно',
                lease_owner = NULL,
                lease_until = NULL,
                heartbeat_at = NULL,
                updated_at = now()
            WHERE normalized_artifact_key IS NOT NULL
              AND applied_revision IS NULL
              AND status IN ('preview_ready', 'applying')
            """
        )
    )


def _add_preorder_contract() -> None:
    op.drop_constraint(
        "ck_special_equipment_payment_type",
        "special_equipment_payments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_payment_type",
        "special_equipment_payments",
        "payment_type IN ('reservation', 'preorder', 'full_purchase', "
        "'remaining_balance', 'leasing', 'leasing_monthly')",
    )
    op.drop_constraint(
        "ck_special_equipment_order_purchase_type",
        "special_equipment_purchase_orders",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_order_purchase_type",
        "special_equipment_purchase_orders",
        "purchase_type IN ('reservation', 'preorder', 'full_purchase', 'leasing')",
    )
    op.drop_constraint(
        "ck_special_equipment_order_status",
        "special_equipment_purchase_orders",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_order_status",
        "special_equipment_purchase_orders",
        "status IN ('payment_pending', 'reserved', 'preordered', 'purchased', "
        "'leasing_pending', 'leasing_active', 'cancellation_requested', "
        "'cancelled', 'expired', 'failed')",
    )
    op.create_check_constraint(
        "ck_special_equipment_order_preorder_state",
        "special_equipment_purchase_orders",
        "(purchase_type = 'preorder' AND status IN ("
        "'preordered', 'cancellation_requested', "
        "'cancelled', 'expired', 'failed')) OR "
        "(purchase_type <> 'preorder' AND status <> 'preordered')",
    )

    op.drop_index(
        "uq_special_equipment_orders_active_product",
        table_name="special_equipment_purchase_orders",
    )
    op.create_index(
        "uq_special_equipment_orders_active_product",
        "special_equipment_purchase_orders",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text(
            "purchase_type <> 'preorder' AND status IN ("
            "'payment_pending', 'reserved', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested')"
        ),
    )
    op.drop_index(
        "idx_se_orders_live_seller",
        table_name="special_equipment_purchase_orders",
    )
    op.create_index(
        "idx_se_orders_live_seller",
        "special_equipment_purchase_orders",
        ["seller_company_id", "product_id"],
        postgresql_where=sa.text(
            "seller_company_id IS NOT NULL AND status IN ("
            "'payment_pending', 'reserved', 'preordered', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested')"
        ),
    )


def upgrade() -> None:
    _stale_pre_v4_import_previews()
    _add_attribute_group_defaults()
    _add_ordered_modification_categories()
    _add_product_contract()
    _add_text_search_indexes()
    _add_preorder_contract()


def downgrade() -> None:
    # The old checks cannot represent these values.  Abort instead of silently
    # rewriting or deleting commercial history.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM special_equipment_products
                    WHERE sale_status = 'on_order'
                ) OR EXISTS (
                    SELECT 1 FROM special_equipment_purchase_orders
                    WHERE purchase_type = 'preorder' OR status = 'preordered'
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 083 while on-order products or preorder orders exist';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM special_equipment_category_attributes
                    WHERE group_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 083 while category group overrides are empty';
                END IF;
            END
            $$
            """
        )
    )

    op.drop_index(
        "idx_se_orders_live_seller",
        table_name="special_equipment_purchase_orders",
    )
    op.create_index(
        "idx_se_orders_live_seller",
        "special_equipment_purchase_orders",
        ["seller_company_id", "product_id"],
        postgresql_where=sa.text(
            "seller_company_id IS NOT NULL AND status IN ("
            "'payment_pending', 'reserved', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested')"
        ),
    )
    op.drop_index(
        "uq_special_equipment_orders_active_product",
        table_name="special_equipment_purchase_orders",
    )
    op.create_index(
        "uq_special_equipment_orders_active_product",
        "special_equipment_purchase_orders",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('payment_pending', 'reserved', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested')"
        ),
    )
    op.drop_constraint(
        "ck_special_equipment_order_preorder_state",
        "special_equipment_purchase_orders",
        type_="check",
    )
    op.drop_constraint(
        "ck_special_equipment_order_status",
        "special_equipment_purchase_orders",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_order_status",
        "special_equipment_purchase_orders",
        "status IN ('payment_pending', 'reserved', 'purchased', "
        "'leasing_pending', 'leasing_active', 'cancellation_requested', "
        "'cancelled', 'expired', 'failed')",
    )
    op.drop_constraint(
        "ck_special_equipment_order_purchase_type",
        "special_equipment_purchase_orders",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_order_purchase_type",
        "special_equipment_purchase_orders",
        "purchase_type IN ('reservation', 'full_purchase', 'leasing')",
    )
    op.drop_constraint(
        "ck_special_equipment_payment_type",
        "special_equipment_payments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_payment_type",
        "special_equipment_payments",
        "payment_type IN ('reservation', 'full_purchase', 'remaining_balance', "
        "'leasing', 'leasing_monthly')",
    )

    op.drop_index(
        "idx_se_modification_attribute_values_text_search",
        table_name="special_equipment_modification_attribute_values",
    )
    for index_name, table_name in (
        ("idx_se_products_description_search", "special_equipment_products"),
        ("idx_se_modifications_name_search", "special_equipment_modifications"),
        ("idx_se_models_name_search", "special_equipment_models"),
        ("idx_se_marks_name_search", "special_equipment_marks"),
    ):
        op.drop_index(index_name, table_name=table_name)
    op.drop_index(
        "idx_se_products_public_availability",
        table_name="special_equipment_products",
    )
    op.drop_constraint(
        "ck_special_equipment_products_on_order_price",
        "special_equipment_products",
        type_="check",
    )
    op.drop_constraint(
        "ck_special_equipment_products_sale_status",
        "special_equipment_products",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_sale_status",
        "special_equipment_products",
        "sale_status IN ('available', 'reserved', 'sold', 'unavailable')",
    )
    for constraint_name in (
        "ck_special_equipment_products_vin_choice",
        "ck_special_equipment_products_condition_owners",
        "ck_special_equipment_products_owners_count_positive",
    ):
        op.drop_constraint(
            constraint_name,
            "special_equipment_products",
            type_="check",
        )
    op.drop_column("special_equipment_products", "no_vin")
    op.drop_column("special_equipment_products", "owners_count")

    op.drop_index(
        "uq_se_modification_categories_primary",
        table_name="special_equipment_modification_categories",
    )
    op.drop_constraint(
        "uq_se_modification_categories_order",
        "special_equipment_modification_categories",
        type_="unique",
    )
    op.drop_constraint(
        "ck_se_modification_categories_sort_order",
        "special_equipment_modification_categories",
        type_="check",
    )
    op.drop_column("special_equipment_modification_categories", "is_primary")
    op.drop_column("special_equipment_modification_categories", "sort_order")

    op.alter_column(
        "special_equipment_category_attributes",
        "group_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        nullable=False,
    )
    op.drop_constraint(
        "ck_special_equipment_attributes_search_text",
        "special_equipment_attributes",
        type_="check",
    )
    op.drop_index(
        "idx_special_equipment_attributes_group",
        table_name="special_equipment_attributes",
    )
    op.drop_constraint(
        "fk_special_equipment_attributes_group",
        "special_equipment_attributes",
        type_="foreignkey",
    )
    op.drop_column("special_equipment_attributes", "attribute_group_id")
