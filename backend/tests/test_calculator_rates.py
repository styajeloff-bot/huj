from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.misc import LeasingRate
from infrastructure.repositories.calculator_repository import get_leasing_rates

pytestmark = pytest.mark.asyncio


async def test_get_leasing_rates_prefers_current_open_period(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            LeasingRate(
                id=UUID("00000000-0000-0000-0000-000000000001"),
                date_from=date(2024, 1, 1),
                date_to=date(2025, 1, 1),
                key_rate=10.0,
                surcharge=2.0,
                vat_rate=18.0,
                profit_tax_rate=20.0,
            ),
            LeasingRate(
                id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
                date_from=date(2025, 1, 1),
                date_to=None,
                key_rate=21.0,
                surcharge=4.0,
                vat_rate=22.0,
                profit_tax_rate=25.0,
            ),
        ]
    )
    await db_session.flush()

    rates = await get_leasing_rates(db_session)

    assert rates == {
        "key_rate": 21.0,
        "surcharge": 4.0,
        "vat_rate": 22.0,
        "profit_tax_rate": 25.0,
    }


async def test_get_leasing_rates_falls_back_to_youngest_period_when_no_current(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            LeasingRate(
                id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
                date_from=date(2024, 1, 1),
                date_to=date(2024, 7, 1),
                key_rate=10.0,
                surcharge=2.0,
                vat_rate=18.0,
                profit_tax_rate=20.0,
            ),
            LeasingRate(
                id=UUID("00000000-0000-0000-0000-000000000001"),
                date_from=date(2025, 1, 1),
                date_to=date(2025, 7, 1),
                key_rate=19.0,
                surcharge=3.0,
                vat_rate=20.0,
                profit_tax_rate=24.0,
            ),
        ]
    )
    await db_session.flush()

    rates = await get_leasing_rates(db_session)

    assert rates == {
        "key_rate": 19.0,
        "surcharge": 3.0,
        "vat_rate": 20.0,
        "profit_tax_rate": 24.0,
    }
