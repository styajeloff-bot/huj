"""Shared DWH client: real driver concurrency against a controlled HTTP boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from io import BytesIO
from threading import Barrier, Event, Lock
from typing import Any, cast

import clickhouse_connect
import pytest
from urllib3 import PoolManager
from urllib3.response import HTTPResponse

from infrastructure.clickhouse import (
    execute_clickhouse_batch_strict,
    get_clickhouse_client,
    set_clickhouse_client,
)
from infrastructure.settings import settings


@pytest.fixture(autouse=True)
def isolated_clickhouse_singleton(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # A failing real-driver traceback must never contain inherited credentials.
    for name, value in {
        "clickhouse_host": "127.0.0.1", "clickhouse_port": 8123,
        "clickhouse_user": "concurrency-test", "clickhouse_password": "local-test-only",
        "clickhouse_db": "default",
    }.items():
        monkeypatch.setattr(settings, name, value)
    set_clickhouse_client(None)
    try:
        yield
    finally:
        set_clickhouse_client(None)


def _describe_uint8_value() -> bytes:
    """One-row Native DESCRIBE response, independent from driver serializers."""
    result = bytearray(b"\x07\x01")
    for name, value in (
        ("name", "value"), ("type", "UInt8"), ("default_type", ""),
        ("default_expression", ""), ("comment", ""),
        ("codec_expression", ""), ("ttl_expression", ""),
    ):
        for string in (name, "String", value):
            encoded = string.encode()
            result.extend(bytes([len(encoded)]) + encoded)
    return bytes(result)


@pytest.mark.asyncio
async def test_shared_real_driver_allows_dwh_read_during_native_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_started, release_read = Event(), Event()
    inserts: list[bytes] = []

    def request(_pool: PoolManager, _method: str, _url: str, **kwargs: Any) -> HTTPResponse:
        body = kwargs.get("body", b"")
        query = body.decode() if isinstance(body, bytes) else body
        if not isinstance(query, str):
            # Consume the real driver's Native insert generator, including its
            # compression, just as the HTTP boundary does when streaming it.
            inserts.append(b"".join(body))
            response = b""
        elif query.startswith("SELECT version(), timezone()"):
            response = b"26.7.3.19\tUTC\n"
        elif query.startswith("SELECT name, value,"):
            response = b"\x00\x00"  # No optional server settings in this fixture.
        elif query.startswith("SELECT 1 AS check"):
            response = b""  # Protocol negotiation safely retains basic Native.
        elif query.startswith("DESCRIBE TABLE"):
            response = _describe_uint8_value()
        elif query.startswith("SELECT 42 AS value"):
            read_started.set()
            assert release_read.wait(timeout=3), "The read was never released"
            response = b"\x01\x01\x05value\x05UInt8\x2a"
        else:
            raise AssertionError(f"Unexpected synthetic ClickHouse query: {query}")
        return HTTPResponse(
            body=BytesIO(response), status=200, headers={},
            preload_content=kwargs.get("preload_content", True),
        )

    monkeypatch.setattr(PoolManager, "request", request)
    client = get_clickhouse_client()
    read = asyncio.create_task(asyncio.to_thread(client.query, "SELECT 42 AS value"))
    try:
        assert await asyncio.to_thread(read_started.wait, 2)
        await asyncio.wait_for(
            execute_clickhouse_batch_strict("concurrency_probe", ["value"], [[7]]),
            timeout=2,
        )
    finally:
        release_read.set()
        result = await read
    assert result.result_rows == [(42,)]
    assert len(inserts) == 1 and inserts[0]


@pytest.mark.asyncio
async def test_cold_start_constructs_one_shared_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callers_ready = Barrier(2)
    first_creation, second_creation, release_creation = Event(), Event(), Event()
    creations: list[object] = []
    creation_lock = Lock()

    def factory(**_kwargs: Any) -> object:
        client = object()
        with creation_lock:
            creations.append(client)
            (first_creation if len(creations) == 1 else second_creation).set()
        assert release_creation.wait(timeout=3)
        return client

    def get() -> Any:
        callers_ready.wait(timeout=2)
        return get_clickhouse_client()

    monkeypatch.setattr(clickhouse_connect, "get_client", factory)
    results = asyncio.gather(asyncio.to_thread(get), asyncio.to_thread(get))
    try:
        assert await asyncio.to_thread(first_creation.wait, 2)
        # Let the second caller attempt initialization while the first factory
        # is blocked. With an init lock it waits without making another client.
        await asyncio.to_thread(second_creation.wait, 0.25)
    finally:
        release_creation.set()
        clients = await results
    assert len(creations) == 1
    assert clients[0] is clients[1] is creations[0]


def test_failed_initialization_remains_retryable_and_test_override_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    recovered, replacement = object(), object()

    def factory(**kwargs: Any) -> object:
        nonlocal attempts
        attempts += 1
        assert kwargs["autogenerate_session_id"] is False
        if attempts == 1:
            raise ConnectionError("synthetic ClickHouse connection failure")
        return recovered

    monkeypatch.setattr(clickhouse_connect, "get_client", factory)
    with pytest.raises(ConnectionError, match="synthetic ClickHouse"):
        get_clickhouse_client()
    assert get_clickhouse_client() is recovered
    assert get_clickhouse_client() is recovered
    assert attempts == 2
    set_clickhouse_client(cast("Any", replacement))
    assert get_clickhouse_client() is replacement
    assert attempts == 2
