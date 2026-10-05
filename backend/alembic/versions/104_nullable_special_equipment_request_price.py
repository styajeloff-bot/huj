"""Allow request-priced equipment without a lower price bound.

Revision ID: 104
Revises: 103
Create Date: 2026-08-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "104"
down_revision: str | None = "103"
branch_labels: str | None = None
depends_on: str | None = None

_PRODUCTS = "special_equipment_products"
_APPLICATION_ITEMS = "special_equipment_application_items"


def upgrade() -> None:
    """Permit unknown request prices while keeping fixed prices strict."""

    op.drop_constraint(
        "ck_se_products_price_mode_valid",
        _PRODUCTS,
        type_="check",
    )
    op.drop_constraint(
        "ck_special_equipment_products_on_order_price",
        _PRODUCTS,
        type_="check",
    )
    op.create_check_constraint(
        "ck_se_products_price_mode_valid",
        _PRODUCTS,
        "price_on_request OR price_from IS NULL",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_on_order_price",
        _PRODUCTS,
        "sale_status <> 'on_order' OR price_on_request OR "
        "(NOT price_on_request AND price > 0)",
    )

    op.drop_constraint(
        "ck_se_application_items_price_status_amounts",
        _APPLICATION_ITEMS,
        type_="check",
    )
    op.create_check_constraint(
        "ck_se_application_items_price_status_amounts",
        _APPLICATION_ITEMS,
        "price_status = 'none' OR "
        "(item_role <> 'component' AND ("
        "(price_status = 'pending' AND ("
        "(unit_price IS NULL AND total_price IS NULL) OR "
        "(unit_price > 0 AND total_price > 0))) OR "
        "(price_status = 'set' AND unit_price > 0 AND total_price > 0)))",
    )


def downgrade() -> None:
    """Restore required request bounds after rejecting incompatible rows."""

    op.execute(
        sa.text(
            """
            DO $migration$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_products
                    WHERE price_on_request AND price_from IS NULL
                ) OR EXISTS (
                    SELECT 1
                    FROM special_equipment_application_items
                    WHERE price_status = 'pending'
                      AND unit_price IS NULL
                      AND total_price IS NULL
                ) THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'Migration 104 downgrade blocked by unknown request prices',
                        HINT = 'Set positive product and pending item prices before downgrade';
                END IF;
            END
            $migration$;
            """
        )
    )

    op.drop_constraint(
        "ck_se_application_items_price_status_amounts",
        _APPLICATION_ITEMS,
        type_="check",
    )
    op.create_check_constraint(
        "ck_se_application_items_price_status_amounts",
        _APPLICATION_ITEMS,
        "price_status = 'none' OR "
        "(item_role <> 'component' AND unit_price > 0 AND total_price > 0)",
    )

    op.drop_constraint(
        "ck_special_equipment_products_on_order_price",
        _PRODUCTS,
        type_="check",
    )
    op.drop_constraint(
        "ck_se_products_price_mode_valid",
        _PRODUCTS,
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_on_order_price",
        _PRODUCTS,
        "sale_status <> 'on_order' OR "
        "(price_on_request AND price_from > 0) OR "
        "(NOT price_on_request AND price > 0)",
    )
    op.create_check_constraint(
        "ck_se_products_price_mode_valid",
        _PRODUCTS,
        "(price_on_request AND price_from IS NOT NULL) OR "
        "(NOT price_on_request AND price_from IS NULL)",
    )
