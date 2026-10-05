"""sopd operator snapshots

Revision ID: 055
Revises: 054
Create Date: 2026-06-18 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "055"
down_revision: str | None = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sopd_operator_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "signature_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("leasing_companies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("contractors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source",
            sa.String(length=64),
            server_default="application_selected_leasing_companies",
            nullable=False,
        ),
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
        sa.UniqueConstraint(
            "signature_request_id",
            name="uq_sopd_operator_snapshots_signature_request_id",
        ),
    )
    op.create_index(
        "idx_sopd_operator_snapshots_application_id",
        "sopd_operator_snapshots",
        ["application_id"],
    )
    op.create_index(
        "idx_sopd_operator_snapshots_user_id",
        "sopd_operator_snapshots",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_sopd_operator_snapshots_user_id",
        table_name="sopd_operator_snapshots",
    )
    op.drop_index(
        "idx_sopd_operator_snapshots_application_id",
        table_name="sopd_operator_snapshots",
    )
    op.drop_table("sopd_operator_snapshots")
