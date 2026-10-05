"""LC response workflow queries.

Two read paths used by the LC cabinet and the client-side detail page:

* ``GetFinancialBundleQuery`` — assembles the duplicate of step #2 of
  the application: questionnaire (requisites + directors + founders +
  beneficiaries) plus the latest accounting report by INN.
* ``GetLcResponseStateQuery`` — current LCA + KP list + PDF metadata,
  used by the LC cabinet to render the response form.
* ``GetClientLeasingResponsesQuery`` — for the client-facing application
  detail page; returns each LC's submitted response with the
  "requested vs offered" diff already computed server-side.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import ensure_application_full_data_access
from application.queries.applications.get_application import (
    ApplicationAccessQuery,
    get_authorized_application,
)
from application.queries.applications.item_projection import (
    group_application_items,
)
from application.services.leasing_access import require_lc_application_access
from application.services.questionnaire_delivery import project_for_leasing_company
from domain.entities.leasing_company_application import (
    LCA_STATUS_DEAL,
    LCA_STATUS_SELECTED_LC,
)
from domain.errors import (
    ApplicationNotFoundError,
)
from infrastructure.repositories import accounting_repository as acc_repo
from infrastructure.repositories import (
    application_documents_repository as app_docs_repo,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import (
    document_types_repository as doc_types_repo,
)
from infrastructure.repositories import documents_repository as docs_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import (
    leasing_proposals_repository as proposals_repo,
)

_LC_COMMERCE_TOTAL_FIELDS = (
    "items_count",
    "special_equipment_count",
    "vehicles_count",
    "total_items_price",
    "total_special_equipment_price",
    "total_vehicles_price",
)

# ---------------------------------------------------------------------------
# Financial bundle (step 2 duplicate for the LC cabinet)
# ---------------------------------------------------------------------------


@dataclass
class GetFinancialBundleQuery:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    actor_user_id: UUID
    actor_company_id: UUID | None


async def handle_get_financial_bundle(
    q: GetFinancialBundleQuery, session: AsyncSession
) -> dict[str, Any]:
    link = await require_lc_application_access(
        session,
        application_id=q.application_id,
        user_id=q.actor_user_id,
        company_id=q.actor_company_id,
        leasing_company_id=q.actor_leasing_company_id,
    )

    questionnaire = await app_repo.get_questionnaire(session, q.application_id)
    if questionnaire is None:
        raise ApplicationNotFoundError(q.application_id)

    inn = questionnaire.get("inn")
    accounting = await acc_repo.get_by_inn(session, str(inn)) if inn else None
    return {
        "application_id": q.application_id,
        "questionnaire": await project_for_leasing_company(
            session, questionnaire, link["leasing_company_id"]
        ),
        "accounting_report": accounting,
    }


# ---------------------------------------------------------------------------
# LC application documents (LC cabinet)
# ---------------------------------------------------------------------------


@dataclass
class GetLcApplicationDocumentsQuery:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    actor_user_id: UUID
    actor_company_id: UUID | None


async def handle_get_lc_application_documents(
    q: GetLcApplicationDocumentsQuery, session: AsyncSession
) -> dict[str, Any]:
    """Return every document attached to ``application_id`` enriched with
    Russian display labels for the LC cabinet «Прикреплённые документы».

    Access control mirrors the financial bundle: only an LC linked to the
    application may read it.
    """
    link_raw = await require_lc_application_access(
        session,
        application_id=q.application_id,
        user_id=q.actor_user_id,
        company_id=q.actor_company_id,
        leasing_company_id=q.actor_leasing_company_id,
    )

    documents = await docs_repo.list_for_application(
        session, application_id=q.application_id
    )
    request_owner_lcs = (
        await app_docs_repo.list_request_owner_leasing_company_ids_for_documents(
            session, application_id=q.application_id
        )
    )
    # A response belongs only to the LC which requested it. Keep ordinary
    # application documents visible under the established LC permissions.
    documents = [
        document
        for document in documents
        if (
            document_owner_lcs := request_owner_lcs.get(document["id"])
        ) is None
        or document_owner_lcs == {link_raw["leasing_company_id"]}
    ]
    association_statuses = await app_docs_repo.list_application_document_statuses(
        session,
        application_id=q.application_id,
        leasing_company_id=link_raw["leasing_company_id"],
    )
    request_display_names = await app_docs_repo.list_request_display_names_for_documents(
        session, application_id=q.application_id
    )
    type_codes = sorted(
        {d["document_type"] for d in documents if d.get("document_type")}
    )
    types = await doc_types_repo.get_many_by_type_codes(session, type_codes)
    labels = {t["type_code"]: t["display_name"] for t in types if t.get("type_code")}

    enriched: list[dict[str, Any]] = []
    for doc in documents:
        type_code = doc.get("document_type") or ""
        doc_id = doc.get("id")
        download_url = f"/api/v1/documents/{doc_id}/content" if doc_id else None
        association_status = _lc_document_status(association_statuses.get(doc_id))
        # company_requisites is created automatically for this application and
        # is accepted immediately. It has no per-LC ApplicationDocument row,
        # so expose its persisted automatic review result as the LC status.
        if (
            association_status is None
            and type_code == "company_requisites"
            and doc.get("leasing_company_status") == "approved"
        ):
            association_status = "approved"
        enriched.append(
            {
                "id": doc_id,
                "document_type": type_code,
                "display_name": (
                    request_display_names.get(doc_id)
                    or ("Реквизиты компании" if type_code == "company_requisites" else None)
                    or labels.get(type_code)
                    or ("Произвольный документ" if type_code == "custom_document" else "Документ")
                ),
                "period_label": doc.get("period_label"),
                "file_name": doc.get("file_name"),
                "file_size": doc.get("file_size"),
                "uploaded_at": doc.get("uploaded_at"),
                "status": doc.get("status"),
                "leasing_company_status": association_status,
                "download_url": download_url,
            }
        )
    enriched.sort(
        key=lambda d: (d.get("display_name") or "", d.get("period_label") or "")
    )
    return {
        "application_id": q.application_id,
        "documents": enriched,
        "total": len(enriched),
    }


def _lc_document_status(association_status: str | None) -> str | None:
    """Translate storage's submitted state to the LC cabinet's pending state."""
    if association_status == "submitted":
        return "pending"
    return association_status


# ---------------------------------------------------------------------------
# LC response state (LC cabinet)
# ---------------------------------------------------------------------------


@dataclass
class GetLcResponseStateQuery:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    actor_user_id: UUID
    actor_company_id: UUID | None


async def handle_get_lc_response_state(
    q: GetLcResponseStateQuery, session: AsyncSession
) -> dict[str, Any]:
    link_raw = await require_lc_application_access(
        session,
        application_id=q.application_id,
        user_id=q.actor_user_id,
        company_id=q.actor_company_id,
        leasing_company_id=q.actor_leasing_company_id,
    )
    display_statuses = await app_docs_repo.list_lc_display_statuses(
        session, application_id=q.application_id
    )
    link_raw["display_status"] = display_statuses.get(
        link_raw["leasing_company_id"], link_raw.get("status")
    )

    # Preserve the established LC allow-list.  The generic application read
    # model also contains actor IDs, internal comments, workflow stages and
    # grouping metadata that must not cross this tenant boundary.
    application = await lca_repo.get_application_full(session, q.application_id)
    proposals = await proposals_repo.list_by_lca(session, link_raw["id"])

    if application is not None:
        commerce_summary = await app_repo.get_by_id(session, q.application_id)
        if commerce_summary is not None:
            for field_name in _LC_COMMERCE_TOTAL_FIELDS:
                application[field_name] = commerce_summary.get(field_name)
        vehicles = await app_repo.list_application_vehicles_with_catalog(
            session,
            q.application_id,
        )
        special_equipment_rows = (
            await app_repo.list_application_special_equipment_item_rows(
                session,
                [q.application_id],
            )
        )
        application["vehicles"] = vehicles
        application["items"] = group_application_items(
            [q.application_id],
            vehicle_rows=vehicles,
            special_equipment_rows=special_equipment_rows,
            for_leasing_company=True,
        )[q.application_id]
        company_id = application.get("company_id")
        if company_id is not None:
            company = await company_repo.get_company_by_id(session, company_id)
            if company is not None:
                application["company"] = {
                    "id": company.get("id"),
                    "name": company.get("name"),
                    "inn": company.get("inn"),
                }
        application[
            "leasing_company_name"
        ] = await lca_repo.get_leasing_company_display_name(
            session, link_raw["leasing_company_id"]
        )

    return {
        "link": link_raw,
        "application": application,
        "proposals": proposals,
        "can_confirm_deal": link_raw.get("status") == LCA_STATUS_SELECTED_LC,
        "confirm_deal_disabled_reason": _confirm_deal_disabled_reason(
            link_raw.get("status")
        ),
    }


def _confirm_deal_disabled_reason(status: str | None) -> str | None:
    if status == LCA_STATUS_SELECTED_LC:
        return None
    if status == LCA_STATUS_DEAL:
        return "Сделка уже подтверждена"
    return "Подтверждение сделки недоступно для текущего статуса заявки"


# ---------------------------------------------------------------------------
# Client-facing list of LC responses ("requested vs offered" view)
# ---------------------------------------------------------------------------


_DIFF_FIELDS: tuple[str, ...] = (
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
)


def _coerce_compare(value: Any) -> Any:
    """Normalise numbers for equality comparison so Decimal('100') == 100."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))
    return value


