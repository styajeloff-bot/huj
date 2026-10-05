"""Role projections: what a leasing company may see about a deal.

A leasing company never receives support programs, amounts, comments, statuses or
their identifiers, nor a price breakdown that would reveal them. The projection is
built on the server from allow-lists; nothing is merely hidden in the UI.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from domain.fast_deals.values import HistoryEvent

# Fields of a position visible to a leasing company at any time.
LC_VEHICLE_FIELDS = (
    "id", "position", "vehicle_source_type", "vin", "vin_entered_manually",
    "mark_name", "model_name", "modification_name", "trim_name", "category_name",
    "body_color_name", "dealer_company_id", "final_price", "equipments", "services",
    "purposes", "regions", "item_status", "replaced_by_id",
)
# Visible only while no support has been accounted: otherwise base price, the
# adjustment and the final price together would disclose the support amount.
LC_PRICE_BREAKDOWN_FIELDS = (
    "base_price", "adjustment_type", "adjustment_amount", "options_amount",
)

# Fields tracked on a position for before/after changes of the dealer in DL.
TRACKED_VEHICLE_FIELDS = (
    "mark_name", "model_name", "modification_name", "body_color_name", "vin",
    "base_price", "adjustment_type", "adjustment_amount", "support_amount",
    "options_amount", "final_price", "equipments", "services", "purposes", "regions",
    "item_status",
)
# Of the tracked fields a leasing company may be shown the following changes.
LC_VISIBLE_CHANGE_FIELDS = frozenset(
    {
        "mark_name", "model_name", "modification_name", "body_color_name", "vin",
        "final_price", "equipments", "services", "purposes", "regions", "item_status",
        "status", "lease_term_months", "down_payment", "down_payment_percent",
        "monthly_payment", "buyout_amount", "total_cost", "total_amount",
        "vehicles_total", "confirmed_amount", "reason", "primary", "additional",
    }
)
SUPPORT_EVENTS = frozenset(
    {
        HistoryEvent.SUPPORT_APPLIED,
        HistoryEvent.SUPPORT_REMOVED,
        HistoryEvent.SUPPORT_REQUESTED,
        HistoryEvent.SUPPORT_DECIDED,
        HistoryEvent.SUPPORT_ACCOUNTED,
    }
)


def project_vehicle_for_lc(vehicle: Mapping[str, Any]) -> dict[str, Any]:
    """Allow-listed position; the breakdown only when it hides nothing."""
    result = {name: vehicle.get(name) for name in LC_VEHICLE_FIELDS}
    support = vehicle.get("support_amount") or Decimal(0)
    if support == 0:
        for name in LC_PRICE_BREAKDOWN_FIELDS:
            result[name] = vehicle.get(name)
    return result


def project_history_event_for_lc(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """A leasing company sees neither support events nor support values."""
    if event.get("event_type") in SUPPORT_EVENTS:
        return None
    projected = dict(event)
    projected["changes"] = filter_changes_for_lc(event.get("changes"))
    return projected


def filter_changes_for_lc(changes: Any) -> dict[str, Any] | None:
    """Keep allow-listed fields of flat ``{field: {before, after}}`` snapshots.

    Keys may be prefixed (``vehicle.<id>.final_price``): the last segment decides.
    """
    if not isinstance(changes, Mapping):
        return None
    kept = {
        key: value
        for key, value in changes.items()
        if str(key).rsplit(".", 1)[-1] in LC_VISIBLE_CHANGE_FIELDS
    }
    return kept or None


def vehicle_snapshot(vehicle: Mapping[str, Any]) -> dict[str, Any]:
    """Comparable image of a position for pending-change detection (DL)."""
    return {name: vehicle.get(name) for name in TRACKED_VEHICLE_FIELDS}


def deal_snapshot(vehicles: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Active positions keyed by id; the "before" side of dealer changes."""
    return {
        str(vehicle["id"]): vehicle_snapshot(vehicle)
        for vehicle in vehicles
        if vehicle.get("item_status") == "active"
    }


def diff_snapshots(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    *,
    vins: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Flat list of ``{vehicle_id, vin, field, before, after}`` for changed fields."""
    changes: list[dict[str, Any]] = []
    for vehicle_id in sorted(set(before) | set(after)):
        old = before.get(vehicle_id, {})
        new = after.get(vehicle_id, {})
        vin = (vins or {}).get(vehicle_id) or new.get("vin") or old.get("vin")
        changes.extend(
            {
                "vehicle_id": vehicle_id,
                "vin": vin,
                "field": field,
                "before": old.get(field),
                "after": new.get(field),
            }
            for field in TRACKED_VEHICLE_FIELDS
            if _norm(old.get(field)) != _norm(new.get(field))
        )
    return changes


def project_changes_for_lc(changes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The leasing company sees changed final prices and ordinary fields, no support."""
    return [
        dict(change) for change in changes if change["field"] in LC_VISIBLE_CHANGE_FIELDS
    ]


def _norm(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value
