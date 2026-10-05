
"""Submit every cart item as an exchange_request in one batch.

LC нажимает «Отправить дилерам» — каждый item превращается в
``exchange_requests`` со ссылками на выбранные склады/опции/комментарии и
со статусом ``open``. Все новые записи получают один общий
``batch_number`` и порядковый ``batch_index`` — так дилерские UI могут
группировать рассылки. После успешного создания корзина очищается.

Items без выбранных складов пропускаются — отправлять такой item некуда.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from application.services.exchange_access import require_exchange_company
from application.services.exchange_dates import dwh_expiration_date
from application.services.exchange_notification_events import record_exchange_event
from application.services.exchange_supports import (
    resolve_exchange_support_selection,
)
from domain.entities.exchange_request import STATUS_OPEN, ExchangeRequest
from infrastructure.messaging.dwh_events import emit_exchange_request_changed
from infrastructure.repositories import exchange_cart_repository as cart_repo
from infrastructure.repositories import exchange_request_repository as req_repo


@dataclass
class SubmitExchangeCartCommand:
    user_id: UUID
    company_id: UUID | None = None


async def handle_submit_exchange_cart(
    cmd: SubmitExchangeCartCommand, session: AsyncSession
) -> dict[str, Any]:
    company_id = await require_exchange_company(session, user_id=cmd.user_id,
        role="leasing_company", company_id=cmd.company_id, write=True)
    items = await cart_repo.list_for_user(session, cmd.user_id)
    if not items:
        raise ServiceError("Корзина биржи пуста", 400)

    batch_number = await req_repo.next_batch_number(session)
    request_ids: list[UUID] = []
    batch_index = 0

    for item in items:
        ExchangeRequest(expiration_at=item.get("expiration_at")).ensure_not_expired()
        item_id = item["id"]
        wh_rows = await cart_repo.list_warehouses(session, item_id)
        warehouse_ids = [r["warehouse_id"] for r in wh_rows]
        if not warehouse_ids:
            # No warehouses selected → no dealers to notify; skip silently.
            continue
        dealer_map = await cart_repo.warehouse_dealer_map(
            session, warehouse_ids
        )
        options = await cart_repo.list_options(session, item_id)
        comments = await cart_repo.list_dealer_comments(session, item_id)
        comments_by_dealer = {
            c["dealer_id"]: c.get("comment") for c in comments
        }
        support_selection = await resolve_exchange_support_selection(
            session,
            user_id=cmd.user_id,
            vehicle_id=item["vehicle_id"],
            requested_ids=list(item.get("selected_support_ids") or []),
            select_default=True,
        )

        batch_index += 1
        request_id = await req_repo.create_request(
            session,
            lc_user_id=cmd.user_id,
            lc_company_id=company_id,
            vehicle_id=item["vehicle_id"],
            quantity=max(int(item.get("quantity") or 1), 1),
            discount_type=item.get("discount_type"),
            discount_value=item.get("discount_value"),
            file_url=item.get("file_url"),
            file_name=item.get("file_name"),
            expiration_at=item.get("expiration_at"),
            batch_number=batch_number,
            batch_index=batch_index,
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
            changed_by=cmd.user_id,
        )

        for wh_id in warehouse_ids:
            dealer_id = dealer_map.get(wh_id)
            if dealer_id is None:
                # Warehouse without an owner — skip so we don't write a
                # dead-end record that no dealer can see.
                continue
            await req_repo.add_warehouse(
                session,
                request_id=request_id,
                warehouse_id=wh_id,
                dealer_id=dealer_id,
            )
            dealer_comment = comments_by_dealer.get(dealer_id)
            if dealer_comment:
                await req_repo.upsert_dealer_comment(
                    session,
                    request_id=request_id,
                    dealer_id=dealer_id,
                    comment=dealer_comment,
                )

        if options:
            await req_repo.set_options(
                session,
                request_id=request_id,
                dealer_option_ids=[o["dealer_option_id"] for o in options],
            )

        saved = await req_repo.get_by_id(session, request_id)
        if saved is not None:
            await record_exchange_event(session, event_type="exchange.request_published", request=saved,
                actor_user_id=cmd.user_id)
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
        request_ids.append(request_id)

    if not request_ids:
        raise ServiceError(
            "Ни одна позиция корзины не имеет выбранных складов", 400
        )

    await cart_repo.clear_cart(session, cmd.user_id)

    return {
        "message": "Заявки биржи отправлены",
        "request_ids": request_ids,
        "count": len(request_ids),
        "batch_number": batch_number,
    }
