"""sopd partial revocations

Revision ID: 056
Revises: 055
Create Date: 2026-06-18 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "056"
down_revision: str | None = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sopd_revoke_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signature_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "selected_leasing_company_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "revoked_leasing_company_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "revoked_contractor_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "excluded_contractor_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("operators_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("document_s3_key", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_ip", postgresql.INET(), nullable=True),
        sa.Column("revoke_user_agent", sa.String(length=512), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_sopd_revoke_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["leasing_applications.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["signature_request_id"],
            ["signature_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sopd_revoke_requests_signature_request_id",
        "sopd_revoke_requests",
        ["signature_request_id"],
    )
    op.create_index(
        "idx_sopd_revoke_requests_status",
        "sopd_revoke_requests",
        ["status"],
    )
    op.create_index(
        "idx_sopd_revoke_requests_user_id",
        "sopd_revoke_requests",
        ["user_id"],
    )

    op.create_table(
        "sopd_revoked_operators",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoke_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signature_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operator_type", sa.String(length=32), nullable=False),
        sa.Column("leasing_company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contractor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operator_name", sa.String(length=255), nullable=False),
        sa.Column("operator_inn", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operator_type IN ('leasing_company', 'contractor')",
            name="ck_sopd_revoked_operators_type",
        ),
        sa.ForeignKeyConstraint(
            ["contractor_id"], ["contractors.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["leasing_company_id"], ["leasing_companies.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["revoke_request_id"],
            ["sopd_revoke_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signature_request_id"],
            ["signature_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signature_request_id",
            "operator_type",
            "contractor_id",
            name="uq_sopd_revoked_operators_contractor",
        ),
        sa.UniqueConstraint(
            "signature_request_id",
            "operator_type",
            "leasing_company_id",
            name="uq_sopd_revoked_operators_lc",
        ),
    )
    op.create_index(
        "idx_sopd_revoked_operators_signature_request_id",
        "sopd_revoked_operators",
        ["signature_request_id"],
    )
    op.create_index(
        "idx_sopd_revoked_operators_user_id",
        "sopd_revoked_operators",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_sopd_revoked_operators_user_id",
        table_name="sopd_revoked_operators",
    )
    op.drop_index(
        "idx_sopd_revoked_operators_signature_request_id",
        table_name="sopd_revoked_operators",
    )
    op.drop_table("sopd_revoked_operators")
    op.drop_index(
        "idx_sopd_revoke_requests_user_id",
        table_name="sopd_revoke_requests",
    )
    op.drop_index(
        "idx_sopd_revoke_requests_status",
        table_name="sopd_revoke_requests",
    )
    op.drop_index(
        "idx_sopd_revoke_requests_signature_request_id",
        table_name="sopd_revoke_requests",
    )
    op.drop_table("sopd_revoke_requests")
