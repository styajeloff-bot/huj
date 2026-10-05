"""Authorized module files, using the existing object-storage port."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.deals import require_revision, require_write
from application.errors import ServiceError
from application.queries.monetization.views import (
    ROLE_PARTY,
    document_view,
    is_deal_participant,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import monetization_repository as repo

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
_CONTENT_TYPES = {
    ".pdf": "application/pdf", ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".txt": "text/plain",
}


@dataclass(frozen=True)
class Upload:
    filename: str
    data: bytes


def prepare_upload(file: Upload) -> tuple[str, str]:
    filename = PurePosixPath(file.filename.replace("\\", "/")).name
    if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
        raise ServiceError("Некорректное имя файла", 400)
    content_type = _CONTENT_TYPES.get(PurePosixPath(filename).suffix.lower())
    if content_type is None:
        raise ServiceError("Допустимы PDF, Word, Excel, PNG, JPEG и TXT", 400)
    if not file.data:
        raise ServiceError("Файл не может быть пустым", 400)
    if len(file.data) > MAX_FILE_BYTES:
        raise ServiceError("Размер файла не должен превышать 20 МБ", 413)
    return filename, content_type


async def upload_files(
    session: AsyncSession, entity_id: UUID, actor: dict[str, Any],
    files: list[Upload], storage: ObjectStorage, *,
    kind: str, revision: int | None = None,
) -> dict[str, Any]:
    require_write(actor)
    if not files or len(files) > MAX_FILES:
        raise ServiceError("Выберите от 1 до 10 файлов", 400)
    prepared = [prepare_upload(file) for file in files]
    party = ROLE_PARTY[actor["role"]]
    if kind == "contracts":
        if party != "admin":
            raise ServiceError("Недостаточно прав", 403)
        parent = await repo.get_program(session, entity_id, actor)
    else:
        parent = await repo.lock_deal(session, entity_id, actor)
    if parent is None:
        raise ServiceError("Запись монетизации не найдена", 404)
    if kind == "deals":
        require_revision(parent, revision if revision is not None else 0)
        if parent["status"] == "paid":
            raise ServiceError("Документы оплаченной сделки нельзя изменять", 409)
        if not is_deal_participant(parent, actor):
            raise ServiceError("Вы не являетесь подтверждающей стороной сделки", 403)
    keys: list[str] = []
    documents = []
    try:
        for file, (filename, content_type) in zip(files, prepared, strict=True):
            key = f"monetization/{kind}/{entity_id}/{uuid4()}"
            keys.append(key)
            await storage.put(key, file.data, content_type)
            values = {"object_key": key, "filename": filename,
                      "content_type": content_type, "size_bytes": len(file.data)}
            if kind == "contracts":
                saved = await repo.add_contract(session, entity_id, values, actor["user_id"])
            else:
                values.update(participant_type=party, participant_company_id=actor.get("company_id"),
                              revision=parent["revision"])
                saved = await repo.add_document(session, entity_id, values, actor["user_id"])
            documents.append(document_view(saved, kind=kind, revision=revision))
    except Exception:
        await cleanup_uploads(storage, keys)
        raise
    return {"documents": documents, "stored_keys": keys}


async def cleanup_uploads(storage: ObjectStorage, keys: list[str]) -> None:
    import logging

    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logging.getLogger("carcraft-backend").warning(
                "monetization_file_cleanup_failed key=%s", key)


async def download_file(
    session: AsyncSession, document_id: UUID, actor: dict[str, Any],
    storage: ObjectStorage, kind: str,
) -> dict[str, Any]:
    if kind == "contracts":
        document = await repo.get_contract(session, document_id, actor)
    elif kind == "deals":
        document = await repo.get_document(session, document_id, actor)
    elif kind == "supports":
        document = await repo.get_support_document(session, document_id, actor)
    else:
        document = None
    if document is None:
        raise ServiceError("Документ не найден", 404)
    key = document.get("object_key")
    if not key:
        raise ServiceError("Документ недоступен в хранилище", 404)
    if kind == "supports":
        # Legacy support files store the canonical URL returned by this port.
        # Recover only a key under our own storage base; never fetch a remote URL.
        base = storage.public_url("")
        if not key.startswith(base):
            raise ServiceError("Документ недоступен в хранилище", 404)
        key = key[len(base):]
    stored = await storage.get(key)
    if stored is None:
        raise ServiceError("Документ не найден в хранилище", 404)
    return {"filename": document["filename"], "content_type": stored.content_type,
            "data": stored.data}
