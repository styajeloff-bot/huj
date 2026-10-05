"""Add warehouse-scoped catalog storefronts.

Revision ID: 101
Revises: 100
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "101"
down_revision: str | None = "100"
branch_labels: str | None = None
depends_on: str | None = None

_DEFAULT_ID = "00000000-0000-0000-0000-000000000001"
_DEFAULT_SQL = sa.text(f"'{_DEFAULT_ID}'::uuid")


def _add_scope_column(table: str, *, index_name: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "storefront_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=_DEFAULT_SQL,
        ),
    )
    op.create_foreign_key(
        f"fk_{table}_storefront_id",
        table,
        "catalog_storefronts",
        ["storefront_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(index_name, table, ["storefront_id"])


def upgrade() -> None:
    op.create_table(
        "catalog_storefronts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(length=63), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("logo_storage_key", sa.String(length=512), nullable=True),
        sa.Column("logo_content_type", sa.String(length=64), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint(
            "(is_default AND slug IS NULL) OR (NOT is_default AND slug IS NOT NULL)",
            name="ck_catalog_storefronts_default_slug",
        ),
        sa.CheckConstraint(
            "slug IS NULL OR slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
            name="ck_catalog_storefronts_slug_format",
        ),
        sa.CheckConstraint("version > 0", name="ck_catalog_storefronts_version"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_catalog_storefronts_slug_lower",
        "catalog_storefronts",
        [sa.text("lower(slug)")],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )
    op.create_index(
        "uq_catalog_storefronts_default",
        "catalog_storefronts",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )
    op.execute(
        sa.text(
            "INSERT INTO catalog_storefronts "
            "(id, slug, is_default, is_active, version, contact_email, contact_phone) "
            "VALUES (CAST(:id AS uuid), NULL, true, true, 1, "
            "'info@multileasing.ru', '+7 (930) 999-03-65')"
        ).bindparams(id=_DEFAULT_ID)
    )

    op.create_table(
        "catalog_storefront_warehouses",
        sa.Column("storefront_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["storefront_id"],
            ["catalog_storefronts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint(
            "storefront_id",
            "warehouse_id",
            name="pk_catalog_storefront_warehouses",
        ),
    )
    op.create_index(
        "idx_catalog_storefront_warehouses_warehouse_id",
        "catalog_storefront_warehouses",
        ["warehouse_id"],
    )

    _add_scope_column(
        "featured_vehicles", index_name="idx_featured_vehicles_storefront_id"
    )
    op.drop_constraint(
        "featured_vehicles_model_unique", "featured_vehicles", type_="unique"
    )
    op.create_unique_constraint(
        "featured_vehicles_model_unique",
        "featured_vehicles",
        ["storefront_id", "model_id"],
    )

    _add_scope_column("shopping_cart", index_name="idx_shopping_cart_storefront_id")
    op.drop_constraint(
        "shopping_cart_user_vehicle_unique", "shopping_cart", type_="unique"
    )
    op.create_unique_constraint(
        "shopping_cart_user_vehicle_unique",
        "shopping_cart",
        ["user_id", "storefront_id", "vehicle_id"],
    )

    _add_scope_column("user_favorites", index_name="idx_user_favorites_storefront_id")
    op.drop_constraint(
        "user_favorites_user_id_vehicle_id_key", "user_favorites", type_="unique"
    )
    op.create_unique_constraint(
        "user_favorites_user_id_vehicle_id_key",
        "user_favorites",
        ["user_id", "storefront_id", "vehicle_id"],
    )

    _add_scope_column(
        "leasing_applications",
        index_name="idx_leasing_applications_storefront_id",
    )

    _add_scope_column(
        "guest_cart_transfers", index_name="idx_guest_cart_transfers_storefront_id"
    )
    op.drop_constraint(
        "pk_guest_cart_transfers", "guest_cart_transfers", type_="primary"
    )
    op.create_primary_key(
        "pk_guest_cart_transfers",
        "guest_cart_transfers",
        ["user_id", "storefront_id", "transfer_id"],
    )


def _drop_scope_column(table: str, *, index_name: str) -> None:
    op.drop_index(index_name, table_name=table)
    op.drop_constraint(f"fk_{table}_storefront_id", table, type_="foreignkey")
    op.drop_column(table, "storefront_id")


def downgrade() -> None:
    # The pre-storefront schema cannot represent duplicate identities across
    # scopes. Custom storefront data is discarded together with its storefront
    # before restoring the legacy uniqueness constraints.
    for table in (
        "guest_cart_transfers",
        "user_favorites",
        "shopping_cart",
        "featured_vehicles",
    ):
        op.execute(
            sa.text(
                f"DELETE FROM {table} WHERE storefront_id <> CAST(:default_id AS uuid)"
            ).bindparams(default_id=_DEFAULT_ID)
        )

    op.drop_constraint(
        "pk_guest_cart_transfers", "guest_cart_transfers", type_="primary"
    )
    op.create_primary_key(
        "pk_guest_cart_transfers",
        "guest_cart_transfers",
        ["user_id", "transfer_id"],
    )
    _drop_scope_column(
        "guest_cart_transfers", index_name="idx_guest_cart_transfers_storefront_id"
    )

    _drop_scope_column(
        "leasing_applications",
        index_name="idx_leasing_applications_storefront_id",
    )

    op.drop_constraint(
        "user_favorites_user_id_vehicle_id_key", "user_favorites", type_="unique"
    )
    op.create_unique_constraint(
        "user_favorites_user_id_vehicle_id_key",
        "user_favorites",
        ["user_id", "vehicle_id"],
    )
    _drop_scope_column("user_favorites", index_name="idx_user_favorites_storefront_id")

    op.drop_constraint(
        "shopping_cart_user_vehicle_unique", "shopping_cart", type_="unique"
    )
    op.create_unique_constraint(
        "shopping_cart_user_vehicle_unique",
        "shopping_cart",
        ["user_id", "vehicle_id"],
    )
    _drop_scope_column("shopping_cart", index_name="idx_shopping_cart_storefront_id")

    op.drop_constraint(
        "featured_vehicles_model_unique", "featured_vehicles", type_="unique"
    )
    op.create_unique_constraint(
        "featured_vehicles_model_unique", "featured_vehicles", ["model_id"]
    )
    _drop_scope_column(
        "featured_vehicles", index_name="idx_featured_vehicles_storefront_id"
    )

    op.drop_index(
        "idx_catalog_storefront_warehouses_warehouse_id",
        table_name="catalog_storefront_warehouses",
    )
    op.drop_table("catalog_storefront_warehouses")
    op.drop_index("uq_catalog_storefronts_default", table_name="catalog_storefronts")
    op.drop_index("uq_catalog_storefronts_slug_lower", table_name="catalog_storefronts")
    op.drop_table("catalog_storefronts")
