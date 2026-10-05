"""Authorised downloads of deal files and the employees a party administrator may assign.

The ACL of ``file_access`` is applied to every channel on its own: a single download and
every entry of the ZIP are checked against the actor, so a known file id or storage key
never reaches a file the actor may not read. A refusal looks exactly like a missing file.
"""
from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import file_access
from application.fast_deals.access import load_context
from application.fast_deals.actor import Actor
from domain.errors import ObjectStorageUnavailableError
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import (
    FastDealAccessDeniedError,
    FastDealFileTooLargeError,
    FastDealNotFoundError,
)
from domain.services.object_storage import ObjectStorage, StoredObject
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_file_repository as file_repo

logger = logging.getLogger("carcraft-backend")

Record = dict[str, Any]

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024  # the ZIP is built in memory
_MIB = 1024 * 1024
_NO_FILE = "Файл не найден"
_NEUTRAL_CONTENT_TYPE = "application/octet-stream"
# Types a browser would render or execute from our origin; the uploader's declared type
# is never trusted, so these are served as plain downloads.
_ACTIVE_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
        "text/xml",
        "application/xml",
        "text/javascript",
        "application/javascript",
        "text/css",
    }
)


@dataclass(frozen=True)
class DownloadedFile:
    filename: str
    content_type: str
    data: bytes


def _served_content_type(declared: str | None) -> str:
    content_type = file_access.safe_content_type(declared)
    return _NEUTRAL_CONTENT_TYPE if content_type in _ACTIVE_CONTENT_TYPES else content_type


async def _read_object(storage: ObjectStorage, key: str) -> StoredObject | None:
    try:
        return await storage.get(key)
    except Exception as exc:
        logger.warning("fast_deal_file_read_failed key=%s", key, exc_info=True)
        raise ObjectStorageUnavailableError from exc


async def handle_download_file(
    actor: Actor,
    deal_id: UUID,
    file_id: UUID,
    session: AsyncSession,
    storage: ObjectStorage,
) -> DownloadedFile:
    ctx = await load_context(session, actor, deal_id, lock=False)
    file: Record | None = await file_repo.get_file(session, file_id)
    if file is None or not file_access.can_read_file(ctx, file):
        raise FastDealNotFoundError(_NO_FILE)
    stored = await _read_object(storage, file["storage_key"])
    if stored is None:
        logger.warning("fast_deal_file_object_missing key=%s", file["storage_key"])
        raise ObjectStorageUnavailableError("Файл не найден в хранилище объектов")
    return DownloadedFile(
        filename=file_access.safe_filename(file["filename"]),
        content_type=_served_content_type(file["content_type"]),
        data=stored.data,
    )


def _distinct_objects(files: list[Record]) -> list[Record]:
    """One entry per stored object: addressee rows of one upload share their key."""
    seen: set[str] = set()
    distinct: list[Record] = []
    for file in files:
        if file["storage_key"] not in seen:
            seen.add(file["storage_key"])
            distinct.append(file)
    return distinct


async def handle_download_archive(
    actor: Actor, deal_id: UUID, session: AsyncSession, storage: ObjectStorage
) -> DownloadedFile:
    """ZIP of only the files the actor may read, with unique safe names."""
    ctx = await load_context(session, actor, deal_id, lock=False)
    rows: list[Record] = await file_repo.list_files(session, deal_id)
    readable = _distinct_objects([row for row in rows if file_access.can_read_file(ctx, row)])
    if not readable:
        raise FastDealNotFoundError("Нет доступных файлов для скачивания")
    if sum(int(file["size_bytes"]) for file in readable) > MAX_ARCHIVE_BYTES:
        raise FastDealFileTooLargeError(
            f"Файлы занимают больше {MAX_ARCHIVE_BYTES // _MIB} МБ. Скачайте их по одному"
        )

    buffer = io.BytesIO()
    taken: set[str] = set()
    included = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in readable:
            stored = await _read_object(storage, file["storage_key"])
            if stored is None:
                logger.warning("fast_deal_file_object_missing key=%s", file["storage_key"])
                continue
            name = file_access.unique_name(file_access.safe_filename(file["filename"]), taken)
            # Compression of a large file must not stall the event loop.
            await asyncio.to_thread(archive.writestr, name, stored.data)
            included += 1
    if included == 0:
        raise ObjectStorageUnavailableError("Файлы не найдены в хранилище объектов")
    return DownloadedFile(
        filename=f"fast-deal_{ctx.deal['display_number']}_files.zip",
        content_type="application/zip",
        data=buffer.getvalue(),
    )


async def handle_assignable_employees(
    actor: Actor, deal_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    """Active members of the actor's own party company; only for its administrator."""
    ctx = await load_context(session, actor, deal_id, lock=False)
    if Action.ASSIGN_EMPLOYEES not in ctx.actions() or actor.company_id is None:
        raise FastDealAccessDeniedError(
            "Ответственных назначает администратор компании, участвующей в сделке"
        )
    employees: list[Record] = await access_repo.eligible_employees(session, actor.company_id)
    return {
        "items": [
            {
                "id": employee["id"],
                "name": employee["name"],
                "email": employee["email"],
                "sub_role": employee["sub_role"],
            }
            for employee in employees
        ]
    }
