"""Immutable company-card change history.

Revision ID: 155
Revises: 154
Create Date: 2026-10-01 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "162"
down_revision = "161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_change_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_display_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("action IN ('company_profile_saved', 'company_status_changed', 'distributor_brands_saved', 'leasing_contractors_saved')", name="ck_company_change_history_action"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_company_change_history_company"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_company_change_history_actor"),
    )
    op.create_index("idx_company_change_history_company_changed_id_desc", "company_change_history", ["company_id", sa.text("changed_at DESC"), sa.text("id DESC")])
    op.execute("""
        CREATE FUNCTION company_change_history_reject_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'company_change_history is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_company_change_history_append_only
        BEFORE UPDATE OR DELETE ON company_change_history
        FOR EACH ROW EXECUTE FUNCTION company_change_history_reject_mutation();
    """)


def downgrade() -> None:
    raise RuntimeError("Downgrade refused: company_change_history contains immutable audit data")
