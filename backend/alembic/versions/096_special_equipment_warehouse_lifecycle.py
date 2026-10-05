"""Enforce canonical special-equipment warehouse lifecycle invariants.

Revision ID: 096
Revises: 095
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "096"
down_revision: str | None = "095"
branch_labels: str | None = None
depends_on: str | None = None


def _execute_postgresql_statements(sql: str) -> None:
    """Execute DDL one statement at a time for asyncpg's prepared protocol."""
    statements: list[str] = []
    statement_start = 0
    dollar_quote: str | None = None
    index = 0

    while index < len(sql):
        if sql[index] == "$":
            quote_end = sql.find("$", index + 1)
            if quote_end != -1:
                candidate = sql[index : quote_end + 1]
                tag = candidate[1:-1]
                if not tag or tag.replace("_", "").isalnum():
                    if dollar_quote is None:
                        dollar_quote = candidate
                        index = quote_end + 1
                        continue
                    if candidate == dollar_quote:
                        dollar_quote = None
                        index = quote_end + 1
                        continue
        if sql[index] == ";" and dollar_quote is None:
            statement = sql[statement_start : index + 1].strip()
            if statement:
                statements.append(statement)
            statement_start = index + 1
        index += 1

    trailing_statement = sql[statement_start:].strip()
    if trailing_statement:
        statements.append(trailing_statement)
    for statement in statements:
        op.execute(sa.text(statement))


def upgrade() -> None:
    bind = op.get_bind()

    # Read-only audit of warehouse status values before normalization.
    bind.execute(
        sa.text("SELECT DISTINCT status FROM warehouses ORDER BY status NULLS FIRST")
    ).all()
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM warehouses
                    WHERE status IS NOT NULL
                      AND status NOT IN ('active', 'inactive')
                ) THEN
                    RAISE EXCEPTION 'unknown warehouse status; migration aborted before data changes'
                        USING ERRCODE = '23514';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(sa.text("UPDATE warehouses SET status = 'active' WHERE status IS NULL"))
    op.alter_column(
        "warehouses",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default=sa.text("'active'"),
    )
    op.create_check_constraint(
        "ck_warehouses_status", "warehouses", "status IN ('active', 'inactive')"
    )

    op.add_column(
        "special_equipment_import_jobs",
        sa.Column("target_warehouse_id", postgresql.UUID(as_uuid=True), nullable=True),
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
    op.create_index(
        "idx_se_import_jobs_target_warehouse",
        "special_equipment_import_jobs",
        ["target_warehouse_id"],
    )
    op.create_index(
        "idx_se_products_published_sale_status",
        "special_equipment_products",
        ["sale_status", "id"],
        postgresql_where=sa.text("publication_status = 'published'"),
    )

    _execute_postgresql_statements(
        """
            CREATE FUNCTION se_product_warehouse_prepare()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                warehouse_status text;
            BEGIN
                IF TG_OP = 'UPDATE' AND NOT OLD.no_vin AND NEW.no_vin THEN
                    NEW.warehouse_id := NULL;
                END IF;

                IF NEW.no_vin AND NEW.warehouse_id IS NOT NULL THEN
                    RAISE EXCEPTION 'a no_vin product cannot have a warehouse'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'trg_se_product_warehouse_no_vin';
                END IF;

                IF NEW.warehouse_id IS NOT NULL THEN
                    SELECT status INTO warehouse_status
                    FROM warehouses
                    WHERE id = NEW.warehouse_id;

                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'special-equipment product warehouse does not exist'
                            USING ERRCODE = '23503',
                                  CONSTRAINT = 'fk_se_products_warehouse';
                    END IF;
                    IF warehouse_status IS DISTINCT FROM 'active' THEN
                        RAISE EXCEPTION 'special-equipment product warehouse must be active'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'trg_se_product_warehouse_active';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$;

            CREATE FUNCTION se_product_warehouse_required()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                product_no_vin boolean;
                product_vin text;
                product_warehouse_id uuid;
                product_publication_status text;
                product_sale_status text;
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RETURN NULL;
                END IF;

                SELECT no_vin, vin, warehouse_id, publication_status, sale_status
                INTO product_no_vin, product_vin, product_warehouse_id,
                     product_publication_status, product_sale_status
                FROM special_equipment_products
                WHERE id = NEW.id;

                IF NOT FOUND OR product_publication_status = 'archived' THEN
                    RETURN NULL;
                END IF;

                IF product_no_vin IS FALSE AND product_vin IS NULL THEN
                    RAISE EXCEPTION 'VIN product requires a VIN'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'trg_se_product_warehouse_vin_required';
                END IF;

                IF product_no_vin IS FALSE
                   AND product_sale_status = 'available'
                   AND product_warehouse_id IS NULL THEN
                    RAISE EXCEPTION 'available VIN product requires an active warehouse'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'trg_se_product_warehouse_required';
                END IF;
                RETURN NULL;
            END;
            $$;

            CREATE FUNCTION warehouses_delete_blocked()
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
                    SELECT 1 FROM vehicle_warehouses WHERE warehouse_id = OLD.id
                ) THEN
                    RAISE EXCEPTION 'warehouse has vehicle locations'
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

            CREATE TRIGGER trg_se_product_warehouse_prepare
            BEFORE INSERT OR UPDATE OF no_vin, warehouse_id
            ON special_equipment_products
            FOR EACH ROW EXECUTE FUNCTION se_product_warehouse_prepare();

            CREATE CONSTRAINT TRIGGER trg_se_product_warehouse_required
            AFTER INSERT OR UPDATE OF no_vin, vin, warehouse_id,
                publication_status, sale_status OR DELETE
            ON special_equipment_products
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION se_product_warehouse_required();

            CREATE TRIGGER trg_warehouses_delete_blocked
            BEFORE DELETE ON warehouses
            FOR EACH ROW EXECUTE FUNCTION warehouses_delete_blocked();
        """
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_import_jobs
                    WHERE target_warehouse_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION 'cannot downgrade revision 096 while import warehouse targets exist'
                        USING ERRCODE = '23503';
                END IF;
            END
            $$;
            """
        )
    )
    _execute_postgresql_statements(
        """
            DROP TRIGGER trg_warehouses_delete_blocked ON warehouses;
            DROP TRIGGER trg_se_product_warehouse_required
                ON special_equipment_products;
            DROP TRIGGER trg_se_product_warehouse_prepare
                ON special_equipment_products;
            DROP FUNCTION warehouses_delete_blocked();
            DROP FUNCTION se_product_warehouse_required();
            DROP FUNCTION se_product_warehouse_prepare();
        """
    )
    op.drop_index(
        "idx_se_products_published_sale_status",
        table_name="special_equipment_products",
    )
    op.drop_constraint(
        "fk_se_import_jobs_target_warehouse",
        "special_equipment_import_jobs",
        type_="foreignkey",
    )
    op.drop_index(
        "idx_se_import_jobs_target_warehouse",
        table_name="special_equipment_import_jobs",
    )
    op.drop_column("special_equipment_import_jobs", "target_warehouse_id")
    op.drop_constraint("ck_warehouses_status", "warehouses", type_="check")
    op.alter_column(
        "warehouses",
        "status",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=sa.text("'active'"),
    )
