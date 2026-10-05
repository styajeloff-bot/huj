"""Keep uploaded passport images among application documents."""
from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_documents_repository as app_docs
from infrastructure.repositories import application_repository as apps
from infrastructure.repositories import documents_repository as documents
from infrastructure.services import document_storage

PASSPORT_DOCUMENT_TYPES = frozenset({"sopd_passport_main", "sopd_passport_registration"})


async def sync_passport_application_documents(session: AsyncSession, application_id: UUID, leasing_company_ids: list[UUID]) -> None:
    rows = await documents.list_for_application(session, application_id=application_id)
    for row in rows:
        if row["document_type"] in PASSPORT_DOCUMENT_TYPES:
            await _sync_document(session, application_id, row["id"], row["file_name"], leasing_company_ids)


async def _sync_document(session: AsyncSession, application_id: UUID, document_id: UUID, title: str, leasing_company_ids: list[UUID]) -> None:
    for leasing_company_id in leasing_company_ids:
        await app_docs.upsert_application_document(
            session, application_id=application_id, document_id=document_id,
            leasing_company_id=leasing_company_id, status="submitted", user_title=title,
        )


async def attach_passport_images(
    session: AsyncSession, *, application_id: UUID, signer_key: str,
    pages: list[dict[str, Any]],
) -> None:
    application = await apps.get_by_id(session, application_id, for_update=True)
    if application is None:
        return
    rows = await documents.list_for_application(session, application_id=application_id)
    links = await apps.list_lc_links(session, application_id)
    leasing_company_ids = [link["leasing_company_id"] for link in links]
    signer_hash = hashlib.sha256(signer_key.encode()).hexdigest()[:16]
    for page in pages:
        digest = hashlib.sha256(page["content"]).hexdigest()
        metadata = {"signer_key": signer_key, "file_hash": digest, "page": page["page"]}
        if any(row["document_type"] in PASSPORT_DOCUMENT_TYPES and row.get("extracted_data") == metadata for row in rows):
            continue
        extension = ".png" if page["content_type"] == "image/png" else ".jpg"
        filename = f"passport-{signer_hash}-{page['page']}-{digest[:16]}{extension}"
        original_name = PurePosixPath(str(page.get("filename") or filename).replace("\\", "/")).name[:255]
        display_name = original_name or filename
        key = document_storage.build_application_key(application_id, filename)
        stored = await document_storage.put_document(key, page["content"], page["content_type"])
        try:
            document_id = await documents.create_document(
                session, company_id=application["company_id"],
                document_type="sopd_passport_" + page["page"], file_name=display_name,
                s3_key=stored.key, file_size=len(page["content"]),
                file_path=stored.public_url, related_application_id=application_id,
                extracted_data=metadata,
            )
            await documents.link_to_application(session, document_id=document_id, application_id=application_id)
            await _sync_document(session, application_id, document_id, display_name, leasing_company_ids)
        except Exception:
            await document_storage.delete_document(key)
            raise
