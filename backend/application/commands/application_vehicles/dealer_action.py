"""Dealer/distributor actions on an application vehicle."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.dealer_distribution_access import ensure_whole_vehicle_write_allowed
from application.distributor_scope import resolve_distributor_application_dealer_filter
from application.notifications.leasing_events import (
    record_leasing_event,
    reservation_expiry_timestamp,
)
from domain.entities.application_vehicle import (
    DealerVehicleAction,
    target_status_for_dealer_action,
)
from domain.entities.leasing_calculator import (
    LeasingCalculator,
    LeasingRates,
)
from domain.errors import (
    ApplicationNotOwnedError,
    ApplicationVehicleAssignmentError,
    ApplicationVehicleNotFoundError,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import application_vehicle_repository as av_repo

_MONEY_QUANTUM = Decimal("0.01")


@dataclass
class DealerVehicleActionCommand:
    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    action: DealerVehicleAction
    comment: str | None = None
    reserve_expires_at: Any | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    markup_type: str | None = None
    markup_value: Decimal | None = None
    show_catalog_price: bool | None = None
    vin: str | None = None
    documents: list[dict[str, Any]] | None = None


def _dealer_action_status(action: DealerVehicleAction) -> str | None:
    try:
        target_status = target_status_for_dealer_action(action)
    except ValueError as exc:
        raise ApplicationVehicleAssignmentError(
            "Неизвестное действие по автомобилю заявки"
        ) from exc
    return target_status.value if target_status is not None else None


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _option_total(items: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for item in items:
        try:
            total += Decimal(str(item.get("price") or 0))
        except (ArithmeticError, TypeError, ValueError):
            continue
    return total


def _discount_amount(
    *, catalog_price: Decimal, discount_type: str | None, value: Decimal | None
) -> Decimal:
    if discount_type is None or value is None:
        return Decimal("0")
    if value < 0:
        raise ApplicationVehicleAssignmentError("Скидка не может быть отрицательной")
    if discount_type == "rubles_off":
        amount = value
    elif discount_type == "percent_off":
        if value > 100:
            raise ApplicationVehicleAssignmentError("Скидка не может превышать 100%")
        amount = catalog_price * value / Decimal("100")
    elif discount_type == "fixed_price":
        amount = catalog_price - value
    else:
        raise ApplicationVehicleAssignmentError("Неизвестный тип скидки")
    if amount < 0 or amount > catalog_price:
        raise ApplicationVehicleAssignmentError(
            "Скидка должна быть в пределах цены по каталогу"
        )
    return _money(amount)


def _markup_amount(
    *, catalog_price: Decimal, markup_type: str | None, value: Decimal | None
) -> Decimal:
    if markup_type is None or value is None:
        return Decimal("0")
    if value < 0:
        raise ApplicationVehicleAssignmentError("Надбавка не может быть отрицательной")
    if markup_type == "rubles_up":
        amount = value
    elif markup_type == "percent_up":
        amount = catalog_price * value / Decimal("100")
    else:
        raise ApplicationVehicleAssignmentError("Неизвестный тип надбавки")
    return _money(amount)


def _require_price_action_payload(cmd: DealerVehicleActionCommand) -> None:
    if cmd.action == "discount" and (
        cmd.discount_type is None or cmd.discount_value is None
    ):
        raise ApplicationVehicleAssignmentError("Укажите размер скидки")
    if cmd.action == "markup" and (
        cmd.markup_type is None or cmd.markup_value is None
    ):
        raise ApplicationVehicleAssignmentError("Укажите размер надбавки")


async def _ensure_vehicle_scope(
    cmd: DealerVehicleActionCommand, session: AsyncSession, *, for_write: bool = False,
) -> None:
    if cmd.actor_role == "carcraft_employee":
        return
    if cmd.actor_company_id is None:
        raise ApplicationNotOwnedError("У пользователя не выбрана компания")
    if cmd.actor_role == "dealer":
        allowed = await app_repo.dealer_company_owns_application_vehicle(
            session,
            application_vehicle_id=cmd.application_vehicle_id,
            company_id=cmd.actor_company_id,
        )
    else:
        dealer_filter = await resolve_distributor_application_dealer_filter(
            session,
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            company_id=cmd.actor_company_id,
        )
        allowed = await app_repo.distributor_can_view_application_vehicle(
            session,
            application_vehicle_id=cmd.application_vehicle_id,
            dealer_ids=dealer_filter,
            distributor_company_id=cmd.actor_company_id,
        )
    if not allowed:
        raise ApplicationNotOwnedError("Автомобиль заявки недоступен пользователю")
    if for_write:
        await ensure_whole_vehicle_write_allowed(session,
            application_vehicle_id=cmd.application_vehicle_id,
            actor_role=cmd.actor_role, actor_company_id=cmd.actor_company_id)


def _derived_tax_rate(total_cost: Decimal, tax_amount: Decimal) -> Decimal:
    taxable_base = total_cost - tax_amount
    if taxable_base <= 0 or tax_amount <= 0:
        return Decimal("0")
    return tax_amount * Decimal("100") / taxable_base


async def _sync_saved_leasing_calculation(
    session: AsyncSession,
    *,
    application_id: UUID,
    total_amount: Decimal | None,
) -> None:
    """Refresh saved calculation when its persisted parameters are sufficient.

    Aggregate inputs are always synchronized. Derived financing fields are
    intentionally preserved when term/rate/down-payment data is incomplete.
    """

    if total_amount is None:
        return
    application = await app_repo.get_by_id(session, application_id)
    if application is None:
        return
    stored_calculation = await app_repo.get_calculation(session, application_id)
    calculation = stored_calculation or {}

    vehicle_support = Decimal(str(calculation.get("vehicle_discount_support") or 0))
    effective_total = max(total_amount - vehicle_support, Decimal("0"))
    down_payment_percent = application.get("down_payment_percent")
    if down_payment_percent is None:
        old_total = Decimal(str(calculation.get("effective_total") or 0))
        old_down_payment = Decimal(str(application.get("down_payment") or 0))
        down_payment_percent = (
            old_down_payment * Decimal("100") / old_total
            if old_total > 0
            else None
        )
    down_payment_support = Decimal(str(calculation.get("down_payment_support") or 0))
    interest_support = Decimal(str(calculation.get("interest_support") or 0))
    calculation_patch: dict[str, Any] = {
        "base_total": total_amount,
        "effective_total": effective_total,
    }
    if down_payment_percent is not None:
        contract_down_payment = _money(
            effective_total * Decimal(str(down_payment_percent)) / Decimal("100")
        )
        calculation_patch["effective_down_payment"] = max(
            contract_down_payment - down_payment_support - interest_support,
            Decimal("0"),
        )
    else:
        contract_down_payment = None

    term = application.get("lease_term_months")
    stored_rate = calculation.get("rate") or application.get("rate")
    stored_total_cost = Decimal(
        str(calculation.get("total_cost") or application.get("total_cost") or 0)
    )
    if contract_down_payment is not None and term and stored_rate is not None:
        vat_rate = _derived_tax_rate(
            stored_total_cost,
            Decimal(
                str(calculation.get("vat_refund") or application.get("vat_refund") or 0)
            ),
        )
        profit_tax_rate = _derived_tax_rate(
            stored_total_cost,
            Decimal(
                str(
                    calculation.get("profit_tax_savings")
                    or application.get("profit_tax_savings")
                    or 0
                )
            ),
        )
        buyout_amount = Decimal(str(application.get("buyout_amount") or 0))
        result = LeasingCalculator.compute_leasing(
            total_amount=float(effective_total),
            down_payment=float(contract_down_payment),
            term_months=int(term),
            rates=LeasingRates(
                key_rate=float(stored_rate),
                surcharge=0,
                vat_rate=float(vat_rate),
                profit_tax_rate=float(profit_tax_rate),
            ),
            buyout_amount=float(buyout_amount),
        )
        derived = {
            "monthly_payment": Decimal(result.monthly_payment),
            "rate": Decimal(str(result.rate)),
            "total_cost": Decimal(result.total_cost),
            "total_interest": Decimal(result.total_interest),
            "buyout_amount": Decimal(result.buyout_amount),
            "vat_refund": Decimal(result.vat_refund),
            "profit_tax_savings": Decimal(result.profit_tax_savings),
            "total_savings": Decimal(result.total_savings),
        }
        calculation_patch.update(derived)
        await app_repo.update_application_fields(
            session,
            application_id,
            fields={
                **derived,
                "down_payment": contract_down_payment,
                "markup": Decimal(result.markup),
            },
        )
    elif stored_calculation is None:
        return
    await app_repo.upsert_calculation(
        session,
        application_id=application_id,
        payload=calculation_patch,
    )


async def handle_dealer_vehicle_action(
    cmd: DealerVehicleActionCommand, session: AsyncSession
) -> dict[str, Any]:
    await av_repo.lock_parent_application(session, cmd.application_vehicle_id)
    if cmd.actor_role not in {"dealer", "distributor", "carcraft_employee"}:
        raise ApplicationVehicleAssignmentError(
            "Роль не имеет права менять статус автомобиля заявки"
        )
    await _ensure_vehicle_scope(cmd, session, for_write=True)
    is_price_action = cmd.action in {"discount", "markup"}
    if is_price_action:
        if cmd.actor_role not in {"dealer", "distributor"}:
            raise ApplicationVehicleAssignmentError(
                "Только дилер или дистрибьютор может менять цену автомобиля заявки"
            )
        _require_price_action_payload(cmd)
    status = await _checked_dealer_action_status(cmd, session)
    vin = (cmd.vin or "").strip() if cmd.action == "replace_vin" else None
    if cmd.action == "replace_vin" and not vin:
        raise ApplicationVehicleAssignmentError("Укажите VIN-номер для замены")
    if vin is not None and await av_repo.vin_used_on_other(
        session,
        vin=vin,
        exclude_id=cmd.application_vehicle_id,
    ):
        raise ApplicationVehicleAssignmentError("VIN уже назначен другому автомобилю заявки")

    pricing = await av_repo.get_pricing_context(session, cmd.application_vehicle_id)
    if pricing is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)
    discount_type = (
        cmd.discount_type if cmd.action == "discount" else pricing.get("discount_type")
    )
    discount_value = (
        cmd.discount_value if cmd.action == "discount" else pricing.get("discount_value")
    )
    markup_type = (
        cmd.markup_type if cmd.action == "markup" else pricing.get("markup_type")
    )
    markup_value = (
        cmd.markup_value if cmd.action == "markup" else pricing.get("markup_value")
    )
    final_price: Decimal | None = None
    total_price: Decimal | None = None
    catalog_price = pricing.get("catalog_unit_price")
    if is_price_action:
        if catalog_price is None:
            raise ApplicationVehicleAssignmentError("Не задана цена автомобиля в каталоге")
        catalog_price = Decimal(str(catalog_price))
        discount = _discount_amount(
            catalog_price=catalog_price,
            discount_type=discount_type,
            value=Decimal(str(discount_value)) if discount_value is not None else None,
        )
        markup = _markup_amount(
            catalog_price=catalog_price,
            markup_type=markup_type,
            value=Decimal(str(markup_value)) if markup_value is not None else None,
        )
        final_price = _money(catalog_price - discount + markup)
        quantity = max(int(pricing.get("quantity") or 1), 1)
        options = _option_total(pricing.get("equipments") or []) + _option_total(
            pricing.get("services") or []
        )
        total_price = _money((final_price + options) * quantity)

    updated = await av_repo.update_dealer_action(
        session,
        cmd.application_vehicle_id,
        status=status,
        dealer_comment=cmd.comment,
        reserve_expires_at=cmd.reserve_expires_at,
        discount_type=discount_type if cmd.action == "discount" else None,
        discount_value=discount_value if cmd.action == "discount" else None,
        markup_type=markup_type if cmd.action == "markup" else None,
        markup_value=markup_value if cmd.action == "markup" else None,
        discount_show_catalog_price=(
            cmd.show_catalog_price if cmd.action == "discount" else None
        ),
        markup_show_catalog_price=(
            cmd.show_catalog_price if cmd.action == "markup" else None
        ),
        final_price=final_price,
        total_price=total_price,
        vin=vin,
        vin_assigned_by=cmd.actor_id if cmd.action == "replace_vin" else None,
    )
    if updated is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)
    if is_price_action:
        total_amount = await app_repo.sum_active_application_items_total(
            session, pricing["application_id"]
        )
        await app_repo.update_application_fields(
            session,
            pricing["application_id"],
            fields={"total_amount": total_amount},
        )
        await _sync_saved_leasing_calculation(
            session,
            application_id=pricing["application_id"],
            total_amount=total_amount,
        )
        updated["catalog_price"] = catalog_price
        updated["discount_amount"] = discount
        updated["markup_amount"] = markup
    if cmd.documents:
        docs = await av_repo.add_dealer_action_documents(
            session,
            cmd.application_vehicle_id,
            action=cmd.action,
            uploaded_by=cmd.actor_id,
            documents=cmd.documents,
        )
        updated["dealer_action_documents"] = [
            *updated.get("dealer_action_documents", []),
            *docs,
        ]
    response_status = updated.get("car_status") or updated.get("status")
    await _record_vehicle_action_event(session, cmd, pricing, updated)
    return {"application_vehicle": updated, "status": response_status, "success": True}


async def _record_vehicle_action_event(
    session: AsyncSession, cmd: DealerVehicleActionCommand,
    previous: dict[str, Any], updated: dict[str, Any],
) -> None:
    await _release_fulfillment_on_rejection(cmd, session)
    if cmd.action not in {"reserve", "reject"}:
        return
    application = await app_repo.get_by_id(session, previous["application_id"])
    if application is None:
        return
    await record_leasing_event(
        session, application=application,
        event_type=("leasing.vehicle_reserved" if cmd.action == "reserve"
                    else "leasing.vehicle_cancelled"),
        actor_user_id=cmd.actor_id,
        previous_values={"car_status": previous.get("car_status"),
                         "reserve_expires_at": reservation_expiry_timestamp(previous.get("reserve_expires_at"))},
        new_values={"car_status": updated.get("car_status"),
                    "reserve_expires_at": reservation_expiry_timestamp(updated.get("reserve_expires_at"))},
        payload={"application_vehicle_id": cmd.application_vehicle_id},
    )


async def _release_fulfillment_on_rejection(cmd: DealerVehicleActionCommand, session: AsyncSession) -> None:
    if cmd.action in {"reject", "replace"}:
        from infrastructure.repositories import (
            vehicle_fulfillment_repository as fulfillment,
        )
        await fulfillment.release_line(session, cmd.application_vehicle_id,
                                       reason=cmd.comment or "Отказ поставщика")


async def _checked_dealer_action_status(cmd: DealerVehicleActionCommand, session: AsyncSession) -> str | None:
    from domain.vehicle_fulfillment import ensure_dealer_action_uses_fulfillment
    ensure_dealer_action_uses_fulfillment(cmd.action)
    if cmd.action in {"replace_vin", "reject", "replace"}:
        from application.errors import ServiceError
        from domain.vehicle_fulfillment import fulfillment_editable
        from infrastructure.repositories import (
            vehicle_fulfillment_repository as fulfillment,
        )
        line = await fulfillment.line(session, cmd.application_vehicle_id)
        if line and line.get("fulfillment_version"):
            if cmd.action == "replace_vin":
                raise ApplicationVehicleAssignmentError("Используйте подбор автомобилей для изменения брони или VIN")
            application = await app_repo.get_by_id(session, line["application_id"])
            if not fulfillment_editable(actor_role=cmd.actor_role,
                    application_status=application.get("status") if application else None,
                    line_status=line.get("car_status"),
                    has_lc_children=await app_repo.has_lc_children(session, line["application_id"])):
                raise ServiceError("Состав закреплён за сделкой. Изменение позиции недоступно", 409)
    return _dealer_action_status(cmd.action)
