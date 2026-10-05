"""Shared normalization helpers for raw DaData company payloads."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ms_to_date(timestamp_ms: Any) -> date | None:
    if not isinstance(timestamp_ms, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date()
    except (TypeError, ValueError, OSError):
        return None


def _normalize_founder(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a DaData founder record for frontend/backend consumption."""
    fio = raw.get("fio") or {}
    name = raw.get("name") or ""
    if not name and fio:
        name = " ".join(
            part
            for part in [
                fio.get("surname"),
                fio.get("name"),
                fio.get("patronymic"),
            ]
            if part
        )
    share = raw.get("share")
    share_value: str | int | float | None = None
    if isinstance(share, dict):
        share_value = share.get("value")
    else:
        share_value = share
    return {
        "name": name,
        "inn": raw.get("inn"),
        "share": share_value,
    }


def normalize_dadata_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten a raw DaData ``findById/party`` ``data`` block."""
    name = data.get("name") or {}
    management = data.get("management") or {}
    address = data.get("address") or {}
    state = data.get("state") or {}
    opf = data.get("opf") or {}
    okveds = data.get("okveds") or []
    main_okved = next((o for o in okveds if o.get("main")), None) or {}
    additional_okveds = [o for o in okveds if not o.get("main")]
    additional_first = additional_okveds[0] if additional_okveds else {}
    finance = data.get("finance") or {}
    authorities = data.get("authorities") or {}
    fts = authorities.get("fts_registration") or {}
    founders = data.get("founders")
    managers = data.get("managers") or []
    director = next((m for m in managers if m.get("type") == "EMPLOYEE"), {}) or management

    legal_address_str = address.get("unrestricted_value") or address.get("value")
    address_data = address.get("data") or {}

    return {
        "full_name": name.get("full_with_opf") or name.get("full"),
        "short_name": name.get("short_with_opf") or name.get("short"),
        "kpp": data.get("kpp"),
        "ogrn": data.get("ogrn"),
        "okpo": data.get("okpo"),
        "okato": data.get("okato"),
        "legal_address": address,
        "legal_address_string": legal_address_str,
        "registration_date": _ms_to_date(state.get("registration_date")),
        "registration_department": fts.get("name"),
        "employees_count": _safe_int(data.get("employee_count")),
        "main_okved_code": main_okved.get("code") or data.get("okved"),
        "main_okved_description": main_okved.get("name"),
        "additional_okved_code": additional_first.get("code"),
        "additional_okved_description": additional_first.get("name"),
        "additional_okved_list": [
            {"code": o.get("code"), "description": o.get("name")}
            for o in additional_okveds
        ],
        "director_full_name": director.get("name") or management.get("name"),
        "director_position": director.get("post") or management.get("post"),
        "director_inn": director.get("inn"),
        "founders": [_normalize_founder(f) for f in founders] if founders else None,
        "bank_bik": None,
        "bank_name": None,
        "bank_account_number": None,
        "region": address_data.get("region_with_type") or address_data.get("region"),
        "city": address_data.get("city_with_type") or address_data.get("city"),
        "legal_form": opf.get("full") or opf.get("short"),
        "authorized_capital": _safe_int((data.get("capital") or {}).get("value")),
        "net_profit": _safe_int(finance.get("revenue")),
        "reporting_year": _safe_int(finance.get("year")),
        "website": None,
        "tax_system": finance.get("tax_system"),
    }
