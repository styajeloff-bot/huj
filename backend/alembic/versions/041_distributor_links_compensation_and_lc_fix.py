"""Distributor links and compensation schedule period.

Squashes three migrations that previously all carried the revision id "041"
(``distributor_dealer_links`` table and ``payment_schedule_period`` columns)
into one linear revision. They had collided
on ``revision = "041"`` / ``down_revision = "040"``, which made Alembic raise
"Revision 041 is present more than once" and "Multiple head revisions are
present", aborting ``alembic upgrade head`` entirely.

Revision ID: 041
Revises: 040
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _create_distributor_dealer_links()
    _add_compensation_schedule_period()


def downgrade() -> None:
    _revert_compensation_schedule_period()
    op.drop_table("distributor_dealer_links")


# ---------------------------------------------------------------------------
# distributor_dealer_links
# ---------------------------------------------------------------------------
def _create_distributor_dealer_links() -> None:
    op.create_table(
        "distributor_dealer_links",
        sa.Column("distributor_company_id", sa.UUID(), nullable=False),
        sa.Column("dealer_company_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("distributor_company_id", "dealer_company_id"),
        sa.UniqueConstraint("dealer_company_id"),
        sa.ForeignKeyConstraint(
            ["distributor_company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dealer_company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
    )


# ---------------------------------------------------------------------------
# compensation payment_schedule_period
# ---------------------------------------------------------------------------
def _add_compensation_schedule_period() -> None:
    op.add_column(
        "compensations",
        sa.Column("payment_schedule_period", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "compensation_templates",
        sa.Column("payment_schedule_period", sa.String(length=20), nullable=True),
    )
    _normalize_legacy_schedule_values()
    _drop_legacy_payment_schedule_enum_values()
    op.alter_column(
        "support_programs",
        "is_active",
        server_default=sa.false(),
        existing_type=sa.Boolean(),
        existing_nullable=True,
    )


def _revert_compensation_schedule_period() -> None:
    _restore_legacy_payment_schedule_enum_values()
    _denormalize_legacy_schedule_values()
    op.alter_column(
        "support_programs",
        "is_active",
        server_default=sa.true(),
        existing_type=sa.Boolean(),
        existing_nullable=True,
    )
    op.drop_column("compensation_templates", "payment_schedule_period")
    op.drop_column("compensations", "payment_schedule_period")


def _normalize_legacy_schedule_values() -> None:
    for table in ("compensations", "compensation_templates"):
        op.execute(
            f"""
            UPDATE {table}
            SET
                payment_schedule_period = CASE payment_schedule_type::text
                    WHEN 'reporting_period_2' THEN 'two_months'
                    WHEN 'reporting_period_3' THEN 'quarter'
                    ELSE payment_schedule_period
                END,
                payment_schedule_type = 'reporting_period'::payment_schedule_type
            WHERE payment_schedule_type::text IN (
                'reporting_period_2',
                'reporting_period_3'
            )
            """
        )


def _denormalize_legacy_schedule_values() -> None:
    for table in ("compensations", "compensation_templates"):
        op.execute(
            f"""
            UPDATE {table}
            SET payment_schedule_type = CASE payment_schedule_period
                WHEN 'two_months' THEN 'reporting_period_2'::payment_schedule_type
                WHEN 'quarter' THEN 'reporting_period_3'::payment_schedule_type
                ELSE payment_schedule_type
            END
            WHERE payment_schedule_type::text = 'reporting_period'
              AND payment_schedule_period IN ('two_months', 'quarter')
            """
        )


def _drop_legacy_payment_schedule_enum_values() -> None:
    op.execute("ALTER TABLE compensations ALTER COLUMN payment_schedule_type DROP DEFAULT")
    op.execute(
        "ALTER TABLE compensation_templates ALTER COLUMN payment_schedule_type DROP DEFAULT"
    )
    op.execute("ALTER TYPE payment_schedule_type RENAME TO payment_schedule_type_old")
    op.execute(
        """CREATE TYPE payment_schedule_type AS ENUM (
            'fixed_date', 'days_count', 'weekly', 'quarterly', 'reporting_period'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN payment_schedule_type TYPE payment_schedule_type
            USING payment_schedule_type::text::payment_schedule_type"""
    )
    op.execute(
        """ALTER TABLE compensation_templates
            ALTER COLUMN payment_schedule_type TYPE payment_schedule_type
            USING payment_schedule_type::text::payment_schedule_type"""
    )
    op.execute(
        "ALTER TABLE compensations ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'"
    )
    op.execute(
        "ALTER TABLE compensation_templates ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'"
    )
    op.execute("DROP TYPE payment_schedule_type_old")


def _restore_legacy_payment_schedule_enum_values() -> None:
    op.execute("ALTER TABLE compensations ALTER COLUMN payment_schedule_type DROP DEFAULT")
    op.execute(
        "ALTER TABLE compensation_templates ALTER COLUMN payment_schedule_type DROP DEFAULT"
    )
    op.execute("ALTER TYPE payment_schedule_type RENAME TO payment_schedule_type_new")
    op.execute(
        """CREATE TYPE payment_schedule_type AS ENUM (
            'fixed_date', 'days_count', 'weekly', 'quarterly',
            'reporting_period', 'reporting_period_2', 'reporting_period_3'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN payment_schedule_type TYPE payment_schedule_type
            USING payment_schedule_type::text::payment_schedule_type"""
    )
    op.execute(
        """ALTER TABLE compensation_templates
            ALTER COLUMN payment_schedule_type TYPE payment_schedule_type
            USING payment_schedule_type::text::payment_schedule_type"""
    )
    op.execute(
        "ALTER TABLE compensations ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'"
    )
    op.execute(
        "ALTER TABLE compensation_templates ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'"
    )
    op.execute("DROP TYPE payment_schedule_type_new")
