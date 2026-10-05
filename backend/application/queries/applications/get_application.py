"""Get a single leasing application with full detail + joined resources."""

from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.calculator.calculate import (
    compute_canonical_application_calculation,
)
from application.permissions import (
    ensure_application_visible_to,
    get_company_permissions,
)
from application.queries.applications.dealer_distribution import (
    build_dealer_distribution,
)
from application.queries.applications.dealer_item_scope import (
    applications_with_hidden_items,
    redact_mixed_application_financials,
    resolve_actor_item_dealer_filter,
    scope_mixed_application_calculation,
)
from application.queries.applications.item_projection import (
    group_application_items,
)
from application.services.questionnaire_delivery import project_for_leasing_company
from domain.application_sources import SOURCE_VIEW_ROLES
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationNotOwnedError,
    LeasingCompanyBindingNotConfiguredError,
)
from infrastructure.repositories import (
    application_assignment_repository as assignment_repo,
)
from infrastructure.repositories import (
    application_documents_repository as application_documents_repo,
)
from infrastructure.repositories import application_repository as repo
from infrastructure.repositories import (
    application_vehicle_assignment_repository as vehicle_assignment_repo,
)
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import documents_repository as docs_repo

logger = logging.getLogger("carcraft-backend")


@dataclass
class ApplicationAccessQuery:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


@dataclass
class GetApplicationQuery(ApplicationAccessQuery):
    pass


