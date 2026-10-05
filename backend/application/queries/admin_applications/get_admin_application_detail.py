"""Get one admin application with LCA/proposal detail."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications.item_projection import (
    group_application_items,
    project_vehicle_item,
)
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import (
    admin_applications_repository as admin_repo,
)
from infrastructure.repositories import application_repository as app_repo


@dataclass
class GetAdminApplicationDetailQuery:
    application_id: uuid.UUID


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _price_adjustment_amount(
    *,
    catalog_price: Decimal | None,
    adjustment_type: str | None,
    adjustment_value: Any,
    direction: str,
) -> Decimal | None:
    value = _decimal(adjustment_value)
    if catalog_price is None or adjustment_type is None or value is None:
        return None
    if adjustment_type in {"rubles_off", "rubles_up"}:
        return value
    if adjustment_type in {"percent_off", "percent_up"}:
        return catalog_price * value / Decimal("100")
    if direction == "discount" and adjustment_type == "fixed_price":
        return catalog_price - value
    return None


def _project_admin_vehicle_price_item(row: dict[str, Any]) -> dict[str, Any]:
    """Extend the common vehicle card with persisted price adjustments."""

    item = project_vehicle_item(row)
    catalog_price = _decimal(row.get("unit_price"))
    stored_final_price = _decimal(row.get("final_price"))
    final_price = (
        stored_final_price if stored_final_price is not None else catalog_price
    )
    item.update(
        {
            # Stored application price is stable; a live catalog join must not
            # rewrite the base used for discount and markup.
            "catalog_price": catalog_price,
            "discount_type": row.get("discount_type"),
            "discount_value": _decimal(row.get("discount_value")),
            "discount_amount": _price_adjustment_amount(
                catalog_price=catalog_price,
                adjustment_type=row.get("discount_type"),
                adjustment_value=row.get("discount_value"),
                direction="discount",
            ),
            "markup_type": row.get("markup_type"),
            "markup_value": _decimal(row.get("markup_value")),
            "markup_amount": _price_adjustment_amount(
                catalog_price=catalog_price,
                adjustment_type=row.get("markup_type"),
                adjustment_value=row.get("markup_value"),
                direction="markup",
            ),
            "final_price": final_price,
            "dealer_comment": row.get("dealer_comment"),
        }
    )
    return item


async def handle_get_admin_application_detail(
    query: GetAdminApplicationDetailQuery, session: AsyncSession
) -> dict[str, Any]:
    application = await admin_repo.get_detail_base(session, query.application_id)
    if application is None:
        raise ApplicationNotFoundError(query.application_id)
    pending_counts = await app_repo.count_pending_requested_price_items(
        session,
        [query.application_id],
    )
    pending_count = pending_counts.get(query.application_id, 0)
    application["pending_price_items_count"] = pending_count
    application["can_assign_leasing_companies"] = (
        application.get("status") == "active" and pending_count == 0
    )
    summary = await app_repo.get_by_id(session, query.application_id)
    if summary is not None:
        application["items_count"] = summary.get("items_count")
        application["total_items_price"] = (
            summary.get("total_items_price")
            if summary.get("total_items_price") is not None
            else application.get("total_amount")
        )
    vehicle_rows = await app_repo.list_application_vehicle_item_rows(
        session, [query.application_id]
    )
    special_equipment_rows = (
        await app_repo.list_application_special_equipment_item_rows(
            session, [query.application_id]
        )
    )
    grouped = group_application_items(
        [query.application_id],
        vehicle_rows=vehicle_rows,
        special_equipment_rows=special_equipment_rows,
        actor_role="carcraft_employee",
    )
    items = grouped.get(query.application_id, [])
    application["items"] = items
    if not application.get("items_count") and items:
        application["items_count"] = sum(
            int(item.get("quantity") or 1) for item in items
        )
    if not application.get("total_items_price") and items:
        calculated_total = sum(
            (
                (
                    (_decimal(item.get("total_price")) or Decimal("0"))
                    if item.get("total_price") is not None
                    else (
                        (_decimal(item.get("unit_price")) or Decimal("0"))
                        * int(item.get("quantity") or 1)
                    )
                )
                for item in items
            ),
            Decimal("0"),
        )
        if calculated_total:
            application["total_items_price"] = calculated_total
        elif application.get("total_items_price") is None:
            application["total_items_price"] = Decimal("0")
    application["vehicle_price_items"] = [
        _project_admin_vehicle_price_item(row) for row in vehicle_rows
    ]

    lca_items = await admin_repo.list_lca_details(session, query.application_id)
    proposals = await admin_repo.list_proposals_by_lca_ids(
        session, [item["id"] for item in lca_items]
    )
    proposals_by_lca_id: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for proposal in proposals:
        proposals_by_lca_id.setdefault(
            proposal["leasing_company_application_id"], []
        ).append(proposal)

    for item in lca_items:
        item["proposals"] = proposals_by_lca_id.get(item["id"], [])

    return {
        "application": application,
        "leasing_company_applications": lca_items,
    }
