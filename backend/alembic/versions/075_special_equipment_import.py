"""Add technical tables for special-equipment XLSX imports.

Revision ID: 075
Revises: 074
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "075"
down_revision: str | None = "074"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "special_equipment_import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("source_code", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("error_policy", sa.String(length=20), nullable=False),
        sa.Column("template_version", sa.SmallInteger(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "actual_size_bytes",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("source_object_key", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.CHAR(length=64), nullable=True),
        sa.Column("multipart_upload_id", sa.Text(), nullable=False),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'awaiting_upload'"),
            nullable=False,
        ),
        sa.Column(
            "phase",
            sa.String(length=64),
            server_default=sa.text("'upload'"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "rows_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "rows_done", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "entities_total",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "entities_done",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "images_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "images_done", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "issues_total", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("normalized_artifact_key", sa.Text(), nullable=True),
        sa.Column("diff_artifact_key", sa.Text(), nullable=True),
        sa.Column("validation_report_key", sa.Text(), nullable=True),
        sa.Column("catalog_revision", sa.BigInteger(), nullable=True),
        sa.Column("preview_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("applied_revision", sa.BigInteger(), nullable=True),
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "confirm_destructive_changes",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "accept_optional_image_failures",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "projection_state",
            sa.String(length=20),
            server_default=sa.text("'not_required'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('awaiting_upload', 'uploaded', 'validating_file', "
            "'validating_data', 'transferring_images', 'preview_ready', "
            "'validation_failed', 'applying', 'preview_stale', 'completed', "
            "'completed_with_warnings', 'failed', 'failed_retryable', 'cancelled')",
            name="ck_se_import_jobs_status",
        ),
        sa.CheckConstraint(
            "expected_size_bytes > 0 AND actual_size_bytes >= 0",
            name="ck_se_import_jobs_sizes",
        ),
        sa.CheckConstraint(
            "rows_total >= 0 AND rows_done >= 0 AND entities_total >= 0 "
            "AND entities_done >= 0 AND images_total >= 0 AND images_done >= 0 "
            "AND issues_total >= 0",
            name="ck_se_import_jobs_counters_nonnegative",
        ),
        sa.CheckConstraint(
            "rows_done <= rows_total AND entities_done <= entities_total "
            "AND images_done <= images_total",
            name="ck_se_import_jobs_counters_bounded",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "requested_by", "idempotency_key", name="uq_se_import_jobs_idempotency"
        ),
    )
    op.create_index(
        "idx_se_import_jobs_user_created",
        "special_equipment_import_jobs",
        ["requested_by", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "idx_se_import_jobs_recovery",
        "special_equipment_import_jobs",
        ["status", "lease_until"],
        postgresql_where=sa.text(
            "status IN ('uploaded', 'validating_file', 'validating_data', "
            "'transferring_images', 'applying', 'failed_retryable')"
        ),
    )

    op.create_table(
        "special_equipment_import_upload_parts",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("byte_start", sa.BigInteger(), nullable=False),
        sa.Column("byte_end", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("storage_etag", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'received'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
            "status IN ('received', 'failed')", name="ck_se_import_parts_status"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["special_equipment_import_jobs.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "part_number"),
        sa.UniqueConstraint(
            "job_id", "byte_start", name="uq_se_import_parts_job_start"
        ),
    )

    op.create_table(
        "special_equipment_import_issues",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("sheet_code", sa.String(length=100), nullable=False),
        sa.Column("row_number", sa.BigInteger(), nullable=True),
        sa.Column("column_name", sa.String(length=100), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("raw_value_preview", sa.String(length=300), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("external_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("sequence > 0", name="ck_se_import_issues_sequence"),
        sa.CheckConstraint(
            "severity IN ('error', 'warning')", name="ck_se_import_issues_severity"
        ),
        sa.CheckConstraint(
            "row_number IS NULL OR row_number > 0",
            name="ck_se_import_issues_row_number",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["special_equipment_import_jobs.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "sequence"),
    )
    op.create_index(
        "idx_se_import_issues_severity",
        "special_equipment_import_issues",
        ["job_id", "severity", "sequence"],
    )
    op.create_index(
        "idx_se_import_issues_row",
        "special_equipment_import_issues",
        ["job_id", "sheet_code", "row_number", "sequence"],
    )

    op.create_table(
        "special_equipment_import_staged_media",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("owner_kind", sa.String(length=20), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'staged'"),
            nullable=False,
        ),
        sa.Column("cleanup_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("referenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "owner_kind IN ('category', 'product')",
            name="ck_se_import_staged_media_owner_kind",
        ),
        sa.CheckConstraint(
            "status IN ('staged', 'referenced', 'deleted')",
            name="ck_se_import_staged_media_status",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["special_equipment_import_jobs.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "storage_key"),
    )
    op.create_index(
        "idx_se_import_staged_media_cleanup",
        "special_equipment_import_staged_media",
        ["status", "cleanup_after"],
    )
    op.create_index(
        "idx_se_import_staged_media_storage_key",
        "special_equipment_import_staged_media",
        ["storage_key", "status"],
    )

    op.create_table(
        "special_equipment_external_refs",
        sa.Column("source_code", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_seen_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_seen_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_type IN ('category', 'manufacturer', 'attribute', "
            "'product', 'product_image')",
            name="ck_se_external_refs_entity_type",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_job_id"],
            ["special_equipment_import_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_job_id"],
            ["special_equipment_import_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("source_code", "entity_type", "external_key"),
        sa.UniqueConstraint(
            "source_code",
            "entity_type",
            "entity_id",
            name="uq_se_external_refs_source_entity",
        ),
    )
    op.create_index(
        "uq_se_external_refs_owned_entity",
        "special_equipment_external_refs",
        ["entity_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text("entity_type IN ('product', 'product_image')"),
    )

    op.create_table(
        "special_equipment_catalog_state",
        sa.Column("singleton", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "revision", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("singleton", name="ck_se_catalog_state_singleton"),
        sa.CheckConstraint("revision >= 0", name="ck_se_catalog_state_revision"),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("singleton"),
    )
    op.execute(
        sa.text(
            "INSERT INTO special_equipment_catalog_state (singleton, revision) "
            "VALUES (TRUE, 0)"
        )
    )


def downgrade() -> None:
    op.drop_table("special_equipment_catalog_state")
    op.drop_index(
        "uq_se_external_refs_owned_entity",
        table_name="special_equipment_external_refs",
    )
    op.drop_table("special_equipment_external_refs")
    op.drop_index(
        "idx_se_import_staged_media_storage_key",
        table_name="special_equipment_import_staged_media",
    )
    op.drop_index(
        "idx_se_import_staged_media_cleanup",
        table_name="special_equipment_import_staged_media",
    )
    op.drop_table("special_equipment_import_staged_media")
    op.drop_index(
        "idx_se_import_issues_row", table_name="special_equipment_import_issues"
    )
    op.drop_index(
        "idx_se_import_issues_severity", table_name="special_equipment_import_issues"
    )
    op.drop_table("special_equipment_import_issues")
    op.drop_table("special_equipment_import_upload_parts")
    op.drop_index(
        "idx_se_import_jobs_recovery", table_name="special_equipment_import_jobs"
    )
    op.drop_index(
        "idx_se_import_jobs_user_created", table_name="special_equipment_import_jobs"
    )
    op.drop_table("special_equipment_import_jobs")
