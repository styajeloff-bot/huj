from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import calculator_repository as repo


@dataclass(frozen=True)
class ListCalculatorRatesQuery:
    pass


@dataclass(frozen=True)
class GetCalculatorRateQuery:
    rate_id: UUID


async def handle_list_calculator_rates(
    _query: ListCalculatorRatesQuery,
    session: AsyncSession,
) -> dict[str, object]:
    return {"items": await repo.list_leasing_rate_rows(session)}


async def handle_get_calculator_rate(
    query: GetCalculatorRateQuery,
    session: AsyncSession,
) -> dict[str, object]:
    rate = await repo.get_leasing_rate_row(session, query.rate_id)
    if rate is None:
        raise ServiceError("Ставка калькулятора не найдена", 404)
    return {"calculator_rate": rate}
