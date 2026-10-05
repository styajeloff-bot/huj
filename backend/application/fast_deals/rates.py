"""Calculator rate used for the monthly payment of fast deal terms."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import calculator_repository
from infrastructure.settings import settings


async def current_annual_rate(session: AsyncSession) -> Decimal | None:
    """``key_rate + surcharge`` in percent per year, or ``None`` if not configured.

    Mirrors the calculator: the configured effective rate, else the documented
    default fallback when it is enabled.
    """
    raw: dict[str, Any] | None = await calculator_repository.get_leasing_rates(session)
    if raw is not None:
        return Decimal(str(raw["key_rate"])) + Decimal(str(raw["surcharge"]))
    if settings.calculator_use_default_rates_fallback:
        return Decimal(str(settings.calculator_default_key_rate)) + Decimal(
            str(settings.calculator_default_surcharge)
        )
    return None
