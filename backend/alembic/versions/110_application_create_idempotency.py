"""Add transactional idempotency receipts for application creation.

Revision ID: 110
Revises: 109
Create Date: 2026-09-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "110"
down_revision: str | None = "109"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # A local pre-release build briefly used revision 108 for this table.
    # Keep the published migration safe for databases created by that build.
    if "application_create_idempotency_keys" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "application_create_idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('in_progress', 'succeeded', 'failed')",
            name="ck_application_create_idempotency_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "endpoint",
            "idempotency_key",
            name="uq_application_create_idempotency_endpoint_key",
        ),
    )
    op.create_index(
        "idx_application_create_idempotency_expires_at",
        "application_create_idempotency_keys",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_application_create_idempotency_expires_at",
        table_name="application_create_idempotency_keys",
    )
    op.drop_table("application_create_idempotency_keys")
