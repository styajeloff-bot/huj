
"""Resubmit (duplicate) an archived / deal exchange request as a new record.

Matches the legacy Express behavior: a closed request is copied into a
fresh ``open`` request owned by the same LC. Source warehouses, dealer
options and per-dealer comments are carried over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from application.services.exchange_access import require_lc_request_access
from application.services.exchange_dates import dwh_expiration_date
from application.services.exchange_notification_events import record_exchange_event
from application.services.exchange_supports import (
    resolve_exchange_support_selection,
)
from domain.entities.exchange_request import (
    STATUS_ARCHIVED,
    STATUS_DEAL,
    STATUS_OPEN,
    ExchangeRequest,
)
from domain.errors import (
    ExchangeRequestNotFoundError,
    InvalidExchangeRequestStatusError,
)
from infrastructure.messaging.dwh_events import emit_exchange_request_changed
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class ResubmitExchangeRequestCommand:
    request_id: UUID
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)


async def handle_resubmit_exchange_request(
    cmd: ResubmitExchangeRequestCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.lock_request(session, cmd.request_id)
    if current is None:
        raise ExchangeRequestNotFoundError(cmd.request_id)
    entity = ExchangeRequest.from_dict(current)
    company_id = await require_lc_request_access(session, current, user_id=cmd.lc_user_id, company_id=cmd.company_id, write=True)
    if entity.status not in {STATUS_ARCHIVED, STATUS_DEAL}:
        raise InvalidExchangeRequestStatusError(
            "Создать повторно можно только для архивных заявок или "
            "заявок в статусе сделки"
        )

    previous_support_ids = list(current.get("selected_support_ids") or [])
    try:
        support_selection = await resolve_exchange_support_selection(
            session,
            user_id=cmd.lc_user_id,
            vehicle_id=entity.vehicle_id,
            requested_ids=previous_support_ids,
            select_default=True,
        )
    except ServiceError:
        support_selection = await resolve_exchange_support_selection(
            session,
            user_id=cmd.lc_user_id,
            vehicle_id=entity.vehicle_id,
            requested_ids=[],
            select_default=True,
        )

    batch_number = await repo.next_batch_number(session)
    new_request_id = await repo.create_request(
        session,
        lc_user_id=cmd.lc_user_id,
        lc_company_id=company_id,
        vehicle_id=entity.vehicle_id,
        quantity=max(entity.quantity, 1),
        discount_type=entity.discount_type,
        discount_value=entity.discount_value,
        file_url=entity.file_url,
        file_name=entity.file_name,
        expiration_at=entity.expiration_at if entity.expiration_at and entity.expiration_at > datetime.now(UTC) else None,
        batch_number=batch_number,
        batch_index=1,
        status=STATUS_OPEN,
        selected_support_ids=support_selection.selected_ids,
    )
    from infrastructure.messaging.status_events import (
        emit_exchange_request_status_changed,
    )
    emit_exchange_request_status_changed(
        request_id=new_request_id,
        old_status=None,
        new_status=STATUS_OPEN,
        changed_by=cmd.lc_user_id,
    )

    # Carry over warehouses / dealer ids / dealer comments / options.
    source_warehouses = await repo.list_warehouses(
        session, request_id=cmd.request_id
    )
    for wh in source_warehouses:
        await repo.add_warehouse(
            session,
            request_id=new_request_id,
            warehouse_id=wh["warehouse_id"],
            dealer_id=wh["dealer_id"],
        )

    source_comments = await repo.list_dealer_comments(
        session, request_id=cmd.request_id
    )
    for c in source_comments:
        comment_text = c.get("comment")
        if comment_text:
            await repo.upsert_dealer_comment(
                session,
                request_id=new_request_id,
                dealer_id=c["dealer_id"],
                comment=str(comment_text),
            )

    source_options = await repo.list_options(
        session, request_id=cmd.request_id
    )
    option_ids = [o["dealer_option_id"] for o in source_options]
    if option_ids:
        await repo.set_options(
            session,
            request_id=new_request_id,
            dealer_option_ids=option_ids,
        )

    saved = await repo.get_by_id(session, new_request_id)
    assert saved is not None
    await record_exchange_event(session, event_type="exchange.request_published", request=saved,
        actor_user_id=cmd.lc_user_id)
    emit_exchange_request_changed({
        "request_id": new_request_id,
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
        "message": "Заявка биржи создана повторно",
        "request_id": new_request_id,
        "request": saved,
        "batch_number": batch_number,
    }
