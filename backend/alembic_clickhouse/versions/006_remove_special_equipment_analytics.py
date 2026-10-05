"""Remove retired special-equipment analytical tables.

Revision ID: 006
Revises: 005
Create Date: 2026-07-18
"""

from __future__ import annotations

import re
from typing import Any

from infrastructure.clickhouse import get_clickhouse_client
from infrastructure.clickhouse_dwh import _DATA_MARTS, _DWH_TABLES

revision = "006"
down_revision = "005"
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
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _drop_staging_tables(client: Any, mart: str) -> None:
    prefix = f"{mart}__rebuild"
    result = client.query(
        "SELECT name FROM system.tables "
        "WHERE database = currentDatabase() "
        "AND startsWith(name, {prefix:String})",
        parameters={"prefix": prefix},
    )
    for row in getattr(result, "result_rows", []):
        table_name = str(row[0])
        if not table_name.startswith(prefix) or not _SAFE_IDENTIFIER.fullmatch(table_name):
            continue
        client.query(f"DROP TABLE IF EXISTS {table_name}")


def upgrade() -> None:
    client: Any = get_clickhouse_client()
    for table in reversed(_MARTS):
        _drop_staging_tables(client, table)
        client.query(f"DROP TABLE IF EXISTS {table}")
    for table in reversed(_SOURCE_TABLES):
        client.query(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    client: Any = get_clickhouse_client()
    for table in _SOURCE_TABLES:
        client.query(_DWH_TABLES[table])
    for table in _MARTS:
        client.query(_DATA_MARTS[table])
