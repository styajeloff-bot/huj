
"""Update draft application's financial conditions (Step 1 of checkout)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from domain.errors import ApplicationNotFoundError
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo


@dataclass
class UpdateConditionsCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: float | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    selected_support: dict[str, list[str]] | None = None
    support_per_vehicle: list[dict[str, Any]] | None = None
    support_per_program: list[dict[str, Any]] | None = None
    support_program_details: list[dict[str, Any]] | None = None
    calculations_per_vehicle: list[dict[str, Any]] | None = None


_EDITABLE_COLUMNS: tuple[str, ...] = (
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
)

_CALC_COLUMNS: tuple[str, ...] = (
    "selected_support",
    "support_per_vehicle",
    "support_per_program",
    "support_program_details",
    "calculations_per_vehicle",
)


async def handle_update_conditions(
    cmd: UpdateConditionsCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.get_by_id(session, cmd.application_id)
    if current is None:
        raise ApplicationNotFoundError(cmd.application_id)
    await require_can_mutate_application(
        session,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        application=current,
    )
    entity = await ensure_application_owned_by(
        session,
        application=current,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
    )
    if cmd.actor_role == "client":
        has_children = await repo.has_lc_children(session, cmd.application_id)
        entity.ensure_editable(has_lc_children=has_children)

    patch: dict[str, Any] = {}
    for key in _EDITABLE_COLUMNS:
        value = getattr(cmd, key)
        if value is not None:
            patch[key] = value
    if cmd.total_amount is not None:
        vehicle_count = await repo.count_application_vehicles(
            session, cmd.application_id
        )
        if vehicle_count > 0:
            vehicle_total = await repo.sum_application_vehicles_total(
                session, cmd.application_id
            )
            patch["total_amount"] = vehicle_total
    if patch:
        await repo.update_application_fields(
            session, cmd.application_id, fields=patch
        )
    calc_patch = {
        key: getattr(cmd, key)
        for key in _EDITABLE_COLUMNS + _CALC_COLUMNS
        if getattr(cmd, key) is not None
    }
    if calc_patch:
        await repo.upsert_calculation(
            session,
            application_id=cmd.application_id,
            payload=calc_patch,
        )

    updated = await repo.get_by_id(session, cmd.application_id)
    assert updated is not None
    emit_leasing_application_changed({
        "application_id": str(updated["id"]),
        "display_number": updated.get("display_number"),
        "company_id": updated.get("company_id"),
        "dealer_company_id": updated.get("dealer_company_id"),
        "vehicle_id": updated.get("vehicle_id"),
        "name": updated.get("name"),
        "email": updated.get("email"),
        "status": updated.get("status"),
        "total_amount": updated.get("total_amount"),
        "down_payment": updated.get("down_payment"),
        "down_payment_percent": updated.get("down_payment_percent"),
        "lease_term_months": updated.get("lease_term_months"),
        "monthly_payment": updated.get("monthly_payment"),
        "total_cost": updated.get("total_cost"),
        "markup": updated.get("markup"),
        "rate": updated.get("rate"),
        "total_interest": updated.get("total_interest"),
        "buyout_amount": updated.get("buyout_amount"),
        "vat_refund": updated.get("vat_refund"),
        "profit_tax_savings": updated.get("profit_tax_savings"),
        "total_savings": updated.get("total_savings"),
        "selected_leasing_companies": updated.get("selected_leasing_companies"),
        "leasing_company_comments": updated.get("leasing_company_comments"),
        "requested_documents": updated.get("requested_documents"),
        "questionnaire_completed": updated.get("questionnaire_completed"),
        "questionnaire_progress": updated.get("questionnaire_progress"),
        "current_stage": updated.get("current_stage"),
        "created_at": _isoformat(updated.get("created_at")),
        "updated_at": _isoformat(updated.get("updated_at")),
        "_deleted": False,
    })
    return {
        "message": "Условия заявки обновлены",
        "application": updated,
    }
