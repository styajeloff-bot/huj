
"""LC uploads a КП (commercial proposal) file to a specific dealer's bid."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.services.exchange_access import require_lc_request_access
from domain.entities.exchange_bid import ExchangeBid
from domain.entities.exchange_request import ExchangeRequest
from domain.errors import (
    ExchangeBidNotFoundError,
    ExchangeRequestNotFoundError,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.messaging.dwh_events import emit_exchange_bid_changed
from infrastructure.repositories import (
    exchange_bid_repository as bid_repo,
)
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)


@dataclass
class UploadKpToBidCommand:
    request_id: UUID
    bid_id: UUID
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)
    filename: str
    content_type: str
    data: bytes


async def handle_upload_kp_to_bid(
    cmd: UploadKpToBidCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    req_raw = await req_repo.get_by_id(session, cmd.request_id)
    if req_raw is None:
        raise ExchangeRequestNotFoundError(cmd.request_id)
    request = ExchangeRequest.from_dict(req_raw)
    await require_lc_request_access(session, req_raw, user_id=cmd.lc_user_id, company_id=cmd.company_id, write=True)
    request.ensure_can_receive_bid()

    bid_raw = await bid_repo.get_by_id(session, cmd.bid_id)
    if bid_raw is None or str(bid_raw["request_id"]) != str(cmd.request_id):
        raise ExchangeBidNotFoundError(cmd.bid_id)
    bid = ExchangeBid.from_dict(bid_raw)

    ts = int(time.time() * 1000)
    safe_name = cmd.filename or "file"
    key = (
        f"exchange/requests/{cmd.request_id}/kp/bid-{bid.id}/{ts}_{safe_name}"
    )
    await storage.put(key, cmd.data, cmd.content_type)

    # Store the bare S3 key — proxy endpoint serves the blob.
    await bid_repo.set_kp_file(
        session, bid.id, file_url=key, file_name=safe_name
    )

    saved = await bid_repo.get_by_id(session, bid.id)
    assert saved is not None
    emit_exchange_bid_changed({
        "bid_id": bid.id,
        "request_id": saved.get("request_id"),
        "dealer_id": saved.get("dealer_id"),
        "price": str(saved.get("price")) if saved.get("price") is not None else None,
        "comment": saved.get("comment"),
        "is_accepted": bool(saved.get("is_accepted")),
        "kp_file_url": saved.get("kp_file_url"),
        "kp_file_name": saved.get("kp_file_name"),
        "kp_status": saved.get("kp_status"),
        "kp_dealer_comment": saved.get("kp_dealer_comment"),
        "kp_sent_at": _isoformat(saved.get("kp_sent_at")),
        "kp_responded_at": _isoformat(saved.get("kp_responded_at")),
        "quantity": saved.get("quantity"),
        "bid_file_url": saved.get("bid_file_url"),
        "bid_file_name": saved.get("bid_file_name"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return {"message": "КП отправлено", "bid": saved}
