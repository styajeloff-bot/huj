from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import (
    get_company_permissions,
    require_distributor_application_read,
)
from application.queries.applications.dealer_distribution import (
    build_dealer_distribution,
)
from application.queries.applications.dealer_item_scope import (
    applications_with_hidden_items,
    redact_mixed_application_financials,
    resolve_actor_item_dealer_filter,
)
from application.queries.applications.item_projection import (
    group_application_items,
)
from application.queries.fast_deals.merged import (
    APPLICATION_LIST_ROLES,
    KIND_FAST_DEAL,
    activity_key,
    merged_page,
    resolve_list_actor,
)
from domain.application_sources import SOURCE_VIEW_ROLES, source_filter_values
from infrastructure.repositories import application_repository as repo


@dataclass
class ListApplicationsQuery:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None
    include_authored_client_applications: bool = True
    status: str | None = None
    source_type: str | None = None
    search: str | None = None
    page: int = 1
    limit: int = 50
    # ``application`` / ``fast_deal``: which kind of rows the shared list returns.
    kind: str | None = None


async def handle_list_applications(
    query: ListApplicationsQuery, session: AsyncSession
) -> dict[str, Any]:
    await require_distributor_application_read(
        session, user_id=query.actor_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    can_view_company_applications = True
    # Company visibility requires current permission; client author access is
    # independent, matching the application detail endpoint.
    if query.actor_company_id and query.actor_role not in {
        "carcraft_employee",
        "distributor",
        "leasing_company",
        "external_api",
    }:
        perms = await get_company_permissions(
            session, query.actor_id, query.actor_company_id
        )
        can_view_company_applications = bool(perms.get("can_view_applications"))
        if not can_view_company_applications and query.actor_role != "client":
            return {
                "applications": [],
                "total": 0,
                "pagination": {
                    "page": query.page,
                    "limit": query.limit,
                    "total": 0,
                    "pages": 0,
                },
            }

    from infrastructure.repositories.application_personal_access import (
        build_personal_application_clause,
    )
    from infrastructure.repositories.user_company_access_repository import (
        check_section_access,
        get_actor_personal_access_rules,
    )

    if not await check_section_access(
        session,
        user_id=query.actor_id,
        company_id=query.actor_company_id,
        role=query.actor_role,
        section_code="applications",
    ):
        return {
            "applications": [],
            "total": 0,
            "pagination": {
                "page": query.page,
                "limit": query.limit,
                "total": 0,
                "pages": 0,
            },
        }

    item_dealer_filter = await resolve_actor_item_dealer_filter(
        session,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    personal_clause = None
    if query.actor_company_id and query.actor_role in ("dealer", "distributor"):
        personal_rules = await get_actor_personal_access_rules(
            session, query.actor_id, query.actor_company_id
        )
        if personal_rules.has_rules:
            personal_clause = build_personal_application_clause(
                personal_rules, query.actor_role, query.actor_company_id
            )

    source_types = (
        source_filter_values(query.source_type) if query.actor_role in SOURCE_VIEW_ROLES else ()
    )

    async def fetch_ordinary(page: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        found: tuple[list[dict[str, Any]], int] = await repo.list_for_user(
            session,
            user_id=query.actor_id,
            role=query.actor_role,
            company_id=query.actor_company_id,
            leasing_company_id=query.actor_leasing_company_id,
            dealer_filter=item_dealer_filter,
            can_view_company_applications=can_view_company_applications,
            include_authored_client_applications=query.include_authored_client_applications,
            status=query.status,
            personal_clause=personal_clause,
            source_types=source_types,
            search=query.search,
            page=page,
            limit=limit,
        )
        return found

    # Fast deals join the list of a dealer and of a distributor; an ordinary status or
    # source filter leaves them out (their statuses are their own dictionary).
    fast_actor = (
        await resolve_list_actor(
            session,
            user_id=query.actor_id,
            role=query.actor_role,
            company_id=query.actor_company_id,
        )
        if query.actor_role in APPLICATION_LIST_ROLES
        else None
    )
    page_rows, total = await merged_page(
        session,
        actor=fast_actor,
        kind=query.kind,
        ordinary_filtered=bool((query.status or "").strip()) or bool(source_types),
        search=query.search,
        page=query.page,
        limit=query.limit,
        fetch_ordinary=fetch_ordinary,
        ordinary_key=activity_key,
    )
    apps = [row for row in page_rows if row.get("kind") != KIND_FAST_DEAL]
    application_ids = [app["id"] for app in apps]
    vehicle_rows = await repo.list_application_vehicle_item_rows(
        session,
        application_ids,
        dealer_filter=item_dealer_filter,
        distributor_company_id=query.actor_company_id if query.actor_role == "distributor" else None,
    )
    special_equipment_rows = (
        await repo.list_application_special_equipment_item_rows(
            session,
            application_ids,
            dealer_filter=item_dealer_filter,
        )
    )
    hidden_item_application_ids: set[UUID] = set()
    if item_dealer_filter is not None:
        unscoped_vehicle_rows = await repo.list_application_vehicle_item_rows(
            session,
            application_ids,
        )
        unscoped_special_equipment_rows = (
            await repo.list_application_special_equipment_item_rows(
                session,
                application_ids,
            )
        )
        hidden_item_application_ids = applications_with_hidden_items(
            vehicle_rows=unscoped_vehicle_rows,
            visible_vehicle_rows=vehicle_rows,
            special_equipment_rows=unscoped_special_equipment_rows,
            visible_special_equipment_rows=special_equipment_rows,
        )
    items_by_application = group_application_items(
        application_ids,
        vehicle_rows=vehicle_rows,
        special_equipment_rows=special_equipment_rows,
        actor_role=query.actor_role,
    )
    dealer_distribution = await build_dealer_distribution(
        session, vehicle_rows=vehicle_rows, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    # Enrich each with leasing-company display names and LCA statuses.
    for app in apps:
        if query.actor_role not in SOURCE_VIEW_ROLES:
            app.pop("source_type", None)
        app["items"] = items_by_application.get(app["id"], [])
        app["dealer_distribution"] = dealer_distribution.get(app["id"], [])
        if app["id"] in hidden_item_application_ids:
            redact_mixed_application_financials(app)
        lc_ids = app.get("selected_leasing_companies") or []
        if lc_ids:
            app["selected_companies_info"] = await repo.list_companies_info(
                session, lc_ids
            )
        else:
            app["selected_companies_info"] = []

        # Add LCA statuses for client/dealer visibility
        app["lc_summary"] = await repo.get_lc_summary(session, app["id"])

    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "applications": page_rows,
        "total": total,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
