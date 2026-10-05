"""Add period validity to leasing calculator rates.

Revision ID: 065
Revises: 064
Create Date: 2026-07-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "065"
down_revision: str | None = "064"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("leasing_rates", sa.Column("date_from", sa.Date(), nullable=True))
    op.add_column("leasing_rates", sa.Column("date_to", sa.Date(), nullable=True))

    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY id ASC) AS rn
                FROM leasing_rates
            )
            UPDATE leasing_rates AS rate
            SET
                date_from = CASE
                    WHEN ordered.rn = 1 THEN CURRENT_DATE
                    ELSE (CURRENT_DATE - (ordered.rn::int * INTERVAL '1 day'))::date
                END,
                date_to = CASE
                    WHEN ordered.rn = 1 THEN NULL
                    ELSE (CURRENT_DATE - ((ordered.rn::int - 1) * INTERVAL '1 day'))::date
                END
            FROM ordered
            WHERE rate.id = ordered.id
            """
        )
    )

    op.alter_column("leasing_rates", "date_from", nullable=False)
    op.create_check_constraint(
        "ck_leasing_rates_valid_period",
        "leasing_rates",
        "date_to IS NULL OR date_to > date_from",
    )
    op.create_index(
        "idx_leasing_rates_period",
        "leasing_rates",
        ["date_from", "date_to"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_leasing_rates_current
        ON leasing_rates ((date_to IS NULL))
        WHERE date_to IS NULL
        """
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE leasing_rates
        ADD CONSTRAINT ex_leasing_rates_period_no_overlap
        EXCLUDE USING gist (
            daterange(date_from, COALESCE(date_to, 'infinity'::date), '[)') WITH &&
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE leasing_rates "
        "DROP CONSTRAINT IF EXISTS ex_leasing_rates_period_no_overlap"
    )
    op.drop_index("uq_leasing_rates_current", table_name="leasing_rates")
    op.drop_index("idx_leasing_rates_period", table_name="leasing_rates")
    op.drop_constraint(
        "ck_leasing_rates_valid_period",
        "leasing_rates",
        type_="check",
    )
    op.drop_column("leasing_rates", "date_to")
    op.drop_column("leasing_rates", "date_from")
