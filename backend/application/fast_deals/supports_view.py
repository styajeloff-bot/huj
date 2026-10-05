"""Read side of supports: what each party sees on a position and which actions apply.

Support data exists only on the dealer's side of a deal. A leasing company gets
nothing at all (not zeros), a distributor sees only the requests addressed to its
company, the platform reads everything. The same dealer-side rule decides who may
act, so the card and the commands cannot disagree.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import DealContext
from application.fast_deals.support_rules import reduces_price
from domain.fast_deals.values import FINAL_STATUSES, DealStatus, Party
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_support_repository as support_repo

Record = dict[str, Any]

NO_DISTRIBUTOR_HINT = "Для этой марки не найден ваш дистрибьютор"
OPEN_REQUEST_STATUSES = frozenset({"requested", "pre_approved"})


def is_dealer_side(ctx: DealContext) -> bool:
    """The dealer of the deal: the initiator of a DD, the dealer of a DL part."""
    return ctx.party == Party.DEALER or (ctx.party == Party.INITIATOR and ctx.is_dd)


def dealer_may_change_supports(ctx: DealContext) -> bool:
    """Requests and programs are open while the dealer still has a say in the deal."""
    if ctx.status in FINAL_STATUSES:
        return False
    return ctx.is_dd or ctx.status == DealStatus.PENDING_DEALER_CONFIRMATION


async def resolve_distributors(
    session: AsyncSession, deal: Record, vehicles: list[Record]
) -> dict[UUID, UUID]:
    """Distributor of every position that can ask one: ``{vehicle_id: distributor}``.

    The distributor is the dealer's linked one and must actively serve the position's
    mark; a manual text mark has no directory id and so no distributor.
    """
    dealer_id = deal.get("dealer_company_id")
    if dealer_id is None:
        return {}
    mark_ids = sorted({item["mark_id"] for item in vehicles if item.get("mark_id")}, key=str)
    by_mark = await support_repo.distributors_by_mark(session, dealer_id, mark_ids)
    return {
        item["id"]: by_mark[item["mark_id"]]
        for item in vehicles
        if item.get("mark_id") in by_mark
    }


async def support_action_facts(session: AsyncSession, ctx: DealContext) -> dict[str, Any]:
    """Keyword facts for ``DealContext.actions`` / ``DealContext.require``."""
    facts: dict[str, Any] = {
        "has_unaccounted_support": False,
        "open_support_requests": 0,
        "can_request_support": False,
    }
    active_ids = {item["id"] for item in ctx.vehicles}
    if is_dealer_side(ctx):
        unaccounted = await support_repo.unaccounted_by_vehicle(session, ctx.deal_id)
        facts["has_unaccounted_support"] = any(
            amount > 0 for vehicle_id, amount in unaccounted.items() if vehicle_id in active_ids
        )
        requests = await support_repo.list_support_requests(session, ctx.deal_id)
        facts["can_request_support"] = bool(await _requestable_vehicles(session, ctx, requests))
    elif ctx.party == Party.DISTRIBUTOR and ctx.actor.company_id is not None:
        requests = await support_repo.list_support_requests(session, ctx.deal_id)
        facts["open_support_requests"] = sum(
            1
            for item in requests
            if item["distributor_company_id"] == ctx.actor.company_id
            and item["status"] in OPEN_REQUEST_STATUSES
            and item["fast_deal_vehicle_id"] in active_ids
        )
    return facts


async def _requestable_vehicles(
    session: AsyncSession, ctx: DealContext, requests: list[Record]
) -> dict[UUID, UUID]:
    """Positions that may get a request now: a distributor exists and none is open."""
    if not dealer_may_change_supports(ctx):
        return {}
    distributors = await resolve_distributors(session, ctx.deal, ctx.vehicles)
    busy = {
        item["fast_deal_vehicle_id"]
        for item in requests
        if item["status"] in OPEN_REQUEST_STATUSES
    }
    return {vehicle_id: owner for vehicle_id, owner in distributors.items() if vehicle_id not in busy}


async def build_vehicle_support_views(
    session: AsyncSession, ctx: DealContext
) -> dict[UUID, dict[str, Any]]:
    """Support keys of each active position for the card, by the viewer's party.

    Dealer side and platform: applied programs, the latest request, the unaccounted
    amount and whether a request is possible. Distributor: only its own requests.
    Leasing company (also the initiator of a DL): nothing.
    """
    if ctx.party in {Party.LEASING, Party.NONE}:
        return {}
    if ctx.party == Party.INITIATOR and not ctx.is_dd:
        return {}
    requests = await support_repo.list_support_requests(session, ctx.deal_id)
    by_vehicle: dict[UUID, list[Record]] = defaultdict(list)
    for item in requests:
        by_vehicle[item["fast_deal_vehicle_id"]].append(item)

    if ctx.party == Party.DISTRIBUTOR:
        own = ctx.actor.company_id
        views: dict[UUID, dict[str, Any]] = {}
        for vehicle in ctx.vehicles:
            mine = [r for r in by_vehicle.get(vehicle["id"], []) if r["distributor_company_id"] == own]
            views[vehicle["id"]] = {"support_request": request_view(_pick_request(mine), {})} if mine else {}
        return views

    applied_by_vehicle: dict[UUID, list[Record]] = defaultdict(list)
    for row in await support_repo.list_applied_supports(session, ctx.deal_id):
        if row["fast_deal_vehicle_id"] is not None:
            applied_by_vehicle[row["fast_deal_vehicle_id"]].append(row)
    unaccounted = await support_repo.unaccounted_by_vehicle(session, ctx.deal_id)
    dealer_side = is_dealer_side(ctx)
    requestable = await _requestable_vehicles(session, ctx, requests) if dealer_side else {}
    distributors = await resolve_distributors(session, ctx.deal, ctx.vehicles) if dealer_side else {}
    names = await access_repo.company_briefs(
        session, sorted({item["distributor_company_id"] for item in requests}, key=str)
    )
    can_change = dealer_side and dealer_may_change_supports(ctx)
    views = {}
    for vehicle in ctx.vehicles:
        vehicle_id = vehicle["id"]
        request = _pick_request(by_vehicle.get(vehicle_id, []))
        amount = unaccounted.get(vehicle_id, Decimal(0))
        views[vehicle_id] = {
            "applied_supports": [applied_view(row) for row in applied_by_vehicle.get(vehicle_id, [])],
            "support_request": request_view(request, names) if request is not None else None,
            "unaccounted_support": amount if amount > 0 else None,
            "can_request_support": vehicle_id in requestable,
            "support_hint": (
                NO_DISTRIBUTOR_HINT if can_change and vehicle_id not in distributors else None
            ),
        }
    return views


def _pick_request(items: list[Record]) -> Record | None:
    """The open request of a position, else the latest decided one."""
    if not items:
        return None
    open_items = [item for item in items if item["status"] in OPEN_REQUEST_STATUSES]
    pool = open_items or items
    return max(pool, key=lambda item: (item["created_at"], str(item["id"])))


def applied_view(row: Record) -> Record:
    """An applied program as the dealer side sees it; the snapshot, not the live program."""
    return {
        "id": row["id"],
        "name": row["name"],
        "support_type": row["support_type"],
        "support_amount": row["support_amount"],
        "base_amount": row["base_amount"],
        "support_program_id": row["support_program_id"],
        "comment": row["comment"],
        "affects_price": reduces_price(row["support_type"]),
    }


def request_view(row: Record | None, names: dict[UUID, Record]) -> Record | None:
    if row is None:
        return None
    distributor = names.get(row["distributor_company_id"])
    return {
        "id": row["id"],
        "status": row["status"],
        "requested_amount": row["requested_amount"],
        "decided_amount": row["decided_amount"],
        "accounted_amount": row["accounted_amount"],
        "comment": row["comment"],
        "decision_comment": row["decision_comment"],
        "distributor_company_id": row["distributor_company_id"],
        "distributor_name": distributor["name"] if distributor else None,
        "created_at": row["created_at"],
        "decided_at": row["decided_at"],
    }
