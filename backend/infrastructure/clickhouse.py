"""ClickHouse client singleton for DWH / analytics reads and writes.

Uses the official ``clickhouse-connect`` HTTP driver. The client is
synchronous; callers inside async code should wrap queries in
``asyncio.to_thread`` if they don't want to block the event loop.

FastAPI may import ``query_clickhouse`` from
``infrastructure.clickhouse_readonly`` for read-only analytics queries.
All writes still go through Kafka → event-worker.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

class _ClientState:
    client: Client | None = None
    initialization_lock = threading.Lock()
    lock = threading.Lock()


def get_clickhouse_client() -> Client:
    """Return the module-level ClickHouse client singleton."""
    client = _ClientState.client
    if client is not None:
        return client
    with _ClientState.initialization_lock:
        client = _ClientState.client
        if client is not None:
            return client
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_db,
            # DWH consumers also run stateless reads outside the write lock.
            # A shared HTTP session rejects these otherwise-safe parallel calls.
            autogenerate_session_id=False,
        )
        _ClientState.client = client
        logger.info(
            "clickhouse_connected host=%s port=%d db=%s",
            settings.clickhouse_host,
            settings.clickhouse_port,
            settings.clickhouse_db,
        )
        return client


def set_clickhouse_client(client: Client | None) -> None:
    """Override the singleton (used by tests)."""
    with _ClientState.initialization_lock:
        _ClientState.client = client


async def execute_clickhouse_batch(
    table: str,
    columns: list[str],
    rows: list[list[Any]],
) -> None:
    """Batch insert into ClickHouse using the native ``client.insert``.

    Failures are logged and swallowed — DWH writes must never block
    application flow.
    """
    import asyncio

    if not rows:
        return

    def _run() -> None:
        client = get_clickhouse_client()
        with _ClientState.lock:
            client.insert(table, rows, column_names=columns)

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning(
            "clickhouse_batch_insert_failed table=%s rows=%d err=%s",
            table,
            len(rows),
            exc,
        )


async def execute_clickhouse_batch_strict(
    table: str,
    columns: list[str],
    rows: list[list[Any]],
) -> None:
    """Insert a batch and propagate failures so Kafka can retry delivery."""
    import asyncio

    if not rows:
        return

    def _run() -> None:
        client = get_clickhouse_client()
        with _ClientState.lock:
            client.insert(table, rows, column_names=columns)

    await asyncio.to_thread(_run)


async def execute_clickhouse_strict(
    query: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Execute a write statement and propagate errors to the Kafka consumer.

    This helper is intentionally used only by ``event-worker`` consumers. It
    shares the same process lock as native inserts, so a mart partition swap
    cannot interleave with another write on the singleton HTTP client.
    """
    import asyncio

    def _run() -> Any:
        client = get_clickhouse_client()
        with _ClientState.lock:
            return client.query(query, parameters=params)

    return await asyncio.to_thread(_run)


async def execute_clickhouse(query: str, params: dict[str, Any] | None = None) -> None:
    """Fire-and-forget ClickHouse insert wrapped in a thread.

    Failures are logged and swallowed — DWH writes must never block
    application flow.
    """
    import asyncio

    def _run() -> None:
        client = get_clickhouse_client()
        with _ClientState.lock:
            client.query(query, parameters=params)

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("clickhouse_execute_failed query=%s err=%s", query, exc)


def ensure_tables() -> None:
    """Idempotent schema creation for DWH tables.

    Called once on event-worker startup.
    """
    client = get_clickhouse_client()

    with _ClientState.lock:
        # Auth audit trail
        client.query(
            """
            CREATE TABLE IF NOT EXISTS auth_audit_log (
                event String,
                timestamp DateTime64(3),
                user_id Nullable(UUID),
                phone Nullable(String),
                payload String
            ) ENGINE = MergeTree()
            ORDER BY (event, timestamp)
            """
        )

    # DWH tables
    try:
        from infrastructure.clickhouse_dwh import ensure_dwh_tables as _ensure_dwh

        _ensure_dwh(client)
    except Exception as exc:
        logger.warning("ensure_dwh_tables_failed err=%s", exc)

    logger.info("clickhouse_tables_ensured")
