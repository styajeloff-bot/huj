"""Dealer allocations shared by application cards and detail responses."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications.item_projection import project_vehicle_item
from domain.dealer_distribution import distribution_availability
from infrastructure.repositories import (
    application_dealer_distribution_repository as distributions,
)
from infrastructure.repositories import application_repository as applications


async def build_dealer_distribution(
    session: AsyncSession,
    *,
    vehicle_rows: list[dict[str, Any]],
    actor_role: str,
    actor_company_id: UUID | None,
) -> dict[UUID, list[dict[str, Any]]]:
    ids = [row["id"] for row in vehicle_rows]
    contexts = await applications.list_vehicle_distribution_context(session, ids)
    allocations_by_id = await distributions.list_distributions(session, ids)
    grouped: dict[UUID, list[dict[str, Any]]] = {}
    for row in vehicle_rows:
        context = contexts[row["id"]]
        quantity = max(1, int(context["quantity"] or 1))
        allocations = list(allocations_by_id.get(row["id"], []))
        if context["legacy_dealer_id"] is not None and not allocations:
            allocations = [
                {
                    "dealer": {
                        "id": context["legacy_dealer_id"],
                        "name": context["legacy_dealer_name"],
                        "inn": context["legacy_dealer_inn"],
                    },
                    "quantity": quantity,
                }
            ]
        stock_dealer = None
        if context["stock_owner_type"] == "dealer":
            stock_dealer = {
                "id": context["stock_owner_id"],
                "name": context["stock_owner_name"],
                "inn": context["stock_owner_inn"],
            }
        availability = distribution_availability(
            actor_role=actor_role,
            actor_company_id=actor_company_id,
            stock_owner_id=context["stock_owner_id"],
            stock_owner_type=context["stock_owner_type"],
            quantity=context["quantity"],
            distributed_quantity=sum(item["quantity"] for item in allocations),
            legacy_dealer_assigned=context["legacy_dealer_id"] is not None,
            status=row.get("status", row.get("car_status")),
        )
        if stock_dealer is not None:
            allocations = []
        if actor_role == "dealer" and context["stock_owner_id"] != actor_company_id:
            allocations = [
                item for item in allocations if item["dealer"]["id"] == actor_company_id
            ]
        projected = project_vehicle_item(row)
        grouped.setdefault(row["application_id"], []).append(
            {
                "application_vehicle_id": row["id"],
                "title": projected["title"],
                "quantity": projected["quantity"],
                "stock_dealer": stock_dealer,
                "dealer_allocations": allocations,
                "unassigned_quantity": availability.unassigned_quantity,
                "can_assign_dealer": availability.can_assign_dealer,
            }
        )
    return grouped
