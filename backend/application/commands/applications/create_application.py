
"""Create a full leasing application (with vehicles + questionnaire + calc).

Atomic — all DB mutations happen inside the handler's single session;
``session.commit()`` runs once in the router after the handler returns.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.display_number import (
    assign_display_number_if_missing,
)
from application.commands.applications.finalize_supports import (
    finalize_application_supports,
)
from application.common import _isoformat
from application.errors import ServiceError
from application.notifications.leasing_events import (
    record_company_assignments,
    record_leasing_event,
)
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
from domain.entities.leasing_application import (
    STATUS_ACTIVE,
    LeasingApplication,
)
from domain.errors import (
    ApplicationNotSubmittableError,
    CompanyNotFoundError,
    LeasingCompanyNotFoundError,
)
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import (
    signature_request_repository as signature_repo,
)
from infrastructure.repositories import warehouse_repository as wh_repo


@dataclass
class ApplicationVehiclePayload:
    vehicle_id: UUID | None = None
    modification_id: str | None = None
    allow_overstock: bool = False
    quantity: int = 1
    custom_price: Decimal | None = None
    comment: str | None = None
    equipments: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    regions: list[str] = field(default_factory=list)
    is_model_order: bool = False


@dataclass
class CreateApplicationCommand:
    actor_id: UUID
    actor_role: str
    source_type: str
    company_id: UUID
    name: str
    email: str
    vehicles: list[ApplicationVehiclePayload] = field(default_factory=list)
    selected_leasing_companies: list[UUID] = field(default_factory=list)
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
    current_stage: str = "leasing_companies"
    create_draft: bool = False
    questionnaire: dict[str, Any] | None = None
    vehicle_calculations: list[dict[str, Any]] | None = None
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_create_application(
    cmd: CreateApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    await _validate_create(cmd, session)
    if cmd.actor_role not in {
        "carcraft_employee",
        "distributor",
        "leasing_company",
        "external_api",
    }:
        perms = await get_company_permissions(session, cmd.actor_id, cmd.company_id)
        if not perms.get("can_create_applications"):
            raise ServiceError(
                "Создание заявок ограничено администратором компании", 403
            )
    status = STATUS_ACTIVE
    application_id = await _insert_application(cmd, status, session)
    from infrastructure.repositories.status_history_repository import (
        append_leasing_app_status_history,
    )
    await append_leasing_app_status_history(
        application_id=application_id,
        old_status=None,
        new_status=status,
        changed_by=cmd.actor_id,
    )
    await _append_vehicle_lines(cmd, application_id, session)
    await _persist_side_records(cmd, application_id, session)
    await finalize_application_supports(
        session,
        application_id=application_id,
        actor_id=cmd.actor_id,
    )
    # Back-fill the just-created application_id onto any signature_requests
    # this applicant issued in step 4. We only touch pending/unlinked rows —
    # never overwrite a value the operator already set manually.
    await signature_repo.backfill_application_id(
        session,
        invited_by_user_id=cmd.actor_id,
        application_id=application_id,
    )
    await _attach_fns_report(cmd, application_id, session)
    saved = await repo.get_by_id(session, application_id)
    assert saved is not None
    display_number = await assign_display_number_if_missing(session, application=saved)
    if display_number is not None:
        saved["display_number"] = display_number
    entity = LeasingApplication.from_dict(saved)
    emit_leasing_application_changed({
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
    })
    await record_leasing_event(
        session, application=saved, event_type="leasing.application_created",
        actor_user_id=cmd.actor_id, new_values={"status": saved["status"]},
        occurrence_key=f"leasing.application_created:{application_id}",
    )
    await record_company_assignments(
        session, application=saved,
        leasing_company_ids=cmd.selected_leasing_companies, actor_user_id=cmd.actor_id,
    )
    return {
        "application_id": application_id,
        **({"source_type": saved["source_type"]} if cmd.actor_role in SOURCE_VIEW_ROLES else {}),
        "display_number": saved.get("display_number"),
        "status": entity.status,
        "applicationIds": [application_id],
        "vehiclesReserved": len(cmd.vehicles),
        "message": "Заявка создана",
    }


async def _validate_create(
    cmd: CreateApplicationCommand, session: AsyncSession
) -> None:
    if not cmd.vehicles:
        raise ApplicationNotSubmittableError(
            "Не указаны автомобили для заявки"
        )
    if not cmd.scope.is_default and any(
        vehicle.vehicle_id is None for vehicle in cmd.vehicles
    ):
        raise ApplicationNotSubmittableError(
            "В витрине доступен только автомобиль со склада витрины"
        )
    if not await repo.company_exists(session, cmd.company_id):
        raise CompanyNotFoundError()
    vehicle_ids = [
        item.vehicle_id for item in cmd.vehicles if item.vehicle_id is not None
    ]
    if not await repo.all_vehicles_visible_in_scope(
        session, vehicle_ids, cmd.scope
    ):
        raise ApplicationNotSubmittableError(
            "Состав корзины изменился. Обновите корзину перед оформлением заявки"
        )
    for lc_id in cmd.selected_leasing_companies:
        if not await repo.leasing_company_exists(session, lc_id):
            raise LeasingCompanyNotFoundError(lc_id)

    if (
        cmd.actor_role != "carcraft_employee"
        and vehicle_ids
        and await wh_repo.has_showcase_only_access(
            session, company_id=cmd.company_id, vehicle_ids=vehicle_ids
        )
    ):
        raise ServiceError(
            "Оформление заявок по технике с данного витринного склада недоступно",
            422,
        )



async def _resolve_dealer_company_id(
    cmd: CreateApplicationCommand, session: AsyncSession
) -> UUID | None:
    """Resolve dealer_company_id from actor and selected vehicle warehouses."""
    if cmd.actor_role == "dealer":
        actor_dealer_id = await wh_repo.resolve_actor_dealer_company_id(
            session,
            cmd.actor_id,
        )
        if actor_dealer_id is not None:
            return cast("UUID", actor_dealer_id)
    vehicle_ids = [
        vehicle.vehicle_id
        for vehicle in cmd.vehicles
        if vehicle.vehicle_id is not None
    ]
    resolved = await wh_repo.resolve_application_dealer_company_id(
        session,
        vehicle_ids,
    )
    return cast("UUID | None", resolved)


async def _insert_application(
    cmd: CreateApplicationCommand, status: str, session: AsyncSession
) -> uuid.UUID:
    dealer_company_id = await _resolve_dealer_company_id(cmd, session)
    application_id = await repo.create_application(
        session,
        payload={
            "company_id": cmd.company_id,
            "dealer_company_id": dealer_company_id,
            "name": cmd.name,
            "email": cmd.email,
            "status": status,
            "total_amount": cmd.total_amount,
            "down_payment": cmd.down_payment,
            "down_payment_percent": cmd.down_payment_percent,
            "lease_term_months": cmd.lease_term_months,
            "monthly_payment": cmd.monthly_payment,
            "total_cost": cmd.total_cost,
            "markup": cmd.markup,
            "rate": cmd.rate,
            "total_interest": cmd.total_interest,
            "buyout_amount": cmd.buyout_amount,
            "vat_refund": cmd.vat_refund,
            "profit_tax_savings": cmd.profit_tax_savings,
            "total_savings": cmd.total_savings,
            "selected_leasing_companies": cmd.selected_leasing_companies,
            "created_by": cmd.actor_id,
            "storefront_id": cmd.scope.id,
            "source_type": await resolve_application_source(
                session, requested=cmd.source_type,
                first_product_id=cmd.vehicles[0].vehicle_id if cmd.vehicles else None,
            ),
            "current_stage": cmd.current_stage,
        },
    )
    application = await repo.get_by_id(session, application_id)
    if application is not None:
        await assign_display_number_if_missing(session, application=application)
    return cast("uuid.UUID", application_id)


async def _append_vehicle_lines(
    cmd: CreateApplicationCommand,
    application_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    for v in cmd.vehicles:
        if v.vehicle_id is None and not v.modification_id:
            raise ApplicationNotSubmittableError(
                "Для каждого автомобиля нужен vehicle_id или modification_id"
            )
        await _validate_vehicle_stock(session, v, cmd.scope)
        unit = _resolve_unit_price(v)
        options_unit = _options_total(v.equipments) + _options_total(v.services)
        qty = v.quantity if v.quantity and v.quantity > 0 else 1
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


async def _persist_side_records(
    cmd: CreateApplicationCommand,
    application_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    if cmd.selected_leasing_companies:
        await repo.upsert_lc_links(
            session,
            application_id=application_id,
            leasing_company_ids=cmd.selected_leasing_companies,
            changed_by=cmd.actor_id,
        )

    await refresh_questionnaire(session, application_id)
    if cmd.questionnaire:
        from application.services.questionnaire import write_questionnaire
        await write_questionnaire(session, application_id, cmd.questionnaire)

    if cmd.vehicle_calculations:
        for calc in cmd.vehicle_calculations:
            await repo.add_vehicle_calculation(
                session,
                application_id=application_id,
                payload=calc,
            )

    if any(
        v is not None
        for v in (
            cmd.monthly_payment,
            cmd.rate,
            cmd.total_cost,
            cmd.total_interest,
        )
    ):
        await repo.upsert_calculation(
            session,
            application_id=application_id,
            payload={
                "monthly_payment": cmd.monthly_payment,
                "rate": cmd.rate,
                "total_cost": cmd.total_cost,
                "total_interest": cmd.total_interest,
                "buyout_amount": cmd.buyout_amount,
                "vat_refund": cmd.vat_refund,
                "profit_tax_savings": cmd.profit_tax_savings,
                "total_savings": cmd.total_savings,
            },
        )


async def _attach_fns_report(
    cmd: CreateApplicationCommand,
    application_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    """Best-effort attach of the FNS bookkeeping PDF for the applicant's INN."""
    company = await company_repo.get_company_by_id(session, cmd.company_id)
    if company is None:
        return
    await attach_fns_report_to_applications(
        session,
        inn=company.get("inn"),
        company_id=cmd.company_id,
        application_ids=[application_id],
    )
    await attach_company_requisites_to_applications(
        session,
        company_id=cmd.company_id,
        application_ids=[application_id],
    )


def _resolve_unit_price(v: ApplicationVehiclePayload) -> Decimal:
    if v.custom_price is not None:
        return _to_decimal(v.custom_price)
    return Decimal("0")


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


async def _validate_vehicle_stock(session: AsyncSession, vehicle: ApplicationVehiclePayload, _scope: CatalogScope) -> None:
    from domain.entities.cart_item import CartItem
    from infrastructure.repositories import special_equipment_commerce_repository
    CartItem.ensure_quantity_valid(vehicle.quantity)
    if vehicle.vehicle_id is None:
        return
    product = await special_equipment_commerce_repository.get_product(session, vehicle.vehicle_id)
    available_count = 1 if product and product.get("sale_status") == "available" else 0
    CartItem.ensure_stock_quantity(
        vehicle.quantity,
        available=available_count,
        allow_overstock=vehicle.allow_overstock,
    )
