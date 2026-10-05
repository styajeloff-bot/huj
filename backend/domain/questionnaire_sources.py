"""Pure projection of documented company sources into questionnaire fields."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5

COMPANY_MAP = {
    "full_name": "full_company_name",
    "short_name": "short_company_name",
    "inn": "inn",
    "kpp": "kpp",
    "ogrn": "ogrn",
    "okpo": "okpo",
    "okato": "okato",
    "legal_form": "legal_form",
    "legal_address": "legal_address",
    "actual_address": "actual_address",
    "registration_date": "registration_date",
    "registration_department": "registration_authority_name",
    "employees_count": "employee_count",
    "director_full_name": "director_full_name",
    "director_position": "director_position",
    "director_inn": "director_inn",
    "bank_name": "bank_name",
    "bank_bik": "bik",
    "bank_account_number": "settlement_account",
    "tax_system": "tax_system",
}
TAX_MODES = {
    "Упрощенная система налогообложения": "УСН",
    "Единый сельскохозяйственный налог": "ЕСХН",
    "Патентная система налогообложения": "ПСН",
    "Налог на профессиональный доход": "НПД",
    "Автоматизированная упрощенная система налогообложения": "АУСН",
    "Единый налог на вменённый доход": "ЕНВД",
    "Соглашение о разделе продукции": "СРП",
}


def _founders(records: list[Any], application_id: UUID) -> list[dict[str, Any]]:
    result = []
    for item in records:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("full_name")
        inn = item.get("inn")
        if not name and not inn:
            continue
        result.append(
            {
                "id": str(
                    uuid5(
                        application_id, "founder/" + str(inn or name).casefold().strip()
                    )
                ),
                "name": name,
                "inn": inn,
                **({"share": item["share"]} if item.get("share") is not None else {}),
            }
        )
    return result


def company_values(data: dict[str, Any], application_id: UUID) -> dict[str, Any]:
    result = {
        target: data[key]
        for key, target in COMPANY_MAP.items()
        if data.get(key) is not None
    }
    if not result.get("full_company_name") and data.get("name"):
        result["full_company_name"] = data["name"]
    if data.get("main_okved_code"):
        result["okved_main"] = " — ".join(
            str(v)
            for v in (data["main_okved_code"], data.get("main_okved_description"))
            if v
        )
    if isinstance(data.get("additional_okved_list"), list):
        result["okved_additional"] = "; ".join(
            " — ".join(str(v) for v in (item.get("code"), item.get("description")) if v)
            for item in data["additional_okved_list"]
            if isinstance(item, dict)
        )
    if isinstance(data.get("founders"), list):
        result["founders"] = _founders(data["founders"], application_id)
    return result


def fns_values(data: dict[str, Any], application_id: UUID) -> dict[str, Any]:
    result = {
        target: data[key]
        for key, target in {
            "name": "full_company_name",
            "name_short": "short_company_name",
            "foreign_company_name": "foreign_company_name",
            "inn": "inn",
            "kpp": "kpp",
            "ogrn": "ogrn",
            "okpo": "okpo",
            "address": "legal_address",
            "registration_date": "registration_date",
        }.items()
        if data.get(key) is not None
    }
    authority = data.get("reg_authority")
    if isinstance(authority, dict) and authority.get("name"):
        result["registration_authority_name"] = authority["name"]
    if data.get("okved"):
        result["okved_main"] = " — ".join(
            str(v) for v in (data["okved"], data.get("okved_name")) if v
        )
    if isinstance(data.get("okved_additional"), list):
        result["okved_additional"] = "; ".join(
            " — ".join(str(v) for v in (item.get("code"), item.get("name")) if v)
            for item in data["okved_additional"]
            if isinstance(item, dict)
        )
    if isinstance(data.get("tax_modes"), list):
        modes = data["tax_modes"]
        known = [TAX_MODES.get(v, v) for v in modes if isinstance(v, str)]
        value = ", ".join(known) if modes else "ОСНО"
        if len(value) <= 50:
            result["tax_system"] = value
    headcounts = [
        item
        for item in (data.get("avg_headcount") or [])
        if isinstance(item, dict)
        and isinstance(item.get("year"), int)
        and isinstance(item.get("count"), int)
        and not isinstance(item["count"], bool)
        and item["count"] >= 0
    ]
    if headcounts:
        result["employee_count"] = max(headcounts, key=lambda item: item["year"])[
            "count"
        ]
    directors = data.get("director")
    if isinstance(directors, list) and directors and isinstance(directors[0], dict):
        result.update(
            {
                target: directors[0][key]
                for key, target in {
                    "name": "director_full_name",
                    "position": "director_position",
                    "inn": "director_inn",
                }.items()
                if directors[0].get(key) is not None
            }
        )
    if isinstance(data.get("owner"), list):
        result["founders"] = _founders(data["owner"], application_id)
    return result
