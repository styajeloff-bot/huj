"""Persist a quantity recalculation without changing line identities or prices."""
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplicationVehicleCalculation,
)


async def update_line_total(session: AsyncSession, line_id: UUID, total: Decimal) -> None:
    await session.execute(sa.update(ApplicationVehicle).where(ApplicationVehicle.id == line_id).values(total_price=total))
    await session.flush()


async def update_vehicle_calculation(session: AsyncSession, snapshot_id: UUID, fields: dict) -> None:
    """Replace financial values only; preserve snapshot identity and ordering."""
    await session.execute(sa.update(LeasingApplicationVehicleCalculation).where(
        LeasingApplicationVehicleCalculation.id == snapshot_id,
    ).values(**fields))
    await session.flush()
