"""Persist Exchange support selection and compensation source.

Revision ID: 106
Revises: 105
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "106"
down_revision: str | None = "105"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    support_ids_column = sa.Column(
        "selected_support_ids",
        postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
        nullable=False,
        server_default=sa.text("'{}'::uuid[]"),
    )
    op.add_column("exchange_cart_items", support_ids_column)
    op.add_column(
        "exchange_requests",
        sa.Column(
            "selected_support_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
    )

    op.alter_column(
        "application_applied_supports",
        "application_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "application_applied_supports",
        sa.Column(
            "exchange_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "application_applied_supports",
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_application_applied_supports_exchange_request",
        "application_applied_supports",
        "exchange_requests",
        ["exchange_request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_application_applied_supports_exchange_request",
        "application_applied_supports",
        ["exchange_request_id"],
    )
    op.create_check_constraint(
        "ck_application_applied_supports_exactly_one_source",
        "application_applied_supports",
        "(application_id IS NULL) <> (exchange_request_id IS NULL)",
    )
    op.create_unique_constraint(
        "uq_application_applied_supports_exchange_program",
        "application_applied_supports",
        ["exchange_request_id", "support_program_id"],
    )

    op.add_column(
        "compensations",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'platform'"),
        ),
    )
    op.add_column(
        "compensations",
        sa.Column(
            "exchange_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_compensations_exchange_request",
        "compensations",
        "exchange_requests",
        ["exchange_request_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_compensations_exchange_request_id",
        "compensations",
        ["exchange_request_id"],
    )
    op.create_check_constraint(
        "ck_compensations_source",
        "compensations",
        "source IN ('platform', 'exchange')",
    )
    op.execute(
        """
        UPDATE compensations AS compensation
        SET application_id = applied.application_id
        FROM application_applied_supports AS applied
        WHERE compensation.applied_support_id = applied.id
          AND compensation.application_id IS NULL
          AND applied.application_id IS NOT NULL
        """
    )
    op.create_check_constraint(
        "ck_compensations_exchange_source_link",
        "compensations",
        "("
        "source = 'platform' AND application_id IS NOT NULL "
        "AND exchange_request_id IS NULL"
        ") OR ("
        "source = 'exchange' AND exchange_request_id IS NOT NULL "
        "AND application_id IS NULL"
        ")",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM application_applied_supports
                WHERE exchange_request_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade revision 103 while Exchange support snapshots exist';
            END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "ck_compensations_exchange_source_link",
        "compensations",
        type_="check",
    )
    op.drop_constraint(
        "ck_compensations_source",
        "compensations",
        type_="check",
    )
    op.drop_index(
        "idx_compensations_exchange_request_id",
        table_name="compensations",
    )
    op.drop_constraint(
        "fk_compensations_exchange_request",
        "compensations",
        type_="foreignkey",
    )
    op.drop_column("compensations", "exchange_request_id")
    op.drop_column("compensations", "source")

    op.drop_constraint(
        "uq_application_applied_supports_exchange_program",
        "application_applied_supports",
        type_="unique",
    )
    op.drop_constraint(
        "ck_application_applied_supports_exactly_one_source",
        "application_applied_supports",
        type_="check",
    )
    op.drop_index(
        "idx_application_applied_supports_exchange_request",
        table_name="application_applied_supports",
    )
    op.drop_constraint(
        "fk_application_applied_supports_exchange_request",
        "application_applied_supports",
        type_="foreignkey",
    )
    op.drop_column(
        "application_applied_supports",
        "exchange_request_id",
    )
    op.drop_column("application_applied_supports", "comment")
    op.alter_column(
        "application_applied_supports",
        "application_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.drop_column("exchange_requests", "selected_support_ids")
    op.drop_column("exchange_cart_items", "selected_support_ids")
