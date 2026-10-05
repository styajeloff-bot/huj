"""Add durable retention state for special-equipment import artifacts.

Revision ID: 076
Revises: 075
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "076"
down_revision: str | None = "075"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "artifact_cleanup_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "artifact_cleanup_lease_owner",
            sa.String(length=200),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "artifact_cleanup_lease_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "artifact_cleanup_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "artifact_cleanup_last_error",
            sa.String(length=1000),
            nullable=True,
        ),
    )
    op.add_column(
        "special_equipment_import_jobs",
        sa.Column(
            "artifacts_cleaned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_se_import_jobs_artifact_cleanup_status",
        "special_equipment_import_jobs",
        "artifact_cleanup_status IN ('pending', 'processing', 'completed')",
    )
    op.create_check_constraint(
        "ck_se_import_jobs_artifact_cleanup_attempts",
        "special_equipment_import_jobs",
        "artifact_cleanup_attempt_count >= 0",
    )
    op.create_check_constraint(
        "ck_se_import_jobs_artifact_cleanup_processing_lease",
        "special_equipment_import_jobs",
        "artifact_cleanup_status <> 'processing' "
        "OR (artifact_cleanup_lease_owner IS NOT NULL "
        "AND artifact_cleanup_lease_until IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_se_import_jobs_artifact_cleanup_completed_at",
        "special_equipment_import_jobs",
        "artifact_cleanup_status <> 'completed' OR artifacts_cleaned_at IS NOT NULL",
    )
    op.create_index(
        "idx_se_import_jobs_artifact_cleanup",
        "special_equipment_import_jobs",
        ["retain_until", "id"],
        unique=False,
        postgresql_where=sa.text(
            "retain_until IS NOT NULL "
            "AND artifact_cleanup_status IN ('pending', 'processing') "
            "AND status IN ('validation_failed', 'completed', "
            "'completed_with_warnings', 'failed', 'cancelled')"
        ),
    )
    op.create_index(
        "idx_se_import_jobs_projection_recovery",
        "special_equipment_import_jobs",
        ["lease_until", "id"],
        unique=False,
        postgresql_where=sa.text(
            "status IN ('completed', 'completed_with_warnings') "
            "AND projection_state IN ('pending', 'failed')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_se_import_jobs_projection_recovery",
        table_name="special_equipment_import_jobs",
    )
    op.drop_index(
        "idx_se_import_jobs_artifact_cleanup",
        table_name="special_equipment_import_jobs",
    )
    op.drop_constraint(
        "ck_se_import_jobs_artifact_cleanup_completed_at",
        "special_equipment_import_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_se_import_jobs_artifact_cleanup_processing_lease",
        "special_equipment_import_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_se_import_jobs_artifact_cleanup_attempts",
        "special_equipment_import_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_se_import_jobs_artifact_cleanup_status",
        "special_equipment_import_jobs",
        type_="check",
    )
    op.drop_column("special_equipment_import_jobs", "artifacts_cleaned_at")
    op.drop_column(
        "special_equipment_import_jobs", "artifact_cleanup_last_error"
    )
    op.drop_column(
        "special_equipment_import_jobs", "artifact_cleanup_attempt_count"
    )
    op.drop_column(
        "special_equipment_import_jobs", "artifact_cleanup_lease_until"
    )
    op.drop_column(
        "special_equipment_import_jobs", "artifact_cleanup_lease_owner"
    )
    op.drop_column("special_equipment_import_jobs", "artifact_cleanup_status")
