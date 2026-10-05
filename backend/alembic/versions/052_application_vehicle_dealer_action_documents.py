"""application vehicle dealer action documents

Revision ID: 052
Revises: 051
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_vehicle_dealer_action_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "application_vehicle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("application_vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=255), nullable=True),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_av_dealer_action_docs_application_vehicle_id",
        "application_vehicle_dealer_action_documents",
        ["application_vehicle_id"],
    )
    op.create_index(
        "idx_av_dealer_action_docs_created_at",
        "application_vehicle_dealer_action_documents",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_av_dealer_action_docs_created_at",
        table_name="application_vehicle_dealer_action_documents",
    )
    op.drop_index(
        "idx_av_dealer_action_docs_application_vehicle_id",
        table_name="application_vehicle_dealer_action_documents",
    )
    op.drop_table("application_vehicle_dealer_action_documents")
