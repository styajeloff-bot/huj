"""UUID migration for DWH tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-19 22:00:00

Converts all Int32/UInt32 ID columns to UUID in DWH tables,
data marts, and ClickHouse support tables.
"""

import logging
from typing import Any

from infrastructure.clickhouse import get_clickhouse_client

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.clickhouse")

_DWH_TABLES = [
    "dwh_leasing_company_applications",
    "dwh_leasing_proposals",
    "dwh_documents",
    "dwh_vehicles",
    "dwh_application_vehicles",
    "dwh_companies",
    "dwh_users",
    "dwh_purchase_orders",
    "dwh_calculations",
    "dwh_questionnaires",
    "dwh_exchange_requests",
    "dwh_exchange_bids",
    "dwh_support_programs",
    "dwh_compensations",
]

_DATA_MARTS = [
    "dm_lk_daily_metrics",
    "dm_lk_application_funnel",
    "dm_lk_proposals",
    "dm_lk_financial_pipeline",
]

_MATERIALIZED_VIEWS = [
    "mv_dm_lk_daily_metrics",
    "mv_dm_lk_application_funnel",
    "mv_dm_lk_proposals",
    "mv_dm_lk_financial_pipeline",
]


def upgrade() -> None:
    client: Any = get_clickhouse_client()

    # Drop materialized views first (they depend on tables)
    for mv in _MATERIALIZED_VIEWS:
        try:
            client.query(f"DROP VIEW IF EXISTS {mv}")
            logger.info("dropped mv=%s", mv)
        except Exception as exc:
            logger.warning("drop_mv_failed mv=%s err=%s", mv, exc)

    # Drop data mart tables
    for dm in _DATA_MARTS:
        try:
            client.query(f"DROP TABLE IF EXISTS {dm}")
            logger.info("dropped mart=%s", dm)
        except Exception as exc:
            logger.warning("drop_mart_failed mart=%s err=%s", dm, exc)

    # Drop DWH source tables
    for table in _DWH_TABLES:
        try:
            client.query(f"DROP TABLE IF EXISTS {table}")
            logger.info("dropped dwh=%s", table)
        except Exception as exc:
            logger.warning("drop_dwh_failed table=%s err=%s", table, exc)

    # Drop support tables
    for table in ("auth_audit_log",):
        try:
            client.query(f"DROP TABLE IF EXISTS {table}")
            logger.info("dropped support=%s", table)
        except Exception as exc:
            logger.warning("drop_support_failed table=%s err=%s", table, exc)

    # Recreate everything with UUID types
    from infrastructure.clickhouse import ensure_tables as _ensure_tables

    _ensure_tables()
    logger.info("uuid_migration_complete")


def downgrade() -> None:
    # Downgrade is not supported — data would be lost.
    # The previous revision (001) created tables with Int32/UInt32 IDs.
    # To downgrade, re-run 001_revision's upgrade (it uses CREATE TABLE IF NOT EXISTS
    # so it would need manual intervention to DROP UUID tables first).
    logger.warning(
        "downgrade_unsupported dwh_uuid_migration — "
        "manually DROP and recreate with 001 revision if needed"
    )
