"""Attach an EGRUL extract to its application without duplicate downloads."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_documents_repository as app_docs
from infrastructure.repositories import application_repository as apps
from infrastructure.repositories import documents_repository as documents
from infrastructure.services import document_storage
from infrastructure.services.egrul_extract import fetch_egrul_extract

logger = logging.getLogger("carcraft-backend")
DOCUMENT_TYPE = "egrul"


async def sync_egrul_application_documents(session: AsyncSession, application_id: UUID, leasing_company_ids: list[UUID]) -> None:
    document_id = await documents.find_document_id_by_type_for_applications(
        session, application_ids=[application_id], document_type=DOCUMENT_TYPE,
    )
    if document_id is None:
        return
    for leasing_company_id in leasing_company_ids:
        await app_docs.upsert_application_document(
            session, application_id=application_id, document_id=document_id,
            leasing_company_id=leasing_company_id, status="submitted",
            user_title="Выписка ЕГРЮЛ",
        )


async def attach_egrul_to_application(session: AsyncSession, *, application_id: UUID, company_id: UUID, inn: str | None, ogrn: str | None) -> str:
    application = await apps.get_by_id(session, application_id, for_update=True)
    if application is None or application["company_id"] != company_id:
        return "unavailable"
    document_id = await documents.find_document_id_by_type_for_applications(
        session, application_ids=[application_id], document_type=DOCUMENT_TYPE,
    )
    links = await apps.list_lc_links(session, application_id)
    leasing_company_ids = [link["leasing_company_id"] for link in links]
    if document_id is not None:
        await sync_egrul_application_documents(session, application_id, leasing_company_ids)
        return "already_attached"
    extract = await fetch_egrul_extract(inn=inn, ogrn=ogrn)
    if extract.status != "updated":
        return extract.status
    key = document_storage.build_application_key(application_id, "egrul.pdf")
    try:
        stored = await document_storage.put_document(key, extract.content, "application/pdf")
    except Exception:
        logger.warning("egrul_storage_unavailable application_id=%s", application_id)
        return "unavailable"
    try:
        async with session.begin_nested():
            document_id = await documents.create_document(
                session, company_id=company_id, document_type=DOCUMENT_TYPE,
                file_name=extract.filename, s3_key=stored.key,
                file_size=len(extract.content), file_path=stored.public_url,
                related_application_id=application_id,
            )
            await documents.link_to_application(session, document_id=document_id, application_id=application_id)
            await sync_egrul_application_documents(session, application_id, leasing_company_ids)
    except Exception:
        await document_storage.delete_document(key)
        raise
    return "updated"
