"""Financial mutations use one row lock and an explicit calculation revision."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.monetization.views import (
    ROLE_PARTY,
    deal_view,
    is_deal_participant,
)
from domain.monetization.deals import adjust_deal, confirm_deal, platform_auto_amount
from domain.monetization.errors import MonetizationConflict, MonetizationError
from domain.monetization.programs import calculate_program, select_program
from infrastructure.repositories import monetization_repository as repo


def require_write(actor: dict[str, Any]) -> None:
    if not actor["can_write"]:
        raise ServiceError("Доступен только просмотр монетизации", 403)


def require_revision(deal: dict[str, Any], revision: int) -> None:
    if deal["revision"] != revision:
        raise MonetizationConflict("Суммы сделки изменились. Обновите карточку.")


async def confirm(session: AsyncSession, deal_id: UUID, actor: dict[str, Any],
                  revision: int) -> dict[str, Any]:
    require_write(actor)
    current = await repo.lock_deal(session, deal_id, actor)
    if current is None:
        raise ServiceError("Сделка монетизации не найдена", 404)
    require_revision(current, revision)
    if not is_deal_participant(current, actor):
        raise ServiceError("Вы не являетесь подтверждающей стороной сделки", 403)
    party = ROLE_PARTY[actor["role"]]
    changed = confirm_deal(current, party, actor["user_id"], datetime.now(UTC))
    changed["confirmations"][party]["user_name"] = actor.get("user_name")
    saved = await repo.update_deal(session, deal_id, {
        "status": changed["status"], "confirmations": changed["confirmations"],
    })
    from application.notifications.monetization import notify_deal_confirmation

    await notify_deal_confirmation(session, saved, party, actor["user_id"])
    return {"deal": deal_view(saved, actor)}


async def adjust(session: AsyncSession, deal_id: UUID, actor: dict[str, Any],
                 revision: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    require_write(actor)
    current = await repo.lock_deal(session, deal_id, actor)
    if current is None:
        raise ServiceError("Сделка монетизации не найдена", 404)
    require_revision(current, revision)
    changed = adjust_deal(current, items, actor["user_id"], datetime.now(UTC))
    did_change = changed["revision"] != current["revision"]
    if did_change:
        await repo.replace_amounts(
            session, deal_id, changed["amounts"], actor["user_id"], changed["revision"])
        await repo.update_deal(session, deal_id, {
            "revision": changed["revision"], "confirmations": changed["confirmations"],
        })
    saved = await repo.get_deal(session, deal_id, actor)
    assert saved is not None
    if did_change:
        from application.notifications.monetization import notify_deal_terms_changed

        await notify_deal_terms_changed(session, saved, actor["user_id"])
    platform_auto = platform_auto_amount(saved["amounts"])
    return {"deal": {
        **deal_view(saved, actor),
        "platform_auto_amount": platform_auto,
        "confirmations_reset": did_change and any(
            (current.get("confirmations") or {}).get(role, {}).get("confirmed_at")
            for role in ("leasing", "dealer", "distributor")),
    }}


async def capture(session: AsyncSession, context: dict[str, Any]) -> dict[str, Any]:
    """Freeze the authoritative source snapshot and enqueue its outcome atomically."""
    from application.notifications.monetization import notify_capture_result

    existing = await repo.find_source_deal(session, context)
    if existing is not None:
        result: dict[str, Any] = {"deal": existing, "reason": None}
    else:
        try:
            candidates = await repo.list_candidate_programs(session, context)
            program = select_program(candidates, context)
            if program is None:
                result = {"deal": None, "reason": "Подходящие условия монетизации не найдены"}
            else:
                amounts = calculate_program(program, context)
                result = {"deal": await repo.insert_deal(session, context, program, amounts), "reason": None}
        except MonetizationError as exc:
            result = {"deal": None, "reason": str(exc)}
    await notify_capture_result(session, context, result)
    return result
