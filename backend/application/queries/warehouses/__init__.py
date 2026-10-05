"""Warehouse admin queries."""
from application.queries.warehouses.get_warehouse import (
    GetWarehouseQuery,
    handle_get_warehouse,
)
from application.queries.warehouses.list_access_rules import (
    ListAccessRulesQuery,
    handle_list_access_rules,
)
from application.queries.warehouses.list_warehouse_brands import (
    ListWarehouseBrandsQuery,
    handle_list_warehouse_brands,
)
from application.queries.warehouses.list_warehouse_vehicles import (
    ListWarehouseVehiclesQuery,
    handle_list_warehouse_vehicles,
)
from application.queries.warehouses.list_warehouses import (
    ListWarehousesQuery,
    handle_list_warehouses,
)

__all__ = [
    "GetWarehouseQuery",
    "ListAccessRulesQuery",
    "ListWarehouseBrandsQuery",
    "ListWarehouseVehiclesQuery",
    "ListWarehousesQuery",
    "handle_get_warehouse",
    "handle_list_access_rules",
    "handle_list_warehouse_brands",
    "handle_list_warehouse_vehicles",
    "handle_list_warehouses",
]
