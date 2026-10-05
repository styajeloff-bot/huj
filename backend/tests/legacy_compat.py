"""Legacy test compatibility stubs to satisfy test fixtures and static checks."""
from __future__ import annotations

import uuid
from typing import Any

from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory as VehicleCategory,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark as Mark,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentModel as CarModel,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentModification as Modification,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct as Vehicle,
)


class VehicleWarehouse:
    """Compatibility stub for deleted vehicle_warehouses ORM table."""

    id: Any = None
    vehicle_id: Any = None
    warehouse_id: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "id") or self.id is None:
            self.id = kwargs.get("id", uuid.uuid4())


class FeaturedVehicle:
    """Compatibility stub for deleted featured_vehicles ORM table."""

    id: Any = None
    vehicle_id: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "id") or self.id is None:
            self.id = kwargs.get("id", uuid.uuid4())


class Generation:
    id: Any = None
    name: Any = None
    model_id: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "id") or self.id is None:
            self.id = kwargs.get("id", uuid.uuid4())


class Configuration:
    id: Any = None
    configuration_name: Any = None
    generation_id: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not hasattr(self, "id") or self.id is None:
            self.id = kwargs.get("id", uuid.uuid4())


__all__ = [
    "CarModel",
    "Configuration",
    "FeaturedVehicle",
    "Generation",
    "Mark",
    "Modification",
    "Vehicle",
    "VehicleCategory",
    "VehicleWarehouse",
]
