from __future__ import annotations

import io
import json
import logging
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response

from infrastructure.logging import configure_logging
from infrastructure.settings import settings
from presentation.errors import handle_unhandled_exception
from presentation.middleware.api_trailing_slash import ApiTrailingSlashMiddleware
from presentation.middleware.csrf import CSRFMiddleware
from presentation.middleware.request_timing import RequestTimingMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(Exception, handle_unhandled_exception)

    leasing_router = APIRouter(prefix="/api/v1/dealer/leasing-applications")

    @leasing_router.patch("/{application_id}/items/{item_id}/price")
    async def update_price(application_id: str, item_id: str) -> dict[str, str]:
        return {"application_id": application_id, "item_id": item_id}

    app.include_router(leasing_router)

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/metrics")
    async def metrics() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/leasing-company-applications/")
    async def leasing_company_applications() -> dict[str, list[object]]:
        return {"items": []}

    @app.get("/unavailable")
    async def unavailable() -> Response:
        return Response(status_code=503)

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("request failed")

    app.add_middleware(ApiTrailingSlashMiddleware, router=app.router)
    app.add_middleware(RequestTimingMiddleware)
    return app


def _capture() -> io.StringIO:
    configure_logging(service_name="carcraft-api")
    stream = io.StringIO()
    handler = logging.getLogger("carcraft-backend").handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    return stream


@pytest.mark.asyncio
async def test_request_logs_full_actual_path_without_query_string() -> None:
    app = _app()
    stream = _capture()
    request_id = "7c8e64ba-9730-40e5-b2c5-fcf650705b18"
    application_id = "1952e0de-0dc7-42f7-86ed-a218f98c4d22"
    item_id = "fb859fb5-484d-4876-8d40-9467ad69b80e"
    requested_path = (
        "/api/v1/dealer/leasing-applications/"
        f"{application_id}/items/{item_id}/price"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            f"{requested_path}?token=plaintext&email=person@example.test",
            headers={"X-Request-ID": request_id},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "info"
    assert payload["component"] == "http"
    assert payload["event"] == "http.request.completed"
    assert payload["request_id"] == request_id
    assert payload["correlation_id"] == request_id
    assert payload["http_method"] == "PATCH"
    assert payload["http_route"] == requested_path
    assert payload["http_status_code"] == 200
    assert isinstance(payload["duration_ms"], float)
    assert requested_path in payload["message"]
    assert application_id in lines[0]
    assert item_id in lines[0]
    assert "plaintext" not in lines[0]
    assert "person@example.test" not in lines[0]


@pytest.mark.asyncio
async def test_invalid_request_id_is_replaced_with_uuid() -> None:
    app = _app()
    stream = _capture()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/items/example", headers={"X-Request-ID": "not-a-uuid"}
        )

    response_id = response.headers["X-Request-ID"]
    assert str(UUID(response_id)) == response_id
    payload = json.loads(stream.getvalue())
    assert payload["request_id"] == response_id


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/health", "/metrics"])
async def test_probe_paths_return_request_id_without_log(path: str) -> None:
    app = _app()
    stream = _capture()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert str(UUID(response.headers["X-Request-ID"]))
    assert stream.getvalue() == ""


@pytest.mark.asyncio
async def test_returned_server_error_has_one_failed_summary() -> None:
    app = _app()
    stream = _capture()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/unavailable")

    assert response.status_code == 503
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "error"
    assert payload["event"] == "http.request.failed"
    assert payload["http_status_code"] == 503


@pytest.mark.asyncio
async def test_raised_server_error_has_one_failed_summary() -> None:
    app = _app()
    stream = _capture()
    request_id = "7c8e64ba-9730-40e5-b2c5-fcf650705b18"

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/crash",
            headers={"X-Request-ID": request_id},
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {
        "detail": "Произошла внутренняя ошибка. Попробуйте позже.",
        "code": "INTERNAL_ERROR",
    }
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "error"
    assert payload["event"] == "http.request.failed"
    assert payload["http_status_code"] == 500
    assert payload["error_type"] == "RuntimeError"


def _middleware_stack_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://allowed.example"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(CSRFMiddleware)
    # Last registration is outermost in Starlette.
    app.add_middleware(RequestTimingMiddleware)

    @app.post("/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_csrf_short_circuit_has_request_id_and_one_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "csrf_enabled", True)
    stream = _capture()

    async with AsyncClient(
        transport=ASGITransport(app=_middleware_stack_app()),
        base_url="http://test",
        cookies={"accessToken": "session-cookie"},
    ) as client:
        response = await client.post("/private/reset-secret-value")

    assert response.status_code == 403
    assert str(UUID(response.headers["X-Request-ID"]))
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 1
    assert records[0]["level"] == "warning"
    assert records[0]["event"] == "http.request.completed"
    assert records[0]["http_status_code"] == 403
    assert records[0]["http_route"] == "/private/reset-secret-value"
    assert "/private/reset-secret-value" in records[0]["message"]
    assert records[0]["security_check"] == "csrf"
    assert records[0]["result"] == "rejected"


@pytest.mark.asyncio
async def test_cors_preflight_has_request_id_and_one_summary() -> None:
    stream = _capture()

    async with AsyncClient(
        transport=ASGITransport(app=_middleware_stack_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/protected",
            headers={
                "Origin": "https://allowed.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert str(UUID(response.headers["X-Request-ID"]))
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 1
    assert records[0]["event"] == "http.request.completed"
    assert records[0]["http_status_code"] == 200
    assert records[0]["http_route"] == "/protected"
    assert "/protected" in records[0]["message"]


@pytest.mark.asyncio
async def test_missing_route_logs_full_actual_path() -> None:
    app = _app()
    stream = _capture()
    requested_path = "/api/v1/missing/private-reset-token"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(requested_path)

    assert response.status_code == 404
    payload = json.loads(stream.getvalue())
    assert payload["http_route"] == requested_path
    assert requested_path in payload["message"]


@pytest.mark.asyncio
async def test_slash_normalization_logs_the_path_actually_requested() -> None:
    app = _app()
    stream = _capture()
    requested_path = "/api/v1/leasing-company-applications"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(requested_path)

    assert response.status_code == 200
    assert "location" not in response.headers
    payload = json.loads(stream.getvalue())
    assert payload["http_route"] == requested_path
    assert requested_path in payload["message"]


@pytest.mark.asyncio
async def test_known_secret_in_path_is_redacted_by_structured_formatter() -> None:
    app = _app()
    stream = _capture()
    secret = "one-shot-secret-token"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/s/{secret}")

    assert response.status_code == 404
    payload = json.loads(stream.getvalue())
    assert payload["http_route"] == "/s/[REDACTED]"
    assert "/s/[REDACTED]" in payload["message"]
    assert secret not in stream.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("inn", ["1234567890", "123456789012"])
async def test_accounting_inn_in_path_is_redacted_by_structured_formatter(
    inn: str,
) -> None:
    app = _app()
    stream = _capture()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/accounting/{inn}")

    assert response.status_code == 404
    payload = json.loads(stream.getvalue())
    assert payload["http_route"] == "/api/v1/accounting/[REDACTED]"
    assert "/api/v1/accounting/[REDACTED]" in payload["message"]
    assert inn not in stream.getvalue()
