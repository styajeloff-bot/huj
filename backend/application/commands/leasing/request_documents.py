
"""LC requests additional documents from the applicant.

Updates the LCA status to ``documents_required``, persists the list of
requested document slugs onto ``leasing_applications.requested_documents``
(JSONB), bumps ``documents_requested_at``, and appends a status-history
entry. The optional ``comments`` field becomes a comment row of type
``request_documents``.

Restored to the post-UUID world — ``application_id`` is now ``uuid.UUID``.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from application.notifications.leasing_events import record_leasing_event
from domain.entities.leasing_company_application import (
    LCA_STATUS_DOCUMENTS_REQUIRED,
    LeasingCompanyApplication,
)
from domain.errors import (
    ApplicationNotFoundError,
    LeasingCompanyApplicationNotFoundError,
    LeasingCompanyBindingNotConfiguredError,
    RequestedDocumentsRequiredError,
)
from infrastructure.messaging.dwh_events import (
    emit_lca_changed,
    emit_leasing_application_changed,
)
from infrastructure.repositories import (
    application_documents_repository as app_docs_repo,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import document_types_repository as types_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo

_MAX_REQUESTED_DOCUMENTS = 10
_MAX_DISPLAY_NAME_LENGTH = 255
_MAX_SLUG_LENGTH = 100


@dataclass(frozen=True)
class RequestedDocument:
    source: str
    display_name: str
    document_type: str | None = None


@dataclass
class RequestDocumentsCommand:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_role: str
    actor_leasing_company_id: UUID | None
    requested_documents: list[RequestedDocument]
    comments: str | None = None


async def handle_request_documents(
    cmd: RequestDocumentsCommand, session: AsyncSession
) -> dict[str, Any]:
    documents = await _resolve_requested_documents(session, cmd.requested_documents)

    application = await app_repo.get_by_id(
        session, cmd.application_id, for_update=True,
    )
    if application is None:
        raise ApplicationNotFoundError(cmd.application_id)
    lc_id = _resolve_target_lc(cmd)
    link_raw = await lca_repo.get_link_for_app_and_lc(
        session,
        application_id=cmd.application_id,
        leasing_company_id=lc_id,
        for_update=True,
    )
    if link_raw is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)
    link = LeasingCompanyApplication.from_dict(link_raw)
    link.ensure_owned_by_lc(leasing_company_id=lc_id)
    link.ensure_can_request_documents()

    request_batch_id = uuid.uuid4()
    created_requests = await app_docs_repo.create_requests_batch(
        session,
        application_id=cmd.application_id,
        leasing_company_id=lc_id,
        request_batch_id=request_batch_id,
        requested_by=cmd.actor_user_id,
        requested_at=datetime.now(UTC),
        request_message=cmd.comments,
        documents=[
            {
                "display_name": document.display_name,
                "slug": document.slug,
                "has_form": document.has_form,
                "form_schema": document.form_schema,
            }
            for document in documents
        ],
    )
    slugs = [document.slug for document in documents]
    old_status = link.status
    await lca_repo.update_link_status(
        session,
        link_id=link.id,
        new_status=LCA_STATUS_DOCUMENTS_REQUIRED,
        review_notes=cmd.comments,
    )
    await app_repo.update_requested_documents(
        session,
        application_id=cmd.application_id,
        requested_documents=slugs,
    )
    if cmd.comments:
        await lca_repo.add_application_comment(
            session,
            application_id=cmd.application_id,
            comment_type="request_documents",
            comment_text=cmd.comments,
            created_by=cmd.actor_user_id,
        )
    await hist_repo.append_lca_status_history(
        session,
        lca_id=link.id,
        application_id=cmd.application_id,
        old_status=old_status,
        new_status=LCA_STATUS_DOCUMENTS_REQUIRED,
        changed_by=cmd.actor_user_id,
        review_notes=cmd.comments,
    )

    updated_link = await lca_repo.get_link_by_id(session, link.id)
    updated_app = await app_repo.get_by_id(session, cmd.application_id)
    if updated_link is not None:
        emit_lca_changed({
            "lca_id": updated_link["id"],
            "application_id": str(updated_link["application_id"]) if updated_link.get("application_id") else None,
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
            # denormalized from parent application
            "dealer_id": None,
            "dealer_company_id": updated_app.get("dealer_company_id") if updated_app else None,
            "client_company_id": updated_app.get("company_id") if updated_app else None,
            "display_number": updated_app.get("display_number") if updated_app else None,
            "vehicle_id": updated_app.get("vehicle_id") if updated_app else None,
            "application_status": updated_app.get("status") if updated_app else None,
        })
    if updated_app is not None:
        emit_leasing_application_changed({
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
        })
    await record_leasing_event(
        session, application=updated_app or application,
        event_type="leasing.documents_requested", actor_user_id=cmd.actor_user_id,
        payload={
            "leasing_company_id": lc_id,
            "leasing_company_application_id": link.id,
            "request_batch_id": request_batch_id,
            "requested_documents": [
                {"slug": item.slug, "display_name": item.display_name}
                for item in documents
            ],
        },
        occurrence_key=f"leasing.documents_requested:{request_batch_id}",
    )
    return {
        "success": True,
        "message": "Запрос документов отправлен",
        "application_id": cmd.application_id,
        "leasing_company_id": lc_id,
        "request_batch_id": request_batch_id,
        "requested_documents": slugs,
        "items": [
            {
                "id": item["id"],
                "display_name": item["display_name"],
                "slug": item["document_type"],
                "status": item.get("status") or "requested",
                "requested_at": item.get("requested_at"),
            }
            for item in created_requests
        ],
    }


@dataclass(frozen=True)
class _ResolvedDocument:
    display_name: str
    slug: str
    has_form: bool
    form_schema: dict[str, Any] | None


async def _resolve_requested_documents(
    session: AsyncSession,
    requested_documents: list[RequestedDocument],
) -> list[_ResolvedDocument]:
    if not requested_documents:
        raise RequestedDocumentsRequiredError()
    if len(requested_documents) > _MAX_REQUESTED_DOCUMENTS:
        raise ServiceError(
            f"Можно запросить не более {_MAX_REQUESTED_DOCUMENTS} "
            "документов за один раз",
            status_code=400,
        )

    normalized: list[_ResolvedDocument] = []
    slugs: set[str] = set()
    for document in requested_documents:
        display_name = document.display_name.strip()
        if not display_name or len(display_name) > _MAX_DISPLAY_NAME_LENGTH:
            raise ServiceError(
                "Название документа должно содержать от 1 до 255 символов",
                status_code=400,
            )
        if document.source == "catalog":
            if not document.document_type:
                raise ServiceError("Для catalog требуется document_type", status_code=400)
            type_row = await types_repo.get_by_type_code(session, document.document_type)
            if type_row is None:
                raise ServiceError("Тип документа из справочника не найден", status_code=400)
            slug = str(type_row["type_code"])
            # Keep a nonblank LC-supplied label for this request. The catalog
            # remains authoritative for type_code and the form snapshot below.
            resolved_name = display_name or str(
                type_row.get("display_name") or type_row.get("name") or slug
            )
            has_form = bool(type_row.get("has_form", False))
            form_schema = type_row.get("form_schema") if has_form else None
        elif document.source == "custom":
            if document.document_type is not None:
                raise ServiceError("custom не принимает document_type", status_code=400)
            slug = _custom_slug(display_name, slugs)
            resolved_name, has_form, form_schema = display_name, False, None
        else:
            raise ServiceError("source должен быть catalog или custom", status_code=400)
        if slug in slugs:
            raise ServiceError(
                "Slug документа должен быть уникальным внутри запроса",
                status_code=400,
            )
        slugs.add(slug)
        normalized.append(_ResolvedDocument(resolved_name, slug, has_form, form_schema))
    return normalized


def _custom_slug(display_name: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_") or "custom_document"
    base = base[:_MAX_SLUG_LENGTH].rstrip("_")
    slug = base
    suffix = 2
    while slug in existing:
        ending = f"_{suffix}"
        slug = f"{base[:_MAX_SLUG_LENGTH - len(ending)]}{ending}"
        suffix += 1
    return slug


def _resolve_target_lc(cmd: RequestDocumentsCommand) -> UUID:
    if cmd.actor_leasing_company_id is not None:
        return cmd.actor_leasing_company_id
    raise LeasingCompanyBindingNotConfiguredError()
