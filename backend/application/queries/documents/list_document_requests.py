"""List the persisted document-request history for an application."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import require_distributor_application_read
from application.services.leasing_access import require_lc_application_access
from domain.errors import ApplicationNotFoundError, DocumentAccessDeniedError
from infrastructure.repositories import (
    application_documents_repository as document_requests_repo,
)


@dataclass(frozen=True)
class ListDocumentRequestsQuery:
    application_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_list_document_requests(
    query: ListDocumentRequestsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    await require_distributor_application_read(
        session, user_id=query.actor_user_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    application = await document_requests_repo.get_application(
        session, query.application_id
    )
    if application is None:
        raise ApplicationNotFoundError(query.application_id)

    if query.actor_role == "leasing_company":
        link = await require_lc_application_access(
            session, application_id=query.application_id,
            user_id=query.actor_user_id, company_id=query.actor_company_id,
            leasing_company_id=query.actor_leasing_company_id,
        )
        leasing_company_filter = link["leasing_company_id"]
    else:
        leasing_company_filter = _resolve_leasing_company_filter(query, application)
    rows = await document_requests_repo.list_request_history(
        session,
        application_id=query.application_id,
        leasing_company_id=leasing_company_filter,
    )
    batches: list[dict[str, Any]] = []
    batches_by_id: dict[UUID, dict[str, Any]] = {}
    items_by_request_id: dict[UUID, dict[str, Any]] = {}

    for row in rows:
        batch_id = row["request_batch_id"]
        batch = batches_by_id.get(batch_id)
        if batch is None:
            batch = {
                "request_batch_id": batch_id,
                "leasing_company": {
                    "id": row["leasing_company_id"],
                    "name": row.get("leasing_company_name") or "",
                },
                "comments": row.get("request_message"),
                "requested_at": row.get("requested_at"),
                "requested_by": (
                    {
                        "id": row["requested_by"],
                        "name": row.get("requested_by_name") or "",
                    }
                    if row.get("requested_by") is not None
                    else None
                ),
                "items": [],
            }
            batches_by_id[batch_id] = batch
            batches.append(batch)

        request_id = row["id"]
        document = row.get("document")
        if document is not None:
            document = {
                "id": document["application_document_id"],
                "document_id": document["id"],
                "file_name": document.get("file_name"),
                "user_title": document.get("user_title"),
                "file_size": document.get("file_size"),
                "uploaded_at": document.get("uploaded_at"),
                "status": document.get("review_status") or document.get("status"),
                "download_url": f"/api/v1/documents/{document['id']}/content",
            }
        item = items_by_request_id.get(request_id)
        if item is None:
            item = {
                "id": request_id,
                "display_name": row["display_name"],
                "slug": row["document_type"],
                "status": row.get("status") or "requested",
                "provided_at": row.get("provided_at"),
                "document": None,
                "attachment": None,
                "attachments": [],
                "document_type": row["document_type"],
                "has_form": bool(row.get("has_form", False)),
                "form_schema": row.get("form_schema"),
                "form_data": mask_form_data_for_actor(row.get("form_data"), query.actor_role),
            }
            items_by_request_id[request_id] = item
            batch["items"].append(item)
        if document is not None:
            item["attachments"].append(document)
            item["attachment"] = item["attachments"][0]
            item["document"] = item["attachment"]

    return {
        "application_id": query.application_id,
        "batches": batches,
        "total": len(batches),
    }


def _resolve_leasing_company_filter(
    query: ListDocumentRequestsQuery,
    application: dict[str, Any],
) -> UUID | None:
    if query.actor_role == "carcraft_employee":
        return None
    if query.actor_role == "client":
        if (
            query.actor_company_id is not None
            and application["company_id"] == query.actor_company_id
        ):
            return None
        raise DocumentAccessDeniedError()
    raise DocumentAccessDeniedError()


def mask_form_data_for_actor(form_data: dict[str, Any] | None, actor_role: str) -> dict[str, Any] | None:
    """Mask a submitted SNILS when the applicant reads it back later."""
    if form_data is None or actor_role in {"leasing_company", "carcraft_employee"}:
        return form_data
    if set(form_data) == {"number"} and isinstance(form_data["number"], str):
        number = form_data["number"]
        if len(number) == 11:
            return {"number": f"***-***-*** {number[-2:]}"}
    return form_data


__all__ = [
    "ListDocumentRequestsQuery",
    "handle_list_document_requests",
    "mask_form_data_for_actor",
]
