"""Resolve leasing-company and contractor operators for SOPD documents."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import contractors_repository as contractors_repo
from infrastructure.repositories import (
    leasing_company_application_repository as applications_repo,
)
from infrastructure.repositories.sopd_operator_snapshot_repository import (
    DEFAULT_SOURCE,
)

SOURCE_MISSING_APPLICATION = "missing_application"
SOURCE_APPLICATION_NOT_FOUND = "application_not_found"
SOURCE_ACTIVE_LEASING_COMPANIES_FALLBACK = "active_leasing_companies_fallback"


@dataclass(frozen=True)
class SopdOperatorSnapshotData:
    leasing_companies: list[dict[str, Any]]
    contractors: list[dict[str, Any]]
    source: str

    @property
    def leasing_companies_text(self) -> str:
        return _format_leasing_companies(self.leasing_companies)

    @property
    def contractors_text(self) -> str:
        return _format_contractors(self.contractors)


async def resolve_sopd_operator_snapshot(
    session: AsyncSession, *, application_id: uuid.UUID | None
) -> SopdOperatorSnapshotData:
    if application_id is None:
        return SopdOperatorSnapshotData(
            leasing_companies=[],
            contractors=[],
            source=SOURCE_MISSING_APPLICATION,
        )

    application = await applications_repo.get_application_projection(
        session, application_id
    )
    if application is None:
        return SopdOperatorSnapshotData(
            leasing_companies=[],
            contractors=[],
            source=SOURCE_APPLICATION_NOT_FOUND,
        )

    selected_ids = _ordered_uuid_values(
        application.get("selected_leasing_companies") or []
    )
    if selected_ids:
        leasing_company_rows = (
            await contractors_repo.get_leasing_companies_by_ids(
                session, set(selected_ids)
            )
        )
        source = DEFAULT_SOURCE
    else:
        active_rows = await applications_repo.list_active_leasing_companies(session)
        leasing_company_rows = [
            contractors_repo.LeasingCompanyRefDict(
                id=row["id"],
                company_id=row["company_id"],
                name=row["name"],
                inn=row["inn"],
            )
            for row in active_rows
        ]
        selected_ids = [row["id"] for row in leasing_company_rows]
        source = SOURCE_ACTIVE_LEASING_COMPANIES_FALLBACK

    leasing_company_by_id = {row["id"]: row for row in leasing_company_rows}
    leasing_companies = [
        _leasing_company_snapshot(leasing_company_by_id[leasing_company_id])
        for leasing_company_id in selected_ids
        if leasing_company_id in leasing_company_by_id
    ]

    links = await contractors_repo.list_links_for_leasing_companies(
        session, leasing_company_ids={item["id"] for item in leasing_company_rows}
    )
    selected_index = {
        leasing_company_id: index
        for index, leasing_company_id in enumerate(selected_ids)
    }
    links.sort(
        key=lambda link: (
            selected_index.get(link["leasing_company_id"], len(selected_ids)),
            link["contractor_name"],
        )
    )
    contractors = _dedupe_contractors(links, leasing_company_by_id)

    return SopdOperatorSnapshotData(
        leasing_companies=leasing_companies,
        contractors=contractors,
        source=source,
    )


def _ordered_uuid_values(values: list[Any]) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for value in values:
        parsed = _parse_uuid(value)
        if parsed is None or parsed in seen:
            continue
        seen.add(parsed)
        result.append(parsed)
    return result


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _leasing_company_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]) if row.get("company_id") else None,
        "name": str(row.get("name") or ""),
        "inn": str(row.get("inn") or ""),
    }


def _dedupe_contractors(
    links: list[contractors_repo.ContractorLinkDict],
    leasing_company_by_id: dict[uuid.UUID, contractors_repo.LeasingCompanyRefDict],
) -> list[dict[str, Any]]:
    contractors_by_key: dict[str, dict[str, Any]] = {}
    for link in links:
        contractor_key = str(link["contractor_inn"] or link["contractor_id"])
        item = contractors_by_key.setdefault(
            contractor_key,
            {
                "id": str(link["contractor_id"]),
                "name": link["contractor_name"],
                "inn": link["contractor_inn"],
                "leasing_company_ids": [],
                "leasing_companies": [],
            },
        )

        leasing_company_id = link["leasing_company_id"]
        if str(leasing_company_id) in item["leasing_company_ids"]:
            continue

        lc_row = leasing_company_by_id.get(leasing_company_id)
        item["leasing_company_ids"].append(str(leasing_company_id))
        item["leasing_companies"].append(
            _leasing_company_snapshot(lc_row)
            if lc_row is not None
            else {
                "id": str(leasing_company_id),
                "company_id": None,
                "name": str(link.get("leasing_company_name") or ""),
                "inn": str(link.get("leasing_company_inn") or ""),
            }
        )

    return sorted(
        contractors_by_key.values(),
        key=lambda item: (str(item.get("name") or ""), str(item.get("inn") or "")),
    )


def _format_leasing_companies(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {_format_operator_name(item)}" for item in items)


def _format_contractors(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    return "\n".join(f"- {_format_contractor(item)}" for item in items)


def _format_operator_name(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    inn = str(item.get("inn") or "").strip()
    if name and inn:
        return f"{name}, ИНН {inn}"
    return name or (f"ИНН {inn}" if inn else "оператор без наименования")


def _format_contractor(item: dict[str, Any]) -> str:
    leasing_company_names = [
        _format_operator_name(lc)
        for lc in item.get("leasing_companies") or []
        if isinstance(lc, dict)
    ]
    base = _format_operator_name(item)
    if not leasing_company_names:
        return base
    return (
        f"{base} (подрядчик лизинговых компаний: "
        f"{', '.join(leasing_company_names)})"
    )
