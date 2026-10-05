"""Queries for LeasingCompanyApplication (LCA) list and detail."""
from application.queries.leasing_company_applications.get_lca import (
    GetLcaQuery,
    handle_get_lca,
)
from application.queries.leasing_company_applications.list_lca import (
    ListLcaQuery,
    handle_list_lca,
)

__all__ = [
    "GetLcaQuery",
    "ListLcaQuery",
    "handle_get_lca",
    "handle_list_lca",
]
