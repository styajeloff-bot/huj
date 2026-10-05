from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import app

pytestmark = pytest.mark.asyncio


async def test_list_applications_collection_route_without_trailing_slash_requires_auth() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/applications?page=1&limit=20")

    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_MISSING"
