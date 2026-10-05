"""Add durable LCA status history and analytics watermark.

Revision ID: 069
Revises: 068
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "069"
down_revision: str | None = "068"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "leasing_company_application_status_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lca_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_status", sa.String(length=64), nullable=True),
        sa.Column("new_status", sa.String(length=64), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("application_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lca_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dealer_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("distributor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("leasing_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_baseline", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "publish_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_publish_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["leasing_applications.id"],
            name="fk_lca_status_history_application_id",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name="fk_lca_status_history_changed_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lca_id"],
            ["leasing_company_applications.id"],
            name="fk_lca_status_history_lca_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lca_status_history"),
    )
    op.create_index(
        "idx_lca_status_history_lca_changed_at",
        "leasing_company_application_status_history",
        ["lca_id", sa.text("changed_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_lca_status_history_publish_queue",
        "leasing_company_application_status_history",
        ["published_at", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "idx_lca_status_history_dealer_changed_at",
        "leasing_company_application_status_history",
        ["dealer_company_id", "changed_at"],
        unique=False,
    )
    op.create_index(
        "uq_lca_status_history_baseline_lca",
        "leasing_company_application_status_history",
        ["lca_id"],
        unique=True,
        postgresql_where=sa.text("is_baseline"),
    )

    op.create_table(
        "lca_status_history_metadata",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("date_value", sa.Date(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_lca_status_history_metadata"),
    )


def downgrade() -> None:
    op.drop_table("lca_status_history_metadata")
    op.drop_index(
        "uq_lca_status_history_baseline_lca",
        table_name="leasing_company_application_status_history",
        postgresql_where=sa.text("is_baseline"),
    )
    op.drop_index(
        "idx_lca_status_history_dealer_changed_at",
        table_name="leasing_company_application_status_history",
    )
    op.drop_index(
        "idx_lca_status_history_publish_queue",
        table_name="leasing_company_application_status_history",
    )
    op.drop_index(
        "idx_lca_status_history_lca_changed_at",
        table_name="leasing_company_application_status_history",
    )
    op.drop_table("leasing_company_application_status_history")
