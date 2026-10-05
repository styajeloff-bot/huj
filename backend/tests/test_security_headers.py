"""Tests for the SecurityHeadersMiddleware.

These tests build a minimal FastAPI application with a couple of routes
and the middleware under test — we intentionally don't use the full
``main.app`` fixture because we want to verify the middleware's behaviour
in isolation without paying the Postgres / Redis fixture cost.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from infrastructure.settings import settings
from presentation.middleware.security_headers import SecurityHeadersMiddleware

pytestmark = pytest.mark.asyncio


def _build_app() -> FastAPI:
    app = FastAPI(
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest_asyncio.fixture
async def sec_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=_build_app()),
        base_url="http://test",
    ) as ac:
        yield ac


EXPECTED_HEADERS = (
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Content-Security-Policy",
)


async def test_regular_route_sets_all_security_headers(
    sec_client: AsyncClient,
) -> None:
    resp = await sec_client.get("/ping")
    assert resp.status_code == 200
    for header in EXPECTED_HEADERS:
        assert header in resp.headers, f"missing header {header}"
    # Spot-check concrete values come from settings.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_docs_route_has_no_csp_but_other_headers_present(
    sec_client: AsyncClient,
) -> None:
    resp = await sec_client.get("/api/v1/docs")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers
    for header in EXPECTED_HEADERS:
        if header == "Content-Security-Policy":
            continue
        assert header in resp.headers, f"missing header {header}"


async def test_openapi_json_has_no_csp_but_other_headers_present(
    sec_client: AsyncClient,
) -> None:
    resp = await sec_client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert "Content-Security-Policy" not in resp.headers
    for header in EXPECTED_HEADERS:
        if header == "Content-Security-Policy":
            continue
        assert header in resp.headers, f"missing header {header}"


async def test_disabling_suppresses_all_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "security_headers_enabled", False)
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ping")
    assert resp.status_code == 200
    for header in EXPECTED_HEADERS:
        assert header not in resp.headers, f"unexpected header {header}"


async def test_individual_header_can_be_suppressed_via_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Suppress HSTS only — others must still appear.
    monkeypatch.setattr(settings, "security_hsts", "")
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ping")
    assert resp.status_code == 200
    assert "Strict-Transport-Security" not in resp.headers
    for header in EXPECTED_HEADERS:
        if header == "Strict-Transport-Security":
            continue
        assert header in resp.headers, f"missing header {header}"
