"""Version monetization rules without rewriting existing conditions or deals."""

from alembic import op
import sqlalchemy as sa

revision = "123"
down_revision = "122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monetization_programs",
        sa.Column("rules_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("monetization_programs", "rules_version", server_default="2")
    op.create_check_constraint(
        "ck_monetization_program_rules_version",
        "monetization_programs",
        "rules_version IN (1, 2)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_monetization_program_rules_version", "monetization_programs", type_="check"
    )
    op.drop_column("monetization_programs", "rules_version")
