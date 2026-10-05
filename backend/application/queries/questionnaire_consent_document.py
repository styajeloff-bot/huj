"""Read the existing signed SOPD through an authorized questionnaire field."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.applications.get_application import ApplicationAccessQuery
from application.services.questionnaire import read_questionnaire
from application.services.questionnaire_consents import (
    CONSENT_PREFIXES,
    build_consent_projection,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import signature_request_repository as signatures


@dataclass(frozen=True)
class QuestionnaireConsentDocument:
    data: bytes
    content_type: str
    filename: str


async def read_questionnaire_consent_document(
    session: AsyncSession,
    storage: ObjectStorage,
    query: ApplicationAccessQuery,
    signature_request_id: UUID,
    field: str,
) -> QuestionnaireConsentDocument:
    questionnaire = (await read_questionnaire(session, query))["questionnaire"]
    if field not in CONSENT_PREFIXES or field not in questionnaire:
        raise ServiceError("СОПД недоступен в этом поле анкеты", 404)
    # Stored questionnaire text can predate a revocation or a replacement SOPD.
    # Authorize against current consent facts, never against a submitted UUID alone.
    current = await build_consent_projection(
        session, query.application_id,
        query.actor_leasing_company_id if query.actor_role == "leasing_company" else None,
    )
    if not any(
        item["signature_request_id"] == str(signature_request_id)
        for item in current[field]
    ):
        raise ServiceError("СОПД недоступен в этой анкете", 404)
    request = await signatures.get_by_id(session, signature_request_id)
    if request is None or not request.get("signed_pdf_s3_key"):
        raise ServiceError("Файл подписанного СОПД отсутствует", 404)
    stored = await storage.get(request["signed_pdf_s3_key"])
    if stored is None:
        raise ServiceError("Файл подписанного СОПД не найден в хранилище", 410)
    content_type = stored.content_type or "application/octet-stream"
    suffix = {
        "application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg",
        "image/heic": "heic",
    }.get(content_type, "bin")
    return QuestionnaireConsentDocument(
        data=stored.data, content_type=content_type,
        filename=f"sopd-{signature_request_id}.{suffix}",
    )
