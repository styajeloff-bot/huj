"""Build a ZIP archive of every document attached to an application.

Authorizes the call through the same rules as
:mod:`list_documents_for_application`, then fetches each document's
bytes from object storage and packages them into an in-memory ZIP.
The bytes are returned to the router which streams them via
``StreamingResponse``.
"""
from __future__ import annotations

import io
import uuid
import zipfile
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.documents.list_documents_for_application import (
    ListDocumentsForApplicationQuery,
    handle_list_documents_for_application,
)
from domain.services.object_storage import ObjectStorage


@dataclass
class DownloadApplicationArchiveQuery:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


@dataclass(frozen=True)
class ApplicationArchive:
    application_id: uuid.UUID
    filename: str
    data: bytes
    included_count: int


async def handle_download_application_archive(
    query: DownloadApplicationArchiveQuery,
    session: AsyncSession,
    storage: ObjectStorage,
) -> ApplicationArchive:
    listing = await handle_list_documents_for_application(
        ListDocumentsForApplicationQuery(
            application_id=query.application_id,
            actor_user_id=query.actor_user_id,
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            actor_leasing_company_id=query.actor_leasing_company_id,
        ),
        session,
    )
    documents = listing.get("documents") or []
    buffer = io.BytesIO()
    included = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        seen_names: set[str] = set()
        for doc in documents:
            s3_key = doc.get("s3_key")
            if not s3_key:
                continue
            obj = await storage.get(str(s3_key))
            if obj is None:
                continue
            display = str(
                doc.get("file_name")
                or f"document_{doc.get('id')}"
            )
            name = _unique_name(display, seen_names)
            seen_names.add(name)
            zf.writestr(name, obj.data)
            included += 1
    data = buffer.getvalue()
    buffer.close()
    return ApplicationArchive(
        application_id=query.application_id,
        filename=f"application_{query.application_id}_documents.zip",
        data=data,
        included_count=included,
    )


def _unique_name(base: str, seen: set[str]) -> str:
    """Avoid filename collisions inside the ZIP by appending a counter."""
    if base not in seen:
        return base
    counter = 2
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    while True:
        candidate = f"{stem}_{counter}{('.' + ext) if ext else ''}"
        if candidate not in seen:
            return candidate
        counter += 1
