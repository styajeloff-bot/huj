"""Persist append-only audit history for warehouse vehicle transfers.

Revision ID: 081
Revises: 080
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "081"
down_revision: str | None = "080"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "vehicle_warehouse_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_warehouse_id <> destination_warehouse_id",
            name="ck_vehicle_warehouse_transfers_distinct_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name="fk_vehicle_warehouse_transfers_vehicle_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_warehouse_id"],
            ["warehouses.id"],
            name="fk_vehicle_warehouse_transfers_source_warehouse_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_warehouse_id"],
            ["warehouses.id"],
            name="fk_vehicle_warehouse_transfers_destination_warehouse_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_vehicle_warehouse_transfers_actor_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vehicle_warehouse_transfers"),
    )
    op.create_index(
        "idx_vehicle_warehouse_transfers_vehicle_created_at",
        "vehicle_warehouse_transfers",
        ["vehicle_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_vehicle_warehouse_transfers_source_created_at",
        "vehicle_warehouse_transfers",
        ["source_warehouse_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_vehicle_warehouse_transfers_destination_created_at",
        "vehicle_warehouse_transfers",
        ["destination_warehouse_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_vehicle_warehouse_transfers_destination_created_at",
        table_name="vehicle_warehouse_transfers",
    )
    op.drop_index(
        "idx_vehicle_warehouse_transfers_source_created_at",
        table_name="vehicle_warehouse_transfers",
    )
    op.drop_index(
        "idx_vehicle_warehouse_transfers_vehicle_created_at",
        table_name="vehicle_warehouse_transfers",
    )
    op.drop_table("vehicle_warehouse_transfers")
