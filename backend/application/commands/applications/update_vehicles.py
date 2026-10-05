
"""Replace draft application's vehicles (and per-vehicle calculations)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.create_application import (
    ApplicationVehiclePayload,
    _validate_vehicle_stock,
)
from application.common import _isoformat
from application.permissions import (
    ensure_application_owned_by,
    require_can_mutate_application,
)
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationNotSubmittableError,
)
from domain.storefronts import DEFAULT_STOREFRONT_ID, CatalogScope
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo
from infrastructure.repositories import (
    dealer_distribution_access_repository as distribution_repo,
)


@dataclass
class UpdateVehiclesCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    vehicles: list[ApplicationVehiclePayload] = field(default_factory=list)
    vehicle_calculations: list[dict[str, Any]] | None = None


async def handle_update_vehicles(
    cmd: UpdateVehiclesCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.get_by_id(session, cmd.application_id, for_update=True)
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

    if not cmd.vehicles:
        raise ApplicationNotSubmittableError(
            "Список автомобилей не может быть пустым"
        )

    from application.errors import ServiceError
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    if (
        await fulfillment.has_managed_lines(session, cmd.application_id)
        or await distribution_repo.application_has_distributions(session, cmd.application_id)
    ):
        raise ServiceError("Поставщик уже подтвердил или распределил состав. Измените его через подбор автомобилей", 409)
    storefront_id = current.get("storefront_id") or DEFAULT_STOREFRONT_ID
    scope = CatalogScope(id=storefront_id, slug=None, version=1,
                         is_default=storefront_id == DEFAULT_STOREFRONT_ID)
    if not scope.is_default and any(v.vehicle_id is None for v in cmd.vehicles):
        raise ApplicationNotSubmittableError("В витрине доступен только автомобиль со склада витрины")
    if not await repo.all_vehicles_visible_in_scope(
        session, [v.vehicle_id for v in cmd.vehicles if v.vehicle_id is not None], scope,
    ):
        raise ApplicationNotSubmittableError("Состав корзины изменился. Обновите корзину перед оформлением заявки")
    keys = [(v.vehicle_id, v.modification_id if v.vehicle_id is None else None) for v in cmd.vehicles]
    if len(keys) != len(set(keys)):
        raise ApplicationNotSubmittableError("Одна позиция не может повторяться в заявке")
    for vehicle in cmd.vehicles:
        if vehicle.vehicle_id is None and not vehicle.modification_id:
            raise ApplicationNotSubmittableError("Для каждого автомобиля нужен vehicle_id или modification_id")
        await _validate_vehicle_stock(session, vehicle, scope)
    previous = await repo.list_application_vehicles(session, cmd.application_id)
    requested = {
        (row["vehicle_id"], row.get("modification_id") if row["vehicle_id"] is None else None):
            row.get("requested_quantity") or row["quantity"]
        for row in previous
    }
    await repo.delete_application_vehicles(session, cmd.application_id)
    await repo.delete_vehicle_calculations(session, cmd.application_id)

    total_amount = Decimal("0")
    for v in cmd.vehicles:
        unit = _to_decimal(v.custom_price) if v.custom_price is not None else Decimal("0")
        options_unit = _options_total(v.equipments) + _options_total(v.services)
        qty = v.quantity if v.quantity and v.quantity > 0 else 1
        total_amount += (unit + options_unit) * Decimal(qty)
        await repo.create_application_vehicle(
            session,
            application_id=cmd.application_id,
            vehicle_id=v.vehicle_id,
            modification_id=v.modification_id,
            quantity=qty,
            requested_quantity=requested.get((v.vehicle_id, v.modification_id if v.vehicle_id is None else None), qty),
            unit_price=unit,
            total_price=(unit + options_unit) * Decimal(qty),
            is_model_order=bool(v.is_model_order or v.vehicle_id is None),
            comment=v.comment,
            equipments=v.equipments,
            services=v.services,
            leasing_purpose=v.leasing_purpose,
            leasing_purposes=v.leasing_purposes,
            regions=v.regions,
        )

    if cmd.vehicle_calculations:
        for calc in cmd.vehicle_calculations:
            await repo.add_vehicle_calculation(
                session,
                application_id=cmd.application_id,
                payload=calc,
            )

    await repo.update_application_fields(
        session,
        cmd.application_id,
        fields={"total_amount": total_amount},
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
        "message": "Автомобили заявки обновлены",
        "application": updated,
    }


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return Decimal("0")


def _options_total(items: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in items:
        total += _to_decimal(item.get("price"))
    return total
