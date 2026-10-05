"""Functional + integration tests for /api/v1/company/search."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from httpx import AsyncClient

from application.queries.company_lookup import (
    SearchCompanyQuery,
    handle_search_company,
)
from domain.errors import CompanyLookupUnavailableError
from domain.values import CompanyInfo
from infrastructure.services.company_lookup import dadata as dadata_module
from infrastructure.services.company_lookup import set_company_lookup_provider
from tests.fakes.company_lookup import FakeCompanyLookupProvider

_SAMPLE = CompanyInfo(
    name="ООО Тест",
    full_name="Общество с ограниченной ответственностью Тест",
    inn="7701234567",
    kpp="770101001",
    ogrn="1027700000000",
    legal_address="г. Москва, ул. Тестовая, д. 1",
    actual_address="г. Москва, ул. Тестовая, д. 1",
    phone="+74951234567",
    email="info@test.ru",
    foundation_date="2001-01-01",
    employee_count=10,
    business_activity="62.01 - Разработка ПО",
    manager_name="Иванов Иван Иванович",
    entity_type="LEGAL",
)


class _DadataHttpClientStub:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> _DadataHttpClientStub:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
        return self.response


def _stub_dadata_http(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
) -> None:
    monkeypatch.setattr(
        dadata_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _DadataHttpClientStub(response),
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        {"suggestions": {}},
        {"suggestions": [None]},
    ],
)
async def test_dadata_malformed_payload_is_not_an_empty_success(
    monkeypatch: pytest.MonkeyPatch,
    body: object,
) -> None:
    _stub_dadata_http(monkeypatch, httpx.Response(200, json=body))
    provider = dadata_module.DadataCompanyLookupProvider("test-key")

    with pytest.raises(CompanyLookupUnavailableError, match="некорректный ответ"):
        await provider.enrich_by_inn("7700000001")


async def test_dadata_invalid_json_is_not_an_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dadata_http(monkeypatch, httpx.Response(200, content=b"not-json"))
    provider = dadata_module.DadataCompanyLookupProvider("test-key")

    with pytest.raises(CompanyLookupUnavailableError, match="некорректный ответ"):
        await provider.enrich_by_inn("7700000001")


async def test_dadata_explicit_empty_suggestions_is_a_valid_empty_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dadata_http(
        monkeypatch,
        httpx.Response(200, json={"suggestions": []}),
    )
    provider = dadata_module.DadataCompanyLookupProvider("test-key")

    assert await provider.enrich_by_inn("7700000001") is None


# ---------------------------------------------------------------------------
# Functional tests — query handler in isolation
# ---------------------------------------------------------------------------


async def test_search_handler_returns_items() -> None:
    provider = FakeCompanyLookupProvider(items=[_SAMPLE])
    result = await handle_search_company(
        SearchCompanyQuery(query="Тест", limit=5), provider
    )
    assert result == [_SAMPLE]
    assert provider.calls == [("Тест", 5)]


async def test_search_handler_short_query_returns_empty_without_provider_call() -> None:
    provider = FakeCompanyLookupProvider(items=[_SAMPLE])
    result = await handle_search_company(
        SearchCompanyQuery(query="a", limit=5), provider
    )
    assert result == []
    assert provider.calls == []


async def test_search_handler_trims_whitespace() -> None:
    provider = FakeCompanyLookupProvider(items=[_SAMPLE])
    await handle_search_company(
        SearchCompanyQuery(query="  Тест  ", limit=5), provider
    )
    assert provider.calls == [("Тест", 5)]


# ---------------------------------------------------------------------------
# Integration tests — real HTTP roundtrip against the app
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_provider() -> Iterator[FakeCompanyLookupProvider]:
    fake = FakeCompanyLookupProvider(items=[_SAMPLE])
    set_company_lookup_provider(fake)
    yield fake
    set_company_lookup_provider(None)


async def test_search_endpoint_returns_normalized_items(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/company/search",
        params={"q": "Тест", "limit": 5},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["name"] == "ООО Тест"
    assert item["inn"] == "7701234567"
    # Provider-specific raw DaData fields must NOT leak
    assert "data" not in item
    assert "suggestions" not in body


async def test_search_endpoint_is_public(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/company/search", params={"q": "Тест"}
    )
    assert response.status_code == 200


async def test_search_endpoint_rejects_short_query(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/company/search",
        params={"q": "a"},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert response.status_code == 422


async def test_search_endpoint_empty_result_is_200(
    client: AsyncClient, client_token: str, _fake_provider: FakeCompanyLookupProvider
) -> None:
    _fake_provider.items = []
    response = await client.get(
        "/api/v1/company/search",
        params={"q": "Неизвестное"},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_search_endpoint_provider_unavailable_returns_503(
    client: AsyncClient, client_token: str, _fake_provider: FakeCompanyLookupProvider
) -> None:
    _fake_provider.raise_unavailable = True
    response = await client.get(
        "/api/v1/company/search",
        params={"q": "Тест"},
        headers={"Authorization": f"Bearer {client_token}"},
    )
    assert response.status_code == 503
