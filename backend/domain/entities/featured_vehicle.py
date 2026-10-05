"""FeaturedVehicle domain entity — homepage curation.

Featured = a single car model that the storefront promotes on the homepage.
The DB enforces unique `model_id` (one featured row per model). This entity
encapsulates the business rules around uniqueness, ordering and toggling.
"""
from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from domain.errors import (
    FeaturedAlreadyExistsError,
    InvalidFeaturedReorderError,
)


@dataclass
class FeaturedVehicle:
    """Aggregate root for a single featured-model entry."""

    featured_id: UUID | None
    model_id: str
    position: int = 0
    is_active: bool | None = True
    created_by: UUID | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeaturedVehicle:
        return cls(
            featured_id=data.get("id") or data.get("featured_id"),
            model_id=str(data["model_id"]),
            position=int(data.get("position") or 0),
            is_active=data.get("is_active"),
            created_by=data.get("created_by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def ensure_unique_per_model(
        model_id: str, existing_model_ids: Iterable[str]
    ) -> None:
        """Raise FeaturedAlreadyExistsError if model_id is already featured."""
        if model_id in set(existing_model_ids):
            raise FeaturedAlreadyExistsError(model_id)

    @staticmethod
    def reorder_positions(
        ordered_ids: Sequence[UUID], known_ids: Iterable[UUID]
    ) -> list[tuple[UUID, int]]:
        """Build (id, position) pairs for an atomic reorder.

        Validates the payload against domain invariants:
        - non-empty
        - no duplicate ids
        - every id is currently featured

        Returns the list of `(featured_id, new_position)` tuples that the
        repository will persist atomically (1-based positions).
        """
        ids = list(ordered_ids)
        if not ids:
            raise InvalidFeaturedReorderError(
                "Список идентификаторов не может быть пустым"
            )
        if len(set(ids)) != len(ids):
            raise InvalidFeaturedReorderError(
                "В списке идентификаторов есть дубликаты"
            )
        known = set(known_ids)
        unknown = [fid for fid in ids if fid not in known]
        if unknown:
            raise InvalidFeaturedReorderError(
                f"Неизвестные идентификаторы избранного: {unknown}"
            )
        return [(fid, idx + 1) for idx, fid in enumerate(ids)]

    def toggle(self) -> None:
        """Flip the is_active flag."""
        self.is_active = not bool(self.is_active)
