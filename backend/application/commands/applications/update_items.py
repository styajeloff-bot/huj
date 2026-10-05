"""Partially update editable application lines by their stable line id."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from domain.errors import ApplicationNotFoundError
from domain.leasing_purposes import selected_purposes
from infrastructure.repositories import application_repository as repo


@dataclass(frozen=True)
class ApplicationItemUpdate:
    line_id: UUID
    kind: Literal["vehicle", "special_equipment"]
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    regions: list[str] = field(default_factory=list)
    region: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class UpdateApplicationItemsCommand:
    application_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    items: list[ApplicationItemUpdate] = field(default_factory=list)


async def handle_update_application_items(
    cmd: UpdateApplicationItemsCommand,
    session: AsyncSession,
) -> dict[str, object]:
    current = await repo.get_by_id(session, cmd.application_id, for_update=True)
    if current is None:
        raise ApplicationNotFoundError(cmd.application_id)
    await require_can_mutate_application(
        session,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        application=current,
    )
    entity = await ensure_application_owned_by(
        session,
        application=current,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
    )
    if cmd.actor_role == "client":
        entity.ensure_editable(
            has_lc_children=await repo.has_lc_children(session, cmd.application_id)
        )

    if not cmd.items:
        return {"ok": True, "items": []}

    purposes = {row["purpose_name"] for row in await repo.list_leasing_purposes(session)}
    region_rows = await repo.list_leasing_regions(session)
    valid_regions = {
        value
        for row in region_rows
        for value in (row["region_name"], row["region_display_name"], row["region_number"])
    }

    editable_rows = {
        row["line_id"]: row
        for row in await repo.get_application_item_edit_rows(
            session, cmd.application_id, [item.line_id for item in cmd.items]
        )
    }
    response_items: list[dict[str, object]] = []
    for item in cmd.items:
        row = editable_rows.get(item.line_id)
        if row is None:
            raise ServiceError("Позиция не найдена в заявке", 404)
        if item.kind != row["kind"]:
            raise ServiceError("Некорректный тип позиции заявки", 422)
        selected = selected_purposes(item.leasing_purposes, item.leasing_purpose)
        previous = selected_purposes(row.get("leasing_purposes"), row.get("leasing_purpose"))
        if item.kind == "special_equipment" and any(len(value) > 100 for value in selected):
            raise ServiceError("Цель приобретения не должна превышать 100 символов", 422)
        if any(value not in purposes and value not in previous for value in selected):
            raise ServiceError("Пожалуйста, выберите цель лизинга из списка", 422)
        regions = list(dict.fromkeys([
            *item.regions,
            *([item.region] if item.region else []),
        ]))
        if any(region not in valid_regions for region in regions):
            raise ServiceError("Пожалуйста, выберите корректный регион из списка", 422)
        response_items.append({
            "line_id": item.line_id,
            "kind": item.kind,
            "leasing_purpose": next(iter(selected), None),
            "leasing_purposes": selected,
            "regions": regions,
            "region": item.region,
            "comment": item.comment,
        })
    await repo.update_application_item_fields(session, cmd.application_id, response_items)
    return {"ok": True, "items": response_items}
