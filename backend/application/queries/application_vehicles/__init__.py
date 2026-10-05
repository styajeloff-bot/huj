"""Application vehicles admin queries."""

from application.queries.application_vehicles.employees import (
    SearchApplicationVehicleEmployeesQuery,
    handle_search_application_vehicle_employees,
)
from application.queries.application_vehicles.list_available_vins import (
    ListAvailableVinsQuery,
    handle_list_available_vins,
)

__all__ = [
    "ListAvailableVinsQuery",
    "SearchApplicationVehicleEmployeesQuery",
    "handle_list_available_vins",
    "handle_search_application_vehicle_employees",
]
