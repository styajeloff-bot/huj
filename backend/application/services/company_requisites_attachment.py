"""Generate a company-requisites PDF and link it to a group of applications.

Mirror of :mod:`fns_report_attachment`, but the blob is rendered locally
from the questionnaire + companies row. No external HTTP — the only
failure modes are "no data" (skip quietly) and "reportlab/storage error"
(log + skip). Never raises to the caller.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import documents_repository as documents_repo
from infrastructure.services import document_storage
from infrastructure.services.company_requisites_pdf import (
    CompanyRequisitesInput,
    render_company_requisites_pdf,
)

logger = logging.getLogger("carcraft-backend")

_DOCUMENT_TYPE = "company_requisites"


async def attach_company_requisites_to_applications(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    application_ids: list[uuid.UUID],
    questionnaire_source_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Render the PDF and link it via ``document_applications`` M2M.

    ``questionnaire_source_id`` points to the leasing_application whose
    ``application_questionnaires`` row should be used. Defaults to the first
    application in ``application_ids``.

    Idempotent: reuses any existing ``company_requisites`` document already
    linked to one of the target apps; only renders + stores a new blob when
    none of them has one yet.
    """
    if not application_ids:
        return None

    already = await documents_repo.list_application_ids_with_document_type(
        session,
        application_ids=application_ids,
        document_type=_DOCUMENT_TYPE,
    )
    missing_ids = [a for a in application_ids if a not in already]
    if not missing_ids:
        logger.info(
            "company_requisites_skip reason=already_attached company_id=%s applications=%s",
            company_id,
            application_ids,
        )
        return None

    existing_id: (
        uuid.UUID | None
    ) = await documents_repo.find_document_id_by_type_for_applications(
        session,
        application_ids=list(already),
        document_type=_DOCUMENT_TYPE,
    )
    if existing_id is not None:
        for app_id in missing_ids:
            await documents_repo.link_to_application(
                session, document_id=existing_id, application_id=app_id
            )
        logger.info(
            "company_requisites_relinked document_id=%s applications=%s",
            existing_id,
            missing_ids,
        )
        return existing_id

    questionnaire = await app_repo.get_questionnaire(
        session, questionnaire_source_id or application_ids[0]
    )
    company = await company_repo.get_company_by_id(session, company_id)

    if not questionnaire and not company:
        logger.info(
            "company_requisites_skip reason=no_data company_id=%s applications=%s",
            company_id,
            application_ids,
        )
        return None

    render_result = await _render_and_store_requisites(
        company_id=company_id,
        questionnaire=questionnaire,
        company=dict(company) if company else None,
    )
    if render_result is None:
        return None
    stored, file_size = render_result

    document_id: uuid.UUID = await documents_repo.create_document(
        session,
        company_id=company_id,
        document_type=_DOCUMENT_TYPE,
        file_name="company-requisites.pdf",
        s3_key=stored.key,
        file_size=file_size,
        file_path=stored.public_url,
        related_application_id=application_ids[0],
        review_status="approved",
    )
    for app_id in application_ids:
        await documents_repo.link_to_application(
            session, document_id=document_id, application_id=app_id
        )
    logger.info(
        "company_requisites_attached company_id=%s document_id=%s applications=%s",
        company_id,
        document_id,
        application_ids,
    )
    return document_id


async def _render_and_store_requisites(
    *,
    company_id: uuid.UUID,
    questionnaire: dict[str, Any] | None,
    company: dict[str, Any] | None,
) -> tuple[document_storage.StoredDocument, int] | None:
    try:
        data = render_company_requisites_pdf(
            CompanyRequisitesInput(
                questionnaire=questionnaire,
                company=dict(company) if company else None,
            )
        )
    except Exception as exc:
        logger.warning(
            "company_requisites_skip reason=render_failed company_id=%s exc=%s",
            company_id,
            exc,
        )
        return None
    if not data:
        logger.warning(
            "company_requisites_skip reason=empty_pdf company_id=%s", company_id
        )
        return None

    key = document_storage.build_company_key(
        company_id,
        f"{uuid.uuid4().hex[:8]}_company-requisites.pdf",
    )
    try:
        stored = await document_storage.put_document(key, data, "application/pdf")
    except Exception as exc:
        logger.warning(
            "company_requisites_skip reason=storage_failed company_id=%s exc=%s",
            company_id,
            exc,
        )
        return None
    return stored, len(data)
