"""Kit superstructure source product reference and synchronization triggers.

Revision ID: 153
Revises: 152
Create Date: 2026-10-01 00:05:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "153"
down_revision = "152"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. special_equipment_products: add superstructure_source_product_id & index
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "superstructure_source_product_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "special_equipment_products.id",
                name="fk_se_products_superstructure_source",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_se_products_superstructure_source",
        "special_equipment_products",
        ["superstructure_source_product_id"],
        postgresql_where=sa.text("superstructure_source_product_id IS NOT NULL"),
    )

    # 2. Check constraints
    op.create_check_constraint(
        "ck_se_products_superstructure_source_not_self",
        "special_equipment_products",
        "superstructure_source_product_id IS NULL OR superstructure_source_product_id <> id",
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
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> ''
           AND superstructure_model_id IS NOT NULL)
        """,
    )

    # 3. DB triggers and sync functions
    op.execute(
        """
        CREATE OR REPLACE FUNCTION se_sync_kit_superstructure_source()
        RETURNS TRIGGER AS $$
        DECLARE
            v_model_id UUID;
            v_mod_id UUID;
            v_super_name VARCHAR(255);
            v_super_manuf VARCHAR(255);
        BEGIN
            SELECT
                m.id,
                p.modification_id,
                m.name,
                mk.name
            INTO
                v_model_id,
                v_mod_id,
                v_super_name,
                v_super_manuf
            FROM special_equipment_products p
            JOIN special_equipment_modifications modif ON modif.id = p.modification_id
            JOIN special_equipment_models m ON m.id = modif.model_id
            JOIN special_equipment_marks mk ON mk.id = m.mark_id
            WHERE p.id = NEW.superstructure_source_product_id;

            IF FOUND THEN
                NEW.superstructure_model_id := v_model_id;
                NEW.superstructure_modification_id := v_mod_id;
                NEW.superstructure_name := v_super_name;
                NEW.superstructure_manufacturer := v_super_manuf;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_se_products_kit_source_fill
        BEFORE INSERT OR UPDATE OF superstructure_source_product_id, superstructure_name, superstructure_manufacturer, superstructure_model_id, superstructure_modification_id
        ON special_equipment_products
        FOR EACH ROW
        WHEN (NEW.superstructure_source_product_id IS NOT NULL)
        EXECUTE FUNCTION se_sync_kit_superstructure_source();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION se_propagate_kit_source_product()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.modification_id IS DISTINCT FROM NEW.modification_id THEN
                UPDATE special_equipment_products
                SET superstructure_source_product_id = superstructure_source_product_id
                WHERE superstructure_source_product_id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_se_products_kit_source_propagate
        AFTER UPDATE OF modification_id
        ON special_equipment_products
        FOR EACH ROW
        EXECUTE FUNCTION se_propagate_kit_source_product();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION se_propagate_kit_source_model()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.name IS DISTINCT FROM NEW.name OR OLD.mark_id IS DISTINCT FROM NEW.mark_id THEN
                UPDATE special_equipment_products
                SET superstructure_source_product_id = superstructure_source_product_id
                WHERE superstructure_source_product_id IN (
                    SELECT p.id
                    FROM special_equipment_products p
                    JOIN special_equipment_modifications modif ON modif.id = p.modification_id
                    WHERE modif.model_id = NEW.id
                );
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_se_models_kit_source_propagate
        AFTER UPDATE OF name, mark_id
        ON special_equipment_models
        FOR EACH ROW
        EXECUTE FUNCTION se_propagate_kit_source_model();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION se_propagate_kit_source_mark()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.name IS DISTINCT FROM NEW.name THEN
                UPDATE special_equipment_products
                SET superstructure_source_product_id = superstructure_source_product_id
                WHERE superstructure_source_product_id IN (
                    SELECT p.id
                    FROM special_equipment_products p
                    JOIN special_equipment_modifications modif ON modif.id = p.modification_id
                    JOIN special_equipment_models m ON m.id = modif.model_id
                    WHERE m.mark_id = NEW.id
                );
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_se_marks_kit_source_propagate
        AFTER UPDATE OF name
        ON special_equipment_marks
        FOR EACH ROW
        EXECUTE FUNCTION se_propagate_kit_source_mark();
        """
    )


def downgrade() -> None:
    # 1. Drop propagation and sync triggers & functions
    op.execute("DROP TRIGGER IF EXISTS trg_se_marks_kit_source_propagate ON special_equipment_marks;")
    op.execute("DROP FUNCTION IF EXISTS se_propagate_kit_source_mark();")
    op.execute("DROP TRIGGER IF EXISTS trg_se_models_kit_source_propagate ON special_equipment_models;")
    op.execute("DROP FUNCTION IF EXISTS se_propagate_kit_source_model();")
    op.execute("DROP TRIGGER IF EXISTS trg_se_products_kit_source_propagate ON special_equipment_products;")
    op.execute("DROP FUNCTION IF EXISTS se_propagate_kit_source_product();")
    op.execute("DROP TRIGGER IF EXISTS trg_se_products_kit_source_fill ON special_equipment_products;")
    op.execute("DROP FUNCTION IF EXISTS se_sync_kit_superstructure_source();")

    # 2. Revert ck_se_products_kind
    op.drop_constraint("ck_se_products_kind", "special_equipment_products", type_="check")
    op.create_check_constraint(
        "ck_se_products_kind",
        "special_equipment_products",
        """
        (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL
           AND superstructure_model_id IS NULL)
        OR
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> ''
           AND superstructure_model_id IS NOT NULL)
        """,
    )

    # 3. Drop check constraint, index, column
    op.drop_constraint(
        "ck_se_products_superstructure_source_not_self",
        "special_equipment_products",
        type_="check",
    )
    op.drop_index(
        "idx_se_products_superstructure_source",
        table_name="special_equipment_products",
    )
    op.drop_column("special_equipment_products", "superstructure_source_product_id")
