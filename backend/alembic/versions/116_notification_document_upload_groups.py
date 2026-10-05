"""Durable ten-minute groups of requested-document upload notifications.

Revision ID: 116
Revises: 115
"""

import sqlalchemy as sa
from alembic import op

revision: str = "116"
down_revision: str = "115"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "notification_document_upload_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("leasing_company_id", sa.Uuid(), nullable=False),
        sa.Column("request_batch_id", sa.Uuid(), nullable=False),
        sa.Column("first_event_id", sa.Uuid(), nullable=False),
        sa.Column("request_number", sa.String(100), nullable=False),
        sa.Column("first_upload_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("first_event_id"),
        sa.ForeignKeyConstraint(["application_id"], ["leasing_applications.id"]),
        sa.ForeignKeyConstraint(["leasing_company_id"], ["leasing_companies.id"]),
        sa.ForeignKeyConstraint(
            ["first_event_id"], ["notification_event_receipts.event_id"]
        ),
        sa.CheckConstraint(
            "closes_at = first_upload_at + interval '10 minutes'",
            name="ck_notification_document_group_window",
        ),
    )
    op.create_index(
        "ix_notification_document_groups_due",
        "notification_document_upload_groups",
        ["closes_at"],
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_index(
        "ix_notification_document_groups_scope",
        "notification_document_upload_groups",
        ["application_id", "leasing_company_id", "request_batch_id", "first_upload_at"],
    )
    op.create_table(
        "notification_document_upload_members",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(["event_id"], ["notification_event_receipts.event_id"]),
        sa.ForeignKeyConstraint(
            ["group_id"], ["notification_document_upload_groups.id"]
        ),
    )
    op.create_index(
        "ix_notification_document_members_group",
        "notification_document_upload_members",
        ["group_id"],
    )


def downgrade() -> None:
    # Existing inbox/outbox/receipt history is deliberately not modified.
    op.drop_index(
        "ix_notification_document_members_group",
        table_name="notification_document_upload_members",
    )
    op.drop_table("notification_document_upload_members")
    op.drop_index(
        "ix_notification_document_groups_scope",
        table_name="notification_document_upload_groups",
    )
    op.drop_index(
        "ix_notification_document_groups_due",
        table_name="notification_document_upload_groups",
    )
    op.drop_table("notification_document_upload_groups")
