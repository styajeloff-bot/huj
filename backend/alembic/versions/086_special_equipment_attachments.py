"""Add special-equipment attachments, composites, and grouped commerce.

Revision ID: 086
Revises: 085
Create Date: 2026-08-05
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "086"
down_revision: str | None = "085"
branch_labels: str | None = None
depends_on: str | None = None


def _add_attachment_catalog_schema() -> None:
    op.add_column(
        "special_equipment_categories",
        sa.Column(
            "is_attachment_category",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_se_categories_attachment",
        "special_equipment_categories",
        ["id"],
        postgresql_where=sa.text("is_attachment_category"),
    )

    op.create_table(
        "special_equipment_product_attachments",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attachment_product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "position",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "product_id <> attachment_product_id",
            name="ck_se_product_attachments_not_self",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_se_product_attachments_position_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            name="fk_se_product_attachments_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_product_id"],
            ["special_equipment_products.id"],
            name="fk_se_product_attachments_attachment_product",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_se_product_attachments_created_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "product_id",
            "attachment_product_id",
            name="pk_special_equipment_product_attachments",
        ),
        sa.UniqueConstraint(
            "product_id",
            "position",
            name="uq_se_product_attachments_product_position",
        ),
    )
    op.create_index(
        "idx_se_product_attachments_attachment",
        "special_equipment_product_attachments",
        ["attachment_product_id", "product_id"],
    )

    op.create_table(
        "special_equipment_product_components",
        sa.Column(
            "composite_product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "component_product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "position",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_base",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "composite_product_id <> component_product_id",
            name="ck_se_product_components_not_self",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_se_product_components_position_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["composite_product_id"],
            ["special_equipment_products.id"],
            name="fk_se_product_components_composite_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["component_product_id"],
            ["special_equipment_products.id"],
            name="fk_se_product_components_component_product",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "composite_product_id",
            "component_product_id",
            name="pk_special_equipment_product_components",
        ),
        sa.UniqueConstraint(
            "composite_product_id",
            "position",
            name="uq_se_product_components_composite_position",
        ),
    )
    op.create_index(
        "idx_se_product_components_component",
        "special_equipment_product_components",
        ["component_product_id", "composite_product_id"],
    )
    op.create_index(
        "uq_se_product_components_single_base",
        "special_equipment_product_components",
        ["composite_product_id"],
        unique=True,
        postgresql_where=sa.text("is_base"),
    )


def _add_grouped_cart_schema() -> None:
    op.create_table(
        "special_equipment_guest_cart_transfers",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(request_hash) = 64",
            name="ck_se_guest_cart_transfers_request_hash",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_se_guest_cart_transfers_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "transfer_id",
            name="pk_special_equipment_guest_cart_transfers",
        ),
    )

    op.add_column(
        "special_equipment_cart_items",
        sa.Column(
            "quantity",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "special_equipment_cart_items",
        sa.Column(
            "parent_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_cart_items",
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_se_cart_items_quantity_positive",
        "special_equipment_cart_items",
        "quantity > 0",
    )
    op.create_foreign_key(
        "fk_se_cart_items_parent",
        "special_equipment_cart_items",
        "special_equipment_cart_items",
        ["parent_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "uq_special_equipment_cart_user_product",
        "special_equipment_cart_items",
        type_="unique",
    )
    op.create_index(
        "uq_special_equipment_cart_user_product",
        "special_equipment_cart_items",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("parent_item_id IS NULL"),
    )
    op.create_index(
        "uq_se_cart_items_child_product",
        "special_equipment_cart_items",
        ["parent_item_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("parent_item_id IS NOT NULL"),
    )
    op.create_index(
        "idx_se_cart_items_parent",
        "special_equipment_cart_items",
        ["parent_item_id"],
    )


def _add_grouped_commerce_documents() -> None:
    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "source_cart_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "parent_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_application_items",
        sa.Column(
            "item_role",
            sa.String(20),
            server_default=sa.text("'offer'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_se_application_items_role",
        "special_equipment_application_items",
        "item_role IN ('offer', 'attachment', 'component')",
    )

    op.create_table(
        "special_equipment_order_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_cart_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "parent_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "item_role",
            sa.String(20),
            server_default=sa.text("'offer'"),
            nullable=False,
        ),
        sa.Column(
            "position",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=False),
        sa.Column("item_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "item_role IN ('offer', 'attachment', 'component')",
            name="ck_se_order_items_role",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_se_order_items_position_nonnegative",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_se_order_items_unit_price_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["special_equipment_purchase_orders.id"],
            name="fk_se_order_items_purchase_order",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["special_equipment_products.id"],
            name="fk_se_order_items_product",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_special_equipment_order_items"),
        sa.UniqueConstraint(
            "purchase_order_id",
            "product_id",
            name="uq_se_order_items_order_product",
        ),
    )
    op.create_index(
        "idx_se_order_items_order_position",
        "special_equipment_order_items",
        ["purchase_order_id", "position", "id"],
    )
    op.create_index(
        "idx_se_order_items_product",
        "special_equipment_order_items",
        ["product_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO special_equipment_order_items (
                id,
                purchase_order_id,
                product_id,
                source_cart_item_id,
                group_id,
                parent_group_id,
                item_role,
                position,
                unit_price,
                item_snapshot,
                created_at
            )
            SELECT
                gen_random_uuid(),
                id,
                product_id,
                NULL,
                gen_random_uuid(),
                NULL,
                'offer',
                0,
                unit_price,
                item_snapshot,
                created_at
            FROM special_equipment_purchase_orders
            """
        )
    )


