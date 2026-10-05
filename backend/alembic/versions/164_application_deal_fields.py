"""Add deal_date and deal_documents to leasing_applications.

Revision ID: 164
Revises: 163
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "164"
down_revision = "163"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leasing_applications",
        sa.Column("deal_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "leasing_applications",
        sa.Column("deal_documents", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leasing_applications", "deal_documents")
    op.drop_column("leasing_applications", "deal_date")
