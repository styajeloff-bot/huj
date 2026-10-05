"""Project completed document-request answers into the application questionnaire.

Files remain owned by the application/document subsystem. Only text and stable
document references are included here, in the same transaction as the answer.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.questionnaire import FILE_DEFAULTS
from infrastructure.repositories import application_repository as applications

DOCUMENT_STATUS_FIELDS: dict[str, tuple[str, str]] = {
    document_type: (field, FILE_DEFAULTS[field])
    for document_type, field in {
        "loans_docs": "loans_credits_leasing",
        "third_member_guarantees": "third_party_guarantees",
        "additional_collateral": "additional_collateral_available",
        "state_defense_order": "state_defense_order",
        "appointment_docs": "director_appointment_document",
    }.items()
}
OPTIONAL_REQUEST_FILE_TYPES = frozenset({
    *DOCUMENT_STATUS_FIELDS,
    "snils", "main_counterparties", "open_bank_accounts", "beneficial_owner", "management_company",
})


def document_status(
    document_type: str, documents: list[dict[str, Any]]
) -> dict[str, Any]:
    references = [
        {"document_id": str(item["id"]), "user_title": item["user_title"]}
        for item in documents
    ]
    return {
        "status": "attached" if references else "missing",
        "text": (
            "Файл приложен: " + "; ".join(item["user_title"] for item in references)
            if references else DOCUMENT_STATUS_FIELDS[document_type][1]
        ),
        "documents": references,
    }


async def project_document_answer(
    session: AsyncSession,
    *,
    application_id: UUID,
    document_type: str,
    form_data: dict[str, Any] | None,
    documents: list[dict[str, Any]],
) -> None:
    payload: dict[str, Any] = {}
    values = form_data or {}
    if document_type in DOCUMENT_STATUS_FIELDS:
        payload[DOCUMENT_STATUS_FIELDS[document_type][0]] = document_status(document_type, documents)
    elif document_type == "management_company":
        references = [
            {"document_id": str(item["id"]), "user_title": item["user_title"]}
            for item in documents
        ]
        # Requisites have their own source and must survive any document answer.
        payload["management_company_details"] = {
            "status": "file_attached" if references else "not_provided",
            "file_name": "; ".join(item["user_title"] for item in references) or None,
            "documents": references,
        }
    elif document_type == "snils":
        payload["director_snils"] = values["number"]
    elif document_type == "main_counterparties":
        payload["main_counterparties"] = values["counterparties"]
    elif document_type == "open_bank_accounts":
        payload["open_bank_accounts"] = values["accounts"]
    elif document_type == "beneficial_owner":
        payload["transaction_beneficiary"] = {"fio": values["fio"]}
    elif document_type in {"licenses", "sro"}:
        current = await applications.get_questionnaire(session, application_id) or {}
        previous = current.get("licenses_or_sro_membership") or []
        # Repeated requests add independently identified documents, without
        # deleting previously supplied licenses from the application.
        entries = [entry for entry in previous if isinstance(entry, dict)]
        entries.extend({
            "document_type": document_type,
            "document_id": str(item["id"]),
            "user_title": item["user_title"],
        } for item in documents)
        payload["licenses_or_sro_membership"] = entries
    if payload:
        await applications.upsert_questionnaire(
            session, application_id=application_id, payload=payload,
            source="document_request",
        )
