"""Exchange-bid repository — async, dict-only API (Phase 5 E2)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.exchange import (
    ExchangeBid,
    ExchangeBidComment,
    ExchangeBidOption,
)
from infrastructure.repository_timing import timed_repository
from infrastructure.services.file_proxy import (
    exchange_bid_file_url,
    exchange_bid_kp_url,
)


def _bid_to_dict(row: ExchangeBid) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "dealer_id": row.dealer_id,
        "dealer_company_id": row.dealer_company_id,
        "price": row.price,
        "quantity": row.quantity,
        "comment": row.comment,
        "is_accepted": bool(row.is_accepted),
        # Proxy private-bucket files through backend endpoints.
        "kp_file_url": (
            exchange_bid_kp_url(row.id) if row.kp_file_url else None
        ),
        "kp_file_name": row.kp_file_name,
        "kp_status": row.kp_status,
        "kp_dealer_comment": row.kp_dealer_comment,
        "kp_sent_at": row.kp_sent_at,
        "kp_responded_at": row.kp_responded_at,
        "bid_file_url": (
            exchange_bid_file_url(row.id) if row.bid_file_url else None
        ),
        "bid_file_name": row.bid_file_name,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

def _comment_to_dict(row: ExchangeBidComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "bid_id": row.bid_id,
        "user_id": row.user_id,
        "comment": row.comment,
        "created_at": row.created_at,
    }

def _option_to_dict(row: ExchangeBidOption) -> dict[str, Any]:
    return {
        "id": row.id,
        "bid_id": row.bid_id,
        "dealer_option_id": row.dealer_option_id,
    }

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@timed_repository
async def get_by_id(
    session: AsyncSession, bid_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(ExchangeBid, bid_id, populate_existing=True)
    if row is None:
        return None
    return _bid_to_dict(row)

@timed_repository
async def get_bid_file_meta(
    session: AsyncSession, bid_id: UUID
) -> tuple[str | None, str | None, UUID, UUID] | None:
    """Raw ``(bid_file_url, bid_file_name, dealer_id, request_id)``."""
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return None
    return (
        row.bid_file_url,
        row.bid_file_name,
        row.dealer_id,
        row.request_id,
    )

@timed_repository
async def get_bid_kp_meta(
    session: AsyncSession, bid_id: UUID
) -> tuple[str | None, str | None, UUID, UUID] | None:
    """Raw ``(kp_file_url, kp_file_name, dealer_id, request_id)``."""
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return None
    return (
        row.kp_file_url,
        row.kp_file_name,
        row.dealer_id,
        row.request_id,
    )

@timed_repository
async def find_by_request_and_dealer(
    session: AsyncSession, *, request_id: UUID, dealer_id: UUID
) -> dict[str, Any] | None:
    stmt = select(ExchangeBid).where(
        ExchangeBid.request_id == request_id,
        ExchangeBid.dealer_id == dealer_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _bid_to_dict(row)

@timed_repository
async def list_for_dealer(
    session: AsyncSession, *, dealer_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeBid)
        .where(ExchangeBid.dealer_id == dealer_id)
        .order_by(ExchangeBid.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_bid_to_dict(r) for r in rows]

@timed_repository
async def list_for_request(
    session: AsyncSession, *, request_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeBid)
        .where(ExchangeBid.request_id == request_id)
        .order_by(ExchangeBid.price.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_bid_to_dict(r) for r in rows]

@timed_repository
async def list_options(
    session: AsyncSession, bid_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeBidOption)
        .where(ExchangeBidOption.bid_id == bid_id)
        .order_by(ExchangeBidOption.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_option_to_dict(r) for r in rows]

@timed_repository
async def list_comments(
    session: AsyncSession, bid_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeBidComment)
        .where(ExchangeBidComment.bid_id == bid_id)
        .order_by(ExchangeBidComment.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_comment_to_dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

async def delete_bid(session: AsyncSession, bid_id: UUID) -> None:
    await session.execute(delete(ExchangeBid).where(ExchangeBid.id == bid_id))
    await session.flush()

@timed_repository
async def create_bid(
    session: AsyncSession,
    *,
    request_id: UUID,
    dealer_id: UUID,
    price: Decimal,
    dealer_company_id: UUID | None = None,
    quantity: int = 1,
    comment: str | None = None,
) -> UUID:
    row = ExchangeBid(
        request_id=request_id,
        dealer_id=dealer_id,
        dealer_company_id=dealer_company_id,
        price=price,
        quantity=quantity,
        comment=comment,
        is_accepted=False,
        kp_status="none",
    )
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def update_bid(
    session: AsyncSession,
    bid_id: UUID,
    *,
    price: Decimal | None = None,
    quantity: int | None = None,
    comment: str | None = None,
) -> bool:
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return False
    if price is not None:
        cast("Any", row).price = price
    if quantity is not None:
        row.quantity = quantity
    if comment is not None:
        row.comment = comment
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def set_is_accepted(
    session: AsyncSession, bid_id: UUID, *, is_accepted: bool
) -> bool:
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return False
    row.is_accepted = is_accepted
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def set_kp_status(
    session: AsyncSession,
    bid_id: UUID,
    *,
    status: str,
    comment: str | None = None,
) -> bool:
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return False
    row.kp_status = status
    row.kp_dealer_comment = comment
    cast("Any", row).updated_at = datetime.now(UTC)
    if status in {"accepted", "rejected"}:
        cast("Any", row).kp_responded_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def set_options(
    session: AsyncSession,
    *,
    bid_id: UUID,
    dealer_option_ids: list[UUID],
) -> None:
    await session.execute(
        delete(ExchangeBidOption).where(ExchangeBidOption.bid_id == bid_id)
    )
    for opt_id in dealer_option_ids:
        session.add(
            ExchangeBidOption(bid_id=bid_id, dealer_option_id=opt_id)
        )
    await session.flush()

@timed_repository
async def add_comment(
    session: AsyncSession,
    *,
    bid_id: UUID,
    user_id: UUID,
    comment: str,
) -> dict[str, Any]:
    row = ExchangeBidComment(
        bid_id=bid_id, user_id=user_id, comment=comment
    )
    session.add(row)
    await session.flush()
    return _comment_to_dict(row)

@timed_repository
async def set_bid_file(
    session: AsyncSession,
    bid_id: UUID,
    *,
    file_url: str,
    file_name: str,
) -> bool:
    """Dealer attaches a supporting file to their own bid."""
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return False
    row.bid_file_url = file_url
    row.bid_file_name = file_name
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def set_kp_file(
    session: AsyncSession,
    bid_id: UUID,
    *,
    file_url: str,
    file_name: str,
) -> bool:
    """LC uploads a КП (commercial proposal) file for a dealer's bid.

    Moves ``kp_status`` to ``sent``, records ``kp_sent_at`` and clears any
    previous dealer response.
    """
    row = await session.get(ExchangeBid, bid_id)
    if row is None:
        return False
    row.kp_file_url = file_url
    row.kp_file_name = file_name
    row.kp_status = "sent"
    row.kp_dealer_comment = None
    cast("Any", row).kp_sent_at = datetime.now(UTC)
    row.kp_responded_at = None
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True
