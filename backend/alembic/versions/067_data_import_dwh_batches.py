"""Add durable DWH delivery batches for CSV imports.

Revision ID: 067
Revises: 066
Create Date: 2026-07-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "067"
down_revision: str | None = "066"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "data_import_dwh_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payloads", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rows_count", sa.Integer(), nullable=False),
        sa.Column("row_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_data_import_dwh_batches_attempts_non_negative",
        ),
        sa.CheckConstraint(
            "rows_count >= 0",
            name="ck_data_import_dwh_batches_rows_count_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'publishing', 'delivered', 'failed')",
            name="ck_data_import_dwh_batches_status",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["data_import_jobs.id"],
            name="data_import_dwh_batches_job_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_import_dwh_batches"),
    )
    op.create_index(
        "idx_data_import_dwh_batches_status_next_attempt",
        "data_import_dwh_batches",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "idx_data_import_dwh_batches_job_status",
        "data_import_dwh_batches",
        ["job_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_data_import_dwh_batches_job_status",
        table_name="data_import_dwh_batches",
    )
    op.drop_index(
        "idx_data_import_dwh_batches_status_next_attempt",
        table_name="data_import_dwh_batches",
    )
    op.drop_table("data_import_dwh_batches")
