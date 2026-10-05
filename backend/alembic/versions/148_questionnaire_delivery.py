"""Questionnaire delivery settings and application document titles (#22286)."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "148"
down_revision = "147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leasing_questionnaire_settings",
        sa.Column("leasing_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fields", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["leasing_company_id"], ["leasing_companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("leasing_company_id"),
    )
    op.add_column("application_documents", sa.Column("user_title", sa.String(255), nullable=True))
    op.execute(sa.text("""
        UPDATE application_documents AS ad SET user_title = left(d.file_name, 255)
        FROM documents AS d WHERE d.id = ad.document_id
    """))
    op.execute(sa.text("""
        UPDATE document_types SET display_name = 'Сведения о кредитах, займах и лизинге'
        WHERE type_code = 'loans_docs'
    """))


def downgrade() -> None:
    op.drop_column("application_documents", "user_title")
    op.drop_table("leasing_questionnaire_settings")
