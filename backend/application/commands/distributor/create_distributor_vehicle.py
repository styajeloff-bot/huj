"""Create vehicle in distributor scope."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.entities.vehicle import Vehicle
from domain.errors import (
    InvalidVehicleError,
    MarkNotFoundError,
    ModelNotFoundError,
    VinAlreadyAssignedError,
)
from infrastructure.repositories import distributor_repository as repo


@dataclass
class CreateDistributorVehicleCommand:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    vin: str | None = None
    mark_id: str | None = None
    model_id: str | None = None
    generation_id: str | None = None
    configuration_id: str | None = None
    complectation_id: str | None = None
    year: int | None = None
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    discount_price: Decimal | None = None
    color: str | None = None
    color_inter: str | None = None
    status: str | None = "available"
    is_available: bool | None = True
    dealer_id: UUID | None = None
    images: list[str] | None = None


async def handle_create_distributor_vehicle(
    cmd: CreateDistributorVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        company_id=cmd.company_id,
    )

    if not cmd.mark_id:
        raise InvalidVehicleError("mark_id обязателен")
    if not cmd.model_id:
        raise InvalidVehicleError("model_id обязателен")

    effective_dealer_id = scope.coerce_dealer_id_for_write(cmd.dealer_id)

    vehicle = Vehicle(
        vehicle_id=None,
        vin=cmd.vin,
        dealer_id=effective_dealer_id,
        mark_id=cmd.mark_id,
        model_id=cmd.model_id,
        generation_id=cmd.generation_id,
        configuration_id=cmd.configuration_id,
        complectation_id=cmd.complectation_id,
        year=cmd.year,
        base_price=cmd.base_price,
        special_price=cmd.special_price,
        discount_price=cmd.discount_price,
        color=cmd.color,
        color_inter=cmd.color_inter,
        status=cmd.status or "available",
        is_available=(
            cmd.is_available if cmd.is_available is not None else True
        ),
        images=cmd.images,
    )
    vehicle.ensure_valid()

    if not await repo.mark_exists(session, vehicle.mark_id or ""):
        raise MarkNotFoundError(vehicle.mark_id)
    if not await repo.model_exists(session, vehicle.model_id or ""):
        raise ModelNotFoundError(vehicle.model_id)

    if vehicle.vin and await repo.vin_exists(session, vehicle.vin):
        raise VinAlreadyAssignedError(vehicle.vin)

    payload: dict[str, Any] = {
        "vin": vehicle.vin,
        "dealer_id": vehicle.dealer_id,
        "mark_id": vehicle.mark_id,
        "model_id": vehicle.model_id,
        "generation_id": vehicle.generation_id,
        "configuration_id": vehicle.configuration_id,
        "complectation_id": vehicle.complectation_id,
        "year": vehicle.year,
        "base_price": vehicle.base_price,
        "special_price": vehicle.special_price,
        "discount_price": vehicle.discount_price,
        "color": vehicle.color,
        "color_inter": vehicle.color_inter,
        "status": vehicle.status,
        "is_available": vehicle.is_available,
        "images": vehicle.images,
    }
    new_id = await repo.create_vehicle_in_scope(session, payload=payload)
    saved = await repo.get_distributor_vehicle(session, new_id)
    assert saved is not None
    return cast("dict[str, Any]", saved)
