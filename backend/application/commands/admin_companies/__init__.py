"""Admin companies commands (Phase 6 — F2)."""
from application.commands.admin_companies.contractors import (
    CreateContractorCommand,
    CreateContractorLinkCommand,
    DeleteContractorLinkCommand,
    ImportContractorLinksCommand,
    SetContractorLeasingCompaniesCommand,
    SetLeasingCompanyContractorsCommand,
    UpdateContractorCommand,
    handle_create_contractor,
    handle_create_contractor_link,
    handle_delete_contractor_link,
    handle_import_contractor_links,
    handle_list_contractor_leasing_company_links,
    handle_list_leasing_company_contractor_links,
    handle_set_contractor_leasing_companies,
    handle_set_leasing_company_contractors,
    handle_update_contractor,
)
from application.commands.admin_companies.create_company import (
    CreateCompanyCommand,
    handle_create_company,
)
from application.commands.admin_companies.distributor_brands import (
    SetDistributorBrandsCommand,
    handle_set_distributor_brands,
)
from application.commands.admin_companies.link_distributor_dealer import (
    LinkDistributorDealerCommand,
    handle_link_distributor_dealer,
)
from application.commands.admin_companies.unlink_distributor_dealer import (
    UnlinkDistributorDealerCommand,
    handle_unlink_distributor_dealer,
)
from application.commands.admin_companies.update_company import (
    AdminUpdateCompanyCommand,
    handle_admin_update_company,
)

__all__ = [
    "AdminUpdateCompanyCommand",
    "CreateCompanyCommand",
    "CreateContractorCommand",
    "CreateContractorLinkCommand",
    "DeleteContractorLinkCommand",
    "ImportContractorLinksCommand",
    "LinkDistributorDealerCommand",
    "SetContractorLeasingCompaniesCommand",
    "SetDistributorBrandsCommand",
    "SetLeasingCompanyContractorsCommand",
    "UnlinkDistributorDealerCommand",
    "UpdateContractorCommand",
    "handle_admin_update_company",
    "handle_create_company",
    "handle_create_contractor",
    "handle_create_contractor_link",
    "handle_delete_contractor_link",
    "handle_import_contractor_links",
    "handle_link_distributor_dealer",
    "handle_list_contractor_leasing_company_links",
    "handle_list_leasing_company_contractor_links",
    "handle_set_contractor_leasing_companies",
    "handle_set_distributor_brands",
    "handle_set_leasing_company_contractors",
    "handle_unlink_distributor_dealer",
    "handle_update_contractor",
]
