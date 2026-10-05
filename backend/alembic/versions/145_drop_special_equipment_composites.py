"""Drop special equipment composites.

Revision ID: 145
Revises: 144
Create Date: 2026-09-30 11:00:00
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger("alembic.runtime.migration")

revision = "145"
down_revision = "144"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. composite_ids = SELECT DISTINCT composite_product_id FROM special_equipment_product_components
    composite_rows = conn.execute(
        sa.text(
            "SELECT DISTINCT composite_product_id FROM special_equipment_product_components"
        )
    ).fetchall()
    composite_ids = [row[0] for row in composite_rows]

    archived_count = 0
    deleted_count = 0

    if composite_ids:
        # 2. history_ids = composite_ids referenced by application_items, purchase_orders, or order_items
        history_rows = conn.execute(
            sa.text(
                """
                SELECT DISTINCT p.id
                FROM special_equipment_products p
                WHERE p.id = ANY(:c_ids)
                  AND (
                    EXISTS (
                        SELECT 1 FROM special_equipment_application_items ai
                        WHERE ai.product_id = p.id
                    )
                    OR EXISTS (
                        SELECT 1 FROM special_equipment_purchase_orders po
                        WHERE po.product_id = p.id
                    )
                    OR EXISTS (
                        SELECT 1 FROM special_equipment_order_items oi
                        WHERE oi.product_id = p.id
                    )
                  )
                """
            ),
            {"c_ids": composite_ids},
        ).fetchall()
        history_ids = [row[0] for row in history_rows]
        remaining_ids = [pid for pid in composite_ids if pid not in set(history_ids)]

        # 3. For history_ids: archive, remove from carts
        if history_ids:
            conn.execute(
                sa.text(
                    """
                    UPDATE special_equipment_products
                    SET publication_status = 'archived',
                        sale_status = 'unavailable',
                        updated_at = NOW()
                    WHERE id = ANY(:h_ids)
                    """
                ),
                {"h_ids": history_ids},
            )
            conn.execute(
                sa.text(
                    """
                    DELETE FROM special_equipment_cart_items
                    WHERE product_id = ANY(:h_ids)
                       OR parent_item_id IN (
                           SELECT id FROM special_equipment_cart_items
                           WHERE product_id = ANY(:h_ids)
                       )
                    """
                ),
                {"h_ids": history_ids},
            )
            archived_count = len(history_ids)

        # 4. For remaining composite_ids:
        if remaining_ids:
            # a) Delete from carts
            conn.execute(
                sa.text(
                    """
                    DELETE FROM special_equipment_cart_items
                    WHERE product_id = ANY(:r_ids)
                       OR parent_item_id IN (
                           SELECT id FROM special_equipment_cart_items
                           WHERE product_id = ANY(:r_ids)
                       )
                    """
                ),
                {"r_ids": remaining_ids},
            )
            # b) Delete attachment links if any
            conn.execute(
                sa.text(
                    """
                    DELETE FROM special_equipment_product_attachments
                    WHERE product_id = ANY(:r_ids)
                       OR attachment_product_id = ANY(:r_ids)
                    """
                ),
                {"r_ids": remaining_ids},
            )
            # c) Enqueue images for media cleanup
            conn.execute(
                sa.text(
                    """
                    INSERT INTO special_equipment_media_cleanup_jobs (
                        id, storage_key, status, attempt_count, next_attempt_at, created_at, updated_at
                    )
                    SELECT
                        gen_random_uuid(),
                        storage_key,
                        'pending',
                        0,
                        NOW(),
                        NOW(),
                        NOW()
                    FROM special_equipment_product_images
                    WHERE product_id = ANY(:r_ids)
                      AND storage_key IS NOT NULL
                      AND storage_key <> ''
                    ON CONFLICT (storage_key) DO NOTHING
                    """
                ),
                {"r_ids": remaining_ids},
            )
            # d) Log deletion in special_equipment_catalog_deletion_log
            prod_rows = conn.execute(
                sa.text(
                    """
                    SELECT id, code, title
                    FROM special_equipment_products
                    WHERE id = ANY(:r_ids)
                    """
                ),
                {"r_ids": remaining_ids},
            ).fetchall()
            for prod in prod_rows:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO special_equipment_catalog_deletion_log (
                            id, created_at, user_id, root_type, root_id, root_code, root_name,
                            catalog_revision, counts, items
                        ) VALUES (
                            gen_random_uuid(), NOW(), NULL, 'product', :root_id, :root_code, :root_name,
                            1, '{"action": "composite_removed"}'::jsonb, '[]'::jsonb
                        )
                        """
                    ),
                    {
                        "root_id": prod[0],
                        "root_code": prod[1],
                        "root_name": prod[2],
                    },
                )
            # e) Delete from special_equipment_product_components before deleting products
            conn.execute(
                sa.text(
                    """
                    DELETE FROM special_equipment_product_components
                    WHERE composite_product_id = ANY(:r_ids)
                       OR component_product_id = ANY(:r_ids)
                    """
                ),
                {"r_ids": remaining_ids},
            )
            # f) Delete products (cascade handles images, categories, overrides, favorites, card_attributes, etc.)
            conn.execute(
                sa.text(
                    "DELETE FROM special_equipment_products WHERE id = ANY(:r_ids)"
                ),
                {"r_ids": remaining_ids},
            )
            deleted_count = len(remaining_ids)

    logger.info(
        "Dropped composites migration: %d archived, %d deleted",
        archived_count,
        deleted_count,
    )

    # 5. DROP TABLE special_equipment_product_components
    op.drop_table("special_equipment_product_components")

    # 6. Drop has_own_categories column
    op.drop_column("special_equipment_products", "has_own_categories")


def downgrade() -> None:
    # 1. Re-add has_own_categories
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "has_own_categories",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # 2. Re-create special_equipment_product_components
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
