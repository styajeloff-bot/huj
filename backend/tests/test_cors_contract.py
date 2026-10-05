from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app

pytestmark = pytest.mark.asyncio


async def test_browser_clients_can_read_etag_for_conditional_updates() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 200
    exposed_headers = {
        header.strip().lower()
        for header in response.headers["access-control-expose-headers"].split(",")
    }
    assert "etag" in exposed_headers
