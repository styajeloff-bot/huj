"""Assign leasing companies to an application (admin) command.

For applications (status ``active``) we create LCA (leasing_company_applications)
records for each selected LC. The original LA stays active — it is the single
source of truth for the application lifecycle. LCA records track per-LC state
(submitted → under_review → approved/rejected).

Phase 4 D3 owns subsequent per-LC status transitions; this command only sets
each LCA to ``submitted`` at dispatch time.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.display_number import (
    assign_display_number_if_missing,
)
from application.commands.applications.finalize_supports import (
    finalize_application_supports,
)
from application.common import _isoformat
from application.notifications.leasing_events import record_company_assignments
from application.services.company_requisites_attachment import (
    attach_company_requisites_to_applications,
)
from application.services.egrul_attachment import sync_egrul_application_documents
from application.services.fns_report_attachment import (
    attach_fns_report_to_applications,
)
from application.services.questionnaire_consents import refresh_consent_projection
from application.services.questionnaire_delivery import assert_ready_for_delivery
from application.services.sopd_passport_files import sync_passport_application_documents
from domain.entities.leasing_application import (
    STATUS_ACTIVE,
    LeasingApplication,
)
from domain.errors import (
    ApplicationLcAssignmentNotAllowedError,
    ApplicationNotFoundError,
    LeasingCompanyNotFoundError,
)
from domain.special_equipment_application_pricing import (
    ensure_no_pending_requested_prices,
)
from domain.values import OrderStatus, PurchaseType
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import (
    admin_applications_repository as admin_repo,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import purchase_repository as purchase_repo

_ALLOWED_STATUSES: frozenset[str] = frozenset({STATUS_ACTIVE})


async def _emit_application_change(
    session: AsyncSession,
    application_id: uuid.UUID,
) -> None:
    app = await app_repo.get_by_id(session, application_id)
    if app is not None:
        emit_leasing_application_changed({
            "application_id": str(app["id"]),
            "display_number": app.get("display_number"),
            "company_id": app.get("company_id"),
            "dealer_company_id": app.get("dealer_company_id"),
            "vehicle_id": app.get("vehicle_id"),
            "name": app.get("name"),
            "email": app.get("email"),
            "status": app.get("status"),
            "total_amount": app.get("total_amount"),
            "down_payment": app.get("down_payment"),
            "down_payment_percent": app.get("down_payment_percent"),
            "lease_term_months": app.get("lease_term_months"),
            "monthly_payment": app.get("monthly_payment"),
            "total_cost": app.get("total_cost"),
            "markup": app.get("markup"),
            "rate": app.get("rate"),
            "total_interest": app.get("total_interest"),
            "buyout_amount": app.get("buyout_amount"),
            "vat_refund": app.get("vat_refund"),
            "profit_tax_savings": app.get("profit_tax_savings"),
            "total_savings": app.get("total_savings"),
            "selected_leasing_companies": app.get("selected_leasing_companies"),
            "leasing_company_comments": app.get("leasing_company_comments"),
            "requested_documents": app.get("requested_documents"),
            "questionnaire_completed": app.get("questionnaire_completed"),
            "questionnaire_progress": app.get("questionnaire_progress"),
            "current_stage": app.get("current_stage"),
            "created_at": _isoformat(app.get("created_at")),
            "updated_at": _isoformat(app.get("updated_at")),
            "_deleted": False,
        })


@dataclass
class AssignLeasingCompaniesToApplicationCommand:
    application_id: uuid.UUID
    leasing_company_ids: list[UUID]
    actor_id: UUID | None = None


async def handle_assign_leasing_companies_to_application(
    cmd: AssignLeasingCompaniesToApplicationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    locked = await app_repo.lock_application_price_state(
        session, cmd.application_id
    )
    if locked is None:
        raise ApplicationNotFoundError(cmd.application_id)
    existing = locked["application"]

    application = LeasingApplication.from_dict(existing)
    if application.status not in _ALLOWED_STATUSES:
        raise ApplicationLcAssignmentNotAllowedError(application.status)
    ensure_no_pending_requested_prices(locked["items"])

    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    if cmd.leasing_company_ids:
        await fulfillment.require_complete_for_financing(session, cmd.application_id)
    lc_ids = list(dict.fromkeys(cmd.leasing_company_ids))
    new_lc_ids = []
    for lc_id in lc_ids:
        if not await app_repo.leasing_company_exists(session, lc_id):
            raise LeasingCompanyNotFoundError(lc_id)
        if await lca_repo.get_link_for_app_and_lc(
            session, application_id=cmd.application_id, leasing_company_id=lc_id,
        ) is None:
            new_lc_ids.append(lc_id)

    if new_lc_ids:
        await refresh_consent_projection(session, cmd.application_id)
        await assert_ready_for_delivery(session, cmd.application_id, new_lc_ids)

    await finalize_application_supports(
        session,
        application_id=cmd.application_id,
        actor_id=cmd.actor_id,
    )

    # Update selected_leasing_companies on the original LA
    await admin_repo.update_selected_leasing_companies(
        session, cmd.application_id, leasing_company_ids=lc_ids
    )

    # Create LCA records for each LC (status=submitted)
    inserted = await app_repo.upsert_lc_links(
        session,
        application_id=cmd.application_id,
        leasing_company_ids=lc_ids,
        changed_by=cmd.actor_id,
    )

    if new_lc_ids:
        await sync_egrul_application_documents(
            session, application_id=cmd.application_id, leasing_company_ids=new_lc_ids
        )
        await sync_passport_application_documents(
            session, application_id=cmd.application_id, leasing_company_ids=new_lc_ids
        )

    if inserted:
        await app_repo.upsert_questionnaire(
            session, application_id=cmd.application_id,
            payload={"questionnaire_completed_at": datetime.now(UTC)},
            source="system",
        )

    # Ensure display_number is assigned
    existing_app = await app_repo.get_by_id(session, cmd.application_id)
    if existing_app is not None:
        await assign_display_number_if_missing(
            session, application=existing_app
        )

    # Purchase orders represent the buyer's commitment to the vehicles.
    await _ensure_leasing_purchase_orders(
        session,
        application_id=cmd.application_id,
        user_id=existing_app.get("created_by") if existing_app else None,
    )

    # Best-effort attach of the FNS bookkeeping PDF + company requisites
    company = await company_repo.get_company_by_id(
        session, existing["company_id"]
    )
    if company is not None:
        await attach_fns_report_to_applications(
            session,
            inn=company.get("inn"),
            company_id=existing["company_id"],
            application_ids=[cmd.application_id],
        )
        await attach_company_requisites_to_applications(
            session,
            company_id=existing["company_id"],
            application_ids=[cmd.application_id],
            questionnaire_source_id=cmd.application_id,
        )

    await _emit_application_change(session, cmd.application_id)
    await record_company_assignments(
        session, application=existing_app or existing,
        leasing_company_ids=new_lc_ids, actor_user_id=cmd.actor_id,
    )

    return {
        "application_id": cmd.application_id,
        "leasing_company_ids": lc_ids,
        "assigned_count": len(lc_ids),
        "new_links_count": inserted,
        "status": application.status,
        "message": "Лизинговые компании назначены",
    }


async def _ensure_leasing_purchase_orders(
    session: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> None:
    """Ensure purchase_orders exist so the applicant's Мои Авто view has
    stable rows to reference."""
    if not user_id:
        return
    vehicles = await app_repo.list_application_vehicles(
        session, application_id
    )
    for v in vehicles:
        vid = v.get("vehicle_id")
        if not vid:
            continue
        price = v.get("total_price") if v.get("total_price") is not None else v.get("unit_price")
        existing = await purchase_repo.find_order_by_application_and_vehicle(
            session, leasing_application_id=application_id, vehicle_id=vid
        )
        if existing is not None:
            continue
        await purchase_repo.create_in_transaction(
            session,
            data={
                "user_id": user_id,
                "leasing_application_id": application_id,
                "vehicle_id": vid,
                "total_price": price or 0,
                "paid_amount": 0,
                "remaining_amount": price or 0,
                "status": OrderStatus.LEASING_PENDING,
                "purchase_type": PurchaseType.RESERVATION,
            },
        )
