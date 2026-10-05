"""Documented parser-api pb.nalog.ru company lookup, with no raw PII logging."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from infrastructure.settings import settings


async def _foreign_company_name(identifier: Mapping[str, str | None]) -> str | None:
    """Read the full English name from an extract for this exact INN/OGRN."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.parser_api_timeout_ms / 1000
        ) as client:
            response = await client.get(
                settings.parser_api_url.rstrip("/")
                + "/parser/nalog_egrul_api/pdf_download",
                params={
                    "key": settings.parser_api_key,
                    **identifier,
                    "includeAttributes": "1",
                    "skipPdf": "1",
                },
            )
        if response.status_code != 200:
            return None
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("success") != 1:
        return None
    attributes = body.get("attributes")
    if not isinstance(attributes, list):
        return None
    names = {
        attribute["value"].strip()
        for attribute in attributes
        if isinstance(attribute, dict)
        and attribute.get("section") == "Наименование"
        and attribute.get("name") == "Полное наименование на английском языке"
        and isinstance(attribute.get("value"), str)
        and attribute["value"].strip()
    }
    # An empty or conflicting extract must not erase a previously accepted name.
    return next(iter(names)) if len(names) == 1 else None


async def fetch_fns_company(
    *, inn: str | None, ogrn: str | None
) -> tuple[str, dict[str, Any] | None]:
    if not settings.parser_api_key or (not inn and not ogrn):
        return "unavailable", None
    method = "search_ip" if inn and len(inn) == 12 else "search_org"
    identifier = {"inn": inn} if inn else {"ogrn": ogrn}
    try:
        async with httpx.AsyncClient(
            timeout=settings.parser_api_timeout_ms / 1000
        ) as client:
            response = await client.get(
                settings.parser_api_url.rstrip("/") + "/parser/nalog_pb_api/" + method,
                params={"key": settings.parser_api_key, **identifier},
            )
        if response.status_code != 200:
            return "unavailable", None
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return "unavailable", None
    if not isinstance(body, dict) or body.get("success") != 1:
        return "unavailable", None
    records = body.get("ip" if method == "search_ip" else "org")
    if not isinstance(records, list):
        return "unavailable", None
    match = None
    for record in records:
        if isinstance(record, dict) and (
            (inn and record.get("inn") == inn)
            or (not inn and record.get("ogrn") == ogrn)
        ):
            match = record
            break
    if match is not None:
        # This normalized field comes only from the documented extract attribute.
        match = {
            key: value for key, value in match.items() if key != "foreign_company_name"
        }
        if (inn and len(inn) == 10) or (not inn and ogrn and len(ogrn) == 13):
            foreign_name = await _foreign_company_name(identifier)
            if foreign_name is not None:
                match["foreign_company_name"] = foreign_name
    return ("updated", match) if match is not None else ("not_found", None)
