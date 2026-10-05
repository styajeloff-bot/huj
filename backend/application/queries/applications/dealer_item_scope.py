"""Tenant-scoped response shaping for mixed application child lines."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import (
    resolve_distributor_application_dealer_filter,
)


async def resolve_actor_item_dealer_filter(
    session: AsyncSession,
    *,
    actor_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
) -> list[UUID] | None:
    """Resolve child-line ownership for roles with dealer data boundaries.

    None means the actor is not dealer-scoped. A company-less dealer gets
    an explicit empty scope so legacy author visibility cannot disclose child
    lines that cannot be attributed to that actor.
    """

    if actor_role == "dealer":
        return [actor_company_id] if actor_company_id is not None else []
    if actor_role != "distributor":
        return None
    return await resolve_distributor_application_dealer_filter(
        session,
        actor_id=actor_id,
        actor_role=actor_role,
        company_id=actor_company_id,
    )


_MIXED_APPLICATION_FINANCIAL_FIELDS = (
    "down_payment",
    "monthly_payment",
    "total_cost",
    "markup",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
)

_MIXED_CALCULATION_AGGREGATE_FIELDS = (
    "monthly_payment",
    "rate",
    "total_cost",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
    "vehicle_discount_support",
    "dealer_commission_support",
    "down_payment_support",
    "interest_support",
    "effective_total",
    "effective_down_payment",
)


def applications_with_hidden_items(
    *,
    vehicle_rows: list[dict[str, Any]],
    visible_vehicle_rows: list[dict[str, Any]],
    special_equipment_rows: list[dict[str, Any]],
    visible_special_equipment_rows: list[dict[str, Any]],
) -> set[UUID]:
    """Return application ids whose line projection was reduced by scope."""

    visible_keys = {
        ("vehicle", row["id"], row.get("quantity")) for row in visible_vehicle_rows
    } | {
        ("special_equipment", row["id"], row.get("quantity"))
        for row in visible_special_equipment_rows
    }
    return {
        row["application_id"]
        for item_type, rows in (
            ("vehicle", vehicle_rows),
            ("special_equipment", special_equipment_rows),
        )
        for row in rows
        if (item_type, row["id"], row.get("quantity")) not in visible_keys
    }


def redact_mixed_application_financials(
    application: dict[str, Any],
) -> None:
    """Remove full-application sums while retaining the scoped item total."""

    application["total_amount"] = application.get("total_items_price")
    for field_name in _MIXED_APPLICATION_FINANCIAL_FIELDS:
        application[field_name] = None


def scope_mixed_application_calculation(
    calculation: dict[str, Any] | None,
    *,
    allowed_vehicle_ids: set[UUID],
    scoped_total: Any,
) -> dict[str, Any] | None:
    """Retain safe per-vehicle rows and remove non-apportionable aggregates."""

    if calculation is None:
        return None

    allowed_ids = {str(vehicle_id) for vehicle_id in allowed_vehicle_ids}

    def filter_vehicle_rows(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            dict(row)
            for row in value
            if isinstance(row, dict)
            and str(row.get("vehicle_id")) in allowed_ids
        ]

    scoped = dict(calculation)
    for field_name in _MIXED_CALCULATION_AGGREGATE_FIELDS:
        scoped[field_name] = None
    scoped["base_total"] = scoped_total
    scoped["support_per_vehicle"] = filter_vehicle_rows(
        calculation.get("support_per_vehicle")
    )
    scoped["calculations_per_vehicle"] = filter_vehicle_rows(
        calculation.get("calculations_per_vehicle")
    )
    selected_support = calculation.get("selected_support")
    scoped["selected_support"] = (
        {
            vehicle_id: value
            for vehicle_id, value in selected_support.items()
            if str(vehicle_id) in allowed_ids
        }
        if isinstance(selected_support, dict)
        else {}
    )
    scoped["support_per_program"] = []
    scoped["support_program_details"] = []
    return scoped


__all__ = [
    "applications_with_hidden_items",
    "redact_mixed_application_financials",
    "resolve_actor_item_dealer_filter",
    "scope_mixed_application_calculation",
]
