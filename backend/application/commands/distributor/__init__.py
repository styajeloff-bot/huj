"""Distributor admin commands (B3 + Phase 7a G3)."""
from application.commands.distributor.add_vehicle_to_application import (
    AddVehicleToApplicationCommand,
    handle_add_vehicle_to_application,
)
from application.commands.distributor.assign_dealer import (
    AssignDealerCommand,
    handle_assign_dealer,
)
from application.commands.distributor.bulk_delete_distributor_vehicles import (
    BulkDeleteDistributorVehiclesCommand,
    handle_bulk_delete_distributor_vehicles,
)
from application.commands.distributor.bulk_import_distributor_vehicles import (
    BulkImportDistributorVehiclesCommand,
    handle_bulk_import_distributor_vehicles,
)
from application.commands.distributor.bulk_update_distributor_vehicles import (
    BulkUpdateDistributorVehiclesCommand,
    handle_bulk_update_distributor_vehicles,
)
from application.commands.distributor.create_distributor_vehicle import (
    CreateDistributorVehicleCommand,
    handle_create_distributor_vehicle,
)
from application.commands.distributor.delete_distributor_vehicle import (
    DeleteDistributorVehicleCommand,
    handle_delete_distributor_vehicle,
)
from application.commands.distributor.preview_import_distributor_vehicles import (
    PreviewImportDistributorVehiclesCommand,
    handle_preview_import_distributor_vehicles,
)
from application.commands.distributor.remove_application_vehicle import (
    RemoveApplicationVehicleCommand,
    handle_remove_application_vehicle,
)
from application.commands.distributor.replace_application_vehicle import (
    ReplaceApplicationVehicleCommand,
    handle_replace_application_vehicle,
)
from application.commands.distributor.update_dealer_status import (
    UpdateDealerStatusCommand,
    handle_update_dealer_status,
)
from application.commands.distributor.update_distributor_vehicle import (
    UpdateDistributorVehicleCommand,
    handle_update_distributor_vehicle,
)

__all__ = [
    "AddVehicleToApplicationCommand",
    "AssignDealerCommand",
    "BulkDeleteDistributorVehiclesCommand",
    "BulkImportDistributorVehiclesCommand",
    "BulkUpdateDistributorVehiclesCommand",
    "CreateDistributorVehicleCommand",
    "DeleteDistributorVehicleCommand",
    "PreviewImportDistributorVehiclesCommand",
    "RemoveApplicationVehicleCommand",
    "ReplaceApplicationVehicleCommand",
    "UpdateDealerStatusCommand",
    "UpdateDistributorVehicleCommand",
    "handle_add_vehicle_to_application",
    "handle_assign_dealer",
    "handle_bulk_delete_distributor_vehicles",
    "handle_bulk_import_distributor_vehicles",
    "handle_bulk_update_distributor_vehicles",
    "handle_create_distributor_vehicle",
    "handle_delete_distributor_vehicle",
    "handle_preview_import_distributor_vehicles",
    "handle_remove_application_vehicle",
    "handle_replace_application_vehicle",
    "handle_update_dealer_status",
    "handle_update_distributor_vehicle",
]
