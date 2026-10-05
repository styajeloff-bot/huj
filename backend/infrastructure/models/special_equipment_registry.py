"""Internal persistence supporting special-equipment catalog management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SpecialEquipmentCatalogMutationReceipt(Base):
    """Actor-scoped receipt used to replay an idempotent catalog create."""

    __tablename__ = "special_equipment_catalog_mutation_receipts"
    __table_args__ = (
        sa.UniqueConstraint(
            "actor_id",
            "idempotency_key",
            name="uq_se_catalog_mutation_receipts_actor_key",
        ),
        sa.CheckConstraint(
            "char_length(request_hash) = 64",
            name="ck_se_catalog_mutation_receipts_request_hash",
        ),
        sa.CheckConstraint(
            "resource_type IN ("
            "'category', 'mark', 'model', 'modification', 'trim', "
            "'attribute_group', 'attribute', 'attribute_option', 'product', "
            "'color', 'unit', 'superstructure')",
            name="ck_se_catalog_mutation_receipts_resource_type",
        ),
        sa.Index(
            "idx_se_catalog_mutation_receipts_resource",
            "resource_type",
            "resource_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            name="fk_se_catalog_mutation_receipts_actor",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    response_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Tagged immutable create response; NULL marks a legacy receipt "
            "that must replay from the current resource"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SpecialEquipmentMediaCleanupJob(Base):
    """Durable retry state for deleting an unreferenced private media object."""

    __tablename__ = "special_equipment_media_cleanup_jobs"
    __table_args__ = (
        sa.UniqueConstraint(
            "storage_key", name="uq_se_media_cleanup_jobs_storage_key"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_se_media_cleanup_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_se_media_cleanup_jobs_attempt_count",
        ),
        sa.CheckConstraint(
            "status <> 'processing' OR "
            "(lease_owner IS NOT NULL AND lease_until IS NOT NULL)",
            name="ck_se_media_cleanup_jobs_processing_lease",
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="ck_se_media_cleanup_jobs_completed_at",
        ),
        sa.Index(
            "idx_se_media_cleanup_pending",
            "next_attempt_at",
            "id",
            postgresql_where=sa.text("status = 'pending'"),
        ),
        sa.Index(
            "idx_se_media_cleanup_recovery",
            "lease_until",
            "id",
            postgresql_where=sa.text("status = 'processing'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    storage_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="pending",
        server_default=sa.text("'pending'"),
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    lease_owner: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
