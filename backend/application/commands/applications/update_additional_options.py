"""Update dealer-confirmed prices for application vehicle options."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from application.notifications.leasing_events import (
    option_price_snapshot,
    record_leasing_event,
)
from application.permissions import ensure_application_vehicle_action_allowed
from domain.additional_options import AdditionalOptionsCatalogPolicy
from domain.errors import ApplicationNotFoundError, ApplicationVehicleNotFoundError
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo


@dataclass(frozen=True)
class UpdateAdditionalOptionsCommand:
    application_id: uuid.UUID
    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None
    equipments: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)


async def handle_update_additional_options(
    cmd: UpdateAdditionalOptionsCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.actor_role not in {"dealer", "distributor", "leasing_company"}:
        raise ServiceError("Недостаточно прав доступа", 403)

    current = await repo.get_by_id(session, cmd.application_id, for_update=True)
    if current is None:
        raise ApplicationNotFoundError(cmd.application_id)
    current_vehicle = await repo.get_application_vehicle(
        session, cmd.application_vehicle_id
    )
    if (
        current_vehicle is None
        or current_vehicle["application_id"] != cmd.application_id
    ):
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)
    await ensure_application_vehicle_action_allowed(
        session,
        application=current,
        application_vehicle_id=cmd.application_vehicle_id,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        actor_leasing_company_id=cmd.actor_leasing_company_id,
    )

    equipments = _normalize_options(cmd.equipments)
    services = _normalize_options(cmd.services)
    equipment_codes = [item.get("equipment_code") for item in equipments]
    service_codes = [item.get("service_code") for item in services]
    requested_codes = [
        code for code in [*equipment_codes, *service_codes] if isinstance(code, str)
    ]
    membership = await repo.get_additional_option_catalog_membership(
        session, list(dict.fromkeys(requested_codes))
    )
    policy = AdditionalOptionsCatalogPolicy(
        equipment_codes=frozenset(membership["equipment_codes"]),
        service_codes=frozenset(membership["service_codes"]),
    )
    policy.validate(
        equipment_codes=equipment_codes,
        service_codes=service_codes,
    )

    updated_vehicle = await repo.update_application_vehicle_additional_options(
        session,
        application_id=cmd.application_id,
        application_vehicle_id=cmd.application_vehicle_id,
        equipments=equipments,
        services=services,
    )
    if updated_vehicle is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)

    total_amount = await repo.sum_active_application_items_total(
        session, cmd.application_id
    )
    if total_amount is not None:
        await repo.update_application_fields(
            session, cmd.application_id, fields={"total_amount": total_amount}
        )
    updated = await repo.get_by_id(session, cmd.application_id)
    assert updated is not None
    await record_leasing_event(
        session, application=updated, event_type="leasing.additional_price_changed",
        actor_user_id=cmd.actor_id,
        previous_values={
            "equipments": option_price_snapshot(current_vehicle.get("equipments") or []),
            "services": option_price_snapshot(current_vehicle.get("services") or []),
        },
        new_values={
            "equipments": option_price_snapshot(updated_vehicle.get("equipments") or []),
            "services": option_price_snapshot(updated_vehicle.get("services") or []),
        },
        payload={
            "application_vehicle_id": cmd.application_vehicle_id,
            **({"leasing_company_id": cmd.actor_leasing_company_id}
               if cmd.actor_leasing_company_id is not None else {}),
        },
    )
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
        "message": "Дополнительное оборудование и услуги обновлены",
        "application_vehicle": updated_vehicle,
        "application": updated,
    }


def _normalize_options(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "comment": item.get("comment")} for item in items]


def options_total(items: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in items:
        total += Decimal(str(item.get("price") or 0))
    return total


__all__ = [
    "UpdateAdditionalOptionsCommand",
    "handle_update_additional_options",
]
