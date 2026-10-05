"""Add append-only LCA status history read model.

Revision ID: 004
Revises: 003
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Any

from infrastructure.clickhouse import get_clickhouse_client

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    client: Any = get_clickhouse_client()
    client.query(
        """
        CREATE TABLE IF NOT EXISTS dwh_lca_status_history (
            event_id               UUID,
            lca_id                 UUID,
            application_id         Nullable(UUID),
            old_status             Nullable(String),
            new_status             String,
            changed_at             DateTime64(3, 'UTC'),
            changed_by             Nullable(UUID),
            reason                 Nullable(String),
            application_created_at Nullable(DateTime64(3, 'UTC')),
            lca_created_at         DateTime64(3, 'UTC'),
            dealer_company_id      Nullable(UUID),
            distributor_id         Nullable(UUID),
            leasing_company_id     Nullable(UUID),
            is_baseline            UInt8 DEFAULT 0,
            ingested_at            DateTime64(3, 'UTC')
        ) ENGINE = ReplacingMergeTree(ingested_at)
        PARTITION BY toYYYYMM(changed_at)
        ORDER BY (lca_id, changed_at, event_id)
        """
    )


def downgrade() -> None:
    client: Any = get_clickhouse_client()
    client.query("DROP TABLE IF EXISTS dwh_lca_status_history")
