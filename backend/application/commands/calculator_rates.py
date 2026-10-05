from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import calculator_repository as repo


@dataclass(frozen=True)
class CreateCalculatorRateCommand:
    date_from: date
    date_to: date | None
    key_rate: float
    surcharge: float
    vat_rate: float
    profit_tax_rate: float


@dataclass(frozen=True)
class PatchCalculatorRateCommand:
    rate_id: UUID
    values: dict[str, object]


def _validate_period(date_from: date, date_to: date | None) -> None:
    if date_to is not None and date_to <= date_from:
        raise ServiceError("Дата окончания должна быть позже даты начала", 422)


async def _ensure_period_available(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date | None,
    exclude_id: UUID | None = None,
) -> None:
    if date_to is None and await repo.has_current_leasing_rate(
        session, exclude_id=exclude_id
    ):
        raise ServiceError("В базе уже есть текущая ставка калькулятора", 422)
    if await repo.has_overlapping_leasing_rate_period(
        session,
        date_from=date_from,
        date_to=date_to,
        exclude_id=exclude_id,
    ):
        raise ServiceError("Период пересекается с существующей ставкой", 422)


async def handle_create_calculator_rate(
    cmd: CreateCalculatorRateCommand,
    session: AsyncSession,
) -> dict[str, object]:
    _validate_period(cmd.date_from, cmd.date_to)
    await _ensure_period_available(
        session,
        date_from=cmd.date_from,
        date_to=cmd.date_to,
    )
    rate = await repo.create_leasing_rate_row(
        session,
        date_from=cmd.date_from,
        date_to=cmd.date_to,
        key_rate=cmd.key_rate,
        surcharge=cmd.surcharge,
        vat_rate=cmd.vat_rate,
        profit_tax_rate=cmd.profit_tax_rate,
    )
    return {"calculator_rate": rate}


async def handle_patch_calculator_rate(
    cmd: PatchCalculatorRateCommand,
    session: AsyncSession,
) -> dict[str, object]:
    existing = await repo.get_leasing_rate_row(session, cmd.rate_id)
    if existing is None:
        raise ServiceError("Ставка калькулятора не найдена", 404)
    values = dict(cmd.values)
    if not values:
        raise ServiceError("Нет полей для обновления", 422)

    next_date_from = values.get("date_from", existing["date_from"])
    next_date_to = values.get("date_to", existing["date_to"])
    if not isinstance(next_date_from, date):
        raise ServiceError("Дата начала периода обязательна", 422)
    if next_date_to is not None and not isinstance(next_date_to, date):
        raise ServiceError("Некорректная дата окончания периода", 422)

    _validate_period(next_date_from, next_date_to)
    await _ensure_period_available(
        session,
        date_from=next_date_from,
        date_to=next_date_to,
        exclude_id=cmd.rate_id,
    )

    updated = await repo.update_leasing_rate_row(session, cmd.rate_id, values)
    if updated is None:
        raise ServiceError("Ставка калькулятора не найдена", 404)
    return {"calculator_rate": updated}
