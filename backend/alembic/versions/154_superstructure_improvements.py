"""Superstructure improvements: model category, superstructure categories, vin fields.

Revision ID: 154
Revises: 153
Create Date: 2026-10-01 14:07:46
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "154"
down_revision = "153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. special_equipment_categories: add is_visible_in_catalog & index
    op.add_column(
        "special_equipment_categories",
        sa.Column(
            "is_visible_in_catalog",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_index(
        "idx_se_categories_visible",
        "special_equipment_categories",
        ["is_visible_in_catalog"],
    )

    # 2. special_equipment_models: add category_id, fk, index, and backfill
    op.add_column(
        "special_equipment_models",
        sa.Column(
            "category_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_special_equipment_models_category",
        "special_equipment_models",
        "special_equipment_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
    )
    op.create_index(
        "idx_special_equipment_models_category",
        "special_equipment_models",
        ["category_id"],
    )

    # Backfill category_id for existing models
    op.execute(
        """
        UPDATE special_equipment_models m
        SET category_id = sub.category_id
        FROM (
            SELECT DISTINCT ON (modif.model_id)
                modif.model_id,
                mc.category_id
            FROM special_equipment_modifications modif
            JOIN special_equipment_modification_categories mc ON mc.modification_id = modif.id
            ORDER BY modif.model_id, mc.is_primary DESC, mc.sort_order ASC, mc.category_id ASC
        ) sub
        WHERE m.id = sub.model_id AND m.category_id IS NULL;
        """
    )

    # 3. special_equipment_superstructure_categories: create junction table
    op.create_table(
        "special_equipment_superstructure_categories",
        sa.Column(
            "superstructure_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "special_equipment_superstructures.id",
                name="fk_se_superstructure_categories_superstructure",
                ondelete="CASCADE",
                onupdate="CASCADE",
            ),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "category_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "special_equipment_categories.id",
                name="fk_se_superstructure_categories_category",
                ondelete="RESTRICT",
                onupdate="CASCADE",
            ),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index(
        "idx_se_superstructure_categories_category",
        "special_equipment_superstructure_categories",
        ["category_id"],
    )

    # 4. special_equipment_products: add chassis_vin & superstructure_vin
    op.add_column(
        "special_equipment_products",
        sa.Column("chassis_vin", sa.String(32), nullable=True),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column("superstructure_vin", sa.String(32), nullable=True),
    )

    # 5. special_equipment_products: update check constraints
    op.drop_constraint(
        "ck_special_equipment_products_vin_choice",
        "special_equipment_products",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_vin_choice",
        "special_equipment_products",
        """
        (no_vin AND vin IS NULL AND chassis_vin IS NULL AND superstructure_vin IS NULL)
        OR
        (NOT no_vin AND vin IS NOT NULL AND btrim(vin) <> '' AND char_length(vin) <= 32)
        """,
    )

    op.drop_constraint("ck_se_products_kind", "special_equipment_products", type_="check")
    op.create_check_constraint(
        "ck_se_products_kind",
        "special_equipment_products",
        """
        (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
           AND superstructure_model_id IS NULL
           AND superstructure_source_product_id IS NULL)
        OR
        (superstructure_id IS NOT NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
           AND superstructure_model_id IS NULL
           AND superstructure_source_product_id IS NULL)
        OR
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> ''
           AND (no_vin OR (chassis_vin IS NOT NULL AND btrim(chassis_vin) <> '')))
        """,
    )


def downgrade() -> None:
    # 1. Revert check constraints
    op.drop_constraint("ck_se_products_kind", "special_equipment_products", type_="check")
    op.create_check_constraint(
        "ck_se_products_kind",
        "special_equipment_products",
        """
        (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
           AND superstructure_model_id IS NULL
           AND superstructure_source_product_id IS NULL)
        OR
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> ''
           AND superstructure_model_id IS NOT NULL)
        """,
    )

    op.drop_constraint(
        "ck_special_equipment_products_vin_choice",
        "special_equipment_products",
        type_="check",
    )
    op.create_check_constraint(
        "ck_special_equipment_products_vin_choice",
        "special_equipment_products",
        """
        (no_vin AND vin IS NULL)
        OR
        (NOT no_vin AND vin IS NOT NULL AND btrim(vin) <> '' AND char_length(vin) <= 17)
        """,
    )

    # 2. Drop columns from special_equipment_products
    op.drop_column("special_equipment_products", "superstructure_vin")
    op.drop_column("special_equipment_products", "chassis_vin")

    # 3. Drop table special_equipment_superstructure_categories
    op.drop_index(
        "idx_se_superstructure_categories_category",
        table_name="special_equipment_superstructure_categories",
    )
    op.drop_table("special_equipment_superstructure_categories")

    # 4. Drop category_id from special_equipment_models
    op.drop_index(
        "idx_special_equipment_models_category",
        table_name="special_equipment_models",
    )
    op.drop_constraint(
        "fk_special_equipment_models_category",
        "special_equipment_models",
        type_="foreignkey",
    )
    op.drop_column("special_equipment_models", "category_id")

    # 5. Drop is_visible_in_catalog from special_equipment_categories
    op.drop_index(
        "idx_se_categories_visible",
        table_name="special_equipment_categories",
    )
    op.drop_column("special_equipment_categories", "is_visible_in_catalog")
