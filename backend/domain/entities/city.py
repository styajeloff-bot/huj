"""City domain entity — administrative reference for warehouse locations."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.errors import InvalidCityError


@dataclass
class City:
    """Aggregate root for a city used in warehouse addressing."""

    city_id: UUID | None
    name: str
    created_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> City:
        return cls(
            city_id=data.get("id") or data.get("city_id"),
            name=data["name"],
            created_at=data.get("created_at"),
        )

    def ensure_valid(self) -> None:
        """Validate invariants. Raises InvalidCityError on failure."""
        name = (self.name or "").strip()
        if not name:
            raise InvalidCityError("Название города обязательно")
        if len(name) > 255:
            raise InvalidCityError("Название города не должно превышать 255 символов")
        self.name = name
