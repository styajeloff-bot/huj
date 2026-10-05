"""Preserve legacy trim matching while new conditions use registered trims."""

import sqlalchemy as sa
from alembic import op

revision = "167"
down_revision = "166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monetization_programs",
        sa.Column("vehicle_filter_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("monetization_programs", "vehicle_filter_version", server_default="2")
    op.create_check_constraint(
        "ck_monetization_program_vehicle_filter_version",
        "monetization_programs",
        "vehicle_filter_version IN (1, 2)",
    )
    op.alter_column(
        "monetization_programs", "trim",
        existing_type=sa.String(150), type_=sa.String(255),
    )


def downgrade() -> None:
    op.alter_column(
        "monetization_programs", "trim",
        existing_type=sa.String(255), type_=sa.String(150),
    )
    op.drop_constraint(
        "ck_monetization_program_vehicle_filter_version",
        "monetization_programs", type_="check",
    )
    op.drop_column("monetization_programs", "vehicle_filter_version")
