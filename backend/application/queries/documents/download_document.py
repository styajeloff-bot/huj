"""Fetch a document's binary payload from object storage.

Runs the same authorization checks as :mod:`get_document` (owner /
employee / selected LC) before streaming the file. Callers wrap the
returned dataclass into a ``Response`` with the appropriate
``Content-Disposition`` header.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.documents.get_document import (
    GetDocumentQuery,
    handle_get_document,
)
from domain.errors import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
    ObjectStorageUnavailableError,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import (
    application_documents_repository as app_docs_repo,
)


@dataclass
class DownloadDocumentQuery:
    document_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


@dataclass(frozen=True)
class DownloadedDocument:
    document_id: UUID
    filename: str
    content_type: str
    data: bytes


async def handle_download_document(
    query: DownloadDocumentQuery,
    session: AsyncSession,
    storage: ObjectStorage,
) -> DownloadedDocument:
    doc = await handle_get_document(
        GetDocumentQuery(
            document_id=query.document_id,
            actor_user_id=query.actor_user_id,
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            actor_leasing_company_id=query.actor_leasing_company_id,
        ),
        session,
    )
    if query.actor_role == "leasing_company" and (
        query.actor_leasing_company_id is None
        or not await app_docs_repo.document_request_visible_to_lc(
            session, document_id=query.document_id,
            leasing_company_id=query.actor_leasing_company_id,
        )
    ):
        raise DocumentAccessDeniedError()
    s3_key = doc.get("s3_key")
    if not s3_key:
        # Nothing to download — row exists but no stored payload.
        raise DocumentNotFoundError(query.document_id)
    obj = await storage.get(str(s3_key))
    if obj is None:
        raise ObjectStorageUnavailableError(
            "Файл не найден в хранилище объектов"
        )
    filename = str(doc.get("file_name") or f"document_{query.document_id}")
    return DownloadedDocument(
        document_id=doc["id"],
        filename=filename,
        content_type=obj.content_type or "application/octet-stream",
        data=obj.data,
    )
