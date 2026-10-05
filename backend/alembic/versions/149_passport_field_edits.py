"""Preserve per-field passport corrections for questionnaire #22286."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "149"
down_revision = "148"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sopd_passport_snapshots", sa.Column("edited_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.execute("""
        UPDATE sopd_passport_snapshots s SET edited_fields = COALESCE((
            SELECT jsonb_agg(key) FROM jsonb_each(
                CASE WHEN s.has_unsaved_changes THEN s.draft_fields
                     ELSE COALESCE(s.confirmed_fields, s.draft_fields) END
            ) AS f(key, value)
            WHERE f.value IS DISTINCT FROM s.recognition_fields -> f.key
        ), '[]'::jsonb)
    """)


def downgrade():
    op.drop_column("sopd_passport_snapshots", "edited_fields")