async def get_authorized_application(
    query: ApplicationAccessQuery, session: AsyncSession
) -> tuple[dict[str, Any], list[UUID] | None]:
    """Load an application and apply the detail endpoint's access rules."""
    app_dict = await repo.get_by_id(session, query.application_id)
    if app_dict is None:
        raise ApplicationNotFoundError(query.application_id)
    # Fine-grained permission: company-linked roles need can_view_applications.
    if query.actor_role not in {
        "carcraft_employee",
        "distributor",
        "leasing_company",
        "external_api",
    }:
        perms = await get_company_permissions(
            session, query.actor_id, query.actor_company_id
        )
        if (
            not perms.get("can_view_applications")
            and app_dict.get("created_by") != query.actor_id
        ):
            raise ApplicationNotOwnedError()

    try:
        await ensure_application_visible_to(
            session,
            application=app_dict,
            user_id=query.actor_id,
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            actor_leasing_company_id=query.actor_leasing_company_id,
        )
    except ApplicationNotOwnedError:
        logger.warning(
            "get_application access denied "
            "application_id=%s app.company_id=%s "
            "app.selected_lcs=%s actor_id=%s actor_role=%s "
            "actor_company_id=%s actor_lc_id=%s",
            query.application_id,
            app_dict.get("company_id"),
            app_dict.get("selected_leasing_companies"),
            query.actor_id,
            query.actor_role,
            query.actor_company_id,
            query.actor_leasing_company_id,
        )
        if query.actor_role == "distributor":
            raise ApplicationNotFoundError(query.application_id) from None
        raise

    item_dealer_filter = await resolve_actor_item_dealer_filter(
        session,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    if item_dealer_filter is not None:
        scoped_app_dict = await repo.get_by_id(
            session,
            query.application_id,
            dealer_filter=item_dealer_filter,
            distributor_company_id=query.actor_company_id if query.actor_role == "distributor" else None,
        )
        if scoped_app_dict is None:
            raise ApplicationNotFoundError(query.application_id)
        app_dict = scoped_app_dict

    return app_dict, item_dealer_filter


async def handle_get_application(  # noqa: PLR0912, PLR0915
    query: GetApplicationQuery, session: AsyncSession
) -> dict[str, Any]:
    app_dict, item_dealer_filter = await get_authorized_application(query, session)

    vehicles = await repo.list_application_vehicles_with_catalog(
        session,
        query.application_id,
        dealer_filter=item_dealer_filter,
        distributor_company_id=query.actor_company_id if query.actor_role == "distributor" else None,
    )
    vehicle_assignments = await vehicle_assignment_repo.list_assignment_details(
        session,
        [vehicle["id"] for vehicle in vehicles],
        actor_dealer_company_id=query.actor_company_id if query.actor_role == "dealer" else None,
    )
    for vehicle in vehicles:
        if vehicle.get("can_manage_whole_vehicle", True):
            vehicle.update(vehicle_assignments.get(vehicle["id"], {}))
        else:
            assignment = vehicle_assignments.get(vehicle["id"], {})
            vehicle["dealer_company_id"] = assignment.get("dealer_company_id")
            vehicle["assigned_dealer"] = assignment.get("assigned_dealer")

    special_equipment_rows = await repo.list_application_special_equipment_item_rows(
        session,
        [query.application_id],
        dealer_filter=item_dealer_filter,
    )
    if not vehicles and special_equipment_rows:
        has_new_vehicles = (
            await repo.ensure_application_vehicles_for_special_equipment(
                session,
                query.application_id,
            )
        )
        if has_new_vehicles:
            vehicles = await repo.list_application_vehicles_with_catalog(
                session,
                query.application_id,
                dealer_filter=item_dealer_filter,
                distributor_company_id=query.actor_company_id if query.actor_role == "distributor" else None,
            )
            vehicle_assignments = await vehicle_assignment_repo.list_assignment_details(
                session,
                [vehicle["id"] for vehicle in vehicles],
                actor_dealer_company_id=query.actor_company_id if query.actor_role == "dealer" else None,
            )
            for vehicle in vehicles:
                if vehicle.get("can_manage_whole_vehicle", True):
                    vehicle.update(vehicle_assignments.get(vehicle["id"], {}))
                else:
                    assignment = vehicle_assignments.get(vehicle["id"], {})
                    vehicle["dealer_company_id"] = assignment.get("dealer_company_id")
                    vehicle["assigned_dealer"] = assignment.get("assigned_dealer")
    hidden_item_application_ids: set[UUID] = set()
    if item_dealer_filter is not None:
        unscoped_vehicles = await repo.list_application_vehicles_with_catalog(
            session,
            query.application_id,
        )
        unscoped_special_equipment_rows = (
            await repo.list_application_special_equipment_item_rows(
                session,
                [query.application_id],
            )
        )
        hidden_item_application_ids = applications_with_hidden_items(
            vehicle_rows=unscoped_vehicles,
            visible_vehicle_rows=vehicles,
            special_equipment_rows=unscoped_special_equipment_rows,
            visible_special_equipment_rows=special_equipment_rows,
        )
    is_mixed_application = query.application_id in hidden_item_application_ids
    items = group_application_items(
        [query.application_id],
        vehicle_rows=vehicles,
        special_equipment_rows=special_equipment_rows,
        actor_role=query.actor_role,
    )[query.application_id]
    allowed_vehicle_ids = {
        vehicle["vehicle_id"]
        for vehicle in vehicles
        if vehicle.get("vehicle_id") is not None
    }
    questionnaire = await repo.get_questionnaire(session, query.application_id)
    calculation = await repo.get_calculation(session, query.application_id)
    if is_mixed_application:
        calculation = scope_mixed_application_calculation(
            calculation,
            allowed_vehicle_ids={vehicle["vehicle_id"] for vehicle in vehicles
                                 if vehicle.get("vehicle_id") is not None
                                 and vehicle.get("can_manage_whole_vehicle", True)},
            scoped_total=app_dict.get("total_items_price"),
        )
    vehicle_calcs = await repo.list_vehicle_calculations(
        session,
        query.application_id,
        dealer_filter=item_dealer_filter,
        distributor_company_id=query.actor_company_id if query.actor_role == "distributor" else None,
    )
    lc_links = await repo.list_lc_links(session, query.application_id)
    display_statuses = await application_documents_repo.list_lc_display_statuses(
        session, application_id=query.application_id
    )
    for link in lc_links:
        leasing_company_id = link.get("leasing_company_id")
        if leasing_company_id in display_statuses:
            link["display_status"] = display_statuses[leasing_company_id]
    comments = await repo.list_comments(session, query.application_id)

    lc_ids = app_dict.get("selected_leasing_companies") or []
    companies_info = await repo.list_companies_info(session, lc_ids) if lc_ids else []

    owner = await _resolve_owner(session, app_dict)
    company = await _resolve_company(session, app_dict)

    # Fallback tax_system from the stored company profile so the
    # checkout step 4 can pre-select the correct option without asking
    # the user. We inject a transient flag ``tax_system_auto`` so the
    # frontend knows it can show an "determined by FNS data" badge.
    if questionnaire is None:
        questionnaire = {}
    company_tax = (company or {}).get("tax_system")
    if company_tax and not questionnaire.get("tax_system"):
        questionnaire["tax_system"] = company_tax
        questionnaire["tax_system_auto"] = True

    result = dict(app_dict)
    if query.actor_role not in SOURCE_VIEW_ROLES:
        result.pop("source_type", None)
    if is_mixed_application:
        redact_mixed_application_financials(result)
        if result.get("vehicle_id") not in allowed_vehicle_ids:
            result["vehicle_id"] = None
    result["vehicles"] = vehicles
    result["items"] = items
    distribution = await build_dealer_distribution(
        session, vehicle_rows=vehicles, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    result["dealer_distribution"] = distribution.get(query.application_id, [])
    questionnaire.pop("field_sources", None)
    questionnaire.pop("people_identity_map", None)
    if query.actor_role == "leasing_company":
        if query.actor_leasing_company_id is None:
            raise LeasingCompanyBindingNotConfiguredError()
        questionnaire = await project_for_leasing_company(
            session, {**questionnaire, "application_id": query.application_id},
            query.actor_leasing_company_id,
        )
    result["questionnaire"] = questionnaire
    result["calculation"] = calculation
    result["vehicle_calculations"] = vehicle_calcs
    result["leasing_company_applications"] = lc_links
    result["comments"] = comments
    result["selected_companies_info"] = companies_info
    if (
        (app_dict.get("monthly_payment") is None or app_dict.get("down_payment") is None)
        and app_dict.get("total_amount") is not None
        and app_dict.get("down_payment_percent") is not None
        and app_dict.get("lease_term_months") is not None
    ):
        fallback_calc = await compute_canonical_application_calculation(
            session,
            total_amount=app_dict.get("total_amount"),
            down_payment_percent=app_dict.get("down_payment_percent"),
            lease_term_months=app_dict.get("lease_term_months"),
        )
        if fallback_calc and not is_mixed_application:
            for k in (
                "down_payment",
                "monthly_payment",
                "total_cost",
                "markup",
                "rate",
                "total_interest",
                "buyout_amount",
                "vat_refund",
                "profit_tax_savings",
                "total_savings",
            ):
                result[k] = fallback_calc[k]
            if not result.get("calculation"):
                result["calculation"] = fallback_calc
    if owner:
        result.setdefault("name", owner.get("name"))
        result["phone"] = owner.get("phone")
        if not result.get("email"):
            result["email"] = owner.get("email")
    if not result.get("phone"):
        result["phone"] = (company or {}).get("phone")
    result["owner"] = owner
    result["company"] = company
    result.update(
        await assignment_repo.get_assignment_details(
            session,
            application_id=query.application_id,
            actor_company_id=query.actor_company_id,
        )
    )
    result["can_assign_dealer"] = any(item["can_assign_dealer"] for item in result["dealer_distribution"])
    if query.actor_role == "dealer" and any(not row.get("can_manage_whole_vehicle", True) for row in vehicles):
        for field in ("assigned_dealer", "assigned_dealer_group", "primary_employee", "additional_employee",
                      "dealer_assigned_by", "employees_assigned_by"):
            result[field] = None

    raw_deal_docs = result.get("deal_documents") or []
    enriched_docs: list[dict[str, Any]] = []
    for item in raw_deal_docs:
        file_id = item.get("file_id")
        doc_meta = None
        if file_id:
            with contextlib.suppress(ValueError, TypeError):
                doc_meta = await docs_repo.get_by_id(session, UUID(str(file_id)))
        enriched_docs.append({
            "file_id": str(file_id) if file_id else None,
            "document_type": item.get("document_type"),
            "file_name": doc_meta.get("file_name") if doc_meta else None,
            "file_size": doc_meta.get("file_size") if doc_meta else None,
            "download_url": f"/api/v1/documents/{file_id}/content" if file_id else None,
        })
    result["deal_documents"] = enriched_docs
    result["documents"] = enriched_docs

    return result


async def _resolve_owner(
    session: AsyncSession, app_dict: dict[str, Any]
) -> dict[str, Any] | None:
    created_by = app_dict.get("created_by")
    if not created_by:
        return None
    return cast(
        "dict[str, Any] | None", await auth_repo.find_user_by_id(session, created_by)
    )


async def _resolve_company(
    session: AsyncSession, app_dict: dict[str, Any]
) -> dict[str, Any] | None:
    company_id = app_dict.get("company_id")
    if not company_id:
        return None
    company = await company_repo.get_company_by_id(session, company_id)
    if company is None:
        return None
    # Only expose display-friendly fields — the modal renders a summary card.
    return {
        "id": company.get("id"),
        "name": company.get("name"),
        "inn": company.get("inn"),
        "kpp": company.get("kpp"),
        "ogrn": company.get("ogrn"),
        "company_type": company.get("company_type"),
        "phone": company.get("phone"),
        "email": company.get("email"),
        "legal_address": company.get("legal_address"),
        "actual_address": company.get("actual_address"),
        "tax_system": company.get("tax_system"),
    }
