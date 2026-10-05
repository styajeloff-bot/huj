"""Retire legacy vehicle catalog, vehicles table and bridge references to special equipment.

Revision ID: 125
Revises: 124
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "125"
down_revision: str | None = "124"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Drop scalar and array reference guards from migration 118
    scalar_guard_tables = (
        "leasing_applications",
        "shopping_cart",
        "compensations",
        "application_applied_supports",
        "leasing_application_vehicle_calculations",
        "guest_cart_transfers",
    )
    for table in scalar_guard_tables:
        op.execute(f"DROP TRIGGER IF EXISTS guard_vehicle_reference ON {table}")
    op.execute("DROP FUNCTION IF EXISTS guard_vehicle_scalar_reference()")

    op.execute("DROP TRIGGER IF EXISTS guard_vehicle_array_references ON calculation_history")
    op.execute("DROP FUNCTION IF EXISTS guard_vehicle_array_references()")

    # 2. Drop allocation protection trigger from migration 119
    op.execute("DROP TRIGGER IF EXISTS protect_allocated_vehicle ON vehicles")
    op.execute("DROP FUNCTION IF EXISTS protect_allocated_vehicle()")

    # 3. Update warehouses_delete_blocked function from migration 096 (remove vehicle_warehouses check)
    op.execute("""
        CREATE OR REPLACE FUNCTION warehouses_delete_blocked()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM special_equipment_products AS product
                WHERE product.warehouse_id = OLD.id
                  AND product.publication_status <> 'archived'
            ) THEN
                RAISE EXCEPTION 'warehouse has non-archived special-equipment products'
                    USING ERRCODE = '23503',
                          CONSTRAINT = 'trg_warehouses_delete_blocked';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM vehicle_warehouse_transfers
                WHERE source_warehouse_id = OLD.id
                   OR destination_warehouse_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'warehouse has vehicle transfer history'
                    USING ERRCODE = '23503',
                          CONSTRAINT = 'trg_warehouses_delete_blocked';
            END IF;

            IF EXISTS (
                SELECT 1 FROM exchange_cart_item_warehouses WHERE warehouse_id = OLD.id
                UNION ALL
                SELECT 1 FROM exchange_request_warehouses WHERE warehouse_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'warehouse has exchange links'
                    USING ERRCODE = '23503',
                          CONSTRAINT = 'trg_warehouses_delete_blocked';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM special_equipment_import_jobs
                WHERE target_warehouse_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'warehouse is a special-equipment import target'
                    USING ERRCODE = '23503',
                          CONSTRAINT = 'trg_warehouses_delete_blocked';
            END IF;
            RETURN OLD;
        END;
        $$;
    """)

    # 4. Drop FK constraints pointing to vehicles
    op.drop_constraint("purchase_orders_vehicle_id_fkey", "purchase_orders", type_="foreignkey")
    op.drop_constraint("application_vehicles_vehicle_id_fkey", "application_vehicles", type_="foreignkey")
    op.drop_constraint("application_vehicle_allocations_vehicle_id_fkey", "application_vehicle_allocations", type_="foreignkey")
    op.drop_constraint("exchange_requests_vehicle_id_fkey", "exchange_requests", type_="foreignkey")
    op.drop_constraint("exchange_cart_items_vehicle_id_fkey", "exchange_cart_items", type_="foreignkey")
    op.drop_constraint("user_favorites_vehicle_id_fkey", "user_favorites", type_="foreignkey")
    op.drop_constraint("fk_vehicle_warehouse_transfers_vehicle_id", "vehicle_warehouse_transfers", type_="foreignkey")
    op.drop_constraint("vehicle_warehouses_vehicle_id_fkey", "vehicle_warehouses", type_="foreignkey")

    # 5. Drop FK constraints pointing to mark & model
    op.drop_constraint("fk_distributor_brands_brand", "distributor_brands", type_="foreignkey")
    op.drop_constraint("support_programs_mark_id_fkey", "support_programs", type_="foreignkey")
    op.drop_constraint("support_programs_model_id_fkey", "support_programs", type_="foreignkey")
    op.drop_constraint("support_program_marks_mark_id_fkey", "support_program_marks", type_="foreignkey")
    op.drop_constraint("featured_vehicles_model_id_fkey", "featured_vehicles", type_="foreignkey")

    # 6. Rename/alter columns vehicle_id -> product_id and add new FKs/indexes
    # purchase_orders
    op.drop_index("idx_purchase_orders_vehicle_id", table_name="purchase_orders")
    op.alter_column("purchase_orders", "vehicle_id", new_column_name="product_id")
    op.create_foreign_key(
        "purchase_orders_product_id_fkey",
        "purchase_orders",
        "special_equipment_products",
        ["product_id"],
        ["id"],
    )
    op.create_index("idx_purchase_orders_product_id", "purchase_orders", ["product_id"])

    # application_vehicles
    op.drop_constraint("uq_application_vehicles", "application_vehicles", type_="unique")
    op.drop_index("idx_application_vehicles_vehicle_id", table_name="application_vehicles")
    op.alter_column("application_vehicles", "vehicle_id", new_column_name="product_id")
    op.create_unique_constraint(
        "uq_application_vehicles", "application_vehicles", ["application_id", "product_id"]
    )
    op.create_foreign_key(
        "application_vehicles_product_id_fkey",
        "application_vehicles",
        "special_equipment_products",
        ["product_id"],
        ["id"],
    )
    op.create_index("idx_application_vehicles_product_id", "application_vehicles", ["product_id"])

    # application_vehicle_allocations
    op.drop_index("uq_vehicle_active_allocation", table_name="application_vehicle_allocations")
    op.alter_column("application_vehicle_allocations", "vehicle_id", new_column_name="product_id")
    op.create_foreign_key(
        "application_vehicle_allocations_product_id_fkey",
        "application_vehicle_allocations",
        "special_equipment_products",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_vehicle_active_allocation",
        "application_vehicle_allocations",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )

    # exchange_requests
    op.drop_index("idx_exchange_requests_vehicle", table_name="exchange_requests")
    op.alter_column("exchange_requests", "vehicle_id", new_column_name="product_id")
    op.create_foreign_key(
        "exchange_requests_product_id_fkey",
        "exchange_requests",
        "special_equipment_products",
        ["product_id"],
        ["id"],
    )
    op.create_index("idx_exchange_requests_product", "exchange_requests", ["product_id"])

    # exchange_cart_items
    op.drop_constraint("exchange_cart_items_user_vehicle_unique", "exchange_cart_items", type_="unique")
    op.alter_column("exchange_cart_items", "vehicle_id", new_column_name="product_id")
    op.create_unique_constraint(
        "exchange_cart_items_user_vehicle_unique",
        "exchange_cart_items",
        ["user_id", "product_id"],
    )
    op.create_foreign_key(
        "exchange_cart_items_product_id_fkey",
        "exchange_cart_items",
        "special_equipment_products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # user_favorites
    op.drop_constraint("user_favorites_user_id_vehicle_id_key", "user_favorites", type_="unique")
    op.drop_index("idx_user_favorites_vehicle_id", table_name="user_favorites")
    op.alter_column("user_favorites", "vehicle_id", new_column_name="product_id")
    op.create_unique_constraint(
        "user_favorites_user_id_vehicle_id_key",
        "user_favorites",
        ["user_id", "storefront_id", "product_id"],
    )
    op.create_foreign_key(
        "user_favorites_product_id_fkey",
        "user_favorites",
        "special_equipment_products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_user_favorites_product_id", "user_favorites", ["product_id"])

    # vehicle_warehouse_transfers
    op.drop_index("idx_vehicle_warehouse_transfers_vehicle_created_at", table_name="vehicle_warehouse_transfers")
    op.alter_column("vehicle_warehouse_transfers", "vehicle_id", new_column_name="product_id")
    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_product_id",
        "vehicle_warehouse_transfers",
        "special_equipment_products",
        ["product_id"],
        ["id"],
    )
    op.create_index(
        "idx_vehicle_warehouse_transfers_product_created_at",
        "vehicle_warehouse_transfers",
        ["product_id", sa.text("created_at DESC")],
    )

    # application_applied_supports
    op.drop_index("idx_application_applied_supports_vehicle", table_name="application_applied_supports")
    op.alter_column("application_applied_supports", "vehicle_id", new_column_name="product_id")
    op.create_index("idx_application_applied_supports_product", "application_applied_supports", ["product_id"])

    # compensations
    op.alter_column("compensations", "vehicle_id", new_column_name="product_id")

    # shopping_cart
    op.drop_constraint("shopping_cart_user_vehicle_unique", "shopping_cart", type_="unique")
    op.drop_index("idx_shopping_cart_vehicle_id", table_name="shopping_cart")
    op.alter_column("shopping_cart", "vehicle_id", new_column_name="product_id")
    op.create_unique_constraint(
        "shopping_cart_user_vehicle_unique",
        "shopping_cart",
        ["user_id", "storefront_id", "product_id"],
    )
    op.create_index("idx_shopping_cart_product_id", "shopping_cart", ["product_id"])

    # 7. distributor_brands.brand_id -> UUID
    op.drop_index("uq_distributor_brands_active_company_brand", table_name="distributor_brands")
    op.drop_index("idx_distributor_brands_brand_id", table_name="distributor_brands")
    op.execute("ALTER TABLE distributor_brands ALTER COLUMN brand_id TYPE uuid USING brand_id::uuid")
    op.create_foreign_key(
        "fk_distributor_brands_brand",
        "distributor_brands",
        "special_equipment_marks",
        ["brand_id"],
        ["id"],
    )
    op.create_index("idx_distributor_brands_brand_id", "distributor_brands", ["brand_id"])
    op.create_index(
        "uq_distributor_brands_active_company_brand",
        "distributor_brands",
        ["distributor_company_id", "brand_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    # 8. support_programs.mark_id and model_id -> UUID
    op.drop_index("idx_support_programs_mark", table_name="support_programs")
    op.drop_index("idx_support_programs_model", table_name="support_programs")
    op.execute("ALTER TABLE support_programs ALTER COLUMN mark_id TYPE uuid USING mark_id::uuid")
    op.execute("ALTER TABLE support_programs ALTER COLUMN model_id TYPE uuid USING model_id::uuid")
    op.create_foreign_key(
        "support_programs_mark_id_fkey",
        "support_programs",
        "special_equipment_marks",
        ["mark_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "support_programs_model_id_fkey",
        "support_programs",
        "special_equipment_models",
        ["model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_support_programs_mark", "support_programs", ["mark_id"])
    op.create_index("idx_support_programs_model", "support_programs", ["model_id"])

    # 9. support_program_marks.mark_id -> UUID
    op.drop_constraint("support_program_marks_pkey", "support_program_marks", type_="primary")
    op.drop_index("idx_support_program_marks_mark", table_name="support_program_marks")
    op.execute("ALTER TABLE support_program_marks ALTER COLUMN mark_id TYPE uuid USING mark_id::uuid")
    op.create_primary_key(
        "support_program_marks_pkey",
        "support_program_marks",
        ["support_program_id", "mark_id"],
    )
    op.create_foreign_key(
        "support_program_marks_mark_id_fkey",
        "support_program_marks",
        "special_equipment_marks",
        ["mark_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_support_program_marks_mark", "support_program_marks", ["mark_id"])

    # 10. Drop legacy tables
    legacy_tables = [
        "featured_vehicles",
        "catalog_facets_snapshot",
        "options",
        "specifications",
        "modification",
        "configuration",
        "generation",
        "model",
        "mark",
        "vehicle_category",
        "vehicle_warehouses",
        "vehicles",
    ]
    for table_name in legacy_tables:
        op.drop_table(table_name)

    # 11. Update catalog_storefronts check constraints and data
    op.drop_constraint("ck_catalog_storefronts_home_page_key", "catalog_storefronts", type_="check")
    op.drop_constraint("ck_catalog_storefronts_public_page_titles", "catalog_storefronts", type_="check")

    op.execute("UPDATE catalog_storefronts SET home_page_key = 'home' WHERE home_page_key IN ('catalog', 'models')")
    op.execute("UPDATE catalog_storefronts SET public_page_titles = public_page_titles - 'catalog' - 'models'")
    op.execute(
        "ALTER TABLE catalog_storefronts ALTER COLUMN public_page_titles SET DEFAULT "
        "'{\"home\": \"Главная\", \"about\": \"О нас\", \"special_equipment_catalog\": \"Спецтехника\"}'::jsonb"
    )

    op.create_check_constraint(
        "ck_catalog_storefronts_home_page_key",
        "catalog_storefronts",
        "home_page_key IN ('home', 'about', 'special_equipment_catalog')",
    )
    op.create_check_constraint(
        "ck_catalog_storefronts_public_page_titles",
        "catalog_storefronts",
        "jsonb_typeof(public_page_titles) = 'object' "
        "AND public_page_titles ?& ARRAY['home', 'about', 'special_equipment_catalog'] "
        "AND (public_page_titles - ARRAY['home', 'about', 'special_equipment_catalog']) = '{}'::jsonb "
        "AND jsonb_typeof(public_page_titles -> 'home') = 'string' "
        "AND jsonb_typeof(public_page_titles -> 'about') = 'string' "
        "AND jsonb_typeof(public_page_titles -> 'special_equipment_catalog') = 'string'",
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for 125_retire_legacy_catalog")
