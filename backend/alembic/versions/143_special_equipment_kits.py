"""Special equipment kits and superstructures directory.

Revision ID: 143
Revises: 142
Create Date: 2026-09-29 15:14:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "143"
down_revision = "142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. special_equipment_modifications: UNIQUE (id, model_id) for composite FK
    op.create_unique_constraint(
        "uq_special_equipment_modifications_id_model",
        "special_equipment_modifications",
        ["id", "model_id"],
    )

    # 2. special_equipment_superstructures
    op.create_table(
        "special_equipment_superstructures",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "lock_version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "model_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "modification_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["modification_id", "model_id"],
            [
                "special_equipment_modifications.id",
                "special_equipment_modifications.model_id",
            ],
            name="fk_se_superstructures_modification_model",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "lock_version >= 1",
            name="ck_special_equipment_superstructures_lock_version",
        ),
    )
    op.create_unique_constraint(
        "uq_special_equipment_superstructures_code",
        "special_equipment_superstructures",
        ["code"],
    )
    op.create_index(
        "uq_se_superstructures_code",
        "special_equipment_superstructures",
        [sa.text("lower(btrim(code))")],
        unique=True,
    )
    op.create_index(
        "uq_se_superstructures_model_mod_name",
        "special_equipment_superstructures",
        [
            "model_id",
            sa.text(
                "coalesce(modification_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.text("lower(btrim(name))"),
        ],
        unique=True,
    )
    op.create_index(
        "uq_se_superstructures_model_mod_slug",
        "special_equipment_superstructures",
        [
            "model_id",
            sa.text(
                "coalesce(modification_id, '00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            sa.text("lower(btrim(slug))"),
        ],
        unique=True,
    )
    op.create_index(
        "idx_se_superstructures_model_mod_active_name",
        "special_equipment_superstructures",
        ["model_id", "modification_id", "is_active", "name", "id"],
    )

    # 3. special_equipment_superstructure_attributes
    op.create_table(
        "special_equipment_superstructure_attributes",
        sa.Column(
            "superstructure_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_superstructures.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "attribute_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_attributes.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "group_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey(
                "special_equipment_attribute_groups.id", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column(
            "is_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_filterable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_se_superstructure_attributes_sort_order",
        ),
    )

    # 4. special_equipment_products alterations
    op.alter_column(
        "special_equipment_products",
        "modification_id",
        nullable=True,
    )
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "model_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "superstructure_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_superstructures.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column(
            "superstructure_modification_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_modifications.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column("superstructure_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "special_equipment_products",
        sa.Column("superstructure_manufacturer", sa.String(255), nullable=True),
    )
    op.create_foreign_key(
        "fk_se_products_modification_model",
        "special_equipment_products",
        "special_equipment_modifications",
        ["modification_id", "model_id"],
        ["id", "model_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_special_equipment_products_id_superstructure",
        "special_equipment_products",
        ["id", "superstructure_id"],
    )
    op.create_check_constraint(
        "ck_se_products_kind",
        "special_equipment_products",
        """
        (superstructure_id IS NULL AND modification_id IS NOT NULL AND model_id IS NULL
           AND superstructure_modification_id IS NULL
           AND superstructure_name IS NULL AND superstructure_manufacturer IS NULL)
        OR
        (superstructure_id IS NOT NULL AND model_id IS NOT NULL AND trim_id IS NULL
           AND superstructure_name IS NOT NULL AND btrim(superstructure_name) <> ''
           AND superstructure_manufacturer IS NOT NULL AND btrim(superstructure_manufacturer) <> '')
        """,
    )
    op.create_index(
        "idx_se_products_superstructure",
        "special_equipment_products",
        ["superstructure_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_se_products_model",
        "special_equipment_products",
        ["model_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )

    # 5. special_equipment_product_chassis_values
    op.create_table(
        "special_equipment_product_chassis_values",
        sa.Column(
            "product_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "attribute_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("special_equipment_attributes.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "option_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("value_number", sa.Numeric(20, 4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["attribute_id", "option_id"],
            [
                "special_equipment_attribute_options.attribute_id",
                "special_equipment_attribute_options.id",
            ],
            name="fk_se_product_chassis_values_option_attribute",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_product_chassis_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_product_chassis_values_text_size",
        ),
    )
    op.create_index(
        "idx_se_product_chassis_values_number",
        "special_equipment_product_chassis_values",
        ["attribute_id", "value_number", "product_id"],
        postgresql_where=sa.text("value_number IS NOT NULL"),
    )
    op.create_index(
        "idx_se_product_chassis_values_option",
        "special_equipment_product_chassis_values",
        ["attribute_id", "option_id", "product_id"],
        postgresql_where=sa.text("option_id IS NOT NULL"),
    )
    op.create_index(
        "idx_se_product_chassis_values_text_search",
        "special_equipment_product_chassis_values",
        [sa.text("lower(value_text)")],
        postgresql_using="gin",
        postgresql_ops={"lower(value_text)": "gin_trgm_ops"},
        postgresql_where=sa.text("value_text IS NOT NULL"),
    )

    # 6. special_equipment_product_superstructure_values
    op.create_table(
        "special_equipment_product_superstructure_values",
        sa.Column(
            "product_id",
            PGUUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "attribute_id",
            PGUUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "superstructure_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "option_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("value_number", sa.Numeric(20, 4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id", "superstructure_id"],
            [
                "special_equipment_products.id",
                "special_equipment_products.superstructure_id",
            ],
            name="fk_se_product_superstructure_values_product",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superstructure_id", "attribute_id"],
            [
                "special_equipment_superstructure_attributes.superstructure_id",
                "special_equipment_superstructure_attributes.attribute_id",
            ],
            name="fk_se_product_superstructure_values_assignment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id", "option_id"],
            [
                "special_equipment_attribute_options.attribute_id",
                "special_equipment_attribute_options.id",
            ],
            name="fk_se_product_superstructure_values_option_attribute",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1",
            name="ck_se_product_superstructure_values_one_value",
        ),
        sa.CheckConstraint(
            "value_text IS NULL OR octet_length(value_text) <= 2000",
            name="ck_se_product_superstructure_values_text_size",
        ),
    )
    op.create_index(
        "idx_se_product_superstructure_values_number",
        "special_equipment_product_superstructure_values",
        ["attribute_id", "value_number", "product_id"],
        postgresql_where=sa.text("value_number IS NOT NULL"),
    )
    op.create_index(
        "idx_se_product_superstructure_values_option",
        "special_equipment_product_superstructure_values",
        ["attribute_id", "option_id", "product_id"],
        postgresql_where=sa.text("option_id IS NOT NULL"),
    )
    op.create_index(
        "idx_se_product_superstructure_values_text_search",
        "special_equipment_product_superstructure_values",
        [sa.text("lower(value_text)")],
        postgresql_using="gin",
        postgresql_ops={"lower(value_text)": "gin_trgm_ops"},
        postgresql_where=sa.text("value_text IS NOT NULL"),
    )


def downgrade() -> None:
    # 1. Drop value tables
    op.drop_table("special_equipment_product_superstructure_values")
    op.drop_table("special_equipment_product_chassis_values")

    # 2. Products alterations revert
    op.drop_index("idx_se_products_model", table_name="special_equipment_products")
    op.drop_index(
        "idx_se_products_superstructure", table_name="special_equipment_products"
    )
    op.drop_constraint(
        "ck_se_products_kind", "special_equipment_products", type_="check"
    )
    op.drop_constraint(
        "uq_special_equipment_products_id_superstructure",
        "special_equipment_products",
        type_="unique",
    )
    op.drop_constraint(
        "fk_se_products_modification_model",
        "special_equipment_products",
        type_="foreignkey",
    )

    # Check that no products have modification_id IS NULL before making it NOT NULL
    bind = op.get_bind()
    null_mod_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM special_equipment_products WHERE modification_id IS NULL"
        )
    ).scalar()
    if null_mod_count:
        raise RuntimeError(
            f"Cannot downgrade migration 141: found {null_mod_count} products with modification_id IS NULL"
        )

    op.alter_column(
        "special_equipment_products",
        "modification_id",
        nullable=False,
    )
    op.drop_column("special_equipment_products", "superstructure_manufacturer")
    op.drop_column("special_equipment_products", "superstructure_name")
    op.drop_column("special_equipment_products", "superstructure_modification_id")
    op.drop_column("special_equipment_products", "superstructure_id")
    op.drop_column("special_equipment_products", "model_id")

    # 3. Drop superstructure attributes table
    op.drop_table("special_equipment_superstructure_attributes")

    # 4. Drop superstructures table
    op.drop_table("special_equipment_superstructures")

    # 5. Drop modification composite unique constraint
    op.drop_constraint(
        "uq_special_equipment_modifications_id_model",
        "special_equipment_modifications",
        type_="unique",
    )
