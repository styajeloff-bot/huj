"""Distributor admin queries (B3 + Phase 7a G3)."""
from application.queries.distributor.export_distributor_vehicles import (
    ExportDistributorVehiclesQuery,
    handle_export_distributor_vehicles,
)
from application.queries.distributor.get_distributor_analytics import (
    GetDistributorAnalyticsQuery,
    handle_get_distributor_analytics,
)
from application.queries.distributor.get_distributor_profile import (
    GetDistributorProfileQuery,
    handle_get_distributor_profile,
)
from application.queries.distributor.get_distributor_vehicle_history import (
    GetDistributorVehicleHistoryQuery,
    handle_get_distributor_vehicle_history,
)
from application.queries.distributor.get_distributor_vehicles_by_ids import (
    GetDistributorVehiclesByIdsQuery,
    handle_get_distributor_vehicles_by_ids,
)
from application.queries.distributor.get_distributor_warehouse_analytics import (
    GetDistributorWarehouseAnalyticsQuery,
    handle_get_distributor_warehouse_analytics,
)
from application.queries.distributor.get_model_orders_stats import (
    GetModelOrdersStatsQuery,
    handle_get_model_orders_stats,
)
from application.queries.distributor.list_application_vehicles import (
    ListApplicationVehiclesQuery,
    handle_list_application_vehicles,
)
from application.queries.distributor.list_available_vehicles_for_app import (
    ListAvailableVehiclesForAppQuery,
    handle_list_available_vehicles_for_app,
)
from application.queries.distributor.list_distributor_applications import (
    ListDistributorApplicationsQuery,
    handle_list_distributor_applications,
)
from application.queries.distributor.list_distributor_applications_grouped import (
    ListDistributorApplicationsGroupedQuery,
    handle_list_distributor_applications_grouped,
)
from application.queries.distributor.list_distributor_brands import (
    ListDistributorBrandsQuery,
    handle_list_distributor_brands,
)
from application.queries.distributor.list_distributor_dealers import (
    ListDistributorDealersQuery,
    handle_list_distributor_dealers,
)
from application.queries.distributor.list_distributor_support_programs import (
    ListDistributorSupportProgramsQuery,
    handle_list_distributor_support_programs,
)
from application.queries.distributor.list_distributor_vehicles import (
    ListDistributorVehiclesQuery,
    handle_list_distributor_vehicles,
)

__all__ = [
    "ExportDistributorVehiclesQuery",
    "GetDistributorAnalyticsQuery",
    "GetDistributorProfileQuery",
    "GetDistributorVehicleHistoryQuery",
    "GetDistributorVehiclesByIdsQuery",
    "GetDistributorWarehouseAnalyticsQuery",
    "GetModelOrdersStatsQuery",
    "ListApplicationVehiclesQuery",
    "ListAvailableVehiclesForAppQuery",
    "ListDistributorApplicationsGroupedQuery",
    "ListDistributorApplicationsQuery",
    "ListDistributorBrandsQuery",
    "ListDistributorDealersQuery",
    "ListDistributorSupportProgramsQuery",
    "ListDistributorVehiclesQuery",
    "handle_export_distributor_vehicles",
    "handle_get_distributor_analytics",
    "handle_get_distributor_profile",
    "handle_get_distributor_vehicle_history",
    "handle_get_distributor_vehicles_by_ids",
    "handle_get_distributor_warehouse_analytics",
    "handle_get_model_orders_stats",
    "handle_list_application_vehicles",
    "handle_list_available_vehicles_for_app",
    "handle_list_distributor_applications",
    "handle_list_distributor_applications_grouped",
    "handle_list_distributor_brands",
    "handle_list_distributor_dealers",
    "handle_list_distributor_support_programs",
    "handle_list_distributor_vehicles",
]
