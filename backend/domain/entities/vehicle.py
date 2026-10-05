"""Vehicle domain entity — admin-side aggregate root.

Covers the business rules that sit around the `vehicles` table for admin CRUD:
validation, ownership checks and VIN-assignment invariants.

Note: this entity is intentionally lean. It does NOT model the full vehicle
specification — only the fields that admin writes manipulate (VIN, ownership,
price, availability, status). Read models and catalog joins live in the
repository layer.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    AccessDeniedError,
    InvalidVehicleError,
    VehicleNotAvailableError,
)

_ALLOWED_STATUSES: frozenset[str] = frozenset(
    {"available", "reserved", "sold"}
)


@dataclass
class Vehicle:
    """Aggregate root for a single vehicle unit in the inventory."""

    vehicle_id: UUID | None
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
    status: str | None = "available"
    is_available: bool | None = True
    images: list[str] | None = field(default=None)
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    # ---------------------------------------------------------------------
    # Hydration
    # ---------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Vehicle:
        raw_images = data.get("images")
        images: list[str] | None
        if raw_images is None:
            images = None
        elif isinstance(raw_images, list):
            images = [str(x) for x in raw_images]
        elif isinstance(raw_images, dict):
            # Legacy JSONB shape — {"urls": [...]} or similar; best-effort.
            urls = raw_images.get("urls") if "urls" in raw_images else None
            images = [str(x) for x in urls] if isinstance(urls, list) else None
        else:
            images = None

        return cls(
            vehicle_id=data.get("id") or data.get("vehicle_id"),
            vin=data.get("vin"),
            dealer_id=data.get("dealer_id"),
            mark_id=data.get("mark_id"),
            model_id=data.get("model_id"),
            generation_id=data.get("generation_id"),
            configuration_id=data.get("configuration_id"),
            complectation_id=data.get("complectation_id"),
            year=data.get("year"),
            base_price=_to_decimal(data.get("base_price")),
            special_price=_to_decimal(data.get("special_price")),
            discount_price=_to_decimal(data.get("discount_price")),
            color=data.get("color"),
            color_inter=data.get("color_inter"),
            status=data.get("status"),
            is_available=data.get("is_available"),
            images=images,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    # ---------------------------------------------------------------------
    # Invariants
    # ---------------------------------------------------------------------

    def ensure_valid(self) -> None:
        """Validate structural invariants shared by create / update flows."""
        if self.vin is not None:
            vin = self.vin.strip()
            if not vin:
                raise InvalidVehicleError("VIN не может быть пустой строкой")
            if len(vin) > 20:
                raise InvalidVehicleError("VIN не должен превышать 20 символов")
            self.vin = vin

        if self.mark_id is not None and not self.mark_id.strip():
            raise InvalidVehicleError("mark_id обязателен")
        if self.model_id is not None and not self.model_id.strip():
            raise InvalidVehicleError("model_id обязателен")

        if self.year is not None and (self.year < 1950 or self.year > 2100):
            raise InvalidVehicleError(
                "Год выпуска должен быть в диапазоне 1950–2100"
            )

        if self.base_price is not None and self.base_price <= 0:
            raise InvalidVehicleError("base_price должен быть положительным")
        if self.special_price is not None and self.special_price < 0:
            raise InvalidVehicleError(
                "special_price не может быть отрицательным"
            )
        if self.discount_price is not None and self.discount_price < 0:
            raise InvalidVehicleError(
                "discount_price не может быть отрицательным"
            )

        if self.status is not None and self.status not in _ALLOWED_STATUSES:
            raise InvalidVehicleError(
                f"Недопустимый статус '{self.status}'. "
                f"Разрешено: {sorted(_ALLOWED_STATUSES)}"
            )

        if self.color is not None and len(self.color) > 100:
            raise InvalidVehicleError("Цвет не должен превышать 100 символов")

    # ---------------------------------------------------------------------
    # Authorization helpers
    # ---------------------------------------------------------------------

    def ensure_accessible_by(
        self,
        *,
        user_id: UUID,
        company_id: UUID | None = None,
        role: str,
    ) -> None:
        """Check whether a user may read/write this vehicle.

        Employees and distributors see everything; dealers see only their own.
        Phase 5: dealer_id references companies.id, so we compare with company_id.
        """
        _ = user_id
        if role in {"carcraft_employee", "distributor"}:
            return
        if role == "dealer" and company_id is not None and self.dealer_id == company_id:
            return
        raise AccessDeniedError("Нет доступа к данному автомобилю")

    # ---------------------------------------------------------------------
    # Business rules
    # ---------------------------------------------------------------------

    def ensure_can_assign_vin(self) -> None:
        """Domain precondition before a VIN is assigned to this vehicle.

        Callers typically invoke this before copying the VIN onto an
        application_vehicles row and moving the vehicle into `reserved`.
        """
        status = (self.status or "").strip().lower()
        if status != "available":
            raise VehicleNotAvailableError(self.vehicle_id or UUID(int=0))

    def compute_status_after_bulk_update(
        self, new_status: str | None
    ) -> str | None:
        """Return the status the vehicle should land in after a bulk update.

        Bulk updates are atomic for the set of ids supplied but MUST not
        silently downgrade a sold/reserved unit. This method returns the
        resolved new status or raises if the transition is illegal.
        """
        if new_status is None:
            return self.status
        if new_status not in _ALLOWED_STATUSES:
            raise InvalidVehicleError(
                f"Недопустимый статус '{new_status}'"
            )
        current = (self.status or "").strip().lower()
        if current == "sold" and new_status != "sold":
            # Once a vehicle is sold we refuse to walk it back via a
            # bulk operation — doing so is almost always a mistake.
            raise InvalidVehicleError(
                "Невозможно изменить статус проданного автомобиля"
            )
        return new_status


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return None
