"""Distribution context for existing whole-line operations."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
)
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.repositories import vehicle_fulfillment_repository as fulfillment
from infrastructure.repositories.vehicle_ownership_repository import (
    resolved_vehicle_owner_expression,
)


async def get_write_scope(
    session: AsyncSession, *, application_vehicle_id: UUID,
    actor_company_id: UUID | None, lock: bool = True,
) -> dict[str, Any] | None:
    line = await fulfillment.line(session, application_vehicle_id, lock=lock)
    if line is None:
        return None
    product_id = line.get("product_id") or line.get("vehicle_id")
    owner = await session.scalar(sa.select(resolved_vehicle_owner_expression()).where(
        SpecialEquipmentProduct.id == product_id,
    )) if product_id else None
    distribution = ApplicationVehicleDealerDistribution
    rows = (await session.execute(sa.select(
        distribution.dealer_company_id, sa.func.sum(distribution.quantity),
    ).where(distribution.application_vehicle_id == application_vehicle_id).group_by(
        distribution.dealer_company_id,
    ))).all()
    return {
        "stock_owner_id": owner,
        "quantity": int(line.get("quantity") or 1),
        "distributed_quantity": sum(int(quantity) for _, quantity in rows),
        "actor_quantity": sum(int(quantity) for dealer, quantity in rows if dealer == actor_company_id),
        "sole_dealer_id": rows[0][0] if len(rows) == 1 else None,
    }


async def application_has_distributions(session: AsyncSession, application_id: UUID) -> bool:
    return bool(await session.scalar(sa.select(sa.exists().where(
        ApplicationVehicle.application_id == application_id,
        ApplicationVehicleDealerDistribution.application_vehicle_id == ApplicationVehicle.id,
    ))))
