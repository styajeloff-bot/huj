"""Dealer option domain entity — global reference of extra dealer services."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.errors import InvalidDealerOptionError


@dataclass
class DealerOption:
    """Aggregate root for a dealer option (winter tires, delivery, etc.)."""

    option_id: UUID | None
    name: str
    sort_order: int = 0
    is_active: bool = True
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DealerOption:
        return cls(
            option_id=data.get("id") or data.get("option_id"),
            name=data["name"],
            sort_order=int(data.get("sort_order") or 0),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def ensure_valid(self) -> None:
        """Validate invariants. Raises InvalidDealerOptionError."""
        name = (self.name or "").strip()
        if not name:
            raise InvalidDealerOptionError("Название опции обязательно")
        if len(name) > 255:
            raise InvalidDealerOptionError(
                "Название опции не должно превышать 255 символов"
            )
        self.name = name

        if self.sort_order < 0:
            raise InvalidDealerOptionError(
                "Порядок сортировки не может быть отрицательным"
            )

    def deactivate(self) -> None:
        self.is_active = False

    def to_persistence_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }
