from __future__ import annotations

from collections import deque

import pytest
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from main import app as production_app
from presentation.middleware.api_trailing_slash import ApiTrailingSlashMiddleware

pytestmark = pytest.mark.asyncio


class _ReadBodyBeforeRoutingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        messages: deque[Message] = deque()
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect" or not message.get(
                "more_body", False
            ):
                break

        async def replay_receive() -> Message:
            if messages:
                return messages.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)


def _client(app: ASGIApp) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


async def test_canonical_request_calls_endpoint_once() -> None:
    app = FastAPI()
    calls = 0

    @app.get("/api/items/")
    async def items() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"calls": calls}

    app.add_middleware(ApiTrailingSlashMiddleware, router=app.router)

    async with _client(app) as client:
        response = await client.get("/api/items/")

    assert response.status_code == 200
    assert response.json() == {"calls": 1}
    assert calls == 1


async def test_slash_mismatch_calls_endpoint_once_without_redirect() -> None:
    app = FastAPI()
    calls = 0

    @app.get("/api/items/")
    async def items() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"calls": calls}

    app.add_middleware(ApiTrailingSlashMiddleware, router=app.router)

    async with _client(app) as client:
        response = await client.get("/api/items")

    assert response.status_code == 200
    assert "location" not in response.headers
    assert response.json() == {"calls": 1}
    assert calls == 1


async def test_post_body_is_preserved_when_consumed_before_retry() -> None:
    app = FastAPI()
    calls = 0

    @app.post("/api/echo/")
    async def echo(request: Request) -> Response:
        nonlocal calls
        calls += 1
        return Response(content=await request.body())

    app.add_middleware(_ReadBodyBeforeRoutingMiddleware)
    app.add_middleware(ApiTrailingSlashMiddleware, router=app.router)
    body = b'{"value":"preserved"}'

    async with _client(app) as client:
        response = await client.post("/api/echo", content=body)

    assert response.status_code == 200
    assert response.content == body
    assert calls == 1


async def test_unrelated_endpoint_redirect_is_not_rerouted() -> None:
    app = FastAPI()
    source_calls = 0
    target_calls = 0

    @app.get("/api/redirect")
    async def source() -> RedirectResponse:
        nonlocal source_calls
        source_calls += 1
        return RedirectResponse("http://test/api/redirect/", status_code=307)

    @app.get("/api/redirect/")
    async def target() -> dict[str, bool]:
        nonlocal target_calls
        target_calls += 1
        return {"reached": True}

    app.add_middleware(ApiTrailingSlashMiddleware, router=app.router)

    async with _client(app) as client:
        response = await client.get("/api/redirect")

    assert response.status_code == 307
    assert response.headers["location"] == "http://test/api/redirect/"
    assert source_calls == 1
    assert target_calls == 0


async def test_slash_normalizer_is_the_innermost_user_middleware() -> None:
    assert production_app.user_middleware[-1].cls is ApiTrailingSlashMiddleware
