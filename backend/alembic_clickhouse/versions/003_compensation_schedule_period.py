"""Add compensation schedule period to DWH.

Revision ID: 003
Revises: 002
Create Date: 2026-05-29 00:00:00
"""

from __future__ import annotations

from typing import Any

from infrastructure.clickhouse import get_clickhouse_client

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    client: Any = get_clickhouse_client()
    client.query(
        """
        ALTER TABLE dwh_compensations
        ADD COLUMN IF NOT EXISTS payment_schedule_period Nullable(String)
        AFTER payment_schedule_type
        """
    )
    client.query(
        """
        ALTER TABLE dwh_compensations
        UPDATE
            payment_schedule_type = 'reporting_period',
            payment_schedule_period = 'two_months'
        WHERE payment_schedule_type = 'reporting_period_2'
        """
    )
    client.query(
        """
        ALTER TABLE dwh_compensations
        UPDATE
            payment_schedule_type = 'reporting_period',
            payment_schedule_period = 'quarter'
        WHERE payment_schedule_type = 'reporting_period_3'
        """
    )


def downgrade() -> None:
    client: Any = get_clickhouse_client()
    client.query(
        """
        ALTER TABLE dwh_compensations
        UPDATE payment_schedule_type = 'reporting_period_2'
        WHERE payment_schedule_type = 'reporting_period'
          AND payment_schedule_period = 'two_months'
        """
    )
    client.query(
        """
        ALTER TABLE dwh_compensations
        UPDATE payment_schedule_type = 'reporting_period_3'
        WHERE payment_schedule_type = 'reporting_period'
          AND payment_schedule_period = 'quarter'
        """
    )
    client.query(
        """
        ALTER TABLE dwh_compensations
        DROP COLUMN IF EXISTS payment_schedule_period
        """
    )
