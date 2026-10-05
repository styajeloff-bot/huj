"""List an LC user's own exchange requests (optionally filtered by status).

Each row is enriched inline so the LC cabinet card can render without
extra round-trips: vehicle catalogue fields (mark/model/generation/...),
selected warehouses with dealer names, dealer_options list, bids with
their own option sets and a precomputed ``bid_count``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import require_exchange_company
from application.services.exchange_supports import (
    selected_support_price_summary,
)
from application.support_programs import build_applicable_support_programs
from infrastructure.repositories import calculator_repository
from infrastructure.repositories import compensation_repository as comp_repo
from infrastructure.repositories import exchange_request_repository as repo

logger = logging.getLogger("carcraft-backend")


@dataclass
class ListLcRequestsQuery:
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)
    status: str | None = None
    page: int = 1
    limit: int = 20


async def handle_list_lc_requests(
    query: ListLcRequestsQuery, session: AsyncSession
) -> dict[str, Any]:
    company_id = await require_exchange_company(session, user_id=query.lc_user_id,
        role="leasing_company", company_id=query.company_id)
    page = max(1, query.page)
    limit = max(1, query.limit)
    offset = (page - 1) * limit

    rows = await repo.list_for_lc(
        session,
        lc_user_id=query.lc_user_id,
        lc_company_id=company_id,
        status=query.status,
        limit=limit,
        offset=offset,
    )
    total = await repo.count_for_lc(
        session, lc_user_id=query.lc_user_id, lc_company_id=company_id, status=query.status
    )
    pages = (total + limit - 1) // limit if total else 0

    enriched = await enrich_requests(session, rows)

    return {
        "requests": enriched,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": pages,
        },
    }


async def enrich_requests(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    own_dealer_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Attach vehicle / warehouses / options / bids to raw request rows.

    When ``own_dealer_id`` is provided, every bid this dealer placed gets
    ``is_own=True`` — used by the dealer cabinet to highlight their rows.
    """
    if not rows:
        return []
    request_ids = [r["id"] for r in rows]
    vehicle_ids = list({r["vehicle_id"] for r in rows if r.get("vehicle_id")})
    support_ids = list(
        {
            support_id
            for row in rows
            for support_id in row.get("selected_support_ids") or []
        }
    )

    vehicles_map = await repo.vehicle_enrichment_by_ids(session, vehicle_ids)
    support_details = (
        await calculator_repository.get_support_program_details_by_ids(
            session, support_ids
        )
        if support_ids
        else []
    )
    support_details_by_id = {
        detail["id"]: detail for detail in support_details
    }
    support_snapshots_by_request = (
        await comp_repo.list_applied_supports_for_exchange_requests(
            session, request_ids
        )
    )
    missing = [vid for vid in vehicle_ids if vid not in vehicles_map]
    if missing:
        logger.warning(
            "exchange enrich: vehicle rows not found for ids=%s "
            "(request_ids=%s) — card will fall back to 'Автомобиль #id'",
            missing, request_ids,
        )
    for vid in vehicles_map:
        v = vehicles_map[vid]
        if not v.get("mark_name") and not v.get("model_name"):
            logger.warning(
                "exchange enrich: vehicle id=%s has no mark/model joined "
                "(mark_id=%s, model_id=%s) — catalog lookup returned empty",
                vid, v.get("mark_id") or "<missing>", v.get("model_id") or "<missing>",
            )
        if v.get("base_price") in (None, 0):
            logger.warning(
                "exchange enrich: vehicle id=%s has no base_price set",
                vid,
            )
    warehouses_map = await repo.warehouses_with_meta_for_requests(
        session, request_ids
    )
    options_map = await repo.options_with_meta_for_requests(
        session, request_ids
    )
    bids_map, bid_counts = await repo.bids_with_options_for_requests(
        session, request_ids
    )
    dealer_comments_map = await repo.dealer_comments_for_requests(
        session, request_ids
    )
    logger.info(
        "exchange enrich: request_ids=%s own_dealer_id=%s "
        "bid_counts=%s bid_dealer_ids=%s",
        request_ids,
        own_dealer_id,
        bid_counts,
        {rid: [b.get("dealer_id") for b in bids] for rid, bids in bids_map.items()},
    )

    out: list[dict[str, Any]] = []
    for row in rows:
        rid = row["id"]
        vehicle_id = row.get("vehicle_id")
        vehicle_fields = vehicles_map.get(vehicle_id, {})
        enriched = dict(row)
        # Copy display fields onto the request root so the frontend
        # ExchangeRequest type sees them at the top level.
        for key in (
            "mark_name",
            "mark_cyrillic",
            "model_name",
            "model_cyrillic",
            "generation_name",
            "configuration_name",
            "group_name",
            "color",
            "vehicle_year",
            "base_price",
            "discount_price",
            "images",
        ):
            if key in vehicle_fields:
                enriched[key] = vehicle_fields.get(key)
        enriched.setdefault("images", [])
        support_program_details = _request_support_details(
            row,
            vehicle_fields=vehicle_fields,
            current_details_by_id=support_details_by_id,
            snapshots=support_snapshots_by_request.get(rid, []),
        )
        enriched["support_program_details"] = support_program_details
        enriched.update(
            selected_support_price_summary(
                support_program_details,
                list(row.get("selected_support_ids") or []),
                fallback_base_price=float(
                    vehicle_fields.get("base_price") or 0
                ),
            )
        )
        enriched["warehouses"] = warehouses_map.get(rid, [])
        enriched["options"] = options_map.get(rid, [])
        bids = bids_map.get(rid, [])
        if own_dealer_id is not None:
            for bid in bids:
                bid["is_own"] = bid.get("dealer_id") == own_dealer_id
        enriched["bids"] = bids
        enriched["bid_count"] = bid_counts.get(rid, 0)
        enriched["dealer_comments"] = dealer_comments_map.get(rid, [])
        out.append(enriched)
    return out


