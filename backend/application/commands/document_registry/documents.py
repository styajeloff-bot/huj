"""Atomic registry commands; routers own commit, rollback and object cleanup."""
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.notifications.document_registry_expiry import (
    record_document_expiry_if_due,
)
from application.queries.document_registry import views
from domain.document_registry import (
    inherit_related,
    normalize_number,
    validate_identity,
    validate_participants,
    validate_period,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import document_registry_repository as repo
from infrastructure.repositories.document_registry_cleanup_repository import (
    lock_file_key,
)

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
_CONTENT_TYPES = {".pdf": "application/pdf", ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".xls": "application/vnd.ms-excel", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@dataclass(frozen=True)
class Upload:
    filename: str
    data: bytes


def _valid_signature(extension: str, data: bytes) -> bool:
    if extension == ".pdf":
        return data.startswith(b"%PDF-") and b"%%EOF" in data[-4096:]
    if extension in (".doc", ".xls"):
        return data.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    if extension in (".docx", ".xlsx"):
        try:
            with ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
                return "[Content_Types].xml" in names and ("word/document.xml" if extension == ".docx" else "xl/workbook.xml") in names
        except (BadZipFile, UnicodeError, ValueError, OSError):
            return False
    try:
        with Image.open(BytesIO(data)) as image:
            matches = image.format == ("PNG" if extension == ".png" else "JPEG")
            image.verify()
        # JPEG verification only checks headers; decoding also rejects truncation.
        with Image.open(BytesIO(data)) as image:
            image.load()
        return matches
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return False


def prepare_uploads(uploads: list[Upload], *, allow_empty: bool = False) -> list[tuple[str, str]]:
    if not (0 if allow_empty else 1) <= len(uploads) <= MAX_FILES:
        raise ServiceError("Выберите от 1 до 10 файлов", 422)
    result = []
    for upload in uploads:
        filename = PurePosixPath(upload.filename.replace("\\", "/")).name
        extension = PurePosixPath(filename).suffix.lower()
        if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
            raise ServiceError("Некорректное имя файла", 422)
        content_type = _CONTENT_TYPES.get(extension)
        if content_type is None:
            raise ServiceError("Допустимы PDF, DOC, DOCX, XLS, XLSX, PNG и JPEG", 415)
        if not upload.data:
            raise ServiceError("Файл не может быть пустым", 422)
        if len(upload.data) > MAX_FILE_BYTES:
            raise ServiceError("Размер файла не должен превышать 20 МиБ", 413)
        if not _valid_signature(extension, upload.data):
            raise ServiceError("Содержимое файла не соответствует его формату", 415)
        result.append((filename, content_type))
    return result


async def cleanup_uploads(storage: ObjectStorage, keys: list[str]) -> None:
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logging.getLogger("carcraft-backend").warning("document_registry_file_cleanup_failed key=%s", key)


async def _store_version(session: AsyncSession, document_id: UUID, payload: dict[str, Any], uploads: list[Upload], prepared: list[tuple[str, str]], actor: dict[str, Any], storage: ObjectStorage, keys: list[str], company_rows: list[dict[str, Any]], retained: list[dict[str, Any]]) -> None:
    version_id = uuid4()
    file_rows = [{"id": uuid4(), "version_id": version_id, "position": position, **{key: file[key] for key in ("file_name", "s3_key", "content_type", "file_size")}} for position, file in enumerate(retained)]
    for position, (upload, (filename, content_type)) in enumerate(zip(uploads, prepared, strict=True), start=len(retained)):
        file_id = uuid4()
        key = f"document-registry/{document_id}/{version_id}/{file_id}"
        keys.append(key)
        await lock_file_key(session, key)
        await storage.put(key, upload.data, content_type)
        file_rows.append({"id": file_id, "version_id": version_id, "file_name": filename, "s3_key": key, "content_type": content_type, "file_size": len(upload.data), "position": position})
    await repo.insert_version(session, document_id, {"id": version_id, "name": payload["name"].strip(), "platform_ml_related": bool(payload["related_companies"].get("platform_ml")), "valid_from": payload["valid_from"], "valid_to": payload.get("valid_to"), "uploaded_by": actor["user_id"]}, file_rows, company_rows)
    await record_document_expiry_if_due(session, document_id, actor_user_id=actor["user_id"])


async def _prepare(session: AsyncSession, payload: dict[str, Any], uploads: list[Upload]) -> list[tuple[str, str]]:
    from asyncio import to_thread
    try:
        validate_identity(payload["document_type"], payload["contract_number"], payload["name"])
        validate_period(payload["valid_from"], payload.get("valid_to"))
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    if not await repo.number_available(session, payload["contract_number"]):
        raise ServiceError("Номер используется", 409)
    return await to_thread(prepare_uploads, uploads)


async def create_document(session: AsyncSession, payload: dict[str, Any], uploads: list[Upload], actor: dict[str, Any], storage: ObjectStorage, keys: list[str], *, group_id: UUID | None = None) -> dict[str, Any]:
    prepared = await _prepare(session, payload, uploads)
    is_main = group_id is None
    related_payload = payload.get("related_companies") or {}
    try:
        if is_main:
            binding = payload["participants"]
            company_rows = await repo.resolve_companies(session, binding)
            await repo.validate_catalog(session, binding.get("mark_id"), binding.get("model_id"))
            validate_participants(binding)
            group_id = await repo.create_group(session, binding, company_rows, actor["user_id"])
        else:
            if group_id is None or await repo.lock_group(session, group_id) is None:
                raise ServiceError("Группа не найдена", 404)
            group_documents = await repo.get_group_documents(session, group_id, actor, views.today_msk())
            main = next((document for document in group_documents if document["is_main"]), None)
            if main is None:
                raise ServiceError("Группа не найдена", 404)
            related_payload = inherit_related(related_payload, main["related_companies"])
        related_rows = await repo.resolve_companies(session, related_payload)
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    document_id = uuid4()
    await repo.insert_document(session, {"id": document_id, "group_id": group_id, "is_main": is_main, "document_type": payload["document_type"], "contract_number": payload["contract_number"], "contract_number_normalized": normalize_number(payload["contract_number"]), "name": payload["name"].strip(), "platform_ml_related": bool(related_payload.get("platform_ml")), "created_by": actor["user_id"]}, related_rows)
    await _store_version(session, document_id, {**payload, "related_companies": related_payload}, uploads, prepared, actor, storage, keys, related_rows, [])
    return {"document": await views.get_document(session, document_id, actor)}


def _require_current_version(current: dict[str, Any], expected: UUID) -> None:
    if current["current_version"]["id"] != expected:
        raise ServiceError("Текущая версия изменилась. Обновите документ перед сохранением", 409)


async def new_version(session: AsyncSession, document_id: UUID, payload: dict[str, Any], uploads: list[Upload], actor: dict[str, Any], storage: ObjectStorage, keys: list[str]) -> dict[str, Any]:
    from asyncio import to_thread
    prepared = await to_thread(prepare_uploads, uploads, allow_empty=True)
    try:
        validate_period(payload["valid_from"], payload.get("valid_to"))
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    if not payload["name"].strip():
        raise ServiceError("Название обязательно", 422)
    if not await repo.lock_documents(session, [document_id]):
        raise ServiceError("Документ не найден", 404)
    current = await views.get_document(session, document_id, actor)
    _require_current_version(current, payload["expected_current_version_id"])
    identifiers = payload["retained_file_ids"]
    if len(set(identifiers)) != len(identifiers):
        raise ServiceError("Сохранённые файлы не должны повторяться", 422)
    retained = await repo.version_files(session, current["current_version"]["id"], identifiers)
    if len(retained) != len(identifiers):
        raise ServiceError("Сохранять можно только файлы текущей версии этого документа", 422)
    if not 1 <= len(retained) + len(uploads) <= MAX_FILES:
        raise ServiceError("В версии должно быть от 1 до 10 файлов", 422)
    try:
        related_rows = await repo.resolve_version_companies(session, payload["related_companies"], current["related_companies"])
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    await _store_version(session, document_id, payload, uploads, prepared, actor, storage, keys, related_rows, retained)
    return {"document": await views.get_document(session, document_id, actor)}


async def activate_version(session: AsyncSession, document_id: UUID, version_id: UUID, expected_current_version_id: UUID, actor: dict[str, Any]) -> dict[str, Any]:
    if not await repo.lock_documents(session, [document_id]):
        raise ServiceError("Документ не найден", 404)
    current = await views.get_document(session, document_id, actor)
    if current["current_version"]["id"] != version_id:
        _require_current_version(current, expected_current_version_id)
        if not await repo.set_current_version(session, document_id, version_id):
            raise ServiceError("Версия документа не найдена", 404)
    await record_document_expiry_if_due(session, document_id, actor_user_id=actor["user_id"], on_activation=True)
    return {"document": await views.get_document(session, document_id, actor)}


async def activation(session: AsyncSession, document_id: UUID, active: bool, actor: dict[str, Any]) -> dict[str, Any]:
    rows = await repo.lock_documents(session, [document_id])
    if not rows:
        raise ServiceError("Документ не найден", 404)
    if (rows[0]["deactivated_at"] is None) != active:
        await repo.update_document(session, document_id, {"deactivated_at": None if active else datetime.now(UTC), "deactivated_by": None if active else actor["user_id"]})
    if active:
        await record_document_expiry_if_due(session, document_id, actor_user_id=actor["user_id"], on_activation=True)
    return {"document": await views.get_document(session, document_id, actor)}


async def delete_document(session: AsyncSession, document_id: UUID, fingerprint: str | None, actor: dict[str, Any]) -> dict[str, Any]:
    if not await repo.lock_documents(session, [document_id]):
        raise ServiceError("Документ не найден", 404)
    usages = await views.deletion_usages(session, document_id)
    if fingerprint is None or fingerprint.strip('"') != usages["fingerprint"]:
        raise ServiceError("Состав связанных документов или условий изменился. Обновите предупреждение и подтвердите удаление", 409)
    await repo.lock_documents(session, usages["document_ids"])
    await repo.delete_documents(session, usages["document_ids"], actor["user_id"], datetime.now(UTC))
    return {"deleted_document_ids": usages["document_ids"]}


async def download(session: AsyncSession, file_id: UUID, actor: dict[str, Any], storage: ObjectStorage) -> dict[str, Any]:
    file = await repo.get_file(session, file_id, actor)
    if file is None:
        raise ServiceError("Файл не найден", 404)
    stored = await storage.get(file["s3_key"])
    if stored is None:
        raise ServiceError("Файл не найден в хранилище", 404)
    return {"filename": file["file_name"], "content_type": file["content_type"], "data": stored.data}
