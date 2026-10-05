"""Technical persistence for resumable special-equipment XLSX imports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SpecialEquipmentImportJob(Base):
    """One durable import resource for one physical XLSX file."""

    __tablename__ = "special_equipment_import_jobs"
    __table_args__ = (
        sa.CheckConstraint(
            "mode IN ('APPEND', 'PATCH', 'FULL_SNAPSHOT')",
            name="ck_se_import_jobs_mode",
        ),
        sa.CheckConstraint(
            "error_policy IN ('ATOMIC', 'BEST_EFFORT')",
            name="ck_se_import_jobs_error_policy",
        ),
        sa.CheckConstraint(
            "mode <> 'FULL_SNAPSHOT' OR error_policy = 'ATOMIC'",
            name="ck_se_import_jobs_full_atomic",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'awaiting_upload', 'uploaded', 'validating_file', "
            "'validating_data', 'transferring_images', 'preview_ready', "
            "'validation_failed', 'applying', 'preview_stale', 'completed', "
            "'completed_with_warnings', 'failed', 'failed_retryable', "
            "'cancelled'"
            ")",
            name="ck_se_import_jobs_status",
        ),
        sa.CheckConstraint(
            "expected_size_bytes > 0 AND actual_size_bytes >= 0",
            name="ck_se_import_jobs_sizes",
        ),
        sa.CheckConstraint(
            "rows_total >= 0 AND rows_done >= 0 AND "
            "entities_total >= 0 AND entities_done >= 0 AND "
            "images_total >= 0 AND images_done >= 0 AND "
            "issues_total >= 0",
            name="ck_se_import_jobs_counters_nonnegative",
        ),
        sa.CheckConstraint(
            "rows_done <= rows_total AND entities_done <= entities_total "
            "AND images_done <= images_total",
            name="ck_se_import_jobs_counters_bounded",
        ),
        sa.CheckConstraint(
            "artifact_cleanup_status IN ('pending', 'processing', 'completed')",
            name="ck_se_import_jobs_artifact_cleanup_status",
        ),
        sa.CheckConstraint(
            "artifact_cleanup_attempt_count >= 0",
            name="ck_se_import_jobs_artifact_cleanup_attempts",
        ),
        sa.CheckConstraint(
            "artifact_cleanup_status <> 'processing' "
            "OR (artifact_cleanup_lease_owner IS NOT NULL "
            "AND artifact_cleanup_lease_until IS NOT NULL)",
            name="ck_se_import_jobs_artifact_cleanup_processing_lease",
        ),
        sa.CheckConstraint(
            "artifact_cleanup_status <> 'completed' "
            "OR artifacts_cleaned_at IS NOT NULL",
            name="ck_se_import_jobs_artifact_cleanup_completed_at",
        ),
        sa.Index(
            "idx_se_import_jobs_user_created",
            "requested_by",
            sa.text("created_at DESC"),
            sa.text("id DESC"),
        ),
        sa.Index(
            "idx_se_import_jobs_recovery",
            "status",
            "lease_until",
            postgresql_where=sa.text(
                "status IN ('uploaded', 'validating_file', 'validating_data', "
                "'transferring_images', 'applying', 'failed_retryable')"
            ),
        ),
        sa.Index(
            "idx_se_import_jobs_artifact_cleanup",
            "retain_until",
            "id",
            postgresql_where=sa.text(
                "retain_until IS NOT NULL "
                "AND artifact_cleanup_status IN ('pending', 'processing') "
                "AND status IN ('validation_failed', 'completed', "
                "'completed_with_warnings', 'failed', 'cancelled')"
            ),
        ),
        sa.Index("idx_se_import_jobs_target_warehouse", "target_warehouse_id"),
        sa.UniqueConstraint(
            "requested_by",
            "idempotency_key",
            name="uq_se_import_jobs_idempotency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    source_code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    target_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    target_warehouse_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    mode: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    error_policy: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    template_version: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    actual_size_bytes: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )

    # Internal-only object-storage metadata. Presentation schemas omit it.
    source_object_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(sa.CHAR(64), nullable=True)
    multipart_upload_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    upload_expires_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )

    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="awaiting_upload",
        server_default=sa.text("'awaiting_upload'"),
    )
    phase: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        default="upload",
        server_default=sa.text("'upload'"),
    )
    lease_owner: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    lease_until: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )

    rows_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    rows_done: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    entities_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    entities_done: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    images_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    images_done: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    issues_total: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )

    normalized_artifact_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    diff_artifact_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    validation_report_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    catalog_revision: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    preview_hash: Mapped[str | None] = mapped_column(sa.CHAR(64), nullable=True)
    applied_revision: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)

    cancellation_requested: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    confirm_destructive_changes: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    accept_optional_image_failures: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    error_code: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
    uploaded_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    previewed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    retain_until: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    artifact_cleanup_status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="pending",
        server_default=sa.text("'pending'"),
    )
    artifact_cleanup_lease_owner: Mapped[str | None] = mapped_column(
        sa.String(200), nullable=True
    )
    artifact_cleanup_lease_until: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    artifact_cleanup_attempt_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    artifact_cleanup_last_error: Mapped[str | None] = mapped_column(
        sa.String(1000), nullable=True
    )
    artifacts_cleaned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class SpecialEquipmentImportUploadPart(Base):
    """Server-confirmed multipart upload part used for resume and recovery."""

    __tablename__ = "special_equipment_import_upload_parts"
    __table_args__ = (
        sa.CheckConstraint("part_number > 0", name="ck_se_import_parts_number"),
        sa.CheckConstraint(
            "byte_start >= 0 AND byte_end >= byte_start",
            name="ck_se_import_parts_range",
        ),
        sa.CheckConstraint(
            "size_bytes = byte_end - byte_start + 1 AND size_bytes > 0",
            name="ck_se_import_parts_size",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'failed')",
            name="ck_se_import_parts_status",
        ),
        sa.UniqueConstraint(
            "job_id", "byte_start", name="uq_se_import_parts_job_start"
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_import_jobs.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    part_number: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    byte_start: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    byte_end: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(sa.CHAR(64), nullable=False)
    storage_etag: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'received'")
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentImportIssue(Base):
    """Bounded, UI-queryable validation issue sample for one job."""

    __tablename__ = "special_equipment_import_issues"
    __table_args__ = (
        sa.CheckConstraint("sequence > 0", name="ck_se_import_issues_sequence"),
        sa.CheckConstraint(
            "severity IN ('error', 'warning')",
            name="ck_se_import_issues_severity",
        ),
        sa.CheckConstraint(
            "row_number IS NULL OR row_number > 0",
            name="ck_se_import_issues_row_number",
        ),
        sa.Index(
            "idx_se_import_issues_severity",
            "job_id",
            "severity",
            "sequence",
        ),
        sa.Index(
            "idx_se_import_issues_row",
            "job_id",
            "sheet_code",
            "row_number",
            "sequence",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_import_jobs.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    sheet_code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    row_number: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    column_name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    severity: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    code: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    message: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    raw_value_preview: Mapped[str | None] = mapped_column(sa.String(300), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    external_key: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class SpecialEquipmentImportStagedMedia(Base):
    """Durable ownership manifest for media uploaded before catalog apply."""

    __tablename__ = "special_equipment_import_staged_media"
    __table_args__ = (
        sa.CheckConstraint(
            "owner_kind IN ('category', 'product')",
            name="ck_se_import_staged_media_owner_kind",
        ),
        sa.CheckConstraint(
            "status IN ('staged', 'referenced', 'deleted')",
            name="ck_se_import_staged_media_status",
        ),
        sa.Index(
            "idx_se_import_staged_media_cleanup",
            "status",
            "cleanup_after",
        ),
        sa.Index(
            "idx_se_import_staged_media_storage_key",
            "storage_key",
            "status",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_import_jobs.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        primary_key=True,
    )
    storage_key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    owner_kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default="staged",
        server_default=sa.text("'staged'"),
    )
    cleanup_after: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    referenced_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentExternalRef(Base):
    """Stable external identity mapping and full-snapshot ownership."""

    __tablename__ = "special_equipment_external_refs"
    __table_args__ = (
        sa.CheckConstraint(
            "entity_type IN ("
            "'category', 'manufacturer', 'attribute', 'product', 'product_image'"
            ")",
            name="ck_se_external_refs_entity_type",
        ),
        sa.UniqueConstraint(
            "source_code",
            "entity_type",
            "entity_id",
            name="uq_se_external_refs_source_entity",
        ),
        sa.Index(
            "uq_se_external_refs_owned_entity",
            "entity_type",
            "entity_id",
            unique=True,
            postgresql_where=sa.text("entity_type IN ('product', 'product_image')"),
        ),
        sa.Index(
            "idx_se_external_refs_entity",
            "entity_type",
            "entity_id",
        ),
    )

    source_code: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    entity_type: Mapped[str] = mapped_column(sa.String(50), primary_key=True)
    external_key: Mapped[str] = mapped_column(sa.String(255), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    first_seen_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_import_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_seen_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_import_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SpecialEquipmentCatalogState(Base):
    """Singleton revision barrier used to invalidate stale previews."""

    __tablename__ = "special_equipment_catalog_state"
    __table_args__ = (
        sa.CheckConstraint("singleton", name="ck_se_catalog_state_singleton"),
        sa.CheckConstraint("revision >= 0", name="ck_se_catalog_state_revision"),
    )

    singleton: Mapped[bool] = mapped_column(
        sa.Boolean, primary_key=True, default=True, server_default=sa.true()
    )
    revision: Mapped[int] = mapped_column(
        sa.BigInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
