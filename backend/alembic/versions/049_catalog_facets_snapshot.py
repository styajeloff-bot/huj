"""add catalog facets snapshot

Revision ID: 049
Revises: 048
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "049"
down_revision: str | None = "048"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_facets_snapshot",
        sa.Column("scope_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("mark_id", sa.String(length=50), nullable=True),
        sa.Column("model_id", sa.String(length=50), nullable=True),
        sa.Column("generation_id", sa.String(length=50), nullable=True),
        sa.Column("popular", sa.Boolean(), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "payload_version",
            sa.Integer(),
            server_default=sa.text("1"),
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
        sa.PrimaryKeyConstraint("scope_hash"),
    )
    op.create_index(
        "idx_catalog_facets_snapshot_updated_at",
        "catalog_facets_snapshot",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_catalog_facets_snapshot_updated_at",
        table_name="catalog_facets_snapshot",
    )
    op.drop_table("catalog_facets_snapshot")
