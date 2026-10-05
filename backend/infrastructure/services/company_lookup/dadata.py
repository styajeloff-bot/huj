"""DaData implementation of CompanyLookupProvider."""
from __future__ import annotations

import re
from datetime import UTC
from typing import Any

import httpx

from domain.errors import CompanyLookupUnavailableError
from domain.values import CompanyInfo
from infrastructure.logging import log_event
from infrastructure.settings import settings

_INN_PATTERN = re.compile(r"\b(\d{10}|\d{12})\b")


class DadataCompanyLookupProvider:
    """Concrete adapter — all DaData specifics live here."""

    def __init__(self, api_key: str, timeout: float | None = None) -> None:
        self._api_key = api_key
        self._timeout = (
            timeout if timeout is not None else settings.dadata_request_timeout
        )

    async def search(self, query: str, limit: int) -> list[CompanyInfo]:
        if not self._api_key:
            raise CompanyLookupUnavailableError("Провайдер поиска компаний не настроен")

        inn = _extract_inn(query)
        endpoint = "findById/party" if inn else "suggest/party"
        payload: dict[str, Any] = (
            {"query": inn} if inn else {"query": query, "count": limit}
        )

        suggestions = await self._request(endpoint, payload)
        return [_to_company_info(s) for s in suggestions[:limit]]

    async def enrich_by_inn(self, inn: str) -> dict[str, Any] | None:
        """Fetch full enrichment data from DaData by INN.

        Returns the raw ``data`` block from the first suggestion, or ``None``
        if no match is found. Raises ``CompanyLookupUnavailableError`` on
        network or provider failure.
        """
        if not self._api_key:
            raise CompanyLookupUnavailableError("Провайдер поиска компаний не настроен")

        suggestions = await self._request("findById/party", {"query": inn})
        if not suggestions:
            return None
        return suggestions[0].get("data") or None

    async def _request(self, endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                response = await http.post(
                    f"{settings.dadata_api_url}/{endpoint}",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Token {self._api_key}",
                    },
                )
        except httpx.HTTPError as exc:
            log_event(
                "warning",
                "company_lookup.dadata.request_failed",
                "Company lookup provider request failed",
                error=exc,
                component="company_lookup",
                dependency="dadata",
                operation=endpoint,
            )
            raise CompanyLookupUnavailableError() from exc

        if response.status_code != 200:
            log_event(
                "warning",
                "company_lookup.dadata.provider_error",
                "Company lookup provider returned an error",
                component="company_lookup",
                dependency="dadata",
                operation=endpoint,
                http_status_code=response.status_code,
                response_size_bytes=len(response.content),
            )
            raise CompanyLookupUnavailableError()

        try:
            body = response.json()
        except ValueError as exc:
            log_event(
                "warning",
                "company_lookup.dadata.invalid_json",
                "Company lookup provider returned invalid JSON",
                error=exc,
                component="company_lookup",
                dependency="dadata",
                operation=endpoint,
            )
            raise CompanyLookupUnavailableError(
                "Сервис поиска компаний вернул некорректный ответ"
            ) from exc

        suggestions = body.get("suggestions") if isinstance(body, dict) else None
        if not isinstance(suggestions, list) or any(
            not isinstance(item, dict) for item in suggestions
        ):
            log_event(
                "warning",
                "company_lookup.dadata.invalid_payload",
                "Company lookup provider returned an invalid payload shape",
                component="company_lookup",
                dependency="dadata",
                operation=endpoint,
            )
            raise CompanyLookupUnavailableError(
                "Сервис поиска компаний вернул некорректный ответ"
            )
        return suggestions


def _extract_inn(query: str) -> str | None:
    if not query:
        return None
    match = _INN_PATTERN.search(query)
    return match.group(0) if match else None


def _to_company_info(suggestion: dict[str, Any]) -> CompanyInfo:
    data = suggestion.get("data") or {}
    name = data.get("name") or {}
    management = data.get("management") or {}
    address = data.get("address") or {}
    legal = address.get("unrestricted_value") or address.get("value")
    phones = data.get("phones") or []
    emails = data.get("emails") or []
    okved = data.get("okved")
    okved_type = data.get("okved_type") or ""
    ogrn_date_ms = data.get("ogrn_date")

    foundation_date: str | None = None
    if isinstance(ogrn_date_ms, (int, float)):
        from datetime import datetime

        foundation_date = datetime.fromtimestamp(
            ogrn_date_ms / 1000, tz=UTC
        ).date().isoformat()

    return CompanyInfo(
        name=(
            name.get("short_with_opf")
            or name.get("short")
            or name.get("full")
            or "Без названия"
        ),
        full_name=name.get("full_with_opf") or name.get("full"),
        inn=data.get("inn"),
        kpp=data.get("kpp"),
        ogrn=data.get("ogrn"),
        legal_address=legal,
        actual_address=legal,
        phone=phones[0].get("value") if phones else None,
        email=emails[0].get("value") if emails else None,
        foundation_date=foundation_date,
        employee_count=data.get("employee_count"),
        business_activity=f"{okved} - {okved_type}".strip(" -") if okved else None,
        manager_name=management.get("name"),
        entity_type=data.get("type"),
    )
