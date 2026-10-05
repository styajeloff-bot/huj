"""Capture commission once on a real source transition; source business rules stay intact."""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.deals import capture
from application.notifications.monetization import notify_capture_result
from domain.monetization.errors import MonetizationError
from domain.monetization.sources import build_source_context
from infrastructure.repositories import monetization_source_repository as sources

logger = logging.getLogger("carcraft-backend")


async def capture_source_transition(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    leasing_company_application_id: UUID | None = None,
    exchange_request_id: UUID | None = None,
) -> dict[str, Any]:
    """A savepoint preserves the completed source action when capture is impossible.

    Caller already holds the source row lock and owns the transaction. This is
    invoked only at the transition, never on historical reads or replayed deals.
    """
    if (leasing_company_application_id is None) == (exchange_request_id is None):
        raise ValueError("Укажите ровно один источник монетизации")
    context: dict[str, Any] = {
        "actor_user_id": actor_user_id,
        "leasing_company_application_id": leasing_company_application_id,
        "exchange_request_id": exchange_request_id,
    }
    try:
        async with session.begin_nested():
            if leasing_company_application_id is not None:
                facts = await sources.lca_source(
                    session, leasing_company_application_id
                )
            elif exchange_request_id is not None:
                facts = await sources.exchange_source(session, exchange_request_id)
            context.update(facts)
            context = build_source_context(context, datetime.now(UTC))
            return await capture(session, context)
    except MonetizationError as exc:
        result: dict[str, Any] = {"deal": None, "reason": str(exc)}
    except Exception:
        logger.exception("monetization_source_capture_failed")
        result = {
            "deal": None,
            "reason": "Не удалось зафиксировать монетизацию: ошибка обработки исходной сделки",
        }
    await notify_capture_result(session, context, result)
    return result
