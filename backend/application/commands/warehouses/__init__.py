"""Warehouse admin commands."""
from application.commands.warehouses.add_vehicle_to_warehouse import (
    AddVehicleToWarehouseCommand,
    handle_add_vehicle_to_warehouse,
)
from application.commands.warehouses.bind_vehicles_by_mark import (
    BindVehiclesByMarkCommand,
    handle_bind_vehicles_by_mark,
)
from application.commands.warehouses.bulk_add_vehicles_to_warehouse import (
    BulkAddVehiclesToWarehouseCommand,
    handle_bulk_add_vehicles_to_warehouse,
)
from application.commands.warehouses.cascade_delete_warehouse import (
    execute_warehouse_cascade_delete,
    get_warehouse_delete_preview,
    handle_cascade_delete_warehouse,
    handle_preview_warehouse_cascade_delete,
)
from application.commands.warehouses.create_access_rules import (
    CreateAccessRulesCommand,
    handle_create_access_rules,
)
from application.commands.warehouses.create_warehouse import (
    CreateWarehouseCommand,
    handle_create_warehouse,
)
from application.commands.warehouses.delete_access_rule import (
    DeleteAccessRuleCommand,
    handle_delete_access_rule,
)
from application.commands.warehouses.delete_warehouse import (
    DeleteWarehouseCommand,
    WarehouseDeleteBlockedError,
    handle_delete_warehouse,
    handle_delete_warehouse_integrity_fallback,
)
from application.commands.warehouses.remove_vehicle_from_warehouse import (
    RemoveVehicleFromWarehouseCommand,
    handle_remove_vehicle_from_warehouse,
)
from application.commands.warehouses.status_events import (
    WarehouseDeleteResult,
    WarehouseMutationResult,
    WarehouseStatusEvent,
    publish_warehouse_status_events,
)
from application.commands.warehouses.update_access_rule import (
    UpdateAccessRuleCommand,
    handle_update_access_rule,
)
from application.commands.warehouses.update_warehouse import (
    UpdateWarehouseCommand,
    handle_update_warehouse,
)

__all__ = [
    "AddVehicleToWarehouseCommand",
    "BindVehiclesByMarkCommand",
    "BulkAddVehiclesToWarehouseCommand",
    "CreateAccessRulesCommand",
    "CreateWarehouseCommand",
    "DeleteAccessRuleCommand",
    "DeleteWarehouseCommand",
    "RemoveVehicleFromWarehouseCommand",
    "UpdateAccessRuleCommand",
    "UpdateWarehouseCommand",
    "WarehouseDeleteBlockedError",
    "WarehouseDeleteResult",
    "WarehouseMutationResult",
    "WarehouseStatusEvent",
    "execute_warehouse_cascade_delete",
    "get_warehouse_delete_preview",
    "handle_add_vehicle_to_warehouse",
    "handle_bind_vehicles_by_mark",
    "handle_bulk_add_vehicles_to_warehouse",
    "handle_cascade_delete_warehouse",
    "handle_create_access_rules",
    "handle_create_warehouse",
    "handle_delete_access_rule",
    "handle_delete_warehouse",
    "handle_delete_warehouse_integrity_fallback",
    "handle_preview_warehouse_cascade_delete",
    "handle_remove_vehicle_from_warehouse",
    "handle_update_access_rule",
    "handle_update_warehouse",
    "publish_warehouse_status_events",
]
