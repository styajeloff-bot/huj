"""Support M2M targeting and compensation templates.

Revision ID: 039
Revises: 038
Create Date: 2026-05-20 14:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def _uuid_pk_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("GEN_RANDOM_UUID()"),
        nullable=False,
    )


def _drop_legacy_compensation_enum_values() -> None:
    op.execute("ALTER TABLE compensations ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE compensation_status RENAME TO compensation_status_old")
    op.execute(
        """CREATE TYPE compensation_status AS ENUM (
            'under_review', 'accepted', 'rejected', 'paid', 'overdue', 'cancelled'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN status TYPE compensation_status
            USING status::text::compensation_status"""
    )
    op.execute("ALTER TABLE compensations ALTER COLUMN status SET DEFAULT 'under_review'")
    op.execute("DROP TYPE compensation_status_old")

    op.execute("ALTER TYPE calculation_base RENAME TO calculation_base_old")
    op.execute(
        """CREATE TYPE calculation_base AS ENUM (
            'base_price', 'special_price', 'dealer_cost',
            'application_price', 'down_payment', 'support_amount'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN calculation_base TYPE calculation_base
            USING calculation_base::text::calculation_base"""
    )
    op.execute(
        """ALTER TABLE compensation_templates
            ALTER COLUMN calculation_base TYPE calculation_base
            USING calculation_base::text::calculation_base"""
    )
    op.execute("DROP TYPE calculation_base_old")

    op.execute("ALTER TABLE compensations ALTER COLUMN payment_schedule_type DROP DEFAULT")
    op.execute(
        "ALTER TABLE compensation_templates ALTER COLUMN payment_schedule_type DROP DEFAULT"
    )
    op.execute("ALTER TYPE payment_schedule_type RENAME TO payment_schedule_type_old")
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
    op.execute("ALTER TABLE compensations ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'")
    op.execute(
        "ALTER TABLE compensation_templates ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'"
    )
    op.execute("DROP TYPE payment_schedule_type_old")


def _restore_legacy_compensation_enum_values() -> None:
    op.execute("ALTER TABLE compensations ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE compensation_status RENAME TO compensation_status_new")
    op.execute(
        """CREATE TYPE compensation_status AS ENUM (
            'pending', 'under_review', 'accepted', 'rejected',
            'paid', 'overdue', 'cancelled'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN status TYPE compensation_status
            USING status::text::compensation_status"""
    )
    op.execute("ALTER TABLE compensations ALTER COLUMN status SET DEFAULT 'pending'")
    op.execute("DROP TYPE compensation_status_new")

    op.execute("ALTER TYPE calculation_base RENAME TO calculation_base_new")
    op.execute(
        """CREATE TYPE calculation_base AS ENUM (
            'base_price', 'special_price', 'dealer_cost',
            'application_price', 'down_payment', 'support_amount'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN calculation_base TYPE calculation_base
            USING calculation_base::text::calculation_base"""
    )
    op.execute("DROP TYPE calculation_base_new")

    op.execute("ALTER TABLE compensations ALTER COLUMN payment_schedule_type DROP DEFAULT")
    op.execute("ALTER TYPE payment_schedule_type RENAME TO payment_schedule_type_new")
    op.execute(
        """CREATE TYPE payment_schedule_type AS ENUM (
            'fixed_date', 'days_count', 'monthly', 'weekly', 'quarterly',
            'reporting_period', 'reporting_period_2', 'reporting_period_3'
        )"""
    )
    op.execute(
        """ALTER TABLE compensations
            ALTER COLUMN payment_schedule_type TYPE payment_schedule_type
            USING payment_schedule_type::text::payment_schedule_type"""
    )
    op.execute("ALTER TABLE compensations ALTER COLUMN payment_schedule_type SET DEFAULT 'days_count'")
    op.execute("DROP TYPE payment_schedule_type_new")


def upgrade() -> None:
    op.execute("ALTER TYPE compensation_status ADD VALUE IF NOT EXISTS 'under_review'")
    op.execute("ALTER TYPE compensation_status ADD VALUE IF NOT EXISTS 'accepted'")
    op.execute("ALTER TYPE compensation_status ADD VALUE IF NOT EXISTS 'rejected'")
    op.execute("ALTER TYPE recipient_type ADD VALUE IF NOT EXISTS 'client'")
    op.execute("ALTER TYPE payment_schedule_type ADD VALUE IF NOT EXISTS 'reporting_period'")
    op.execute("ALTER TYPE payment_schedule_type ADD VALUE IF NOT EXISTS 'reporting_period_2'")
    op.execute("ALTER TYPE payment_schedule_type ADD VALUE IF NOT EXISTS 'reporting_period_3'")
    op.execute("COMMIT")
    op.create_table(
        "support_program_marks",
        sa.Column(
            "support_program_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("mark_id", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["mark_id"],
            ["mark.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["support_program_id"],
            ["support_programs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("support_program_id", "mark_id"),
    )
    op.create_index(
        "idx_support_program_marks_mark",
        "support_program_marks",
        ["mark_id"],
    )
    op.create_index(
        "idx_support_program_marks_program",
        "support_program_marks",
        ["support_program_id"],
    )

    op.create_table(
        "support_program_distributors",
        sa.Column(
            "support_program_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("distributor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["distributor_id"],
            ["distributors.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["support_program_id"],
            ["support_programs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("support_program_id", "distributor_id"),
    )
    op.create_index(
        "idx_support_program_distributors_distributor",
        "support_program_distributors",
        ["distributor_id"],
    )
    op.create_index(
        "idx_support_program_distributors_program",
        "support_program_distributors",
        ["support_program_id"],
    )

    op.create_table(
        "application_applied_supports",
        _uuid_pk_column("id"),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("support_program_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "support_type",
            postgresql.ENUM(
                "down_payment_compensation",
                "vehicle_discount_dealer_compensation",
                "vehicle_discount_dealer_invoice",
                "leasing_interest_compensation",
                name="support_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "support_params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("main_payer", sa.String(length=50), nullable=True),
        sa.Column(
            "base_amount",
            sa.Numeric(15, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "support_amount",
            sa.Numeric(15, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["leasing_applications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["support_program_id"],
            ["support_programs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_application_applied_supports_application",
        "application_applied_supports",
        ["application_id"],
    )
    op.create_index(
        "idx_application_applied_supports_program",
        "application_applied_supports",
        ["support_program_id"],
    )
    op.create_index(
        "idx_application_applied_supports_vehicle",
        "application_applied_supports",
        ["vehicle_id"],
    )

    op.create_table(
        "compensation_templates",
        _uuid_pk_column("id"),
        sa.Column(
            "support_program_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "payer",
            postgresql.ENUM(
                "distributor",
                "dealer",
                "carcraft",
                "minpromtorg",
                "client",
                name="payer_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "recipient",
            postgresql.ENUM(
                "leasing_company",
                "dealer",
                "carcraft",
                "client",
                name="recipient_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "calculation_base",
            postgresql.ENUM(
                "base_price",
                "special_price",
                "dealer_cost",
                "application_price",
                "down_payment",
                "support_amount",
                name="calculation_base",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "value_type",
            postgresql.ENUM("percent", "sum", name="compensation_value_type", create_type=False),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(15, 2), nullable=False),
        sa.Column("min_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("max_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("min_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column(
            "payment_schedule_type",
            postgresql.ENUM(
                "fixed_date",
                "days_count",
                "weekly",
                "quarterly",
                "reporting_period",
                "reporting_period_2",
                "reporting_period_3",
                name="payment_schedule_type",
                create_type=False,
            ),
            server_default=sa.text("'days_count'"),
            nullable=False,
        ),
        sa.Column("payment_schedule_value", sa.String(length=50), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["support_program_id"],
            ["support_programs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_compensation_templates_support",
        "compensation_templates",
        ["support_program_id"],
    )

    op.add_column(
        "leasing_application_calculations",
        sa.Column("selected_support", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "leasing_application_calculations",
        sa.Column("support_per_vehicle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "leasing_application_calculations",
        sa.Column("support_per_program", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "leasing_application_calculations",
        sa.Column("support_program_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "leasing_application_calculations",
        sa.Column("calculations_per_vehicle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("compensations", sa.Column("acceptance_comment", sa.Text(), nullable=True))
    op.add_column("compensations", sa.Column("rejection_comment", sa.Text(), nullable=True))

    op.execute(
        """
        INSERT INTO support_program_marks (support_program_id, mark_id)
        SELECT id, mark_id
        FROM support_programs
        WHERE mark_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO support_program_distributors (support_program_id, distributor_id)
        SELECT id, distributor_id
        FROM support_programs
        WHERE distributor_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO compensation_templates (
            support_program_id, payer, recipient, calculation_base, value_type,
            value, min_amount, max_amount, min_percent, max_percent,
            payment_schedule_type, payment_schedule_value, comment, created_by,
            created_at, updated_at
        )
        SELECT
            applied_support_id,
            payer,
            recipient,
            calculation_base,
            value_type,
            value,
            min_amount,
            max_amount,
            min_percent,
            max_percent,
            CASE
                WHEN payment_schedule_type::text = 'monthly'
                    THEN 'reporting_period'::payment_schedule_type
                ELSE payment_schedule_type
            END,
            payment_schedule_value,
            comment,
            created_by,
            created_at,
            updated_at
        FROM compensations
        WHERE application_id IS NULL AND vehicle_id IS NULL
        """
    )
    op.execute(
        """
        DELETE FROM compensations
        WHERE application_id IS NULL AND vehicle_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE compensations
        SET status = 'under_review'::compensation_status
        WHERE status = 'pending'::compensation_status
        """
    )
    op.execute(
        """
        UPDATE compensations
        SET payment_schedule_type = 'reporting_period'::payment_schedule_type
        WHERE payment_schedule_type = 'monthly'::payment_schedule_type
        """
    )
    op.alter_column(
        "compensations",
        "status",
        server_default=sa.text("'under_review'"),
    )
    _drop_legacy_compensation_enum_values()

    op.execute(
        """
        DO $$
        DECLARE
            rec RECORD;
            snapshot_id UUID;
        BEGIN
            FOR rec IN
                SELECT DISTINCT
                    c.application_id,
                    c.vehicle_id,
                    c.applied_support_id AS support_program_id,
                    sp.name,
                    sp.support_type,
                    COALESCE(sp.support_params, '{}'::jsonb) AS support_params,
                    sp.starts_at,
                    sp.ends_at,
                    COALESCE(lac.down_payment_support, 0) AS support_amount,
                    COALESCE(c.calculation_base_amount, 0) AS base_amount
                FROM compensations c
                JOIN support_programs sp ON sp.id = c.applied_support_id
                LEFT JOIN leasing_application_calculations lac
                    ON lac.leasing_application_id = c.application_id
                WHERE c.application_id IS NOT NULL
            LOOP
                INSERT INTO application_applied_supports (
                    application_id, vehicle_id, support_program_id, name,
                    support_type, support_params, starts_at, ends_at,
                    base_amount, support_amount
                )
                VALUES (
                    rec.application_id, rec.vehicle_id, rec.support_program_id,
                    rec.name, rec.support_type, rec.support_params,
                    rec.starts_at, rec.ends_at, rec.base_amount, rec.support_amount
                )
                RETURNING id INTO snapshot_id;

                UPDATE compensations
                SET applied_support_id = snapshot_id
                WHERE application_id = rec.application_id
                  AND applied_support_id = rec.support_program_id
                  AND vehicle_id IS NOT DISTINCT FROM rec.vehicle_id;
            END LOOP;
        END $$;
        """
    )
    op.create_foreign_key(
        "fk_compensations_applied_support_snapshot",
        "compensations",
        "application_applied_supports",
        ["applied_support_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_compensations_applied_support_snapshot",
        "compensations",
        type_="foreignkey",
    )
    op.drop_index("idx_compensation_templates_support", table_name="compensation_templates")
    op.drop_table("compensation_templates")
    _restore_legacy_compensation_enum_values()
    op.drop_column("compensations", "rejection_comment")
    op.drop_column("compensations", "acceptance_comment")
    op.drop_column("leasing_application_calculations", "calculations_per_vehicle")
    op.drop_column("leasing_application_calculations", "support_program_details")
    op.drop_column("leasing_application_calculations", "support_per_program")
    op.drop_column("leasing_application_calculations", "support_per_vehicle")
    op.drop_column("leasing_application_calculations", "selected_support")
    op.drop_index(
        "idx_application_applied_supports_vehicle",
        table_name="application_applied_supports",
    )
    op.drop_index(
        "idx_application_applied_supports_program",
        table_name="application_applied_supports",
    )
    op.drop_index(
        "idx_application_applied_supports_application",
        table_name="application_applied_supports",
    )
    op.drop_table("application_applied_supports")
    op.drop_index(
        "idx_support_program_distributors_program",
        table_name="support_program_distributors",
    )
    op.drop_index(
        "idx_support_program_distributors_distributor",
        table_name="support_program_distributors",
    )
    op.drop_table("support_program_distributors")
    op.drop_index("idx_support_program_marks_program", table_name="support_program_marks")
    op.drop_index("idx_support_program_marks_mark", table_name="support_program_marks")
    op.drop_table("support_program_marks")
