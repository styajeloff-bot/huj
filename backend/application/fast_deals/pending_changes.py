"""DL: the dealer's changes against the state the leasing company sent.

When a deal goes to its dealer, ``sent_snapshot`` keeps every active position as the
leasing company wrote it. While the deal waits for the dealer, each change the dealer
makes is compared with that snapshot: ``has_pending_changes`` is true exactly while
the current positions differ from it. Confirming without changes is possible only
when there are none; otherwise the dealer sends the changes to the leasing company.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.fast_deals.projection import (
    deal_snapshot,
    diff_snapshots,
    project_changes_for_lc,
)
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]


def jsonable_snapshot(snapshot: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """JSON image of a snapshot: money and ids as exact strings."""
    return {
        vehicle_id: {name: _jsonable(value) for name, value in fields.items()}
        for vehicle_id, fields in snapshot.items()
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


async def capture_sent_snapshot(session: AsyncSession, deal_id: UUID) -> dict[str, dict[str, Any]]:
    """The image of the active positions at the moment of sending (DL)."""
    vehicles: list[Record] = await repo.list_vehicles(session, deal_id)
    return jsonable_snapshot(deal_snapshot(vehicles))


async def refresh_pending_changes(
    session: AsyncSession, deal_id: UUID
) -> tuple[Record, list[dict[str, Any]]]:
    """Recompute the difference and store ``has_pending_changes`` accordingly."""
    deal: Record | None = await repo.get_deal(session, deal_id)
    assert deal is not None
    vehicles: list[Record] = await repo.list_vehicles(session, deal_id)
    before: dict[str, dict[str, Any]] = deal.get("sent_snapshot") or {}
    after = jsonable_snapshot(deal_snapshot(vehicles))
    changes = diff_snapshots(before, after)
    if bool(changes) != bool(deal["has_pending_changes"]):
        deal = await repo.update_deal(session, deal_id, {"has_pending_changes": bool(changes)})
    return deal, changes


def changes_for_card(changes: list[dict[str, Any]], *, leasing_view: bool) -> list[dict[str, Any]]:
    """The leasing company sees changed final prices and ordinary fields, no support."""
    return project_changes_for_lc(changes) if leasing_view else changes
