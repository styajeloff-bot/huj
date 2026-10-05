"""Add warehouse_access_rules and update warehouses schema.

Revision ID: 128
Revises: 127
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "128"
down_revision: str | None = "127"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add new columns to warehouses as nullable initially for backfill
    op.add_column("warehouses", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column(
        "warehouses",
        sa.Column("owner_company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "warehouses",
        sa.Column("owner_company_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "warehouses",
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "warehouses",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )

    # 2. Backfill existing warehouses data
    # 2.1 Name: COALESCE(brand - address, Склад address)
    conn.execute(
        sa.text("""
            UPDATE warehouses
            SET name = COALESCE(NULLIF(TRIM(brand), '') || ' - ' || address, 'Склад ' || address)
            WHERE name IS NULL
        """)
    )

    # 2.2 Owner company ID & type from company_id / dealer_id and companies table
    conn.execute(
        sa.text("""
            UPDATE warehouses w
            SET owner_company_id = COALESCE(w.company_id, w.dealer_id),
                owner_company_type = CASE
                    WHEN c.company_type IN ('dealer', 'distributor') THEN c.company_type
                    ELSE 'dealer'
                END
            FROM companies c
            WHERE c.id = COALESCE(w.company_id, w.dealer_id)
              AND w.owner_company_id IS NULL
        """)
    )

    # Fallback if any warehouse had both company_id and dealer_id NULL
    conn.execute(
        sa.text("""
            UPDATE warehouses w
            SET owner_company_id = (SELECT id FROM companies WHERE company_type IN ('dealer', 'distributor') LIMIT 1),
                owner_company_type = (SELECT company_type FROM companies WHERE company_type IN ('dealer', 'distributor') LIMIT 1)
            WHERE w.owner_company_id IS NULL
        """)
    )

    # 2.3 Brand ID matching special_equipment_marks
    conn.execute(
        sa.text("""
            UPDATE warehouses w
            SET brand_id = m.id
            FROM special_equipment_marks m
            WHERE lower(trim(w.brand)) = lower(trim(m.name))
              AND w.brand_id IS NULL
        """)
    )

    # 2.4 is_active from status
    conn.execute(
        sa.text("""
            UPDATE warehouses
            SET is_active = (status = 'active')
        """)
    )

    # 3. Alter columns to NOT NULL
    op.alter_column("warehouses", "name", nullable=False)
    op.alter_column("warehouses", "owner_company_id", nullable=False)
    op.alter_column("warehouses", "owner_company_type", nullable=False)

    # 4. Add constraints and foreign keys to warehouses
    op.create_foreign_key(
        "fk_warehouses_owner_company_id_companies",
        "warehouses",
        "companies",
        ["owner_company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_warehouses_brand_id_special_equipment_marks",
        "warehouses",
        "special_equipment_marks",
        ["brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_warehouses_owner_company_type",
        "warehouses",
        "owner_company_type IN ('dealer', 'distributor')",
    )

    # 5. Drop old constraints, indexes and columns
    op.drop_constraint("ck_warehouses_status", "warehouses", type_="check")
    op.drop_constraint("warehouses_company_id_fkey", "warehouses", type_="foreignkey")
    op.drop_constraint("warehouses_dealer_id_fkey", "warehouses", type_="foreignkey")

    op.drop_index("idx_warehouses_brand", table_name="warehouses")
    op.drop_index("idx_warehouses_company_id", table_name="warehouses")
    op.drop_index("idx_warehouses_dealer_id", table_name="warehouses")

    op.drop_column("warehouses", "brand")
    op.drop_column("warehouses", "company_id")
    op.drop_column("warehouses", "dealer_id")
    op.drop_column("warehouses", "status")

    # 6. Create new indexes on warehouses
    op.create_index("idx_warehouses_name", "warehouses", ["name"])
    op.create_index(
        "idx_warehouses_owner_company_id", "warehouses", ["owner_company_id"]
    )
    op.create_index(
        "idx_warehouses_owner_company_type", "warehouses", ["owner_company_type"]
    )
    op.create_index("idx_warehouses_brand_id", "warehouses", ["brand_id"])
    op.create_index("idx_warehouses_is_active", "warehouses", ["is_active"])

    # 7. Create warehouse_access_rules table
    op.create_table(
        "warehouse_access_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE", name="fk_warehouse_access_rules_warehouse_id"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE", name="fk_warehouse_access_rules_target_id"),
            nullable=False,
        ),
        sa.Column("warehouse_access_type", sa.String(length=5), nullable=False),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("catalog_storefronts.id", ondelete="SET NULL", name="fk_warehouse_access_rules_site_id"),
            nullable=True,
        ),
        sa.Column(
            "brand_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("special_equipment_marks.id", ondelete="SET NULL", name="fk_warehouse_access_rules_brand_id"),
            nullable=True,
        ),
        sa.Column(
            "source_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dealer_groups.id", ondelete="SET NULL", name="fk_warehouse_access_rules_source_group_id"),
            nullable=True,
        ),
        sa.Column(
            "is_visible",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "can_create_application",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )

    op.create_check_constraint(
        "ck_warehouse_access_rules_target_type",
        "warehouse_access_rules",
        "target_type IN ('dealer', 'distributor')",
    )
    op.create_check_constraint(
        "ck_warehouse_access_rules_access_type",
        "warehouse_access_rules",
        "warehouse_access_type IN ('A', 'B', 'C')",
    )
    op.create_index(
        "idx_warehouse_access_rules_unique_rule",
        "warehouse_access_rules",
        [
            "warehouse_id",
            "target_type",
            "target_id",
            sa.text("COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            sa.text("COALESCE(brand_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
        ],
        unique=True,
    )
    op.create_index(
        "idx_warehouse_access_rules_target",
        "warehouse_access_rules",
        ["target_id", "is_active"],
    )
    op.create_index(
        "idx_warehouse_access_rules_warehouse",
        "warehouse_access_rules",
        ["warehouse_id", "is_active"],
    )
    op.create_index(
        "idx_warehouse_access_rules_source_group",
        "warehouse_access_rules",
        ["source_group_id"],
    )

    # 8. Seed type 'A' rules for all existing warehouses
    conn.execute(
        sa.text("""
            INSERT INTO warehouse_access_rules (
                id, warehouse_id, target_type, target_id, warehouse_access_type,
                site_id, brand_id, source_group_id, is_visible, can_create_application, is_active,
                created_at, updated_at
            )
            SELECT
                gen_random_uuid(), id, owner_company_type, owner_company_id, 'A',
                NULL, NULL, NULL, true, true, true,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM warehouses
        """)
    )


def downgrade() -> None:
    op.drop_table("warehouse_access_rules")

    # Restore old columns and constraints on warehouses
    op.add_column("warehouses", sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False))
    op.add_column("warehouses", sa.Column("dealer_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("warehouses", sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("warehouses", sa.Column("brand", sa.String(length=100), server_default="", nullable=False))

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE warehouses
            SET company_id = owner_company_id,
                dealer_id = owner_company_id,
                status = CASE WHEN is_active THEN 'active' ELSE 'inactive' END
        """)
    )

    op.create_foreign_key(
        "warehouses_dealer_id_fkey",
        "warehouses",
        "companies",
        ["dealer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "warehouses_company_id_fkey",
        "warehouses",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_warehouses_status",
        "warehouses",
        "status IN ('active', 'inactive')",
    )
    op.create_index("idx_warehouses_dealer_id", "warehouses", ["dealer_id"])
    op.create_index("idx_warehouses_company_id", "warehouses", ["company_id"])
    op.create_index("idx_warehouses_brand", "warehouses", ["brand"])

    op.drop_index("idx_warehouses_is_active", table_name="warehouses")
    op.drop_index("idx_warehouses_brand_id", table_name="warehouses")
    op.drop_index("idx_warehouses_owner_company_type", table_name="warehouses")
    op.drop_index("idx_warehouses_owner_company_id", table_name="warehouses")
    op.drop_index("idx_warehouses_name", table_name="warehouses")

    op.drop_constraint("ck_warehouses_owner_company_type", "warehouses", type_="check")
    op.drop_constraint("fk_warehouses_brand_id_special_equipment_marks", "warehouses", type_="foreignkey")
    op.drop_constraint("fk_warehouses_owner_company_id_companies", "warehouses", type_="foreignkey")

    op.drop_column("warehouses", "is_active")
    op.drop_column("warehouses", "brand_id")
    op.drop_column("warehouses", "owner_company_type")
    op.drop_column("warehouses", "owner_company_id")
    op.drop_column("warehouses", "name")
