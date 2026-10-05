"""Add allow_overstock to se cart items and overstock_requested_quantity to se app items.

Revision ID: 136
Revises: 135
Create Date: 2026-09-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "136"
down_revision = "135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "special_equipment_cart_items",
        sa.Column(
            "allow_overstock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "overstock_requested_quantity",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_se_application_items_overstock_qty",
        "special_equipment_application_items",
        "overstock_requested_quantity >= 0",
    )
    conn = op.get_bind()
    count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM special_equipment_cart_items WHERE quantity > 1000"
        )
    ).scalar()
    if count and count > 0:
        raise RuntimeError(
            f"Cannot create constraint ck_se_cart_items_quantity_max: "
            f"found {count} rows with quantity > 1000 in special_equipment_cart_items"
        )
    op.create_check_constraint(
        "ck_se_cart_items_quantity_max",
        "special_equipment_cart_items",
        "quantity <= 1000",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_se_cart_items_quantity_max",
        "special_equipment_cart_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_se_application_items_overstock_qty",
        "special_equipment_application_items",
        type_="check",
    )
    op.drop_column("special_equipment_application_items", "overstock_requested_quantity")
    op.drop_column("special_equipment_cart_items", "allow_overstock")
