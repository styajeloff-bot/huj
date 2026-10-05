"""Serialized ClickHouse Alembic upgrades for event-worker startup.

Historically the event-worker created ClickHouse tables through
``ensure_dwh_tables()`` without advancing ``alembic_clickhouse``.  Existing
environments therefore have the revision-005 schema but no Alembic version
table.  Startup stamps that legacy baseline before applying forward
migrations, which avoids replaying the destructive UUID migration 002.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from infrastructure.clickhouse import get_clickhouse_client
from infrastructure.clickhouse_dwh import _RETIRED_DATA_MARTS, _RETIRED_DWH_TABLES
from infrastructure.database import AsyncSessionLocal

logger = logging.getLogger("carcraft-backend")

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_LEGACY_RUNTIME_BASELINE = "005"
_MIGRATION_LOCK_KEY = 21808006


def _alembic_config() -> Config:
    # A programmatic config deliberately has no config_file_name, so importing
    # Alembic's env.py does not replace the event-worker logging configuration.
    config = Config()
    config.set_main_option(
        "script_location",
        str(_BACKEND_ROOT / "alembic_clickhouse"),
    )
    return config


def _table_names(client: Any) -> set[str]:
    result = client.query(
        "SELECT name FROM system.tables WHERE database = currentDatabase()"
    )
    return {str(row[0]) for row in getattr(result, "result_rows", [])}


def _current_revision(client: Any, table_names: set[str]) -> str | None:
    if "alembic_version" not in table_names:
        return None
    result = client.query(
        "SELECT version_num FROM alembic_version FINAL ORDER BY changed_at DESC LIMIT 1"
    )
    rows = getattr(result, "result_rows", [])
    return str(rows[0][0]) if rows else None


def _retired_tables(table_names: set[str]) -> set[str]:
    retired = set(_RETIRED_DWH_TABLES | _RETIRED_DATA_MARTS)
    staging_prefixes = tuple(f"{mart}__rebuild" for mart in _RETIRED_DATA_MARTS)
    return {
        table_name
        for table_name in table_names
        if table_name in retired or table_name.startswith(staging_prefixes)
    }


def _upgrade_clickhouse_schema_sync() -> None:
    client = get_clickhouse_client()
    config = _alembic_config()
    required_revision = ScriptDirectory.from_config(config).get_current_head()
    if required_revision is None:
        raise RuntimeError("ClickHouse Alembic has no head revision")
    current_revision = _current_revision(client, _table_names(client))

    if current_revision is None:
        # Pre-Alembic deployments were maintained by ensure_dwh_tables() and
        # already match the last runtime-managed schema.  Replaying revision
        # 002 would drop operational DWH tables, so establish the safe baseline.
        # Fresh deployments have no tables yet, so initialize baseline tables
        # first before applying forward schema alterations.
        from infrastructure.clickhouse import ensure_tables

        ensure_tables()
        command.stamp(config, _LEGACY_RUNTIME_BASELINE)
        logger.info(
            "clickhouse_migrations_legacy_baseline_stamped revision=%s",
            _LEGACY_RUNTIME_BASELINE,
        )

    command.upgrade(config, "head")

    table_names = _table_names(client)
    applied_revision = _current_revision(client, table_names)
    if applied_revision != required_revision:
        raise RuntimeError(
            "ClickHouse migration revision mismatch: "
            f"expected {required_revision}, got {applied_revision!r}"
        )

    remaining = sorted(_retired_tables(table_names))
    if remaining:
        raise RuntimeError(
            "Retired special-equipment analytics tables remain after migration: "
            + ", ".join(remaining)
        )

    logger.info(
        "clickhouse_migrations_current revision=%s retired_tables=0",
        applied_revision,
    )


async def ensure_clickhouse_migrations_current() -> None:
    """Apply ClickHouse migrations once across concurrent event-worker replicas."""

    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.text("SELECT pg_advisory_lock(:key)"),
            {"key": _MIGRATION_LOCK_KEY},
        )
        try:
            migration_task = asyncio.create_task(
                asyncio.to_thread(_upgrade_clickhouse_schema_sync)
            )
            try:
                await asyncio.shield(migration_task)
            except asyncio.CancelledError:
                # ``to_thread`` cannot stop a running migration.  Keep the
                # PostgreSQL session lock until DDL has finished, then honour
                # cancellation so another replica cannot overlap the upgrade.
                await migration_task
                raise
        finally:
            await session.execute(
                sa.text("SELECT pg_advisory_unlock(:key)"),
                {"key": _MIGRATION_LOCK_KEY},
            )
