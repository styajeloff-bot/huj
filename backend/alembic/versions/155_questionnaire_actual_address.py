"""Persist the explicit link between actual and legal company addresses."""

import sqlalchemy as sa
from alembic import op

revision = "155"
down_revision = "154_questionnaire_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_questionnaires",
        sa.Column(
            "actual_address_same_as_legal",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("application_questionnaires", "actual_address_same_as_legal")
