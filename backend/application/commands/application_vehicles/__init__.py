"""Admin commands for assigning vehicles / VINs to application_vehicles."""

from application.commands.application_vehicles.assign_dealer import (
    AssignApplicationVehicleDealerCommand,
    handle_assign_application_vehicle_dealer,
)
from application.commands.application_vehicles.assign_employees import (
    AssignApplicationVehicleEmployeesCommand,
    handle_assign_application_vehicle_employees,
)
from application.commands.application_vehicles.assign_vehicle import (
    AssignVehicleCommand,
    handle_assign_vehicle,
)
from application.commands.application_vehicles.assign_vin import (
    AssignVinCommand,
    handle_assign_vin,
)
from application.commands.application_vehicles.dealer_action import (
    DealerVehicleActionCommand,
    handle_dealer_vehicle_action,
)

__all__ = [
    "AssignApplicationVehicleDealerCommand",
    "AssignApplicationVehicleEmployeesCommand",
    "AssignVehicleCommand",
    "AssignVinCommand",
    "DealerVehicleActionCommand",
    "handle_assign_application_vehicle_dealer",
    "handle_assign_application_vehicle_employees",
    "handle_assign_vehicle",
    "handle_assign_vin",
    "handle_dealer_vehicle_action",
]
