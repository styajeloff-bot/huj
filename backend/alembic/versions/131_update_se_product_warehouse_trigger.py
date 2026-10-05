"""Update se_product_warehouse_prepare trigger function for warehouses.is_active.

Revision ID: 131
Revises: 130
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "131"
down_revision = "130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION se_product_warehouse_prepare()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                warehouse_is_active boolean;
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
                    SELECT is_active INTO warehouse_is_active
                    FROM warehouses
                    WHERE id = NEW.warehouse_id;

                    IF NOT FOUND THEN
                        RAISE EXCEPTION 'special-equipment product warehouse does not exist'
                            USING ERRCODE = '23503',
                                  CONSTRAINT = 'fk_se_products_warehouse';
                    END IF;
                    IF warehouse_is_active IS NOT TRUE THEN
                        RAISE EXCEPTION 'special-equipment product warehouse must be active'
                            USING ERRCODE = '23514',
                                  CONSTRAINT = 'trg_se_product_warehouse_active';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION se_product_warehouse_prepare()
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
            """
        )
    )
