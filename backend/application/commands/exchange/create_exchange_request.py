
"""Create an exchange request (LC-owned).

Supports atomic batch creation: when multiple warehouses/dealers are
targeted, the first step of the batch is allocated a ``batch_number`` and
each request persisted with an increasing ``batch_index``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.services.exchange_access import require_exchange_company
from application.services.exchange_dates import dwh_expiration_date
from application.services.exchange_notification_events import record_exchange_event
from application.services.exchange_supports import (
    resolve_exchange_support_selection,
)
from domain.entities.exchange_request import STATUS_OPEN, ExchangeRequest
from infrastructure.messaging.dwh_events import emit_exchange_request_changed
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class ExchangeRequestWarehousePayload:
    warehouse_id: UUID
    dealer_id: UUID
    dealer_comment: str | None = None


@dataclass
class CreateExchangeRequestCommand:
    lc_user_id: UUID
    vehicle_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)
    quantity: int = 1
    discount_type: str | None = None
    discount_value: Decimal | None = None
    file_url: str | None = None
    file_name: str | None = None
    expiration_at: Any | None = None
    dealer_option_ids: list[UUID] = field(default_factory=list)
    warehouses: list[ExchangeRequestWarehousePayload] = field(
        default_factory=list
    )
    selected_support_ids: list[UUID] = field(default_factory=list)


async def handle_create_exchange_request(
    cmd: CreateExchangeRequestCommand, session: AsyncSession
) -> dict[str, Any]:
    ExchangeRequest(expiration_at=cmd.expiration_at).ensure_not_expired()
    company_id = await require_exchange_company(session, user_id=cmd.lc_user_id,
        role="leasing_company", company_id=cmd.company_id, write=True)
    support_selection = await resolve_exchange_support_selection(
        session,
        user_id=cmd.lc_user_id,
        vehicle_id=cmd.vehicle_id,
        requested_ids=list(cmd.selected_support_ids),
        select_default=True,
    )
    batch_number = await repo.next_batch_number(session)

    request_id = await repo.create_request(
        session,
        lc_user_id=cmd.lc_user_id,
        lc_company_id=company_id,
        vehicle_id=cmd.vehicle_id,
        quantity=max(cmd.quantity, 1),
        discount_type=cmd.discount_type,
        discount_value=cmd.discount_value,
        file_url=cmd.file_url,
        file_name=cmd.file_name,
        expiration_at=cmd.expiration_at,
        batch_number=batch_number,
        batch_index=1,
        status=STATUS_OPEN,
        selected_support_ids=support_selection.selected_ids,
    )
    from infrastructure.messaging.status_events import (
        emit_exchange_request_status_changed,
    )
    emit_exchange_request_status_changed(
        request_id=request_id,
        old_status=None,
        new_status=STATUS_OPEN,
        changed_by=cmd.lc_user_id,
    )

    for wh in cmd.warehouses:
        await repo.add_warehouse(
            session,
            request_id=request_id,
            warehouse_id=wh.warehouse_id,
            dealer_id=wh.dealer_id,
        )
        if wh.dealer_comment:
            await repo.upsert_dealer_comment(
                session,
                request_id=request_id,
                dealer_id=wh.dealer_id,
                comment=wh.dealer_comment,
            )

    if cmd.dealer_option_ids:
        await repo.set_options(
            session,
            request_id=request_id,
            dealer_option_ids=cmd.dealer_option_ids,
        )

    saved = await repo.get_by_id(session, request_id)
    assert saved is not None
    await record_exchange_event(session, event_type="exchange.request_published", request=saved,
        actor_user_id=cmd.lc_user_id)
    emit_exchange_request_changed({
        "request_id": request_id,
        "lc_user_id": saved.get("lc_user_id"),
        "vehicle_id": saved.get("vehicle_id"),
        "quantity": saved.get("quantity"),
        "expiration_date": dwh_expiration_date(saved.get("expiration_at")),
        "discount_type": saved.get("discount_type"),
        "discount_value": str(saved.get("discount_value")) if saved.get("discount_value") is not None else None,
        "file_url": saved.get("file_url"),
        "file_name": saved.get("file_name"),
        "status": saved.get("status"),
        "accepted_bid_id": saved.get("accepted_bid_id"),
        "batch_number": saved.get("batch_number"),
        "batch_index": saved.get("batch_index"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return {
        "message": "Заявка биржи создана",
        "request": saved,
        "batch_number": batch_number,
    }
