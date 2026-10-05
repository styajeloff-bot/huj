"""Scoped read queries for warehouse vehicle transfers."""

from application.queries.warehouse_transfers.list_available_warehouses import (
    ListAvailableWarehousesQuery,
    handle_list_available_warehouses,
)
from application.queries.warehouse_transfers.list_source_vehicles import (
    ListSourceVehiclesQuery,
    handle_list_source_vehicles,
)

__all__ = [
    "ListAvailableWarehousesQuery",
    "ListSourceVehiclesQuery",
    "handle_list_available_warehouses",
    "handle_list_source_vehicles",
]
