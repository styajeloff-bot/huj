"""Read-only company-card audit history queries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import company_change_history_repository as repo


@dataclass(frozen=True)
class ListCompanyChangeHistoryQuery:
    company_id: UUID
    limit: int
    cursor: str | None = None


@dataclass(frozen=True)
class CompareCompanyChangeHistoryQuery:
    company_id: UUID
    base_id: UUID
    target_id: UUID


def _resource(record: dict[str, Any]) -> dict[str, Any]:
    return {"id": record["id"], "changed_at": record["changed_at"],
            "actor_display_name": record["actor_display_name"], "action": record["action"],
            "snapshot": record["snapshot"]}


async def handle_list_company_change_history(query: ListCompanyChangeHistoryQuery, session: AsyncSession) -> dict[str, Any]:
    if not await repo.company_exists(session, query.company_id):
        raise ServiceError("Компания не найдена.", 404, code="COMPANY_NOT_FOUND")
    try:
        cursor = repo.decode_cursor(query.cursor) if query.cursor else None
    except ValueError as exc:
        raise ServiceError("Некорректный курсор истории.", 422, code="VALIDATION_ERROR") from exc
    rows = await repo.list_history(session, query.company_id, limit=query.limit, cursor=cursor)
    has_more = len(rows) > query.limit
    items = rows[:query.limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = repo.encode_cursor(last["changed_at"], last["id"])
    return {"items": [_resource(row) for row in items], "pagination": {"next_cursor": next_cursor, "has_more": has_more}}


async def handle_compare_company_change_history(query: CompareCompanyChangeHistoryQuery, session: AsyncSession) -> dict[str, Any]:
    if not await repo.company_exists(session, query.company_id):
        raise ServiceError("Компания не найдена.", 404, code="COMPANY_NOT_FOUND")
    base = await repo.get_history_record(session, query.company_id, query.base_id)
    target = await repo.get_history_record(session, query.company_id, query.target_id)
    if base is None or target is None:
        raise ServiceError("Версия истории не найдена для указанной компании.", 404, code="HISTORY_VERSION_NOT_FOUND")
    if (target["changed_at"], target["id"]) <= (base["changed_at"], base["id"]):
        raise ServiceError("Целевая версия должна быть позже базовой.", 422, code="INVALID_VERSION_ORDER")
    old_snapshot, new_snapshot = base["snapshot"], target["snapshot"]
    fields = sorted(set(old_snapshot) | set(new_snapshot))
    diffs = [{"field": field, "old_value": old_snapshot.get(field), "new_value": new_snapshot.get(field)}
             for field in fields if old_snapshot.get(field) != new_snapshot.get(field)]
    return {"base": _resource(base), "target": _resource(target), "diffs": diffs}
