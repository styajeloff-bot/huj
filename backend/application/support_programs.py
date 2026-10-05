"""Shared application service for applicable vehicle support summaries."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_calculator import (
    SUPPORT_TYPE_DOWN_PAYMENT,
    SUPPORT_TYPE_VEHICLE_DISCOUNT,
    LeasingCalculator,
)
from infrastructure.repositories import calculator_repository


def build_applicable_support_programs(
    vehicle_rows: list[dict[str, Any]],
    program_details: list[dict[str, Any]],
    *,
    down_payment_percent: float | None = None,
    vehicle_discount_support_by_vehicle: dict[UUID, float] | None = None,
) -> dict[UUID, list[dict[str, Any]]]:
    """Build the common per-vehicle support DTO from repository rows."""

    details_by_id = {row["id"]: row for row in program_details}
    result: dict[UUID, list[dict[str, Any]]] = {}
    seen: set[tuple[UUID, UUID]] = set()
    for vehicle_row in vehicle_rows:
        vehicle_id = vehicle_row["vehicle_id"]
        program_id = vehicle_row.get("support_program_id")
        if program_id is None or (vehicle_id, program_id) in seen:
            continue
        details = details_by_id.get(program_id)
        if details is None:
            continue
        seen.add((vehicle_id, program_id))

        base_price = max(0.0, float(vehicle_row.get("base_price") or 0))
        support_type = vehicle_row.get("support_type")
        support_params = vehicle_row.get("support_params") or {}
        calculation_base = base_price
        if support_type == SUPPORT_TYPE_DOWN_PAYMENT and down_payment_percent is not None:
            selected_discount = (
                vehicle_discount_support_by_vehicle.get(vehicle_id, 0.0)
                if vehicle_discount_support_by_vehicle
                else 0.0
            )
            effective_price = max(0.0, base_price - selected_discount)
            calculation_base = round(
                effective_price * max(0.0, down_payment_percent) / 100
            )
        support_amount = LeasingCalculator.compute_support_from_params(
            support_params,
            calculation_base,
        )
        display_price = (
            max(0, round(base_price - support_amount))
            if support_type in SUPPORT_TYPE_VEHICLE_DISCOUNT
            else round(base_price)
        )
        summary = {
            "vehicle_id": vehicle_id,
            "id": program_id,
            "name": details["name"],
            "support_type": support_type,
            "support_params": support_params,
            "comment": details.get("comment"),
            "starts_at": details.get("starts_at"),
            "ends_at": details.get("ends_at"),
            "support_amount": support_amount,
            "base_price": round(base_price),
            "display_price": display_price,
            "is_compatible": bool(details.get("is_compatible", False)),
            "compatible_support_ids": list(
                details.get("compatible_support_ids") or []
            ),
            "bill_of_lading": details.get("bill_of_lading"),
        }
        result.setdefault(vehicle_id, []).append(summary)

    for summaries in result.values():
        summaries.sort(key=lambda item: item["id"])
    return result


async def load_applicable_support_programs(
    session: AsyncSession,
    vehicle_ids: list[UUID],
    *,
    leasing_company_id: UUID | None = None,
    base_prices: dict[UUID, float] | None = None,
    down_payment_percent: float | None = None,
) -> dict[UUID, list[dict[str, Any]]]:
    """Load applicable programs once and return the common DTO by vehicle."""

    if not vehicle_ids:
        return {}
    vehicle_rows = await calculator_repository.get_vehicles_with_support_info(
        session,
        vehicle_ids,
        leasing_company_id=leasing_company_id,
    )
    if base_prices:
        vehicle_rows = [
            {
                **row,
                "base_price": base_prices.get(
                    row["vehicle_id"],
                    float(row.get("base_price") or 0),
                ),
            }
            for row in vehicle_rows
        ]
    program_ids = sorted(
        {
            row["support_program_id"]
            for row in vehicle_rows
            if row.get("support_program_id") is not None
        }
    )
    details = await calculator_repository.get_support_program_details_by_ids(
        session,
        program_ids,
    )
    return build_applicable_support_programs(
        vehicle_rows,
        details,
        down_payment_percent=down_payment_percent,
    )


async def enrich_cars_with_applicable_supports(
    session: AsyncSession,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach support summaries and a deterministic price preview to cars."""

    vehicle_ids = [item["vehicle_id"] for item in items]
    base_prices = {
        item["vehicle_id"]: float(item.get("effective_price") or 0)
        for item in items
    }
    applicable_by_vehicle = await load_applicable_support_programs(
        session,
        vehicle_ids,
        base_prices=base_prices,
    )

    enriched: list[dict[str, Any]] = []
    for item in items:
        vehicle_id = item["vehicle_id"]
        base_price = round(base_prices.get(vehicle_id, 0))
        applicable = applicable_by_vehicle.get(vehicle_id, [])
        vehicle_price_programs = [
            program
            for program in applicable
            if program["support_type"] in SUPPORT_TYPE_VEHICLE_DISCOUNT
        ]
        preview_amount = min(
            base_price,
            _maximum_compatible_support_amount(vehicle_price_programs),
        )
        preview_display_price = max(0, base_price - preview_amount)
        enriched.append(
            {
                **item,
                "applicable_support_programs": applicable,
                "support_preview_base_price": base_price,
                "support_preview_display_price": preview_display_price,
                "support_preview_amount": max(
                    0,
                    preview_amount,
                ),
            }
        )
    return enriched


def _maximum_compatible_support_amount(
    programs: list[dict[str, Any]],
) -> int:
    """Return the maximum weighted clique; a single program is always valid."""

    candidates = sorted(
        (program for program in programs if int(program["support_amount"]) > 0),
        key=lambda program: (-int(program["support_amount"]), str(program["id"])),
    )
    best = 0

    def can_combine(
        left: dict[str, Any],
        right: dict[str, Any],
    ) -> bool:
        return bool(left["is_compatible"] and right["is_compatible"]) and (
            right["id"] in set(left["compatible_support_ids"])
            and left["id"] in set(right["compatible_support_ids"])
        )

    def search(
        remaining: list[dict[str, Any]],
        total: int,
    ) -> None:
        nonlocal best
        best = max(best, total)
        if total + sum(int(item["support_amount"]) for item in remaining) <= best:
            return
        while remaining:
            current = remaining[0]
            tail = remaining[1:]
            search(
                [candidate for candidate in tail if can_combine(current, candidate)],
                total + int(current["support_amount"]),
            )
            remaining = tail
            if total + sum(
                int(item["support_amount"]) for item in remaining
            ) <= best:
                return

    search(candidates, 0)
    return best
