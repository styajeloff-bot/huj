from __future__ import annotations

import io
import json
import logging
from typing import Any

import httpx
import pytest

from domain.errors import CompanyLookupUnavailableError
from infrastructure.logging import configure_logging
from infrastructure.messaging.consumers import auth_audit
from infrastructure.services import document_recognition
from infrastructure.services.accounting import parser_api_provider
from infrastructure.services.company_lookup import dadata
from infrastructure.settings import settings


def _capture(*, level: int = logging.INFO) -> io.StringIO:
    configure_logging(service_name="carcraft-api")
    stream = io.StringIO()
    logger = logging.getLogger("carcraft-backend")
    logger.setLevel(level)
    handler = logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    return stream


class _DocumentClientStub:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def __aenter__(self) -> _DocumentClientStub:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self._response


@pytest.mark.asyncio
async def test_document_recognition_does_not_log_provider_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "passport-series-1234"
    response = httpx.Response(
        200,
        json={
            "task_id": "provider-task",
            "items": [{"fields": {"passport": secret}}],
        },
    )
    monkeypatch.setattr(settings, "document_recognition_token", "configured")
    monkeypatch.setattr(
        document_recognition.httpx,
        "AsyncClient",
        lambda **_kwargs: _DocumentClientStub(response),
    )
    stream = _capture()

    result = await document_recognition.recognize_document(
        b"image",
        "ceo_passport_page23",
    )

    assert result.success is True
    assert result.data is not None
    assert result.data["items"][0]["fields"]["passport"] == secret
    payload = json.loads(stream.getvalue())
    assert payload["event"] == "document.recognition.completed"
    assert payload["item_count"] == 1
    assert secret not in stream.getvalue()
    assert "items" not in payload


class _ParserClientStub:
    async def __aenter__(self) -> _ParserClientStub:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
    ) -> httpx.Response:
        if url.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 42,
                            "inn": params["inn"],
                            "email": "provider-person@example.test",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "organization": {"inn": "7701234567"},
                "reports": [],
                "provider_secret": "full-parser-response-secret",
            },
        )


@pytest.mark.asyncio
async def test_parser_api_does_not_log_request_or_response_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        parser_api_provider.httpx,
        "AsyncClient",
        lambda **_kwargs: _ParserClientStub(),
    )
    provider = parser_api_provider.ParserApiAccountingProvider(
        base_url="https://parser.example.test",
        api_key="plain-parser-api-key",
        timeout_ms=1000,
    )
    stream = _capture(level=logging.DEBUG)

    result = await provider.fetch_report("7701234567")

    assert result is None
    rendered = stream.getvalue()
    payloads = [json.loads(line) for line in rendered.splitlines()]
    assert any(item["event"] == "accounting.parser.response_received" for item in payloads)
    assert "plain-parser-api-key" not in rendered
    assert "provider-person@example.test" not in rendered
    assert "full-parser-response-secret" not in rendered
    assert all("body" not in item and "payload" not in item for item in payloads)


class _DadataClientStub:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def __aenter__(self) -> _DadataClientStub:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self._response


@pytest.mark.asyncio
async def test_dadata_error_does_not_log_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "provider-error-person@example.test"
    response = httpx.Response(429, text=f'{{"detail":"{secret}"}}')
    monkeypatch.setattr(
        dadata.httpx,
        "AsyncClient",
        lambda **_kwargs: _DadataClientStub(response),
    )
    stream = _capture()
    provider = dadata.DadataCompanyLookupProvider("plain-dadata-key")

    with pytest.raises(CompanyLookupUnavailableError):
        await provider.enrich_by_inn("7701234567")

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "company_lookup.dadata.provider_error"
    assert payload["http_status_code"] == 429
    assert secret not in stream.getvalue()
    assert "plain-dadata-key" not in stream.getvalue()


@pytest.mark.asyncio
async def test_auth_audit_missing_event_does_not_log_envelope() -> None:
    stream = _capture()
    secret = "audit-person@example.test"

    await auth_audit.handle_auth_event(
        {
            "phone": "+375291112233",
            "payload": {"password": "plain-password", "email": secret},
        }
    )

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "auth_audit.event_missing"
    assert payload["field_count"] == 2
    assert secret not in stream.getvalue()
    assert "plain-password" not in stream.getvalue()
    assert "+375291112233" not in stream.getvalue()
