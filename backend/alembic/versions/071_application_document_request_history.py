"""Persist readable, repeatable application document request history.

Revision ID: 071
Revises: 070
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "071"
down_revision: str | None = "070"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "application_document_requests",
        sa.Column("request_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "application_document_requests",
        sa.Column("display_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "application_document_requests",
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_application_document_requests_requested_by",
        "application_document_requests",
        "users",
        ["requested_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            """
            UPDATE application_document_requests AS request
            SET request_batch_id = request.id,
                display_name = COALESCE(
                    (
                        SELECT COALESCE(type.display_name, type.name)
                        FROM document_types AS type
                        WHERE type.type_code = request.document_type
                        LIMIT 1
                    ),
                    request.document_type
                )
            """
        )
    )

    op.alter_column(
        "application_document_requests",
        "request_batch_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "application_document_requests",
        "display_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.drop_constraint(
        "uq_application_document_requests",
        "application_document_requests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_application_document_requests_batch_type",
        "application_document_requests",
        ["request_batch_id", "document_type"],
    )
    op.create_index(
        "idx_application_document_requests_app_lc_requested_at",
        "application_document_requests",
        ["application_id", "leasing_company_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "idx_application_document_requests_batch_id",
        "application_document_requests",
        ["request_batch_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_application_document_requests_batch_id",
        table_name="application_document_requests",
    )
    op.drop_index(
        "idx_application_document_requests_app_lc_requested_at",
        table_name="application_document_requests",
    )
    op.drop_constraint(
        "uq_application_document_requests_batch_type",
        "application_document_requests",
        type_="unique",
    )
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY application_id,
                                        leasing_company_id,
                                        document_type
                           ORDER BY requested_at DESC NULLS LAST, id DESC
                       ) AS position
                FROM application_document_requests
            )
            DELETE FROM application_document_requests AS request
            USING ranked
            WHERE request.id = ranked.id
              AND ranked.position > 1
            """
        )
    )
    op.create_unique_constraint(
        "uq_application_document_requests",
        "application_document_requests",
        ["application_id", "leasing_company_id", "document_type"],
    )
    op.drop_constraint(
        "fk_application_document_requests_requested_by",
        "application_document_requests",
        type_="foreignkey",
    )
    op.drop_column("application_document_requests", "requested_by")
    op.drop_column("application_document_requests", "display_name")
    op.drop_column("application_document_requests", "request_batch_id")
