"""SOPD passport snapshots.

Revision ID: 142
Revises: 141
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "142"
down_revision = "141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sopd_passport_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("application_id", UUID(as_uuid=True), sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signer_key", sa.String(255), nullable=False),
        sa.Column("signature_request_id", UUID(as_uuid=True), sa.ForeignKey("signature_requests.id", ondelete="CASCADE"), nullable=True),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recognition_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("recognition_confidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("draft_fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confirmed_fields", JSONB, nullable=True),
        sa.Column("has_unsaved_changes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("application_id", "signer_key", name="uq_sopd_passport_snapshot_signer"),
        sa.UniqueConstraint("signature_request_id", name="uq_sopd_passport_snapshot_request"),
    )
    op.create_index("idx_sopd_passport_snapshots_request", "sopd_passport_snapshots", ["signature_request_id"])


def downgrade() -> None:
    op.drop_index("idx_sopd_passport_snapshots_request", table_name="sopd_passport_snapshots")
    op.drop_table("sopd_passport_snapshots")
