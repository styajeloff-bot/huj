"""Provider-neutral identifiers used by the unified commerce facade."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE = "_carcraft_vehicle_commerce_v1"


class CommerceItemType(StrEnum):
    """A bounded-context discriminator; IDs are never guessed across domains."""

    VEHICLE = "vehicle"
    SPECIAL_EQUIPMENT = "special_equipment"


@dataclass(frozen=True, slots=True)
class CommerceItemRef:
    """A typed reference to one sellable catalog unit."""

    type: CommerceItemType
    id: UUID

    def as_dict(self) -> dict[str, CommerceItemType | UUID]:
        return {"type": self.type, "id": self.id}


@dataclass(frozen=True, slots=True)
class CommerceOrderRef:
    """A typed order identifier; semantically distinct from a catalog item."""

    type: CommerceItemType
    id: UUID

    def as_dict(self) -> dict[str, CommerceItemType | UUID]:
        return {"type": self.type, "id": self.id}
