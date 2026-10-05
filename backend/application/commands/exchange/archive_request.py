
"""Archive an exchange request (LC-owned)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.services.exchange_access import require_lc_request_access
from application.services.exchange_dates import dwh_expiration_date
from application.services.exchange_notification_events import record_exchange_event
from domain.entities.exchange_request import STATUS_ARCHIVED, ExchangeRequest
from domain.errors import ExchangeRequestNotFoundError
from infrastructure.messaging.dwh_events import emit_exchange_request_changed
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class ArchiveExchangeRequestCommand:
    request_id: UUID
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)


async def handle_archive_exchange_request(
    cmd: ArchiveExchangeRequestCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.lock_request(session, cmd.request_id)
    if current is None:
        raise ExchangeRequestNotFoundError(cmd.request_id)
    entity = ExchangeRequest.from_dict(current)
    await require_lc_request_access(session, current, user_id=cmd.lc_user_id, company_id=cmd.company_id, write=True)
    entity.ensure_can_archive()

    await repo.set_status(session, cmd.request_id, status=STATUS_ARCHIVED)
    from infrastructure.messaging.status_events import (
        emit_exchange_request_status_changed,
    )
    emit_exchange_request_status_changed(
        request_id=cmd.request_id,
        old_status=entity.status,
        new_status=STATUS_ARCHIVED,
        changed_by=cmd.lc_user_id,
    )
    archived = await repo.get_by_id(session, cmd.request_id)
    if archived is not None:
        await record_exchange_event(session, event_type="exchange.request_finalized", request=archived,
            previous=current, actor_user_id=cmd.lc_user_id)
        emit_exchange_request_changed({
            "request_id": cmd.request_id,
            "lc_user_id": archived.get("lc_user_id"),
            "vehicle_id": archived.get("vehicle_id"),
            "quantity": archived.get("quantity"),
            "expiration_date": dwh_expiration_date(archived.get("expiration_at")),
            "discount_type": archived.get("discount_type"),
            "discount_value": str(archived.get("discount_value")) if archived.get("discount_value") is not None else None,
            "file_url": archived.get("file_url"),
            "file_name": archived.get("file_name"),
            "status": archived.get("status"),
            "accepted_bid_id": archived.get("accepted_bid_id"),
            "batch_number": archived.get("batch_number"),
            "batch_index": archived.get("batch_index"),
            "created_at": _isoformat(archived.get("created_at")),
            "updated_at": _isoformat(archived.get("updated_at")),
            "_deleted": False,
        })
    return {"message": "Заявка архивирована"}
