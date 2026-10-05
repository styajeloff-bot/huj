"""Add request pricing and application price agreement state.

Revision ID: 099
Revises: 098
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "099"
down_revision: str | None = "098"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Install explicit request pricing without guessing legacy zero prices."""

    op.execute(
        sa.text(
            """
            DO $migration$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_products
                    WHERE price = 0 OR special_price = 0
                ) THEN
                    RAISE EXCEPTION USING
                        MESSAGE = 'Migration 099 blocked: special-equipment prices contain zero values',
                        HINT = 'Correct price/special_price values before enabling price-on-request constraints';
                END IF;
            END
            $migration$;
            """
        )
    )

    op.add_column(
        "special_equipment_products",
        sa.Column(
            "price_on_request",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column("price_from", sa.Numeric(precision=15, scale=2), nullable=True),
    )
    op.drop_index(
        "idx_se_products_effective_price_published",
        table_name="special_equipment_products",
    )
    for constraint_name in (
        "ck_special_equipment_products_price_nonnegative",
        "ck_special_equipment_products_on_order_price",
        "ck_special_equipment_products_claimed_price",
    ):
        op.drop_constraint(
            constraint_name,
            "special_equipment_products",
            type_="check",
        )
    op.create_check_constraint(
        "ck_special_equipment_products_price_nonnegative",
        "special_equipment_products",
        "price IS NULL OR price > 0",
    )
    op.create_check_constraint(
        "ck_se_products_price_from_valid",
        "special_equipment_products",
        "price_from IS NULL OR price_from > 0",
    )
    op.create_check_constraint(
        "ck_se_products_price_mode_valid",
        "special_equipment_products",
        "(price_on_request AND price_from IS NOT NULL) OR "
        "(NOT price_on_request AND price_from IS NULL)",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_on_order_price",
        "special_equipment_products",
        "sale_status <> 'on_order' OR "
        "(price_on_request AND price_from > 0) OR "
        "(NOT price_on_request AND price > 0)",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_claimed_price",
        "special_equipment_products",
        "sale_status NOT IN ('reserved', 'sold') OR "
        "(price_on_request AND price_from > 0) OR "
        "(NOT price_on_request AND price IS NOT NULL)",
    )
    op.create_index(
        "idx_se_products_effective_price_published",
        "special_equipment_products",
        [
            sa.text(
                "(CASE WHEN price_on_request THEN price_from "
                "ELSE COALESCE(special_price, price) END)"
            ),
            "id",
        ],
        postgresql_where=sa.text("publication_status = 'published'"),
    )

    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "price_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "price_set_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_application_items",
        sa.Column("price_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_se_application_items_price_set_by",
        "special_equipment_application_items",
        "users",
        ["price_set_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_se_application_items_price_status",
        "special_equipment_application_items",
        "price_status IN ('none', 'pending', 'set')",
    )
    op.create_check_constraint(
        "ck_se_application_items_price_status_consistency",
        "special_equipment_application_items",
        "(price_status IN ('none', 'pending') "
        "AND price_set_by IS NULL AND price_set_at IS NULL) OR "
        "(price_status = 'set' "
        "AND price_set_by IS NOT NULL AND price_set_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_se_application_items_price_status_amounts",
        "special_equipment_application_items",
        "price_status = 'none' OR "
        "(item_role <> 'component' AND unit_price > 0 AND total_price > 0)",
    )

    op.create_table(
        "special_equipment_price_change_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("old_price", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("new_price", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "new_price > 0",
            name="ck_se_price_change_log_new_price_positive",
        ),
        sa.CheckConstraint(
            "source IN ('dealer_ui', 'api')",
            name="ck_se_price_change_log_source",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["special_equipment_application_items.id"],
            name="fk_se_price_change_log_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name="fk_se_price_change_log_changed_by",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_price_change_log"),
    )
    op.create_index(
        "idx_se_price_change_log_item_changed",
        "special_equipment_price_change_log",
        ["item_id", sa.text("changed_at DESC"), "id"],
    )
    op.create_index(
        "idx_se_price_change_log_changed_by",
        "special_equipment_price_change_log",
        ["changed_by", sa.text("changed_at DESC")],
    )


def downgrade() -> None:
    """Remove only the request-price schema introduced by this revision."""

    op.drop_index(
        "idx_se_price_change_log_changed_by",
        table_name="special_equipment_price_change_log",
    )
    op.drop_index(
        "idx_se_price_change_log_item_changed",
        table_name="special_equipment_price_change_log",
    )
    op.drop_table("special_equipment_price_change_log")

    for constraint_name in (
        "ck_se_application_items_price_status_amounts",
        "ck_se_application_items_price_status_consistency",
        "ck_se_application_items_price_status",
    ):
        op.drop_constraint(
            constraint_name,
            "special_equipment_application_items",
            type_="check",
        )
    op.drop_constraint(
        "fk_se_application_items_price_set_by",
        "special_equipment_application_items",
        type_="foreignkey",
    )
    op.drop_column("special_equipment_application_items", "price_set_at")
    op.drop_column("special_equipment_application_items", "price_set_by")
    op.drop_column("special_equipment_application_items", "price_status")

    op.drop_index(
        "idx_se_products_effective_price_published",
        table_name="special_equipment_products",
    )
    for constraint_name in (
        "ck_special_equipment_products_claimed_price",
        "ck_special_equipment_products_on_order_price",
        "ck_se_products_price_mode_valid",
        "ck_se_products_price_from_valid",
        "ck_special_equipment_products_price_nonnegative",
    ):
        op.drop_constraint(
            constraint_name,
            "special_equipment_products",
            type_="check",
        )
    op.create_check_constraint(
        "ck_special_equipment_products_price_nonnegative",
        "special_equipment_products",
        "price IS NULL OR price >= 0",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_on_order_price",
        "special_equipment_products",
        "sale_status <> 'on_order' OR price > 0",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_claimed_price",
        "special_equipment_products",
        "sale_status NOT IN ('reserved', 'sold') OR price IS NOT NULL",
    )
    op.drop_column("special_equipment_products", "price_from")
    op.drop_column("special_equipment_products", "price_on_request")
    op.create_index(
        "idx_se_products_effective_price_published",
        "special_equipment_products",
        [sa.text("COALESCE(special_price, price)"), "id"],
        postgresql_where=sa.text("publication_status = 'published'"),
    )