def upgrade() -> None:
    _add_attachment_catalog_schema()
    _add_grouped_cart_schema()
    _add_grouped_commerce_documents()


def _guard_lossless_downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_categories
                    WHERE is_attachment_category
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 086: attachment categories exist';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM special_equipment_product_attachments
                ) OR EXISTS (
                    SELECT 1 FROM special_equipment_product_components
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 086: product attachment data exists';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM special_equipment_guest_cart_transfers
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 086: guest cart receipts exist';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_cart_items
                    WHERE quantity <> 1
                       OR parent_item_id IS NOT NULL
                       OR transfer_id IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 086: grouped cart data exists';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_application_items
                    WHERE source_cart_item_id IS NOT NULL
                       OR parent_group_id IS NOT NULL
                       OR item_role <> 'offer'
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 086: grouped application data exists';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM special_equipment_order_items AS item
                    JOIN special_equipment_purchase_orders AS purchase_order
                      ON purchase_order.id = item.purchase_order_id
                    WHERE item.product_id <> purchase_order.product_id
                       OR item.source_cart_item_id IS NOT NULL
                       OR item.parent_group_id IS NOT NULL
                       OR item.item_role <> 'offer'
                       OR item.position <> 0
                       OR item.unit_price <> purchase_order.unit_price
                       OR item.item_snapshot <> purchase_order.item_snapshot
                ) OR EXISTS (
                    SELECT purchase_order_id
                    FROM special_equipment_order_items
                    GROUP BY purchase_order_id
                    HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Cannot downgrade 086: grouped order data exists';
                END IF;
            END $$
            """
        )
    )


def _drop_grouped_commerce_documents() -> None:
    op.drop_index(
        "idx_se_order_items_product",
        table_name="special_equipment_order_items",
    )
    op.drop_index(
        "idx_se_order_items_order_position",
        table_name="special_equipment_order_items",
    )
    op.drop_table("special_equipment_order_items")
    op.drop_constraint(
        "ck_se_application_items_role",
        "special_equipment_application_items",
        type_="check",
    )
    op.drop_column("special_equipment_application_items", "item_role")
    op.drop_column("special_equipment_application_items", "parent_group_id")
    op.drop_column("special_equipment_application_items", "group_id")
    op.drop_column("special_equipment_application_items", "source_cart_item_id")


def _drop_grouped_cart_schema() -> None:
    op.drop_index(
        "idx_se_cart_items_parent",
        table_name="special_equipment_cart_items",
    )
    op.drop_index(
        "uq_se_cart_items_child_product",
        table_name="special_equipment_cart_items",
    )
    op.drop_index(
        "uq_special_equipment_cart_user_product",
        table_name="special_equipment_cart_items",
    )
    op.create_unique_constraint(
        "uq_special_equipment_cart_user_product",
        "special_equipment_cart_items",
        ["user_id", "product_id"],
    )
    op.drop_constraint(
        "fk_se_cart_items_parent",
        "special_equipment_cart_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_se_cart_items_quantity_positive",
        "special_equipment_cart_items",
        type_="check",
    )
    op.drop_column("special_equipment_cart_items", "transfer_id")
    op.drop_column("special_equipment_cart_items", "parent_item_id")
    op.drop_column("special_equipment_cart_items", "quantity")
    op.drop_table("special_equipment_guest_cart_transfers")


def _drop_attachment_catalog_schema() -> None:
    op.drop_index(
        "uq_se_product_components_single_base",
        table_name="special_equipment_product_components",
    )
    op.drop_index(
        "idx_se_product_components_component",
        table_name="special_equipment_product_components",
    )
    op.drop_table("special_equipment_product_components")
    op.drop_index(
        "idx_se_product_attachments_attachment",
        table_name="special_equipment_product_attachments",
    )
    op.drop_table("special_equipment_product_attachments")
    op.drop_index(
        "idx_se_categories_attachment",
        table_name="special_equipment_categories",
    )
    op.drop_column(
        "special_equipment_categories",
        "is_attachment_category",
    )


def downgrade() -> None:
    _guard_lossless_downgrade()
    _drop_grouped_commerce_documents()
    _drop_grouped_cart_schema()
    _drop_attachment_catalog_schema()
