"""Add soft-deactivatable brand assignments for distributor companies.

Revision ID: 080
Revises: 079
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "080"
down_revision: str | None = "079"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "distributor_brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "distributor_company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("brand_id", sa.String(length=50), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["distributor_company_id"],
            ["companies.id"],
            name="fk_distributor_brands_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["mark.id"],
            name="fk_distributor_brands_brand",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_distributor_brands"),
    )
    op.create_index(
        "uq_distributor_brands_active_company_brand",
        "distributor_brands",
        ["distributor_company_id", "brand_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "idx_distributor_brands_active_company",
        "distributor_brands",
        ["distributor_company_id"],
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "idx_distributor_brands_brand_id",
        "distributor_brands",
        ["brand_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_distributor_brands_brand_id",
        table_name="distributor_brands",
    )
    op.drop_index(
        "idx_distributor_brands_active_company",
        table_name="distributor_brands",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_index(
        "uq_distributor_brands_active_company_brand",
        table_name="distributor_brands",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("distributor_brands")
