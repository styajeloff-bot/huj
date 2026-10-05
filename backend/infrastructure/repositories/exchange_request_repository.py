"""Exchange-request repository — async, dict-only API (Phase 5 E2)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import DateTime, String, and_, case, delete, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from infrastructure.models.companies import Company
from infrastructure.models.exchange import (
    DealerOption,
    ExchangeBid,
    ExchangeBidOption,
    ExchangeRequest,
    ExchangeRequestDealerComment,
    ExchangeRequestFile,
    ExchangeRequestOption,
    ExchangeRequestWarehouse,
)
from infrastructure.models.notification_delivery import NotificationEventOutbox
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repository_timing import timed_repository
from infrastructure.services.file_proxy import (
    exchange_bid_file_url,
    exchange_bid_kp_url,
    exchange_request_file_url,
)


def _request_to_dict(row: ExchangeRequest) -> dict[str, Any]:
    prod_id = getattr(row, "product_id", getattr(row, "vehicle_id", None))
    return {
        "id": row.id,
        "lc_user_id": row.lc_user_id,
        "lc_company_id": row.lc_company_id,
        "distributor_id": row.distributor_id,
        "product_id": prod_id,
        "vehicle_id": prod_id,
        "quantity": row.quantity,
        "expiration_at": row.expiration_at,
        "discount_type": row.discount_type,
        "discount_value": row.discount_value,
        # Proxy raw-S3 URLs through a backend endpoint — bucket is private.
        "file_url": (
            exchange_request_file_url(row.id) if row.file_url else None
        ),
        "file_name": row.file_name,
        "status": row.status,
        "accepted_bid_id": row.accepted_bid_id,
        "selected_support_ids": list(row.selected_support_ids or []),
        "batch_number": row.batch_number,
        "batch_index": row.batch_index,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

def _warehouse_to_dict(row: ExchangeRequestWarehouse) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "warehouse_id": row.warehouse_id,
        "dealer_id": row.dealer_id,
    }

def _option_to_dict(row: ExchangeRequestOption) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "dealer_option_id": row.dealer_option_id,
    }

def _comment_to_dict(row: ExchangeRequestDealerComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "dealer_id": row.dealer_id,
        "comment": row.comment,
    }

def _file_to_dict(row: ExchangeRequestFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "dealer_id": row.dealer_id,
        "file_url": row.file_url,
        "file_name": row.file_name,
        "file_type": row.file_type,
        "uploaded_by": row.uploaded_by,
        "created_at": row.created_at,
    }

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _lc_owned(user_id: UUID, company_id: UUID | None) -> ColumnElement[bool]:
    legacy = and_(ExchangeRequest.lc_company_id.is_(None), ExchangeRequest.lc_user_id == user_id)
    return or_(ExchangeRequest.lc_company_id == company_id, legacy) if company_id else legacy


async def get_notification_context(session: AsyncSession, request_id: UUID) -> dict[str, Any] | None:
    request = await get_by_id(session, request_id)
    if request is None:
        return None
    dealers = await list_company_ids_for_request(session, request_id)
    bidders = list((await session.execute(select(ExchangeBid.dealer_company_id).where(
        ExchangeBid.request_id == request_id, ExchangeBid.dealer_company_id.is_not(None),
    ).distinct())).scalars().all())
    return {"request": request, "dealer_company_ids": dealers,
            "bidding_dealer_company_ids": bidders, "lc_company_id": request["lc_company_id"],
            "distributor_id": request["distributor_id"]}


async def lock_request(session: AsyncSession, request_id: UUID) -> dict[str, Any] | None:
    row = (await session.execute(select(ExchangeRequest).where(
        ExchangeRequest.id == request_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    return _request_to_dict(row) if row else None


async def list_due_deadlines(session: AsyncSession, now: datetime) -> list[dict[str, Any]]:
    from datetime import timedelta
    event_type = case((ExchangeRequest.expiration_at <= now + timedelta(hours=1), "exchange.deadline_1h"),
                      else_="exchange.deadline_24h")
    reminder_exists = select(NotificationEventOutbox.event_id).where(
        NotificationEventOutbox.aggregate_id == ExchangeRequest.id,
        NotificationEventOutbox.event_type == event_type,
        NotificationEventOutbox.payload["payload"]["expiration_at"].astext.cast(DateTime(timezone=True)) == ExchangeRequest.expiration_at,
    ).exists()
    rows = (await session.execute(select(ExchangeRequest).where(
        ExchangeRequest.status == "open", ExchangeRequest.expiration_at.is_not(None),
        ExchangeRequest.expiration_at <= now + timedelta(hours=24),
        or_(ExchangeRequest.expiration_at <= now, ~reminder_exists),
    ).order_by(ExchangeRequest.expiration_at).with_for_update(skip_locked=True).limit(500))).scalars().all()
    return [_request_to_dict(row) for row in rows]


async def list_for_distributor(
    session: AsyncSession, *, company_id: UUID, dealer_company_ids: list[UUID],
    status: str | None = None, limit: int = 20, offset: int = 0,
) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
    selected = select(ExchangeRequestWarehouse.request_id).where(
        ExchangeRequestWarehouse.dealer_id.in_(dealer_company_ids),
    )
    predicate = or_(ExchangeRequest.distributor_id == company_id, ExchangeRequest.id.in_(selected))
    counts = {"open": 0, "deal": 0, "archived": 0}
    counts.update({state: int(count) for state, count in (await session.execute(select(ExchangeRequest.status, func.count()).where(
        predicate,
    ).group_by(ExchangeRequest.status))).all()})
    if status:
        predicate = and_(predicate, ExchangeRequest.status == status)
    total = int((await session.execute(select(func.count()).select_from(ExchangeRequest).where(predicate))).scalar() or 0)
    rows = (await session.execute(select(ExchangeRequest).where(predicate).order_by(
        ExchangeRequest.created_at.desc(), ExchangeRequest.id,
    ).offset(offset).limit(limit))).scalars().all()
    return [_request_to_dict(row) for row in rows], total, counts

@timed_repository
async def get_by_id(
    session: AsyncSession, request_id: UUID
) -> dict[str, Any] | None:
    row = (await session.execute(
        select(ExchangeRequest).where(ExchangeRequest.id == request_id)
    )).scalar_one_or_none()
    if row is None:
        return None
    return _request_to_dict(row)

@timed_repository
async def list_for_lc(
    session: AsyncSession,
    *,
    lc_user_id: UUID,
    lc_company_id: UUID | None = None,
    status: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeRequest)
        .where(_lc_owned(lc_user_id, lc_company_id))
        .order_by(ExchangeRequest.created_at.desc())
    )
    if status:
        stmt = stmt.where(ExchangeRequest.status == status)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_request_to_dict(r) for r in rows]

@timed_repository
async def count_for_lc(
    session: AsyncSession,
    *,
    lc_user_id: UUID,
    lc_company_id: UUID | None = None,
    status: str | None = None,
) -> int:
    stmt = select(func.count(ExchangeRequest.id)).where(
        _lc_owned(lc_user_id, lc_company_id)
    )
    if status:
        stmt = stmt.where(ExchangeRequest.status == status)
    return int((await session.execute(stmt)).scalar() or 0)

@timed_repository
async def list_for_dealer(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    company_id: UUID | None = None,
    status: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    where_clause = (
        ExchangeRequestWarehouse.dealer_id == company_id
        if company_id is not None
        else ExchangeRequestWarehouse.dealer_id == dealer_id
    )

    stmt = (
        select(ExchangeRequest)
        .join(
            ExchangeRequestWarehouse,
            ExchangeRequestWarehouse.request_id == ExchangeRequest.id,
        )
        .join(
            Warehouse,
            Warehouse.id == ExchangeRequestWarehouse.warehouse_id,
            isouter=True,
        )
        .where(where_clause)
        .order_by(ExchangeRequest.created_at.desc())
        .distinct()
    )
    if status:
        stmt = stmt.where(ExchangeRequest.status == status)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_request_to_dict(r) for r in rows]

@timed_repository
async def count_for_dealer(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    company_id: UUID | None = None,
    status: str | None = None,
) -> int:
    where_clause = (
        ExchangeRequestWarehouse.dealer_id == company_id
        if company_id is not None
        else ExchangeRequestWarehouse.dealer_id == dealer_id
    )

    stmt = (
        select(func.count(func.distinct(ExchangeRequest.id)))
        .select_from(ExchangeRequest)
        .join(
            ExchangeRequestWarehouse,
            ExchangeRequestWarehouse.request_id == ExchangeRequest.id,
        )
        .join(
            Warehouse,
            Warehouse.id == ExchangeRequestWarehouse.warehouse_id,
            isouter=True,
        )
        .where(where_clause)
    )
    if status:
        stmt = stmt.where(ExchangeRequest.status == status)
    return int((await session.execute(stmt)).scalar() or 0)

@timed_repository
async def status_counts_for_lc(
    session: AsyncSession, *, lc_user_id: UUID, lc_company_id: UUID | None = None
) -> dict[str, int]:
    stmt = (
        select(ExchangeRequest.status, func.count(ExchangeRequest.id))
        .where(_lc_owned(lc_user_id, lc_company_id))
        .group_by(ExchangeRequest.status)
    )
    rows = (await session.execute(stmt)).all()
    counts = {"open": 0, "deal": 0, "archived": 0}
    for status, count in rows:
        if status in counts:
            counts[status] = int(count)
    return counts

@timed_repository
async def status_counts_for_dealer(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    company_id: UUID | None = None,
) -> dict[str, int]:
    where_clause = (
        ExchangeRequestWarehouse.dealer_id == company_id
        if company_id is not None
        else ExchangeRequestWarehouse.dealer_id == dealer_id
    )

    stmt = (
        select(
            ExchangeRequest.status,
            func.count(func.distinct(ExchangeRequest.id)),
        )
        .join(
            ExchangeRequestWarehouse,
            ExchangeRequestWarehouse.request_id == ExchangeRequest.id,
        )
        .join(
            Warehouse,
            Warehouse.id == ExchangeRequestWarehouse.warehouse_id,
            isouter=True,
        )
        .where(where_clause)
        .group_by(ExchangeRequest.status)
    )
    rows = (await session.execute(stmt)).all()
    counts = {"open": 0, "deal": 0, "archived": 0}
    for status, count in rows:
        if status in counts:
            counts[status] = int(count)
    return counts

@timed_repository
async def list_warehouses(
    session: AsyncSession, request_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeRequestWarehouse)
        .where(ExchangeRequestWarehouse.request_id == request_id)
        .order_by(ExchangeRequestWarehouse.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_warehouse_to_dict(r) for r in rows]

@timed_repository
async def get_request_file_meta(
    session: AsyncSession, request_id: UUID
) -> tuple[str | None, str | None, UUID] | None:
    """Raw ``(file_url, file_name, lc_user_id)`` for a request."""
    row = (await session.execute(
        select(ExchangeRequest).where(ExchangeRequest.id == request_id)
    )).scalar_one_or_none()
    if row is None:
        return None
    return (
        row.file_url,
        row.file_name,
        row.lc_user_id,
    )

@timed_repository
async def list_dealer_ids_for_request(
    session: AsyncSession, request_id: UUID
) -> list[UUID]:
    stmt = (
        select(ExchangeRequestWarehouse.dealer_id)
        .where(ExchangeRequestWarehouse.request_id == request_id)
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    return [r[0] for r in rows if r[0] is not None]

@timed_repository
async def list_company_ids_for_request(
    session: AsyncSession, request_id: UUID
) -> list[UUID]:
    stmt = (
        select(ExchangeRequestWarehouse.dealer_id)
        .where(ExchangeRequestWarehouse.request_id == request_id)
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    return [r[0] for r in rows if r[0] is not None]

@timed_repository
async def list_options(
    session: AsyncSession, request_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeRequestOption)
        .where(ExchangeRequestOption.request_id == request_id)
        .order_by(ExchangeRequestOption.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_option_to_dict(r) for r in rows]

@timed_repository
async def list_dealer_comments(
    session: AsyncSession, request_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeRequestDealerComment)
        .where(ExchangeRequestDealerComment.request_id == request_id)
        .order_by(ExchangeRequestDealerComment.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_comment_to_dict(r) for r in rows]

@timed_repository
async def list_files(
    session: AsyncSession, request_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ExchangeRequestFile)
        .where(ExchangeRequestFile.request_id == request_id)
        .order_by(ExchangeRequestFile.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_file_to_dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Batch enrichment — used by list endpoints (LC cabinet + dealer cabinet)
# ---------------------------------------------------------------------------

@timed_repository
async def vehicle_enrichment_by_ids(
    session: AsyncSession, vehicle_ids: list[UUID]
) -> dict[UUID, dict[str, Any]]:
    """Return {vehicle_id → display fields} for the given set.

    Mirrors the enrichment shape the exchange-cart repository uses for its
    list view (same column names so the frontend ``ExchangeRequest`` /
    ``ExchangeCartItem`` types stay interchangeable).
    """
    if not vehicle_ids:
        return {}
    stmt = (
        select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.id.label("vehicle_id"),
            SpecialEquipmentProduct.price.label("base_price"),
            SpecialEquipmentProduct.special_price.label("discount_price"),
            sql_cast(None, String).label("color"),
            SpecialEquipmentProduct.manufacture_year.label("vehicle_year"),
            sql_cast(None, JSONB).label("images"),
            SpecialEquipmentModel.mark_id.label("mark_id"),
            sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ).label("model_id"),
            SpecialEquipmentProduct.modification_id.label("modification_id"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentMark.name.label("mark_cyrillic"),
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentModel.name.label("model_cyrillic"),
            sql_cast(None, String).label("generation_name"),
            sa.func.coalesce(
                SpecialEquipmentModification.name,
                SpecialEquipmentProduct.superstructure_name,
            ).label("configuration_name"),
            sa.func.coalesce(
                SpecialEquipmentModification.name,
                SpecialEquipmentProduct.superstructure_name,
            ).label("group_name"),
            SpecialEquipmentProduct.superstructure_name,
            SpecialEquipmentProduct.superstructure_manufacturer,
        )
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(SpecialEquipmentProduct.id.in_(vehicle_ids))
    )
    out: dict[UUID, dict[str, Any]] = {}
    for row in (await session.execute(stmt)).mappings().all():
        d = dict(row)
        base = d.get("base_price")
        disc = d.get("discount_price")
        if isinstance(base, Decimal):
            d["base_price"] = float(base)
        if isinstance(disc, Decimal):
            d["discount_price"] = float(disc)
        raw_images = d.get("images")
        if isinstance(raw_images, dict):
            for key in ("urls", "list", "items"):
                value = raw_images.get(key)
                if isinstance(value, list):
                    d["images"] = [str(v) for v in value if v]
                    break
            else:
                d["images"] = []
        elif isinstance(raw_images, list):
            d["images"] = [str(v) for v in raw_images if v]
        else:
            d["images"] = []
        out[d["id"]] = d
    return out

@timed_repository
async def warehouses_with_meta_for_requests(
    session: AsyncSession, request_ids: list[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    """Grouped by ``request_id`` — each warehouse is enriched with the
    dealer's name + company + city label so the card can show `dealer_name`
    without extra round-trips.
    """
    if not request_ids:
        return {}
    stmt = (
        select(
            ExchangeRequestWarehouse.request_id,
            ExchangeRequestWarehouse.warehouse_id,
            ExchangeRequestWarehouse.dealer_id,
            Warehouse.address,
            Warehouse.brand,
            Warehouse.city_id,
            Warehouse.company_id,
            City.name.label("city_name"),
            Company.name.label("dealer_name"),
            Company.name.label("company_name"),
        )
        .select_from(ExchangeRequestWarehouse)
        .outerjoin(Warehouse, Warehouse.id == ExchangeRequestWarehouse.warehouse_id)
        .outerjoin(City, City.id == Warehouse.city_id)
        .outerjoin(Company, Company.id == ExchangeRequestWarehouse.dealer_id)
        .where(ExchangeRequestWarehouse.request_id.in_(request_ids))
        .order_by(ExchangeRequestWarehouse.id)
    )
    grouped: dict[UUID, list[dict[str, Any]]] = {rid: [] for rid in request_ids}
    for row in (await session.execute(stmt)).mappings().all():
        request_id = row["request_id"]
        grouped.setdefault(request_id, []).append(
            {
                "id": row["warehouse_id"],
                "dealer_id": row["dealer_id"],
                "dealer_name": row["dealer_name"],
                "company_id": row["dealer_id"],
                "company_name": row["company_name"],
                "address": row["address"],
                "brand": row["brand"],
                "city_id": row["city_id"],
                "city_name": row["city_name"],
            }
        )
    return grouped

@timed_repository
async def options_with_meta_for_requests(
    session: AsyncSession, request_ids: list[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    """Grouped by ``request_id`` — each option is the full ``DealerOption``
    (id, name, sort_order). ``id`` is the dealer_option id so the frontend
    can intersect it with bid options."""
    if not request_ids:
        return {}
    stmt = (
        select(
            ExchangeRequestOption.request_id,
            DealerOption.id,
            DealerOption.name,
            DealerOption.sort_order,
            DealerOption.is_active,
        )
        .select_from(ExchangeRequestOption)
        .join(DealerOption, DealerOption.id == ExchangeRequestOption.dealer_option_id)
        .where(ExchangeRequestOption.request_id.in_(request_ids))
        .order_by(DealerOption.sort_order, DealerOption.name)
    )
    grouped: dict[UUID, list[dict[str, Any]]] = {rid: [] for rid in request_ids}
    for row in (await session.execute(stmt)).mappings().all():
        request_id = row["request_id"]
        grouped.setdefault(request_id, []).append(
            {
                "id": row["id"],
                "name": row["name"],
                "sort_order": int(row["sort_order"] or 0),
                "is_active": bool(row["is_active"]),
            }
        )
    return grouped

@timed_repository
async def bids_with_options_for_requests(
    session: AsyncSession, request_ids: list[UUID]
) -> tuple[dict[UUID, list[dict[str, Any]]], dict[UUID, int]]:
    """Return ({request_id → [bid dict]}, {request_id → bid_count}).

    Bid dicts carry a nested ``options: [DealerOption]`` list so the card
    can compute best-bid option match client-side without another fetch.
    """
    if not request_ids:
        return {}, {}
    bids_stmt = (
        select(
            ExchangeBid.id,
            ExchangeBid.request_id,
            ExchangeBid.dealer_id,
            ExchangeBid.dealer_company_id,
            ExchangeBid.price,
            ExchangeBid.quantity,
            ExchangeBid.comment,
            ExchangeBid.is_accepted,
            ExchangeBid.kp_file_url,
            ExchangeBid.kp_file_name,
            ExchangeBid.kp_status,
            ExchangeBid.bid_file_url,
            ExchangeBid.bid_file_name,
            ExchangeBid.created_at,
            ExchangeBid.updated_at,
            User.name.label("dealer_name"),
        )
        .select_from(ExchangeBid)
        .outerjoin(User, User.id == ExchangeBid.dealer_id)
        .where(ExchangeBid.request_id.in_(request_ids))
        .order_by(ExchangeBid.price.asc())
    )
    bid_rows = (await session.execute(bids_stmt)).mappings().all()
    bid_ids = [row["id"] for row in bid_rows]
    bid_options_map: dict[UUID, list[dict[str, Any]]] = {
        bid_id: [] for bid_id in bid_ids
    }
    if bid_ids:
        opt_stmt = (
            select(
                ExchangeBidOption.bid_id,
                DealerOption.id,
                DealerOption.name,
                DealerOption.sort_order,
                DealerOption.is_active,
            )
            .select_from(ExchangeBidOption)
            .join(DealerOption, DealerOption.id == ExchangeBidOption.dealer_option_id)
            .where(ExchangeBidOption.bid_id.in_(bid_ids))
        )
        for opt in (await session.execute(opt_stmt)).mappings().all():
            bid_options_map.setdefault(opt["bid_id"], []).append(
                {
                    "id": opt["id"],
                    "name": opt["name"],
                    "sort_order": int(opt["sort_order"] or 0),
                    "is_active": bool(opt["is_active"]),
                }
            )

    grouped: dict[UUID, list[dict[str, Any]]] = {rid: [] for rid in request_ids}
    counts: dict[UUID, int] = dict.fromkeys(request_ids, 0)
    for row in bid_rows:
        request_id = row["request_id"]
        bid_id = row["id"]
        price = row["price"]
        grouped.setdefault(request_id, []).append(
            {
                "id": bid_id,
                "request_id": request_id,
                "dealer_id": row["dealer_id"],
                "dealer_company_id": row["dealer_company_id"],
                "dealer_name": row["dealer_name"],
                "price": float(price) if isinstance(price, Decimal) else price,
                "quantity": int(row["quantity"] or 1),
                "comment": row["comment"],
                "is_accepted": bool(row["is_accepted"]),
                "kp_file_url": (
                    exchange_bid_kp_url(bid_id) if row["kp_file_url"] else None
                ),
                "kp_file_name": row["kp_file_name"],
                "kp_status": row["kp_status"],
                "bid_file_url": (
                    exchange_bid_file_url(bid_id) if row["bid_file_url"] else None
                ),
                "bid_file_name": row["bid_file_name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "options": bid_options_map.get(row["id"], []),
                "rank": 0,
                "is_own": False,
            }
        )
        counts[request_id] = counts.get(request_id, 0) + 1
    # Rank within each request (cheapest first).
    for bids in grouped.values():
        for idx, b in enumerate(bids, start=1):
            b["rank"] = idx
    return grouped, counts

@timed_repository
async def dealer_comments_for_requests(
    session: AsyncSession, request_ids: list[UUID]
) -> dict[UUID, list[dict[str, Any]]]:
    if not request_ids:
        return {}
    stmt = (
        select(
            ExchangeRequestDealerComment.request_id,
            ExchangeRequestDealerComment.dealer_id,
            ExchangeRequestDealerComment.comment,
            Company.name.label("dealer_name"),
        )
        .select_from(ExchangeRequestDealerComment)
        .outerjoin(Company, Company.id == ExchangeRequestDealerComment.dealer_id)
        .where(ExchangeRequestDealerComment.request_id.in_(request_ids))
        .order_by(ExchangeRequestDealerComment.id)
    )
    grouped: dict[UUID, list[dict[str, Any]]] = {rid: [] for rid in request_ids}
    for row in (await session.execute(stmt)).mappings().all():
        request_id = row["request_id"]
        grouped.setdefault(request_id, []).append(
            {
                "dealer_id": row["dealer_id"],
                "dealer_name": row["dealer_name"] or "",
                "comment": row["comment"] or "",
            }
        )
    return grouped

# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

@timed_repository
async def create_request(
    session: AsyncSession,
    *,
    lc_user_id: UUID,
    product_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    lc_company_id: UUID | None = None,
    quantity: int = 1,
    discount_type: str | None = None,
    discount_value: Decimal | None = None,
    file_url: str | None = None,
    file_name: str | None = None,
    expiration_at: Any | None = None,
    batch_number: int | None = None,
    batch_index: int | None = None,
    status: str = "open",
    selected_support_ids: list[UUID] | None = None,
) -> UUID:
    target_id = product_id or vehicle_id
    if target_id is None:
        raise ValueError("product_id or vehicle_id must be provided")
    kwargs: dict[str, Any] = {
        "lc_user_id": lc_user_id,
        "lc_company_id": lc_company_id,
        "quantity": quantity,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "file_url": file_url,
        "file_name": file_name,
        "expiration_at": expiration_at,
        "batch_number": batch_number,
        "batch_index": batch_index,
        "status": status,
        "selected_support_ids": list(selected_support_ids or []),
    }
    if hasattr(ExchangeRequest, "product_id"):
        kwargs["product_id"] = target_id
    else:
        kwargs["vehicle_id"] = target_id
    row = ExchangeRequest(**kwargs)
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def update_request_core(
    session: AsyncSession,
    request_id: UUID,
    *,
    quantity: int | None = None,
    discount_type: str | None = None,
    discount_value: Decimal | None = None,
    expiration_at: Any | None = None,
    expiration_at_set: bool = False,
    file_url: str | None = None,
    file_name: str | None = None,
) -> bool:
    row = (await session.execute(
        select(ExchangeRequest).where(ExchangeRequest.id == request_id)
    )).scalar_one_or_none()
    if row is None:
        return False
    if quantity is not None:
        row.quantity = quantity
    if discount_type is not None:
        row.discount_type = discount_type
    if discount_value is not None:
        cast("Any", row).discount_value = discount_value
    if expiration_at_set or expiration_at is not None:
        row.expiration_at = expiration_at
    if file_url is not None:
        row.file_url = file_url
    if file_name is not None:
        row.file_name = file_name
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def set_status(
    session: AsyncSession,
    request_id: UUID,
    *,
    status: str,
    accepted_bid_id: UUID | None = None,
) -> bool:
    row = (await session.execute(
        select(ExchangeRequest).where(ExchangeRequest.id == request_id)
    )).scalar_one_or_none()
    if row is None:
        return False
    row.status = status
    if accepted_bid_id is not None:
        row.accepted_bid_id = accepted_bid_id
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def add_warehouse(
    session: AsyncSession,
    *,
    request_id: UUID,
    warehouse_id: UUID,
    dealer_id: UUID,
) -> UUID:
    row = ExchangeRequestWarehouse(
        request_id=request_id,
        warehouse_id=warehouse_id,
        dealer_id=dealer_id,
    )
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def set_options(
    session: AsyncSession,
    *,
    request_id: UUID,
    dealer_option_ids: list[UUID],
) -> None:
    await session.execute(
        delete(ExchangeRequestOption).where(
            ExchangeRequestOption.request_id == request_id
        )
    )
    for opt_id in dealer_option_ids:
        session.add(
            ExchangeRequestOption(
                request_id=request_id, dealer_option_id=opt_id
            )
        )
    await session.flush()

@timed_repository
async def upsert_dealer_comment(
    session: AsyncSession,
    *,
    request_id: UUID,
    dealer_id: UUID,
    comment: str | None,
) -> None:
    stmt = select(ExchangeRequestDealerComment).where(
        ExchangeRequestDealerComment.request_id == request_id,
        ExchangeRequestDealerComment.dealer_id == dealer_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is None:
        session.add(
            ExchangeRequestDealerComment(
                request_id=request_id,
                dealer_id=dealer_id,
                comment=comment,
            )
        )
    else:
        existing.comment = comment
    await session.flush()

@timed_repository
async def next_batch_number(session: AsyncSession) -> int:
    """Allocate a fresh batch number.

    The Express implementation uses a dedicated sequence
    (``exchange_request_batch_seq``). For portability we compute the next
    number as ``max(batch_number) + 1`` — this is sufficient for the use
    case (batch allocation happens within a single request handler).
    """
    stmt = select(func.coalesce(func.max(ExchangeRequest.batch_number), 0))
    current = int((await session.execute(stmt)).scalar() or 0)
    return current + 1
