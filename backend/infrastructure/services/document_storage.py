"""Document object-storage helper.

Thin wrapper around :mod:`infrastructure.services.object_storage` that
encodes the naming convention for documents inside the configured S3
bucket. Keys follow the same shape Express used so that documents
uploaded by either backend remain reachable:

    {prefix}/company_{company_id}/{filename}
    {prefix}/application_{application_id}/{filename}
    {prefix}/user_{user_id}/{filename}

Filename collisions are avoided by callers — typically by prepending a
short UUID4 fragment.

Returning ``StorageObject`` keeps the calling code free of awareness
about the underlying provider.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from infrastructure.services.object_storage import get_object_storage
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True)
class StoredDocument:
    key: str
    public_url: str


def _company_prefix(company_id: UUID) -> str:
    return f"{settings.document_storage_prefix}/company_{company_id}"


def _application_prefix(application_id: UUID) -> str:
    return f"{settings.document_storage_prefix}/application_{application_id}"


def _user_prefix(user_id: UUID) -> str:
    return f"{settings.document_storage_prefix}/user_{user_id}"


def build_company_key(company_id: UUID, filename: str) -> str:
    return f"{_company_prefix(company_id)}/{filename}"


def build_application_key(application_id: UUID, filename: str) -> str:
    return f"{_application_prefix(application_id)}/{filename}"


def build_user_key(user_id: UUID, filename: str) -> str:
    return f"{_user_prefix(user_id)}/{filename}"


def build_compensation_key(compensation_id: UUID, filename: str) -> str:
    return f"{settings.document_storage_prefix}/compensation_{compensation_id}/{filename}"


async def put_document(
    key: str,
    data: bytes,
    content_type: str,
) -> StoredDocument:
    storage = get_object_storage()
    public_url = await storage.put(key, data, content_type)
    return StoredDocument(key=key, public_url=public_url)


async def get_document(key: str) -> bytes | None:
    storage = get_object_storage()
    obj = await storage.get(key)
    return obj.data if obj else None


async def delete_document(key: str) -> bool:
    storage = get_object_storage()
    return await storage.delete(key)


def public_url(key: str) -> str:
    return get_object_storage().public_url(key)
