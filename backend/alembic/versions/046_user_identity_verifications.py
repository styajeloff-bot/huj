"""Add user identity verification attempts.

Revision ID: 046
Revises: 045
Create Date: 2026-06-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "046"
down_revision: str | None = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_identity_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("auth_req_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mobile_id_sub", sa.String(length=128), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("birthdate", sa.Date(), nullable=True),
        sa.Column("birthdate_match", sa.String(length=8), nullable=True),
        sa.Column("given_name", sa.String(length=255), nullable=True),
        sa.Column("middle_name", sa.String(length=255), nullable=True),
        sa.Column("family_name", sa.String(length=255), nullable=True),
        sa.Column("national_identifier_masked", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sms_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id"),
    )
    op.create_index(
        "idx_user_identity_verifications_auth_req_id",
        "user_identity_verifications",
        ["auth_req_id"],
    )
    op.create_index(
        "idx_user_identity_verifications_correlation_id",
        "user_identity_verifications",
        ["correlation_id"],
        unique=True,
    )
    op.create_index(
        "idx_user_identity_verifications_user_provider_status",
        "user_identity_verifications",
        ["user_id", "provider", "status"],
    )
    op.create_index(
        "idx_user_identity_verifications_user_verified_at",
        "user_identity_verifications",
        ["user_id", sa.text("verified_at DESC")],
        postgresql_where=sa.text("status = 'verified'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_user_identity_verifications_user_verified_at",
        table_name="user_identity_verifications",
        postgresql_where=sa.text("status = 'verified'"),
    )
    op.drop_index(
        "idx_user_identity_verifications_user_provider_status",
        table_name="user_identity_verifications",
    )
    op.drop_index(
        "idx_user_identity_verifications_correlation_id",
        table_name="user_identity_verifications",
    )
    op.drop_index(
        "idx_user_identity_verifications_auth_req_id",
        table_name="user_identity_verifications",
    )
    op.drop_table("user_identity_verifications")
