"""Admin companies queries (Phase 6 — F2)."""
from application.queries.admin_companies.change_history import (
    CompareCompanyChangeHistoryQuery,
    ListCompanyChangeHistoryQuery,
    handle_compare_company_change_history,
    handle_list_company_change_history,
)
from application.queries.admin_companies.distributor_brands import (
    GetDistributorBrandsQuery,
    GetDistributorInventoryBrandsQuery,
    handle_get_distributor_brands,
    handle_get_distributor_inventory_brands,
)
from application.queries.admin_companies.list_contractor_links import (
    ListContractorLinksQuery,
    handle_list_contractor_links,
)
from application.queries.admin_companies.list_contractors import (
    ListContractorsQuery,
    handle_list_contractors,
)
from application.queries.admin_companies.list_dealers_all import (
    ListDealersAllQuery,
    handle_list_dealers_all,
)
from application.queries.admin_companies.list_distributor_dealers import (
    ListDistributorDealersQuery,
    handle_list_distributor_dealers,
)
from application.queries.admin_companies.list_distributors_all import (
    ListDistributorsAllQuery,
    handle_list_distributors_all,
)
from application.queries.admin_companies.list_leasing_companies_all import (
    ListLeasingCompaniesAllQuery,
    handle_list_leasing_companies_all,
)

__all__ = [
    "CompareCompanyChangeHistoryQuery",
    "GetDistributorBrandsQuery",
    "GetDistributorInventoryBrandsQuery",
    "ListCompanyChangeHistoryQuery",
    "ListContractorLinksQuery",
    "ListContractorsQuery",
    "ListDealersAllQuery",
    "ListDistributorDealersQuery",
    "ListDistributorsAllQuery",
    "ListLeasingCompaniesAllQuery",
    "handle_compare_company_change_history",
    "handle_get_distributor_brands",
    "handle_get_distributor_inventory_brands",
    "handle_list_company_change_history",
    "handle_list_contractor_links",
    "handle_list_contractors",
    "handle_list_dealers_all",
    "handle_list_distributor_dealers",
    "handle_list_distributors_all",
    "handle_list_leasing_companies_all",
]
