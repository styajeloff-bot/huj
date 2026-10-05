"""Add persistence primitives for the special-equipment operational registry.

Revision ID: 078
Revises: 077
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "078"
down_revision: str | None = "077"
branch_labels: str | None = None
depends_on: str | None = None


_LOCKED_TABLES = (
    "special_equipment_categories",
    "special_equipment_manufacturers",
    "special_equipment_attributes",
    "special_equipment_products",
)


def upgrade() -> None:
    for table_name in _LOCKED_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "lock_version",
                sa.BigInteger(),
                server_default=sa.text("1"),
                nullable=False,
            ),
        )
        op.create_check_constraint(
            f"ck_{table_name}_lock_version",
            table_name,
            "lock_version >= 1",
        )

    op.create_index(
        "idx_se_products_admin_updated",
        "special_equipment_products",
        [sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_se_products_admin_status_updated",
        "special_equipment_products",
        [
            "publication_status",
            sa.text("updated_at DESC"),
            sa.text("id DESC"),
        ],
    )
    op.create_index(
        "idx_se_products_admin_manufacturer_updated",
        "special_equipment_products",
        ["manufacturer_id", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_se_products_admin_slug_prefix",
        "special_equipment_products",
        [sa.text("lower(slug) text_pattern_ops")],
    )
    op.create_index(
        "idx_se_products_claimed_seller",
        "special_equipment_products",
        ["seller_company_id", "id"],
        postgresql_where=sa.text(
            "seller_company_id IS NOT NULL "
            "AND sale_status IN ('reserved', 'sold')"
        ),
    )
    op.create_index(
        "idx_se_application_items_live_seller",
        "special_equipment_application_items",
        ["seller_company_id", "product_id"],
        postgresql_where=sa.text(
            "seller_company_id IS NOT NULL "
            "AND item_status IN ('active', 'reserved')"
        ),
    )
    op.create_index(
        "idx_se_orders_live_seller",
        "special_equipment_purchase_orders",
        ["seller_company_id", "product_id"],
        postgresql_where=sa.text(
            "seller_company_id IS NOT NULL AND status IN ("
            "'payment_pending', 'reserved', 'purchased', "
            "'leasing_pending', 'leasing_active', 'cancellation_requested')"
        ),
    )
    op.create_index(
        "idx_se_external_refs_entity",
        "special_equipment_external_refs",
        ["entity_type", "entity_id"],
    )

    op.create_table(
        "special_equipment_catalog_mutation_receipts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(request_hash) = 64",
            name="ck_se_catalog_mutation_receipts_request_hash",
        ),
        sa.CheckConstraint(
            "resource_type IN ('category', 'manufacturer', 'attribute', 'product')",
            name="ck_se_catalog_mutation_receipts_resource_type",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_se_catalog_mutation_receipts_actor",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_id",
            "idempotency_key",
            name="uq_se_catalog_mutation_receipts_actor_key",
        ),
    )
    op.create_index(
        "idx_se_catalog_mutation_receipts_resource",
        "special_equipment_catalog_mutation_receipts",
        ["resource_type", "resource_id"],
    )

    op.create_table(
        "special_equipment_media_cleanup_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_se_media_cleanup_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_se_media_cleanup_jobs_attempt_count",
        ),
        sa.CheckConstraint(
            "status <> 'processing' OR "
            "(lease_owner IS NOT NULL AND lease_until IS NOT NULL)",
            name="ck_se_media_cleanup_jobs_processing_lease",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="ck_se_media_cleanup_jobs_completed_at",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key", name="uq_se_media_cleanup_jobs_storage_key"
        ),
    )
    op.create_index(
        "idx_se_media_cleanup_pending",
        "special_equipment_media_cleanup_jobs",
        ["next_attempt_at", "id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_se_media_cleanup_recovery",
        "special_equipment_media_cleanup_jobs",
        ["lease_until", "id"],
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_se_media_cleanup_recovery",
        table_name="special_equipment_media_cleanup_jobs",
    )
    op.drop_index(
        "idx_se_media_cleanup_pending",
        table_name="special_equipment_media_cleanup_jobs",
    )
    op.drop_table("special_equipment_media_cleanup_jobs")

    op.drop_index(
        "idx_se_catalog_mutation_receipts_resource",
        table_name="special_equipment_catalog_mutation_receipts",
    )
    op.drop_table("special_equipment_catalog_mutation_receipts")

    op.drop_index(
        "idx_se_external_refs_entity",
        table_name="special_equipment_external_refs",
    )
    op.drop_index(
        "idx_se_orders_live_seller",
        table_name="special_equipment_purchase_orders",
    )
    op.drop_index(
        "idx_se_application_items_live_seller",
        table_name="special_equipment_application_items",
    )
    op.drop_index(
        "idx_se_products_claimed_seller",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_se_products_admin_slug_prefix",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_se_products_admin_manufacturer_updated",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_se_products_admin_status_updated",
        table_name="special_equipment_products",
    )
    op.drop_index(
        "idx_se_products_admin_updated",
        table_name="special_equipment_products",
    )

    for table_name in reversed(_LOCKED_TABLES):
        op.drop_constraint(
            f"ck_{table_name}_lock_version",
            table_name,
            type_="check",
        )
        op.drop_column(table_name, "lock_version")
