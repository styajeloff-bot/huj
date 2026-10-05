"""Recalculate supplier quantities through the same calculator as checkout."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.calculator.calculate import CalculateCommand, handle_calculate
from application.errors import ServiceError
from domain.entities.leasing_calculator import LeasingRates
from infrastructure.repositories import application_repository as applications
from infrastructure.repositories import application_vehicle_repository as vehicles
from infrastructure.repositories import quantity_calculation_repository as repo


def _money(value: Any) -> Decimal:
    result = Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if not result.is_finite() or abs(result) >= Decimal('10000000000000'):
        raise ServiceError('Стоимость превышает допустимый размер. Уменьшите количество ТС', 422)
    return result


def line_total(row: dict[str, Any]) -> Decimal:
    price = row.get('final_price')
    if price is None:
        price = row.get('unit_price')
    if price is None:
        raise ServiceError('Для изменения количества требуется согласованная цена', 409)
    options = sum((_money(option.get('price')) for key in ('equipments', 'services')
                   for option in row.get(key) or []), Decimal(0))
    return _money((_money(price) + options) * int(row.get('quantity') or 1))


def _tax_rate(total: Any, tax: Any) -> float:
    total, tax = _money(total), _money(tax)
    return float(tax * 100 / (total - tax)) if total > tax > 0 else 0.0


async def recalculate_quantity(
    session: AsyncSession, *, application_vehicle_id: UUID, previous_quantity: int,
) -> None:
    del previous_quantity  # Rebuild from authoritative values, never scale old totals.
    line = await vehicles.get_by_id(session, application_vehicle_id)
    if line is None:
        raise ServiceError('Позиция заявки не найдена', 404)
    application_id = line['application_id']
    await repo.update_line_total(session, application_vehicle_id, line_total(line))
    total = await applications.sum_active_application_items_total(session, application_id)
    if total is None:
        raise ServiceError('Для пересчёта нужно указать цены всех позиций заявки', 409)
    total = _money(total)
    app = await applications.get_by_id(session, application_id) or {}
    stored = await applications.get_calculation(session, application_id) or {}
    rows = [row for row in await applications.list_application_vehicles(session, application_id)
            if row.get('car_status') in {'active', 'confirmed', 'replacement'}]
    term = app.get('lease_term_months')
    percent = app.get('down_payment_percent')
    if not term or percent is None:
        if any(app.get(key) is not None or stored.get(key) is not None
               for key in ('monthly_payment', 'total_cost', 'total_interest')):
            raise ServiceError('Не хватает условий для пересчёта. Укажите срок и аванс', 409)
        await applications.update_application_fields(session, application_id, fields={'total_amount': total})
        await _recalculate_snapshots(session, app, stored, rows)
        return
    quantities: dict[UUID, int] = {}
    prices: dict[UUID, float] = {}
    vehicle_total = Decimal(0)
    for row in rows:
        vehicle_id = row.get('vehicle_id')
        if vehicle_id is None:
            continue
        if vehicle_id in quantities:
            raise ServiceError('Повторяющиеся позиции требуют уточнения расчёта', 409)
        price = _money(row.get('final_price') if row.get('final_price') is not None else row.get('unit_price'))
        quantity = int(row.get('quantity') or 1)
        quantities[vehicle_id] = quantity
        prices[vehicle_id] = float(price)
        vehicle_total += price * quantity
    rates = _stored_rates(app, stored)
    response = (await handle_calculate(CalculateCommand(
        total_amount=float(total), additional_amount=float(total - vehicle_total) if quantities else None,
        down_payment=float(_money(total * Decimal(str(percent)) / 100)),
        down_payment_percent=float(percent), lease_term_months=int(term),
        buyout_amount=float(app.get('buyout_amount') or 0), vehicle_ids=list(quantities),
        vehicle_quantities=quantities, vehicle_price_overrides=prices,
        selected_support=dict(stored.get('selected_support') or {}),
        user={'id': app.get('user_id'), 'role': 'dealer', 'company_id': app.get('dealer_company_id')},
        persist_history=False, rates_override=rates,
    ), session)).response
    result = response['calculation']
    parameters = response['calculation_parameters']
    fields = _financial_fields(result, rates)
    fields['markup'] = _money(result['markup'])
    fields.update(total_amount=total, down_payment=_money(parameters['down_payment']))
    await applications.update_application_fields(session, application_id, fields=fields)
    support = response.get('support') or {}
    payload = {**fields, 'base_total': total, 'effective_total': support.get('effective_total', total),
               'effective_down_payment': parameters['down_payment'],
               **_snapshot_payload_fields(response, stored)}
    for key in ('vehicle_discount_support', 'dealer_commission_support', 'down_payment_support', 'interest_support'):
        payload[key] = support.get(key, 0)
    await applications.upsert_calculation(session, application_id=application_id, payload=payload)
    await _recalculate_snapshots(session, app, stored, rows)


def _stored_rates(app: dict[str, Any], stored: dict[str, Any]) -> LeasingRates | None:
    rate = stored.get('rate') if stored.get('rate') is not None else app.get('rate')
    rates = None
    if rate is not None:
        old_total = stored.get('total_cost') or app.get('total_cost')
        rates = LeasingRates(key_rate=float(rate), surcharge=0,
            vat_rate=_tax_rate(old_total, stored.get('vat_refund') or app.get('vat_refund')),
            profit_tax_rate=_tax_rate(old_total, stored.get('profit_tax_savings') or app.get('profit_tax_savings')))
    return rates


def _rate(rates: LeasingRates | None, fallback: Any) -> Decimal:
    # The calculator's public display rate is rounded to two decimals; persist
    # the exact four-decimal contract rate used by its annuity calculation.
    value = rates.key_rate + rates.surcharge if rates is not None else fallback
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def _recalculate_snapshots(
    session: AsyncSession, app: dict[str, Any], stored: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    snapshots = await applications.list_vehicle_calculations(session, app["id"])
    for snapshot in snapshots:
        matches = [row for row in rows if (
            row.get("vehicle_id") == snapshot["vehicle_id"]
            if snapshot.get("vehicle_id") is not None
            else row.get("vehicle_id") is None
            and row.get("modification_id") == snapshot.get("modification_id")
            and (snapshot.get("color") is None or row.get("color") == snapshot["color"])
        )]
        if not matches:
            continue  # Historical removed/replaced positions retain their snapshots.
        if len(matches) != 1:
            raise ServiceError("Не удалось однозначно определить индивидуальный расчёт", 409)
        row = matches[0]
        total = line_total(row)
        price = _money(row.get("final_price") if row.get("final_price") is not None else row.get("unit_price"))
        quantity = int(row.get("quantity") or 1)
        term = snapshot.get("lease_term_months") or app.get("lease_term_months")
        percent = snapshot.get("down_payment_percent")
        if percent is None:
            percent = app.get("down_payment_percent")
        if not term or percent is None:
            raise ServiceError("Не хватает срока или аванса индивидуального расчёта", 409)
        vehicle_id = row.get("vehicle_id")
        selected = {key: value for key, value in (stored.get("selected_support") or {}).items()
                    if str(key) == str(vehicle_id)}
        rates = _stored_rates(snapshot, snapshot) or _stored_rates(app, stored)
        response = (await handle_calculate(CalculateCommand(
            total_amount=float(total), additional_amount=float(total - price * quantity) if vehicle_id else None,
            down_payment=float(_money(total * Decimal(str(percent)) / 100)),
            down_payment_percent=float(percent), lease_term_months=int(term),
            buyout_amount=float(snapshot.get("buyout_amount") or 0),
            vehicle_ids=[vehicle_id] if vehicle_id else [],
            vehicle_quantities={vehicle_id: quantity} if vehicle_id else {},
            vehicle_price_overrides={vehicle_id: float(price)} if vehicle_id else {},
            selected_support=selected, persist_history=False, rates_override=rates,
            user={"id": app.get("user_id"), "role": "dealer", "company_id": app.get("dealer_company_id")},
        ), session)).response
        result = response["calculation"]
        fields = _financial_fields(result, rates)
        fields.update(quantity=quantity, unit_price=price, total_amount=total,
                      down_payment=_money(response["calculation_parameters"]["down_payment"]),
                      down_payment_percent=Decimal(str(percent)), lease_term_months=int(term))
        await repo.update_vehicle_calculation(session, snapshot["id"], fields)


def _financial_fields(result: dict[str, Any], rates: LeasingRates | None) -> dict[str, Any]:
    mapping = {"monthly_payment": "monthlyPayment", "total_cost": "totalCost",
               "total_interest": "totalInterest", "buyout_amount": "buyoutAmount",
               "vat_refund": "vatRefund", "profit_tax_savings": "profitTaxSavings",
               "total_savings": "totalSavings"}
    return {**{key: _money(result[value]) for key, value in mapping.items()},
            "rate": _rate(rates, result["rate"])}


def _snapshot_payload_fields(response: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """JSONB columns must work with PostgreSQL's ordinary JSON serializer."""
    payload = {key: response.get(key) or [] for key in (
        "support_per_vehicle", "support_per_program", "support_program_details", "calculations_per_vehicle",
    )}
    payload["selected_support"] = stored.get("selected_support") or {}
    return cast('dict[str, Any]', to_jsonable_python(payload))
