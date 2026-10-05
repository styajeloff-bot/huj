"""Confirm the selected leasing company deal."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.integration import capture_source_transition
from application.common import _isoformat
from application.errors import ServiceError
from application.special_equipment_commerce import (
    create_leasing_orders_for_issued_application,
)
from domain.entities.leasing_application import STATUS_ISSUED, LeasingApplication
from domain.entities.leasing_company_application import (
    LCA_STATUS_DEAL,
    LCA_STATUS_SELECTED_LC,
    LeasingCompanyApplication,
)
from domain.entities.leasing_proposal import KIND_FINAL
from domain.errors import (
    ApplicationNotFoundError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.messaging.dwh_events import (
    emit_lca_changed,
    emit_leasing_application_changed,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import documents_repository as docs_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import (
    leasing_proposals_repository as proposals_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo

REQUIRED_DEAL_DOC_TYPES = frozenset({"signed_lease_agreement", "acceptance_transfer_act"})


@dataclass
class ConfirmDealCommand:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_leasing_company_id: UUID | None
    deal_date: date | None = None
    vehicles: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)


async def _apply_deal_closure(
    cmd: ConfirmDealCommand, session: AsyncSession
) -> None:
    if cmd.deal_date is None:
        raise ServiceError("Дата сделки обязательна", status_code=400)

    provided_types = {
        d.get("document_type") for d in cmd.documents if d.get("document_type")
    }
    missing_types = REQUIRED_DEAL_DOC_TYPES - provided_types
    if missing_types:
        raise ServiceError(
            "Необходимо прикрепить подписанный договор лизинга и акт приёма-передачи",
            status_code=400,
        )

    for d in cmd.documents:
        file_id = d.get("file_id")
        if not file_id:
            raise ServiceError("Идентификатор файла обязателен", status_code=400)
        try:
            f_uuid = UUID(str(file_id))
        except (ValueError, TypeError) as exc:
            raise ServiceError(f"Некорректный UUID файла: {file_id}", status_code=400) from exc
        doc = await docs_repo.get_by_id(session, f_uuid)
        if doc is None:
            raise ServiceError(f"Документ {file_id} не найден", status_code=400)
        await docs_repo.link_to_application(
            session, document_id=f_uuid, application_id=cmd.application_id
        )

    app_vehicles = await app_repo.list_application_vehicles(session, cmd.application_id)
    if app_vehicles:
        vin_by_id = {
            str(v.get("vehicle_id")): str(v.get("vin") or "").strip()
            for v in cmd.vehicles
            if v.get("vehicle_id")
        }
        for v in app_vehicles:
            v_id = str(v.get("id"))
            prod_id = str(v.get("product_id")) if v.get("product_id") else None
            vin = vin_by_id.get(v_id) or (vin_by_id.get(prod_id) if prod_id else None)
            if not vin:
                raise ServiceError(
                    "Не указан VIN-номер для техники в заявке", status_code=400
                )

    deal_docs = [
        {"file_id": str(d["file_id"]), "document_type": str(d["document_type"])}
        for d in cmd.documents
    ]
    await app_repo.save_deal_confirmation(
        session,
        cmd.application_id,
        deal_date=cmd.deal_date,
        deal_documents=deal_docs,
    )
    if cmd.vehicles:
        await app_repo.update_application_vehicles_vins(
            session,
            cmd.application_id,
            vehicles_vin_data=[
                {"vehicle_id": v["vehicle_id"], "vin": str(v["vin"]).strip()}
                for v in cmd.vehicles
            ],
            actor_id=cmd.actor_user_id,
        )


async def handle_confirm_deal(
    cmd: ConfirmDealCommand, session: AsyncSession
) -> dict[str, Any]:
    """Confirm a selected LC link, leaving external events for post-commit."""
    if cmd.actor_leasing_company_id is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)

    raw_app = await app_repo.get_by_id(session, cmd.application_id, for_update=True)
    if raw_app is None:
        raise ApplicationNotFoundError(cmd.application_id)

    # PostgreSQL holds this row lock until the router commits or rolls back.
    # A competing request therefore observes ``deal`` after waiting and follows
    # the replay branch without histories, finalization, or emitted events.
    raw_link = await lca_repo.get_link_for_app_and_lc_for_update(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    if raw_link is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)
    link = LeasingCompanyApplication.from_dict(raw_link)
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)

    replayed = link.status == LCA_STATUS_DEAL
    if link.status not in {LCA_STATUS_SELECTED_LC, LCA_STATUS_DEAL}:
        raise ServiceError(
            "Подтвердить сделку можно только для выбранной клиентом ЛК",
            status_code=400,
        )

    application = LeasingApplication.from_dict(raw_app)
    application_status_changed = application.status != STATUS_ISSUED
    special_equipment_orders: list[dict[str, Any]] = []
    lca_changed_event: dict[str, Any] | None = None
    application_changed_event: dict[str, Any] | None = None

    if not replayed:
        link.ensure_can_deal()

        if cmd.deal_date is not None or cmd.documents or cmd.vehicles:
            await _apply_deal_closure(cmd, session)

        await lca_repo.update_link_status(
            session, link_id=link.id, new_status=LCA_STATUS_DEAL
        )
        await hist_repo.append_lca_status_history(
            session,
            lca_id=link.id,
            application_id=cmd.application_id,
            old_status=LCA_STATUS_SELECTED_LC,
            new_status=LCA_STATUS_DEAL,
            changed_by=cmd.actor_user_id,
        )

        if application_status_changed:
            await app_repo.update_application_status(
                session, cmd.application_id, new_status=STATUS_ISSUED
            )

        proposals = await proposals_repo.list_by_lca(session, link.id)
        final_proposal: dict[str, Any] = next(
            (proposal for proposal in proposals if proposal.get("kind") == KIND_FINAL),
            {},
        )
        special_equipment_orders = await create_leasing_orders_for_issued_application(
            application=raw_app,
            final_proposal=final_proposal,
            session=session,
        )

        await capture_source_transition(session, actor_user_id=cmd.actor_user_id,
                                        leasing_company_application_id=link.id)

        updated_link = await lca_repo.get_link_by_id(session, link.id)
        updated_app = await app_repo.get_by_id(session, cmd.application_id)
        if updated_link is not None:
            lca_changed_event = {
                "lca_id": updated_link["id"],
                "application_id": str(updated_link["application_id"]),
                "leasing_company_id": updated_link.get("leasing_company_id"),
                "status": updated_link.get("status"),
                "review_notes": updated_link.get("review_notes"),
                "decision_comment": updated_link.get("decision_comment"),
                "response_pdf_s3_key": updated_link.get("response_pdf_s3_key"),
                "response_pdf_file_name": updated_link.get("response_pdf_file_name"),
                "response_pdf_size": updated_link.get("response_pdf_size"),
                "response_pdf_uploaded_at": _isoformat(updated_link.get("response_pdf_uploaded_at")),
                "submitted_at": _isoformat(updated_link.get("submitted_at")),
                "created_at": _isoformat(updated_link.get("created_at")),
                "updated_at": _isoformat(updated_link.get("updated_at")),
                "_deleted": False,
                "dealer_id": None,
                "dealer_company_id": updated_app.get("dealer_company_id") if updated_app else None,
                "client_company_id": updated_app.get("company_id") if updated_app else None,
                "display_number": updated_app.get("display_number") if updated_app else None,
                "vehicle_id": updated_app.get("vehicle_id") if updated_app else None,
                "application_status": updated_app.get("status") if updated_app else None,
            }
        if updated_app is not None:
            application_changed_event = {
                "application_id": str(updated_app["id"]),
                "display_number": updated_app.get("display_number"),
                "company_id": updated_app.get("company_id"),
                "dealer_company_id": updated_app.get("dealer_company_id"),
                "vehicle_id": updated_app.get("vehicle_id"),
                "name": updated_app.get("name"),
                "email": updated_app.get("email"),
                "status": updated_app.get("status"),
                "total_amount": updated_app.get("total_amount"),
                "down_payment": updated_app.get("down_payment"),
                "down_payment_percent": updated_app.get("down_payment_percent"),
                "lease_term_months": updated_app.get("lease_term_months"),
                "monthly_payment": updated_app.get("monthly_payment"),
                "total_cost": updated_app.get("total_cost"),
                "markup": updated_app.get("markup"),
                "rate": updated_app.get("rate"),
                "total_interest": updated_app.get("total_interest"),
                "buyout_amount": updated_app.get("buyout_amount"),
                "vat_refund": updated_app.get("vat_refund"),
                "profit_tax_savings": updated_app.get("profit_tax_savings"),
                "total_savings": updated_app.get("total_savings"),
                "selected_leasing_companies": updated_app.get("selected_leasing_companies"),
                "leasing_company_comments": updated_app.get("leasing_company_comments"),
                "requested_documents": updated_app.get("requested_documents"),
                "questionnaire_completed": updated_app.get("questionnaire_completed"),
                "questionnaire_progress": updated_app.get("questionnaire_progress"),
                "current_stage": updated_app.get("current_stage"),
                "created_at": _isoformat(updated_app.get("created_at")),
                "updated_at": _isoformat(updated_app.get("updated_at")),
                "_deleted": False,
            }

    return {
        "application_id": cmd.application_id,
        "leasing_company_application_id": link.id,
        "status": LCA_STATUS_DEAL,
        "message": "Сделка подтверждена",
        "replayed": replayed,
        "post_commit_events": {
            "parent_status": (
                {
                    "application_id": cmd.application_id,
                    "old_status": application.status,
                    "new_status": STATUS_ISSUED,
                    "changed_by": cmd.actor_user_id,
                }
                if not replayed and application_status_changed
                else None
            ),
            "lca_changed": lca_changed_event,
            "application_changed": application_changed_event,
        },
        "special_equipment_orders": [
            {
                "id": str(order["id"]),
                "product_id": str(order["product_id"]),
                "status": order["status"],
            }
            for order in special_equipment_orders
        ],
    }


async def publish_confirm_deal_events(result: dict[str, Any]) -> None:
    """Publish the deferred status/DWH events after a successful commit."""
    events = result.pop("post_commit_events", {})
    parent_status = events.get("parent_status")
    if parent_status is not None:
        await hist_repo.append_leasing_app_status_history(**parent_status)
    lca_changed = events.get("lca_changed")
    if lca_changed is not None:
        emit_lca_changed(lca_changed)
    application_changed = events.get("application_changed")
    if application_changed is not None:
        emit_leasing_application_changed(application_changed)
