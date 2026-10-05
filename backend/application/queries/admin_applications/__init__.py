"""Admin applications queries (Phase 6 — F2)."""
from application.queries.admin_applications.get_admin_application_detail import (
    GetAdminApplicationDetailQuery,
    handle_get_admin_application_detail,
)
from application.queries.admin_applications.list_admin_applications import (
    ListAdminApplicationsQuery,
    handle_list_admin_applications,
)
from application.queries.admin_applications.list_application_vehicles import (
    ListAdminApplicationVehiclesQuery,
    handle_list_admin_application_vehicles,
)
from application.queries.admin_applications.list_price_changes import (
    ListApplicationPriceChangesQuery,
    handle_list_application_price_changes,
)

__all__ = [
    "GetAdminApplicationDetailQuery",
    "ListAdminApplicationVehiclesQuery",
    "ListAdminApplicationsQuery",
    "ListApplicationPriceChangesQuery",
    "handle_get_admin_application_detail",
    "handle_list_admin_application_vehicles",
    "handle_list_admin_applications",
    "handle_list_application_price_changes",
]
