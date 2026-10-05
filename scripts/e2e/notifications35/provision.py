#!/usr/bin/env python3
"""Fail-closed schema initialization for the isolated local E2E fixture only."""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from infrastructure.clickhouse import get_clickhouse_client
from infrastructure.clickhouse_dwh import _RETIRED_DATA_MARTS, _RETIRED_DWH_TABLES
from infrastructure.settings import settings
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def guard() -> None:
    dsn = make_url(settings.database_dsn)
    require(dsn.database == "notifications35_runtime", "Unexpected PostgreSQL database")
    require(dsn.username == "notifications35" and dsn.host == "postgres", "Unexpected PostgreSQL owner/host")
    require(settings.clickhouse_host == "clickhouse" and settings.clickhouse_db == "default", "Unexpected ClickHouse target")
    require(settings.public_url == "http://localhost:18048", "Unexpected runtime URL")
    require(settings.jwt_keys_dir == "/runtime-keys/jwt", "Unexpected signing key location")


def pg_revision_state(versions: list[str], scripts: ScriptDirectory) -> str:
    heads = scripts.get_heads()
    require(len(heads) == 1, "Checkout must have exactly one PostgreSQL migration head")
    require(len(versions) == 1, "PostgreSQL must have exactly one recorded revision")
    if versions == heads:
        return "current"
    ancestors = {revision.revision for revision in scripts.walk_revisions(head=heads[0])}
    require(versions[0] in ancestors, "Unknown or divergent PostgreSQL revision; inspect manually")
    return "upgrade"


async def pg_state() -> str:
    engine = create_async_engine(settings.database_dsn)
    try:
        async with engine.connect() as connection:
            tables = set((await connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))).scalars())
            if not tables:
                return "empty"
            require("alembic_version" in tables, "Nonempty PostgreSQL without migration revision; refusing initialization")
            versions = list((await connection.execute(text("SELECT version_num FROM alembic_version"))).scalars())
            return pg_revision_state(versions, ScriptDirectory.from_config(Config("/app/alembic.ini")))
    finally:
        await engine.dispose()


def ch_state(client: Any) -> str:
    tables = {row[0] for row in client.query(
        "SELECT name FROM system.tables WHERE database = currentDatabase()"
    ).result_rows}
    if not tables:
        return "empty"
    require("alembic_version" in tables, "Nonempty ClickHouse without migration revision; refusing destructive historical migrations")
    versions = client.query("SELECT version_num FROM alembic_version FINAL").result_rows
    require(versions == [("007",)], "ClickHouse is neither empty nor at head 007; inspect manually")
    retired = _RETIRED_DWH_TABLES | _RETIRED_DATA_MARTS
    require(not any(name in retired or any(name.startswith(f"{mart}__rebuild") for mart in _RETIRED_DATA_MARTS)
        for name in tables), "Retired ClickHouse analytics tables remain")
    return "current"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pg-state", "ch-state", "pg-init", "ch-init", "verify"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    require(args.execute, "Explicit isolated fixture opt-in is required")
    guard()
    if args.mode.startswith("pg-"):
        current = asyncio.run(pg_state())
        if args.mode == "pg-init" and current in {"empty", "upgrade"}:
            command.upgrade(Config("/app/alembic.ini"), "head")
            require(asyncio.run(pg_state()) == "current", "PostgreSQL initialization incomplete")
            current = "current"
        sys.stdout.write(current + "\n")
        return
    client = get_clickhouse_client()
    require(client is not None, "ClickHouse unavailable")
    current = ch_state(client)
    if args.mode == "ch-init" and current == "empty":
        # Historical migration 002 drops/recreates DWH tables. The exact empty
        # schema check above is mandatory; never stamp or replay over user data.
        command.upgrade(Config("/app/alembic_clickhouse.ini"), "head")
        require(ch_state(client) == "current", "ClickHouse initialization incomplete")
    if args.mode == "verify":
        require(current == "current" and asyncio.run(pg_state()) == "current", "Runtime schema is not initialized")
        compatibility = client.query("SELECT value FROM system.merge_tree_settings "
            "WHERE name = 'allow_dimensions_outside_sorting_key'").result_rows
        require(compatibility == [("0",)], "Temporary historical-DDL compatibility is still enabled")
    sys.stdout.write(current + "\n")


if __name__ == "__main__":
    main()
