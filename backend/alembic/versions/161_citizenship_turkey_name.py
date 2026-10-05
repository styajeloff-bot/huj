"""Correct Türkiye's controlled citizenship display name.

Revision ID: 161
Revises: 160
"""

from alembic import op
import sqlalchemy as sa

revision = "161"
down_revision = "160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE citizenship "
            "SET citizenship_name = 'Турция' "
            "WHERE code2 = 'TR' AND code3 = 'TUR'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE citizenship "
            "SET citizenship_name = 'Türkiye' "
            "WHERE code2 = 'TR' AND code3 = 'TUR'"
        )
    )
