"""Durable vehicle file cleanup and Kafka tombstone outbox.

Revision ID: 117
Revises: 116
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "117"
down_revision: str = "116"
branch_labels: str | None = None
depends_on: str | None = None


def _delivery_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "object_storage_deletion_jobs",
        *_delivery_columns(),
        sa.Column(
            "entity_type", sa.String(40), nullable=False, server_default="vehicle"
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "object_key", name="uq_vehicle_deletion_object"
        ),
        sa.CheckConstraint(
            "entity_type = 'vehicle'", name="ck_vehicle_deletion_entity"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_vehicle_deletion_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_vehicle_deletion_attempts"),
    )
    op.create_index(
        "ix_vehicle_deletion_due",
        "object_storage_deletion_jobs",
        ["status", "scheduled_at"],
    )
    op.create_table(
        "vehicle_deletion_outbox",
        *_delivery_columns(),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vehicle_id", name="uq_vehicle_deletion_event"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_vehicle_deletion_event_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_vehicle_deletion_event_attempts"),
    )
    op.create_index(
        "ix_vehicle_deletion_event_due",
        "vehicle_deletion_outbox",
        ["status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_table("vehicle_deletion_outbox")
    op.drop_table("object_storage_deletion_jobs")
