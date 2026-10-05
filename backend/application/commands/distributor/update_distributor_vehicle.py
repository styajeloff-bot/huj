"""Partial update of a distributor-scoped vehicle."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.entities.vehicle import Vehicle
from domain.errors import (
    MarkNotFoundError,
    ModelNotFoundError,
    VehicleNotFoundError,
    VinAlreadyAssignedError,
)
from infrastructure.repositories import distributor_repository as repo

# Names of fields the partial-update path is allowed to overwrite.
_PARTIAL_FIELD_NAMES: tuple[str, ...] = (
    "vin",
    "dealer_id",
    "mark_id",
    "model_id",
    "generation_id",
    "configuration_id",
    "complectation_id",
    "year",
    "base_price",
    "special_price",
    "discount_price",
    "color",
    "color_inter",
    "status",
    "is_available",
    "images",
)


@dataclass
class UpdateDistributorVehicleCommand:
    vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    fields_set: set[str] = field(default_factory=set)
    vin: str | None = None
    dealer_id: UUID | None = None
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
    status: str | None = None
    is_available: bool | None = None
    images: list[str] | None = None


def _build_updates(cmd: UpdateDistributorVehicleCommand) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for name in _PARTIAL_FIELD_NAMES:
        if name in cmd.fields_set:
            updates[name] = getattr(cmd, name)
    return updates


async def handle_update_distributor_vehicle(
    cmd: UpdateDistributorVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )

    existing = await repo.get_distributor_vehicle(session, cmd.vehicle_id)
    if existing is None:
        raise VehicleNotFoundError(cmd.vehicle_id)
    scope.ensure_can_write(existing.get("dealer_id"))

    updates = _build_updates(cmd)
    if "dealer_id" in cmd.fields_set:
        updates["dealer_id"] = scope.coerce_dealer_id_for_write(cmd.dealer_id)

    # Validate the would-be result against domain invariants.
    merged = dict(existing)
    merged.update(updates)
    Vehicle.from_dict(merged).ensure_valid()

    if updates.get("mark_id") and not await repo.mark_exists(
        session, updates["mark_id"]
    ):
        raise MarkNotFoundError(updates["mark_id"])
    if updates.get("model_id") and not await repo.model_exists(
        session, updates["model_id"]
    ):
        raise ModelNotFoundError(updates["model_id"])
    if updates.get("vin") and await repo.vin_exists(
        session, updates["vin"], exclude_id=cmd.vehicle_id
    ):
        raise VinAlreadyAssignedError(updates["vin"])

    await repo.update_vehicle_in_scope(
        session,
        vehicle_id=cmd.vehicle_id,
        dealer_filter=scope.dealer_filter(),
        fields=updates,
    )
    saved = await repo.get_distributor_vehicle(session, cmd.vehicle_id)
    assert saved is not None
    return cast("dict[str, Any]", saved)