def _request_support_details(
    request: dict[str, Any],
    *,
    vehicle_fields: dict[str, Any],
    current_details_by_id: dict[UUID, dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    vehicle_id = request["vehicle_id"]
    snapshots_by_program = {
        snapshot["support_program_id"]: snapshot
        for snapshot in snapshots
        if snapshot.get("support_program_id") is not None
    }
    detail_rows: list[dict[str, Any]] = []
    vehicle_rows: list[dict[str, Any]] = []
    for support_id in request.get("selected_support_ids") or []:
        current = current_details_by_id.get(support_id, {})
        snapshot = snapshots_by_program.get(support_id)
        if snapshot is not None:
            detail_rows.append(
                {
                    **current,
                    "id": support_id,
                    "name": snapshot["name"],
                    "support_type": snapshot["support_type"],
                    "support_params": snapshot["support_params"],
                    "comment": snapshot.get("comment"),
                    "starts_at": snapshot.get("starts_at"),
                    "ends_at": snapshot.get("ends_at"),
                }
            )
            vehicle_rows.append(
                {
                    "vehicle_id": vehicle_id,
                    "support_program_id": support_id,
                    "base_price": snapshot["base_amount"],
                    "support_type": snapshot["support_type"],
                    "support_params": snapshot["support_params"],
                }
            )
            continue
        if not current:
            continue
        vehicle_rows.append(
            {
                "vehicle_id": vehicle_id,
                "support_program_id": support_id,
                "base_price": vehicle_fields.get("base_price") or 0,
                "support_type": current["support_type"],
                "support_params": current.get("support_params") or {},
            }
        )
        detail_rows.append(current)

    summaries = build_applicable_support_programs(
        vehicle_rows,
        detail_rows,
    ).get(vehicle_id, [])
    snapshot_amounts = {
        support_id: float(snapshot["support_amount"])
        for support_id, snapshot in snapshots_by_program.items()
    }
    for summary in summaries:
        snapshot_amount = snapshot_amounts.get(summary["id"])
        if snapshot_amount is None:
            continue
        amount = max(0, round(snapshot_amount))
        summary["support_amount"] = amount
        if summary["display_price"] < summary["base_price"]:
            summary["display_price"] = max(
                0, summary["base_price"] - amount
            )
    return summaries
