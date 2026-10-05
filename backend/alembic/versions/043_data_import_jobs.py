"""Generic async data-import job tracking table.

Backs the Taskiq ``data_import.*`` pipeline + ``GET /api/v1/imports/{job_id}``
progress polling for CSV uploads (vehicles, exchange requests/bids,
distributor-dealer links, companies, users, applications).

Revision ID: 043
Revises: 042
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_import_jobs",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("s3_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="queued"
        ),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_sample", JSONB(), nullable=True),
        sa.Column("params", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "idx_data_import_jobs_user_id", "data_import_jobs", ["user_id"]
    )
    op.create_index(
        "idx_data_import_jobs_status", "data_import_jobs", ["status"]
    )
    op.create_index("idx_data_import_jobs_kind", "data_import_jobs", ["kind"])


def downgrade() -> None:
    op.drop_index("idx_data_import_jobs_kind", table_name="data_import_jobs")
    op.drop_index("idx_data_import_jobs_status", table_name="data_import_jobs")
    op.drop_index("idx_data_import_jobs_user_id", table_name="data_import_jobs")
    op.drop_table("data_import_jobs")
