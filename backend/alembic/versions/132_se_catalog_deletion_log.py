"""Create special equipment catalog deletion log table.

Revision ID: 132
Revises: 131
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "132"
down_revision: str | None = "131"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "special_equipment_catalog_deletion_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("root_type", sa.String(length=50), nullable=False),
        sa.Column("root_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("root_code", sa.String(length=100), nullable=True),
        sa.Column("root_name", sa.String(length=255), nullable=True),
        sa.Column("catalog_revision", sa.Integer(), nullable=False),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_se_catalog_deletion_log_created_at",
        "special_equipment_catalog_deletion_log",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_se_catalog_deletion_log_root",
        "special_equipment_catalog_deletion_log",
        ["root_type", "root_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_se_catalog_deletion_log_root",
        table_name="special_equipment_catalog_deletion_log",
    )
    op.drop_index(
        "idx_se_catalog_deletion_log_created_at",
        table_name="special_equipment_catalog_deletion_log",
    )
    op.drop_table("special_equipment_catalog_deletion_log")
