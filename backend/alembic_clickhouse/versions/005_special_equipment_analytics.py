"""Add special-equipment analytics projections, fact, and daily marts.

Revision ID: 005
Revises: 004
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Any

from infrastructure.clickhouse import get_clickhouse_client
from infrastructure.clickhouse_dwh import _DATA_MARTS, _DWH_TABLES

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

_SOURCE_TABLES = (
    "dwh_special_equipment_products",
    "dwh_special_equipment_categories",
    "fct_special_equipment_events",
)
_MARTS = (
    "dm_special_equipment_daily_funnel",
    "dm_special_equipment_product_daily",
    "dm_special_equipment_filter_daily",
    "dm_special_equipment_search_daily",
    "dm_special_equipment_catalog_quality_daily",
)


def upgrade() -> None:
    client: Any = get_clickhouse_client()
    for table in _SOURCE_TABLES:
        client.query(_DWH_TABLES[table])
    for table in _MARTS:
        client.query(_DATA_MARTS[table])


def downgrade() -> None:
    client: Any = get_clickhouse_client()
    for table in reversed(_MARTS):
        client.query(f"DROP TABLE IF EXISTS {table}")
        client.query(f"DROP TABLE IF EXISTS {table}__rebuild")
    for table in reversed(_SOURCE_TABLES):
        client.query(f"DROP TABLE IF EXISTS {table}")