def _build_diff(
    requested: dict[str, Any], proposal: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in _DIFF_FIELDS:
        req = requested.get(name) if requested else None
        offered = proposal.get(name)
        out.append(
            {
                "field": name,
                "requested": req,
                "offered": offered,
                "changed": _coerce_compare(req) != _coerce_compare(offered),
            }
        )
    return out


@dataclass
class GetClientLeasingResponsesQuery(ApplicationAccessQuery):
    pass


async def handle_get_client_leasing_responses(
    q: GetClientLeasingResponsesQuery, session: AsyncSession
) -> dict[str, Any]:
    await get_authorized_application(q, session)
    await ensure_application_full_data_access(
        session, application_id=q.application_id, actor_role=q.actor_role,
        actor_company_id=q.actor_company_id,
    )
    requested = await lca_repo.get_application_full(session, q.application_id)
    if requested is None:
        raise ApplicationNotFoundError(q.application_id)

    approval_offers: dict[str, list[dict[str, Any]]] = {}
    for kind in ("preliminary", "final"):
        rows = await proposals_repo.list_approval_offers(
            session,
            application_id=q.application_id,
            kind=kind,
        )
        approval_offers[kind] = [
            {
                **row,
                "proposal": {
                    **row["proposal"],
                    "diff": _build_diff(requested, row["proposal"]),
                },
            }
            for row in rows
        ]

    responses = await lca_repo.list_submitted_responses_for_application(
        session, q.application_id
    )
    out: list[dict[str, Any]] = []
    for resp in responses:
        proposals = await proposals_repo.list_by_lca(session, resp["id"])
        out.append(
            {
                "leasing_company": resp.get("leasing_company"),
                "decision": resp.get("status"),
                "decision_comment": resp.get("decision_comment"),
                "submitted_at": resp.get("submitted_at"),
                "response_pdf": (
                    {
                        "file_name": resp.get("response_pdf_file_name"),
                        "file_size": resp.get("response_pdf_size"),
                        "uploaded_at": resp.get("response_pdf_uploaded_at"),
                    }
                    if resp.get("response_pdf_s3_key")
                    else None
                ),
                "proposals": [
                    {**p, "diff": _build_diff(requested, p)} for p in proposals
                ],
            }
        )
    return {
        "application_id": q.application_id,
        "requested": {f: requested.get(f) for f in _DIFF_FIELDS},
        "responses": out,
        "approval_offers": approval_offers,
    }


__all__ = [
    "GetClientLeasingResponsesQuery",
    "GetFinancialBundleQuery",
    "GetLcApplicationDocumentsQuery",
    "GetLcResponseStateQuery",
    "handle_get_client_leasing_responses",
    "handle_get_financial_bundle",
    "handle_get_lc_application_documents",
    "handle_get_lc_response_state",
]
