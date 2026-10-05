"""Remove retired special-equipment analytics persistence.

Revision ID: 077
Revises: 076
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "077"
down_revision: str | None = "076"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_index(
        "idx_se_import_jobs_projection_recovery",
        table_name="special_equipment_import_jobs",
    )
    op.drop_column("special_equipment_import_jobs", "projection_state")

    op.drop_table("special_equipment_commerce_outbox")

    op.drop_column("special_equipment_payments", "analytics_session_id")
    op.drop_column("special_equipment_purchase_orders", "analytics_session_id")


def downgrade() -> None:
    op.add_column(
        "special_equipment_purchase_orders",
        sa.Column(
            "analytics_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_payments",
        sa.Column(
            "analytics_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_table(
        "special_equipment_commerce_outbox",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "schema_version",
            sa.SmallInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_special_equipment_outbox_attempt_count",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "idx_special_equipment_outbox_pending",
        "special_equipment_commerce_outbox",
        ["available_at", "occurred_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "projection_state",
            sa.String(20),
            server_default=sa.text("'not_required'"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_se_import_jobs_projection_recovery",
        "special_equipment_import_jobs",
        ["lease_until", "id"],
        postgresql_where=sa.text(
            "status IN ('completed', 'completed_with_warnings') "
            "AND projection_state IN ('pending', 'failed')"
        ),
    )
