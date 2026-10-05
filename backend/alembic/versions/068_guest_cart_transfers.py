"""Add idempotency receipts for guest cart transfers.

Revision ID: 068
Revises: 067
Create Date: 2026-07-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "068"
down_revision: str | None = "067"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "guest_cart_transfers",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "equipments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "services",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_guest_cart_transfers_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="guest_cart_transfers_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "transfer_id",
            name="pk_guest_cart_transfers",
        ),
    )


def downgrade() -> None:
    op.drop_table("guest_cart_transfers")
