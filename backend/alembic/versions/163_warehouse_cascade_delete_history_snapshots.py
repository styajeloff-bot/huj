"""Warehouse cascade delete history snapshots and trigger relaxation.

Revision ID: 163
Revises: 162
Create Date: 2026-10-05 13:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "163"
down_revision = "162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. vehicle_warehouse_transfers snapshot columns
    op.add_column(
        "vehicle_warehouse_transfers",
        sa.Column(
            "product_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "vehicle_warehouse_transfers",
        sa.Column(
            "source_warehouse_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "vehicle_warehouse_transfers",
        sa.Column(
            "destination_warehouse_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    # Backfill vehicle_warehouse_transfers snapshots from products and warehouses
    op.execute("""
        UPDATE vehicle_warehouse_transfers AS t
        SET product_snapshot = jsonb_build_object(
            'id', p.id,
            'vin', p.vin,
            'code', p.code,
            'title', COALESCE(p.code, '')
        )
        FROM special_equipment_products AS p
        WHERE t.product_id = p.id;
    """)

    op.execute("""
        UPDATE vehicle_warehouse_transfers AS t
        SET source_warehouse_snapshot = jsonb_build_object(
            'id', w.id,
            'name', w.name,
            'address', w.address,
            'owner_company_id', w.owner_company_id
        )
        FROM warehouses AS w
        WHERE t.source_warehouse_id = w.id;
    """)

    op.execute("""
        UPDATE vehicle_warehouse_transfers AS t
        SET destination_warehouse_snapshot = jsonb_build_object(
            'id', w.id,
            'name', w.name,
            'address', w.address,
            'owner_company_id', w.owner_company_id
        )
        FROM warehouses AS w
        WHERE t.destination_warehouse_id = w.id;
    """)

    # Make FK columns nullable
    op.alter_column(
        "vehicle_warehouse_transfers",
        "product_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "vehicle_warehouse_transfers",
        "source_warehouse_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "vehicle_warehouse_transfers",
        "destination_warehouse_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Recreate FKs with ON DELETE SET NULL
    op.drop_constraint(
        "fk_vehicle_warehouse_transfers_product_id",
        "vehicle_warehouse_transfers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_product_id",
        "vehicle_warehouse_transfers",
        "special_equipment_products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_vehicle_warehouse_transfers_source_warehouse_id",
        "vehicle_warehouse_transfers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_source_warehouse_id",
        "vehicle_warehouse_transfers",
        "warehouses",
        ["source_warehouse_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_vehicle_warehouse_transfers_destination_warehouse_id",
        "vehicle_warehouse_transfers",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_destination_warehouse_id",
        "vehicle_warehouse_transfers",
        "warehouses",
        ["destination_warehouse_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Update distinct warehouses check constraint
    op.drop_constraint(
        "ck_vehicle_warehouse_transfers_distinct_warehouses",
        "vehicle_warehouse_transfers",
        type_="check",
    )
    op.create_check_constraint(
        "ck_vehicle_warehouse_transfers_distinct_warehouses",
        "vehicle_warehouse_transfers",
        "source_warehouse_id IS NULL OR destination_warehouse_id IS NULL OR source_warehouse_id <> destination_warehouse_id",
    )

    # 2. special_equipment_import_jobs
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "target_warehouse_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.execute("""
        UPDATE special_equipment_import_jobs AS j
        SET target_warehouse_snapshot = jsonb_build_object(
            'id', w.id,
            'name', w.name,
            'address', w.address,
            'owner_company_id', w.owner_company_id
        )
        FROM warehouses AS w
        WHERE j.target_warehouse_id = w.id;
    """)

    op.drop_constraint(
        "fk_se_import_jobs_target_warehouse",
        "special_equipment_import_jobs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_se_import_jobs_target_warehouse",
        "special_equipment_import_jobs",
        "warehouses",
        ["target_warehouse_id"],
        ["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
    )

    # 3. Update trigger function warehouses_delete_blocked()
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
            ) THEN
                RAISE EXCEPTION 'warehouse has special-equipment products'
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
                  AND status NOT IN ('completed', 'completed_with_warnings', 'failed', 'cancelled', 'validation_failed')
            ) THEN
                RAISE EXCEPTION 'warehouse has active special-equipment import jobs'
                    USING ERRCODE = '23503',
                          CONSTRAINT = 'trg_warehouses_delete_blocked';
            END IF;
            RETURN OLD;
        END;
        $$;
    """)


def downgrade() -> None:
    conn = op.get_bind()
    null_transfers = conn.execute(
        sa.text(
            "SELECT count(*) FROM vehicle_warehouse_transfers "
            "WHERE product_id IS NULL OR source_warehouse_id IS NULL OR destination_warehouse_id IS NULL"
        )
    ).scalar()
    if null_transfers and null_transfers > 0:
        raise RuntimeError(
            f"Cannot downgrade migration 163: vehicle_warehouse_transfers contains {null_transfers} "
            "row(s) with NULL product_id, source_warehouse_id, or destination_warehouse_id. "
            "Reverting would violate NOT NULL constraints or lose data."
        )

    # Restore trigger function from migration 125
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

    # Revert special_equipment_import_jobs
    op.drop_constraint(
        "fk_se_import_jobs_target_warehouse",
        "special_equipment_import_jobs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_se_import_jobs_target_warehouse",
        "special_equipment_import_jobs",
        "warehouses",
        ["target_warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.drop_column("special_equipment_import_jobs", "target_warehouse_snapshot")

    # Revert vehicle_warehouse_transfers check constraint
    op.drop_constraint(
        "ck_vehicle_warehouse_transfers_distinct_warehouses",
        "vehicle_warehouse_transfers",
        type_="check",
    )
    op.create_check_constraint(
        "ck_vehicle_warehouse_transfers_distinct_warehouses",
        "vehicle_warehouse_transfers",
        "source_warehouse_id <> destination_warehouse_id",
    )

    # Revert FKs
    op.drop_constraint(
        "fk_vehicle_warehouse_transfers_destination_warehouse_id",
        "vehicle_warehouse_transfers",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_vehicle_warehouse_transfers_source_warehouse_id",
        "vehicle_warehouse_transfers",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_vehicle_warehouse_transfers_product_id",
        "vehicle_warehouse_transfers",
        type_="foreignkey",
    )

    op.alter_column(
        "vehicle_warehouse_transfers",
        "destination_warehouse_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "vehicle_warehouse_transfers",
        "source_warehouse_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "vehicle_warehouse_transfers",
        "product_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_destination_warehouse_id",
        "vehicle_warehouse_transfers",
        "warehouses",
        ["destination_warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_source_warehouse_id",
        "vehicle_warehouse_transfers",
        "warehouses",
        ["source_warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_vehicle_warehouse_transfers_product_id",
        "vehicle_warehouse_transfers",
        "special_equipment_products",
        ["product_id"],
        ["id"],
    )

    op.drop_column("vehicle_warehouse_transfers", "destination_warehouse_snapshot")
    op.drop_column("vehicle_warehouse_transfers", "source_warehouse_snapshot")
    op.drop_column("vehicle_warehouse_transfers", "product_snapshot")
