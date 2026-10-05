"""Immutable transaction-local Exchange facts, never transport or recipients."""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.events import record_notification_event


def request_number(request: dict[str, Any]) -> str:
    if request.get("batch_number") is not None and request.get("batch_index") is not None:
        return f'{request["batch_number"]}-{request["batch_index"]}'
    return str(request["id"])


async def record_exchange_event(
    session: AsyncSession, *, event_type: str, request: dict[str, Any],
    actor_user_id: UUID | None = None, previous: dict[str, Any] | None = None,
    bid: dict[str, Any] | None = None, payload: dict[str, Any] | None = None,
    occurrence_key: str | None = None,
) -> UUID | None:
    current = bid if bid is not None else request
    allowed = ("price", "quantity", "comment", "dealer_option_ids") if bid is not None else (
        "quantity", "discount_type", "discount_value", "expiration_at", "status", "accepted_bid_id",
        "file_url", "file_name",
    )
    old = previous or {}
    changed = [key for key in allowed if old.get(key) != current.get(key)]
    if previous is not None and not changed and event_type in {"exchange.bid_updated", "exchange.request_changed"}:
        return None
    details = {"expiration_at": request.get("expiration_at"),
               "lc_company_id": request.get("lc_company_id"), **(payload or {})}
    if bid is None and {"file_url", "file_name"}.intersection(changed):
        details["attachment_name"] = request.get("file_name")
    if bid is not None:
        details.update({"bid_id": bid["id"], "dealer_company_id": bid.get("dealer_company_id"),
                        "price": bid.get("price")})
    return await record_notification_event(
        session, event_type=event_type,
        entity_type="exchange_bid" if bid is not None else "exchange_request",
        entity_id=current["id"], aggregate_id=request["id"],
        request_number=request_number(request), actor_user_id=actor_user_id,
        previous_values={key: old.get(key) for key in changed},
        new_values={key: current.get(key) for key in changed},
        payload=details, occurrence_key=occurrence_key,
    )
