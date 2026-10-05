"""Warehouse access rule domain entity."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.errors import InvalidWarehouseError
from domain.values import WarehouseAccessType


@dataclass
class WarehouseAccessRule:
    """Access rule granting a dealer or distributor access to a warehouse."""

    id: UUID | None
    warehouse_id: UUID
    target_type: str
    target_id: UUID
    warehouse_access_type: WarehouseAccessType
    site_id: UUID | None = None
    brand_id: UUID | None = None
    source_group_id: UUID | None = None
    is_visible: bool = True
    can_create_application: bool = True
    is_active: bool = True
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WarehouseAccessRule:
        return cls(
            id=data.get("id"),
            warehouse_id=data["warehouse_id"],
            target_type=data["target_type"],
            target_id=data["target_id"],
            warehouse_access_type=WarehouseAccessType(data["warehouse_access_type"]),
            site_id=data.get("site_id"),
            brand_id=data.get("brand_id"),
            source_group_id=data.get("source_group_id"),
            is_visible=bool(data.get("is_visible", True)),
            can_create_application=bool(data.get("can_create_application", True)),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def ensure_valid(self) -> None:
        if self.target_type not in ("dealer", "distributor"):
            raise InvalidWarehouseError("Тип участника должен быть dealer или distributor")
        if self.warehouse_access_type not in (
            WarehouseAccessType.A,
            WarehouseAccessType.B,
            WarehouseAccessType.C,
        ):
            raise InvalidWarehouseError("Тип доступа должен быть A, B или C")
