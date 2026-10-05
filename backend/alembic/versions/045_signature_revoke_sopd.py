"""Add СОПД revoke audit fields.

Revision ID: 045
Revises: 044
Create Date: 2026-05-27 14:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "045"
down_revision: str | None = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signature_requests",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "signature_requests",
        sa.Column(
            "revoke_requested_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "signature_requests",
        sa.Column("revoke_ip", postgresql.INET(), nullable=True),
    )
    op.add_column(
        "signature_requests",
        sa.Column("revoke_user_agent", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "idx_signature_requests_status_revoked",
        "signature_requests",
        ["status"],
        postgresql_where=sa.text("status = 'revoked'"),
    )
    op.execute(
        "ALTER TABLE signature_requests "
        "DROP CONSTRAINT IF EXISTS ck_signature_requests_status"
    )
    op.create_check_constraint(
        "ck_signature_requests_status",
        "signature_requests",
        "status IN ('pending', 'signed_electronic', 'signed_physical', "
        "'cancelled', 'revoked')",
    )

    op.add_column(
        "verification_codes",
        sa.Column("purpose", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "verification_codes",
        sa.Column("entity_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "verification_codes",
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "verification_codes",
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_index(
        "idx_verification_codes_purpose_entity",
        "verification_codes",
        ["purpose", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_verification_codes_purpose_entity",
        table_name="verification_codes",
    )
    op.drop_column("verification_codes", "failed_attempts")
    op.drop_column("verification_codes", "used_at")
    op.drop_column("verification_codes", "entity_id")
    op.drop_column("verification_codes", "purpose")

    op.drop_index(
        "idx_signature_requests_status_revoked",
        table_name="signature_requests",
    )
    op.execute(
        "ALTER TABLE signature_requests "
        "DROP CONSTRAINT IF EXISTS ck_signature_requests_status"
    )
    op.create_check_constraint(
        "ck_signature_requests_status",
        "signature_requests",
        "status IN ('pending', 'signed_electronic', "
        "'signed_physical', 'cancelled')",
    )
    op.drop_column("signature_requests", "revoke_user_agent")
    op.drop_column("signature_requests", "revoke_ip")
    op.drop_column("signature_requests", "revoke_requested_at")
    op.drop_column("signature_requests", "revoked_at")
