"""Dealer group domain entity — distributor-owned dealer company groups."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from domain.errors import InvalidDealerGroupError


@dataclass
class DealerGroup:
    """Aggregate root for support targeting by distributor dealer companies."""

    group_id: UUID | None
    name: str
    distributor_company_id: UUID | None
    description: str | None = None
    is_active: bool = True
    dealer_company_ids: list[UUID] = field(default_factory=list)
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DealerGroup:
        dealers_raw = data.get("dealers") or []
        dealer_company_ids: list[UUID] = list(
            data.get("dealer_company_ids")
            or data.get("dealer_ids")
            or []
        )
        if not dealer_company_ids and dealers_raw:
            dealer_company_ids = [
                dealer["id"]
                for dealer in dealers_raw
                if dealer and dealer.get("id") is not None
            ]
        return cls(
            group_id=data.get("id") or data.get("group_id"),
            name=data["name"],
            distributor_company_id=(
                data.get("distributor_company_id")
                or data.get("distributor_id")
            ),
            description=_normalize_optional_text(data.get("description")),
            is_active=bool(data.get("is_active", True)),
            dealer_company_ids=dealer_company_ids,
            created_by=data.get("created_by"),
            updated_by=data.get("updated_by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def ensure_valid(self) -> None:
        name = (self.name or "").strip()
        if not name:
            raise InvalidDealerGroupError("Название группы обязательно")
        self.name = name

        if self.distributor_company_id is None:
            raise InvalidDealerGroupError("Дистрибьютор обязателен")

        if self.description is not None:
            self.description = self.description.strip() or None

        self.dealer_company_ids = list(dict.fromkeys(self.dealer_company_ids))
        if self.is_active and not self.dealer_company_ids:
            raise InvalidDealerGroupError("В группе должен быть минимум один дилер")


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
