"""Support-program queries."""
from application.queries.support.get_dealer_group import (
    GetDealerGroupQuery,
    handle_get_dealer_group,
)
from application.queries.support.get_support_program import (
    GetSupportProgramQuery,
    handle_get_support_program,
)
from application.queries.support.list_dealer_groups import (
    ListDealerGroupsQuery,
    handle_list_dealer_groups,
)
from application.queries.support.list_organization_support_programs import (
    ListOrganizationSupportProgramsQuery,
    handle_list_organization_support_programs,
)
from application.queries.support.list_support_programs import (
    ListSupportProgramsQuery,
    handle_list_support_programs,
)

__all__ = [
    "GetDealerGroupQuery",
    "GetSupportProgramQuery",
    "ListDealerGroupsQuery",
    "ListOrganizationSupportProgramsQuery",
    "ListSupportProgramsQuery",
    "handle_get_dealer_group",
    "handle_get_support_program",
    "handle_list_dealer_groups",
    "handle_list_organization_support_programs",
    "handle_list_support_programs",
]
