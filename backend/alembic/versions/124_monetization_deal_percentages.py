"""Persist exact deal percentages and input modes without rewriting history."""

from alembic import op
import sqlalchemy as sa

revision = "124"
down_revision = "123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monetization_deal_participant_amounts",
        sa.Column("percent", sa.Numeric(38, 8), nullable=True),
    )
    op.add_column(
        "monetization_deal_participant_amounts",
        sa.Column("input_mode", sa.String(10), nullable=True),
    )
    op.create_check_constraint(
        "ck_monetization_amount_percent", "monetization_deal_participant_amounts",
        "percent IS NULL OR percent >= 0",
    )
    op.create_check_constraint(
        "ck_monetization_amount_input_mode", "monetization_deal_participant_amounts",
        "input_mode IS NULL OR input_mode IN ('percent','amount')",
    )
    op.create_check_constraint(
        "ck_monetization_amount_percent_input", "monetization_deal_participant_amounts",
        "input_mode IS DISTINCT FROM 'percent' OR (percent IS NOT NULL AND percent > 0)",
    )
    for field in ("old_percent", "new_percent"):
        op.add_column(
            "monetization_deal_adjustments",
            sa.Column(field, sa.Numeric(38, 8), nullable=True),
        )
    for field in ("old_input_mode", "new_input_mode"):
        op.add_column(
            "monetization_deal_adjustments",
            sa.Column(field, sa.String(10), nullable=True),
        )
    op.create_check_constraint(
        "ck_monetization_adjustment_percent", "monetization_deal_adjustments",
        "(old_percent IS NULL OR old_percent >= 0) AND (new_percent IS NULL OR new_percent >= 0)",
    )
    op.create_check_constraint(
        "ck_monetization_adjustment_input_mode", "monetization_deal_adjustments",
        "(old_input_mode IS NULL OR old_input_mode IN ('percent','amount')) AND (new_input_mode IS NULL OR new_input_mode IN ('percent','amount'))",
    )


def downgrade() -> None:
    for constraint in (
        "ck_monetization_adjustment_input_mode",
        "ck_monetization_adjustment_percent",
    ):
        op.drop_constraint(constraint, "monetization_deal_adjustments", type_="check")
    for field in ("new_input_mode", "old_input_mode", "new_percent", "old_percent"):
        op.drop_column("monetization_deal_adjustments", field)
    for constraint in (
        "ck_monetization_amount_percent_input",
        "ck_monetization_amount_input_mode",
        "ck_monetization_amount_percent",
    ):
        op.drop_constraint(
            constraint, "monetization_deal_participant_amounts", type_="check"
        )
    op.drop_column("monetization_deal_participant_amounts", "input_mode")
    op.drop_column("monetization_deal_participant_amounts", "percent")
