"""Create a draft leasing application (step 1 / minimal fields)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.create_application import (
    ApplicationVehiclePayload,
)
from application.commands.applications.display_number import (
    assign_display_number_if_missing,
)
from application.commands.cart.remove_from_cart import (
    RemoveFromCartCommand,
    handle_remove_from_cart,
)
from application.common import _isoformat
from application.errors import ServiceError
from application.notifications.leasing_events import record_leasing_event
from application.permissions import get_company_permissions
from application.services.application_source import resolve_application_source
from application.services.company_requisites_attachment import (
    attach_company_requisites_to_applications,
)
from application.services.fns_report_attachment import (
    attach_fns_report_to_applications,
)
from application.services.questionnaire import refresh_questionnaire
from domain.application_sources import SOURCE_VIEW_ROLES
from domain.entities.leasing_application import STATUS_ACTIVE
from domain.errors import (
    ApplicationNotSubmittableError,
    CompanyNotFoundError,
)
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo
from infrastructure.repositories import (
    company_registration_repository as company_reg_repo,
)
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import warehouse_repository as wh_repo


@dataclass
class ApplicationSpecialEquipmentPayload:
    product_id: UUID
    seller_company_id: UUID | None
    unit_price: Decimal | None
    total_price: Decimal | None
    currency_code: str
    item_snapshot: dict[str, Any]
    comment: str | None = None
    equipments: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    regions: list[str] = field(default_factory=list)
    source_cart_item_id: UUID | None = None
    group_id: UUID | None = None
    parent_group_id: UUID | None = None
    item_role: str = "offer"
    overstock_requested_quantity: int = 0


@dataclass
class CreateDraftCommand:
    actor_id: UUID
    actor_role: str
    source_type: str
    actor_company_id: UUID | None
    company_id: UUID | None
    company: dict[str, Any] | None = None
    name: str = ""
    email: str = ""
    vehicles: list[ApplicationVehiclePayload] = field(default_factory=list)
    special_equipment_items: list[ApplicationSpecialEquipmentPayload] = field(
        default_factory=list
    )
    calculation: dict[str, Any] | None = None
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE
    source_product_id: UUID | None = None


def _first_source_product_id(cmd: CreateDraftCommand) -> UUID | None:
    if cmd.source_product_id is not None:
        return cmd.source_product_id
    if cmd.vehicles:
        return cmd.vehicles[0].vehicle_id
    if cmd.special_equipment_items:
        return cmd.special_equipment_items[0].product_id
    return None


def _validate_create_draft(cmd: CreateDraftCommand) -> None:
    if not cmd.company_id:
        raise ApplicationNotSubmittableError("Не указана компания")
    if not cmd.vehicles and not cmd.special_equipment_items:
        raise ApplicationNotSubmittableError(
            "Не указаны транспортные средства для заявки"
        )
    if not cmd.scope.is_default and any(
        vehicle.vehicle_id is None for vehicle in cmd.vehicles
    ):
        raise ApplicationNotSubmittableError(
            "В витрине доступен только автомобиль со склада витрины"
        )


async def _resolve_dealer_company_id(
    session: AsyncSession, cmd: CreateDraftCommand
) -> UUID | None:
    if cmd.actor_role == "dealer" and cmd.actor_company_id is not None:
        actor_dealer_id = await wh_repo.get_first_active_dealer_by_company_id(
            session,
            cmd.actor_company_id,
        )
        if actor_dealer_id is not None:
            return cast("UUID", actor_dealer_id)
    vehicle_ids = [
        vehicle.vehicle_id
        for vehicle in cmd.vehicles
        if vehicle.vehicle_id is not None
    ]
    dealers: set[UUID] = set()
    if vehicle_ids:
        vehicle_dealer = await wh_repo.resolve_application_dealer_company_id(
            session,
            vehicle_ids,
        )
        if vehicle_dealer is not None:
            dealers.add(cast("UUID", vehicle_dealer))
        else:
            dealers.add(uuid4())
            dealers.add(uuid4())

    for item in cmd.special_equipment_items:
        if item.seller_company_id is not None:
            dealers.add(item.seller_company_id)

    if len(dealers) == 1:
        return next(iter(dealers))
    if len(dealers) > 1:
        return None

    if cmd.special_equipment_items:
        return cmd.actor_company_id
    return None


async def _ensure_create_permission(
    session: AsyncSession,
    cmd: CreateDraftCommand,
    *,
    allow_dealer_client_company: bool = False,
) -> None:
    if cmd.actor_role == "dealer" and allow_dealer_client_company:
        if cmd.actor_company_id is None:
            raise ApplicationNotSubmittableError("Не указана компания дилера")
        return
    if cmd.actor_role not in {
        "carcraft_employee",
        "distributor",
        "leasing_company",
        "external_api",
    }:
        if cmd.company_id is None:
            raise ApplicationNotSubmittableError("Не указана компания")
        perms = await get_company_permissions(session, cmd.actor_id, cmd.company_id)
        if not perms.get("can_create_applications"):
            raise ServiceError(
                "Создание заявок ограничено администратором компании", 403
            )


async def _resolve_dealer_client_company(
    session: AsyncSession, cmd: CreateDraftCommand
) -> bool:
    if cmd.actor_role != "dealer" or cmd.company is None:
        return False
    if cmd.actor_company_id is None:
        raise ApplicationNotSubmittableError("Не указана компания дилера")
    if not cmd.company.get("inn"):
        raise ApplicationNotSubmittableError(
            "Для создания заявки на компанию клиента выберите компанию из списка"
        )
    payload = cast("company_reg_repo.CompanyPayload", cmd.company)
    company = await company_reg_repo.create_or_get_company(session, payload)
    if company is None or company.get("id") is None:
        raise CompanyNotFoundError()
    cmd.company_id = company["id"]
    return True


async def _build_application_payload(
    cmd: CreateDraftCommand,
    dealer_company_id: UUID | None,
    company_id: UUID,
    selected_leasing_company_ids: list[UUID],
) -> dict[str, Any]:
    calc = cmd.calculation or {}
    return {
        "company_id": company_id,
        "dealer_company_id": dealer_company_id,
        "name": cmd.name,
        "email": cmd.email,
        "status": STATUS_ACTIVE,
        "selected_leasing_companies": selected_leasing_company_ids,
        "created_by": cmd.actor_id,
        "total_amount": calc.get("total_amount"),
        "down_payment": calc.get("down_payment"),
        "down_payment_percent": calc.get("down_payment_percent"),
        "lease_term_months": calc.get("lease_term_months"),
        "monthly_payment": calc.get("monthly_payment"),
        "total_cost": calc.get("total_cost"),
        "markup": calc.get("markup"),
        "rate": calc.get("rate"),
        "total_interest": calc.get("total_interest"),
        "buyout_amount": calc.get("buyout_amount"),
        "vat_refund": calc.get("vat_refund"),
        "profit_tax_savings": calc.get("profit_tax_savings"),
        "total_savings": calc.get("total_savings"),
        "current_stage": "leasing_companies",
    }


async def _emit_draft_event(
    session: AsyncSession,
    application_id: UUID,
) -> None:
    saved = await repo.get_by_id(session, application_id)
    if saved is None:
        return
    emit_leasing_application_changed(
        {
            "application_id": str(saved["id"]),
            "display_number": saved.get("display_number"),
            "company_id": saved.get("company_id"),
            "dealer_company_id": saved.get("dealer_company_id"),
            "vehicle_id": saved.get("vehicle_id"),
            "name": saved.get("name"),
            "email": saved.get("email"),
            "status": saved.get("status"),
            "total_amount": saved.get("total_amount"),
            "down_payment": saved.get("down_payment"),
            "down_payment_percent": saved.get("down_payment_percent"),
            "lease_term_months": saved.get("lease_term_months"),
            "monthly_payment": saved.get("monthly_payment"),
            "total_cost": saved.get("total_cost"),
            "markup": saved.get("markup"),
            "rate": saved.get("rate"),
            "total_interest": saved.get("total_interest"),
            "buyout_amount": saved.get("buyout_amount"),
            "vat_refund": saved.get("vat_refund"),
            "profit_tax_savings": saved.get("profit_tax_savings"),
            "total_savings": saved.get("total_savings"),
            "selected_leasing_companies": saved.get("selected_leasing_companies"),
            "leasing_company_comments": saved.get("leasing_company_comments"),
            "requested_documents": saved.get("requested_documents"),
            "questionnaire_completed": saved.get("questionnaire_completed"),
            "questionnaire_progress": saved.get("questionnaire_progress"),
            "current_stage": saved.get("current_stage"),
            "created_at": _isoformat(saved.get("created_at")),
            "updated_at": _isoformat(saved.get("updated_at")),
            "_deleted": False,
        }
    )


async def handle_create_draft(
    cmd: CreateDraftCommand, session: AsyncSession
) -> dict[str, Any]:
    dealer_client_company = await _resolve_dealer_client_company(session, cmd)
    _validate_create_draft(cmd)
    company_id = cmd.company_id
    if company_id is None:
        raise ApplicationNotSubmittableError("Не указана компания")
    if not await repo.company_exists(session, company_id):
        raise CompanyNotFoundError()
    await _ensure_create_permission(
        session,
        cmd,
        allow_dealer_client_company=dealer_client_company,
    )

    dealer_company_id = await _resolve_dealer_company_id(session, cmd)
    payload = await _build_application_payload(
        cmd,
        dealer_company_id,
        company_id,
        [],
    )
    vehicle_ids = [
        item.vehicle_id for item in cmd.vehicles if item.vehicle_id is not None
    ]
    if not await repo.all_vehicles_visible_in_scope(
        session, vehicle_ids, cmd.scope
    ):
        raise ApplicationNotSubmittableError(
            "Состав корзины изменился. Обновите корзину перед оформлением заявки"
        )
    from application.commands.applications.create_application import (
        _validate_vehicle_stock,
    )
    for vehicle in cmd.vehicles:
        await _validate_vehicle_stock(session, vehicle, cmd.scope)
    payload["storefront_id"] = cmd.scope.id
    payload["source_type"] = await resolve_application_source(
        session, requested=cmd.source_type, first_product_id=_first_source_product_id(cmd)
    )
    application_id = await repo.create_application(session, payload=payload)

    application = await repo.get_by_id(session, application_id)
    if application is not None:
        await assign_display_number_if_missing(session, application=application)

    vehicle_line_ids = await _create_application_vehicles(
        session,
        application_id=application_id,
        vehicles=cmd.vehicles,
    )
    special_equipment_line_ids = await _create_special_equipment_items(
        session,
        application_id=application_id,
        items=cmd.special_equipment_items,
    )

    if cmd.calculation:
        await repo.upsert_calculation(
            session,
            application_id=application_id,
            payload=cmd.calculation,
        )

    company = await company_repo.get_company_by_id(session, company_id)
    if company is not None:
        await attach_fns_report_to_applications(
            session,
            inn=company.get("inn"),
            company_id=company_id,
            application_ids=[application_id],
        )
        await attach_company_requisites_to_applications(
            session,
            company_id=company_id,
            application_ids=[application_id],
        )

    await refresh_questionnaire(session, application_id)
    await _emit_draft_event(session, application_id)
    # This checkout entry point creates a live active application. "Draft" is
    # a legacy command name, not a persisted draft state.
    saved = await repo.get_by_id(session, application_id)
    assert saved is not None
    overstock_items = []
    for se_item in cmd.special_equipment_items:
        if getattr(se_item, "overstock_requested_quantity", 0) > 0:
            snapshot = se_item.item_snapshot or {}
            mark = snapshot.get("mark_name") or (snapshot.get("mark") or {}).get("name") or ""
            model = snapshot.get("model_name") or (snapshot.get("model") or {}).get("name") or ""
            mod = snapshot.get("modification_name") or (snapshot.get("modification") or {}).get("name") or ""
            label = " ".join(part for part in (mark, model, mod) if part)
            overstock_items.append({
                "quantity": se_item.overstock_requested_quantity,
                "name": label,
                "mark": mark,
                "model": model,
                "modification": mod,
            })
    await record_leasing_event(
        session, application=saved, event_type="leasing.application_created",
        actor_user_id=cmd.actor_id, new_values={"status": saved["status"]},
        payload={"overstock_items": overstock_items} if overstock_items else None,
        occurrence_key=f"leasing.application_created:{application_id}",
    )
    for vehicle in cmd.vehicles:
        if vehicle.vehicle_id is not None:
            await handle_remove_from_cart(
                RemoveFromCartCommand(
                    user_id=cmd.actor_id,
                    vehicle_id=vehicle.vehicle_id,
                    scope=cmd.scope,
                ),
                session,
            )
    return {
        "application_id": application_id,
        **({"source_type": saved["source_type"]} if cmd.actor_role in SOURCE_VIEW_ROLES else {}),
        "dealer_company_id": dealer_company_id,
        "vehicle_line_ids": vehicle_line_ids,
        "special_equipment_line_ids": special_equipment_line_ids,
        "status": STATUS_ACTIVE,
    }


async def _create_application_vehicles(
    session: AsyncSession,
    *,
    application_id: Any,
    vehicles: list[ApplicationVehiclePayload],
) -> list[UUID]:
    line_ids: list[UUID] = []
    for v in vehicles:
        if v.vehicle_id is None and not v.modification_id:
            raise ApplicationNotSubmittableError(
                "Для каждого автомобиля нужен vehicle_id или modification_id"
            )
        unit = (
            _to_decimal(v.custom_price) if v.custom_price is not None else Decimal("0")
        )
        options_unit = _options_total(v.equipments) + _options_total(v.services)
        qty = v.quantity if v.quantity and v.quantity > 0 else 1
        line_ids.append(
            await repo.create_application_vehicle(
                session,
                application_id=application_id,
                vehicle_id=v.vehicle_id,
                modification_id=v.modification_id,
                quantity=qty,
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
        )
    return line_ids


async def _create_special_equipment_items(
    session: AsyncSession,
    *,
    application_id: UUID,
    items: list[ApplicationSpecialEquipmentPayload],
) -> list[UUID]:
    return [
        await repo.create_special_equipment_application_item(
            session,
            application_id=application_id,
            product_id=item.product_id,
            seller_company_id=item.seller_company_id,
            unit_price=item.unit_price,
            total_price=item.total_price,
            currency_code=item.currency_code,
            item_snapshot=item.item_snapshot,
            comment=item.comment,
            equipments=item.equipments,
            services=item.services,
            leasing_purpose=item.leasing_purpose,
            leasing_purposes=item.leasing_purposes,
            regions=item.regions,
            source_cart_item_id=item.source_cart_item_id,
            group_id=item.group_id,
            parent_group_id=item.parent_group_id,
            item_role=item.item_role,
            overstock_requested_quantity=item.overstock_requested_quantity,
        )
        for item in items
    ]


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
