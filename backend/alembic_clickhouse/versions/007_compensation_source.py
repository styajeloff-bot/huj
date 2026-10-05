"""Add platform or Exchange source to DWH compensations.

Revision ID: 007
Revises: 006
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import Any

from infrastructure.clickhouse import get_clickhouse_client

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    client: Any = get_clickhouse_client()
    client.query(
        """
        ALTER TABLE dwh_compensations
        ADD COLUMN IF NOT EXISTS exchange_request_id Nullable(UUID)
        AFTER application_id
        """
    )
    client.query(
        """
        ALTER TABLE dwh_compensations
        ADD COLUMN IF NOT EXISTS source String DEFAULT 'platform'
        AFTER exchange_request_id
        """
    )


def downgrade() -> None:
    client: Any = get_clickhouse_client()
    client.query(
        """
        ALTER TABLE dwh_compensations
        DROP COLUMN IF EXISTS source
        """
    )
    client.query(
        """
        ALTER TABLE dwh_compensations
        DROP COLUMN IF EXISTS exchange_request_id
        """
    )
