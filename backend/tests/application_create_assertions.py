"""Shared public-HTTP assertions for the three application creation surfaces."""
from __future__ import annotations

import json

from httpx import AsyncClient, Response


async def assert_create_idempotency(
    client: AsyncClient, created: Response, *, change_field: str,
) -> None:
    """Replay the actual wire payload and preserve the required header contract."""
    payload = json.loads(created.request.content)
    endpoint = str(created.request.url)
    headers = dict(created.request.headers)
    headers.pop("content-length", None)
    missing_headers = {key: value for key, value in headers.items() if key.lower() != "idempotency-key"}
    missing = await client.post(endpoint, json=payload, headers=missing_headers)
    assert missing.status_code == 422
    assert "Idempotency-Key" in json.dumps(missing.json()["detail"])
    replay = await client.post(endpoint, json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == created.json()
    conflict = await client.post(endpoint, json={**payload, change_field: "Изменённый payload"}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Idempotency-Key уже используется с другим payload"
