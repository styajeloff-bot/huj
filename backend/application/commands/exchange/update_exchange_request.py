
"""Update an exchange request (LC-owned)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.services.exchange_access import require_lc_request_access
from application.services.exchange_dates import dwh_expiration_date
from application.services.exchange_notification_events import record_exchange_event
from domain.entities.exchange_request import ExchangeRequest
from domain.errors import ExchangeRequestNotFoundError
from infrastructure.messaging.dwh_events import emit_exchange_request_changed
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class UpdateExchangeRequestCommand:
    request_id: UUID
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)
    quantity: int | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    expiration_at: Any | None = None
    expiration_at_set: bool = False
    file_url: str | None = None
    file_name: str | None = None


async def handle_update_exchange_request(
    cmd: UpdateExchangeRequestCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.lock_request(session, cmd.request_id)
    if current is None:
        raise ExchangeRequestNotFoundError(cmd.request_id)
    entity = ExchangeRequest.from_dict(current)
    await require_lc_request_access(session, current, user_id=cmd.lc_user_id, company_id=cmd.company_id, write=True)
    entity.ensure_can_receive_bid()
    # The HTTP projection masks storage URLs behind a stable proxy route. Read
    # the old source only for the internal event snapshot, under the same lock.
    previous_file = await repo.get_request_file_meta(session, cmd.request_id) if cmd.file_url is not None else None

    await repo.update_request_core(
        session,
        cmd.request_id,
        quantity=cmd.quantity,
        discount_type=cmd.discount_type,
        discount_value=cmd.discount_value,
        expiration_at=cmd.expiration_at,
        expiration_at_set=cmd.expiration_at_set,
        file_url=cmd.file_url,
        file_name=cmd.file_name,
    )

    updated = await repo.get_by_id(session, cmd.request_id)
    assert updated is not None
    event_before, event_after = current, updated
    if previous_file is not None:
        updated_file = await repo.get_request_file_meta(session, cmd.request_id)
        assert updated_file is not None
        event_before = current | {"file_url": previous_file[0]}
        event_after = updated | {"file_url": updated_file[0]}
    await record_exchange_event(session, event_type="exchange.request_changed", request=event_after,
        previous=event_before, actor_user_id=cmd.lc_user_id)
    emit_exchange_request_changed({
        "request_id": cmd.request_id,
        "lc_user_id": updated.get("lc_user_id"),
        "vehicle_id": updated.get("vehicle_id"),
        "quantity": updated.get("quantity"),
        "expiration_date": dwh_expiration_date(updated.get("expiration_at")),
        "discount_type": updated.get("discount_type"),
        "discount_value": str(updated.get("discount_value")) if updated.get("discount_value") is not None else None,
        "file_url": updated.get("file_url"),
        "file_name": updated.get("file_name"),
        "status": updated.get("status"),
        "accepted_bid_id": updated.get("accepted_bid_id"),
        "batch_number": updated.get("batch_number"),
        "batch_index": updated.get("batch_index"),
        "created_at": _isoformat(updated.get("created_at")),
        "updated_at": _isoformat(updated.get("updated_at")),
        "_deleted": False,
    })
    return {"message": "Заявка биржи обновлена", "request": updated}
