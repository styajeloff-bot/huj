"""Leasing application commands (Phase 3)."""

from application.commands.applications.assign_employees import (
    AssignApplicationEmployeesCommand,
    handle_assign_application_employees,
)
from application.commands.applications.attach_documents import (
    AttachDocumentsToApplicationCommand,
    handle_attach_documents_to_application,
)
from application.commands.applications.change_status import (
    ChangeStatusCommand,
    handle_change_status,
)
from application.commands.applications.create_application import (
    ApplicationVehiclePayload,
    CreateApplicationCommand,
    handle_create_application,
)
from application.commands.applications.create_draft import (
    ApplicationSpecialEquipmentPayload,
    CreateDraftCommand,
    handle_create_draft,
)
from application.commands.applications.update_additional_options import (
    UpdateAdditionalOptionsCommand,
    handle_update_additional_options,
)
from application.commands.applications.update_company import (
    UpdateCompanyCommand,
    handle_update_company,
)
from application.commands.applications.update_conditions import (
    UpdateConditionsCommand,
    handle_update_conditions,
)
from application.commands.applications.update_items import (
    ApplicationItemUpdate,
    UpdateApplicationItemsCommand,
    handle_update_application_items,
)
from application.commands.applications.update_leasing_companies import (
    UpdateLeasingCompaniesCommand,
    handle_update_leasing_companies,
)
from application.commands.applications.update_questionnaire import (
    UpdateQuestionnaireCommand,
    handle_update_questionnaire,
)
from application.commands.applications.update_vehicles import (
    UpdateVehiclesCommand,
    handle_update_vehicles,
)

__all__ = [
    "ApplicationItemUpdate",
    "ApplicationSpecialEquipmentPayload",
    "ApplicationVehiclePayload",
    "AssignApplicationEmployeesCommand",
    "AttachDocumentsToApplicationCommand",
    "ChangeStatusCommand",
    "CreateApplicationCommand",
    "CreateDraftCommand",
    "UpdateAdditionalOptionsCommand",
    "UpdateApplicationItemsCommand",
    "UpdateCompanyCommand",
    "UpdateConditionsCommand",
    "UpdateLeasingCompaniesCommand",
    "UpdateQuestionnaireCommand",
    "UpdateVehiclesCommand",
    "handle_assign_application_employees",
    "handle_attach_documents_to_application",
    "handle_change_status",
    "handle_create_application",
    "handle_create_draft",
    "handle_update_additional_options",
    "handle_update_application_items",
    "handle_update_company",
    "handle_update_conditions",
    "handle_update_leasing_companies",
    "handle_update_questionnaire",
    "handle_update_vehicles",
]
