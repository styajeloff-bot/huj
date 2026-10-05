"""Warehouse domain entity — physical storage location for vehicles."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from domain.errors import InvalidWarehouseError


@dataclass
class Warehouse:
    """Aggregate root for a dealer/distributor warehouse."""

    warehouse_id: UUID | None
    name: str
    owner_company_id: UUID
    owner_company_type: str
    address: str
    city_id: UUID | None = None
    brand_ids: list[UUID] = field(default_factory=list)
    category_id: UUID | None = None
    is_active: bool = True
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Warehouse:
        return cls(
            warehouse_id=data.get("id") or data.get("warehouse_id"),
            name=data["name"],
            owner_company_id=data["owner_company_id"],
            owner_company_type=data.get("owner_company_type", "dealer"),
            address=data["address"],
            city_id=data.get("city_id"),
            brand_ids=list(data.get("brand_ids", [])),
            category_id=data.get("category_id"),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def ensure_valid(self) -> None:
        """Validate invariants. Raises InvalidWarehouseError on failure."""
        name = (self.name or "").strip()
        if not name:
            raise InvalidWarehouseError("Название склада обязательно")
        if len(name) > 255:
            raise InvalidWarehouseError("Название склада не должно превышать 255 символов")
        self.name = name

        address = (self.address or "").strip()
        if not address:
            raise InvalidWarehouseError("Адрес склада обязателен")
        if len(address) > 500:
            raise InvalidWarehouseError("Адрес склада не должен превышать 500 символов")
        self.address = address

        if self.owner_company_type not in ("dealer", "distributor"):
            raise InvalidWarehouseError("Тип компании-владельца должен быть dealer или distributor")

    def to_persistence_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "owner_company_id": self.owner_company_id,
            "owner_company_type": self.owner_company_type,
            "address": self.address,
            "city_id": self.city_id,
            "brand_ids": self.brand_ids,
            "category_id": self.category_id,
            "is_active": self.is_active,
        }

