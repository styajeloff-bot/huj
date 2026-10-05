"""Durable, transaction-local side effects of deleting a vehicle."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class _DeliveryState:
    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(sa.String(20), server_default="pending")
    attempts: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    scheduled_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class ObjectStorageDeletionJob(_DeliveryState, Base):
    __tablename__ = "object_storage_deletion_jobs"
    __table_args__ = (
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
        sa.Index("ix_vehicle_deletion_due", "status", "scheduled_at"),
    )

    entity_type: Mapped[str] = mapped_column(sa.String(40), server_default="vehicle")
    # Deliberately no FK: these records must survive deletion of the vehicle.
    entity_id: Mapped[UUID] = mapped_column(sa.Uuid)
    object_key: Mapped[str] = mapped_column(sa.String(500))


class VehicleDeletionOutbox(_DeliveryState, Base):
    __tablename__ = "vehicle_deletion_outbox"
    __table_args__ = (
        sa.UniqueConstraint("vehicle_id", name="uq_vehicle_deletion_event"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_vehicle_deletion_event_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_vehicle_deletion_event_attempts"),
        sa.Index("ix_vehicle_deletion_event_due", "status", "scheduled_at"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(sa.Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
