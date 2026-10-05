"""Upload a Bill of Lading file for a support program."""
from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    InvalidUploadError,
    SupportProgramNotFoundError,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import support_repository

# Allowed file extensions and content types — mirror Express multer rules.
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".doc", ".docx", ".pptx"})
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
)
# 50 MB upper bound; pydantic schema enforces a tighter limit on request side.
MAX_BILL_OF_LADING_SIZE = 50 * 1024 * 1024


@dataclass
class UploadedBillOfLadingFile:
    filename: str
    content_type: str
    data: bytes


@dataclass
class UploadBillOfLadingCommand:
    program_id: UUID
    file: UploadedBillOfLadingFile
    bill_date: _dt.date | None = None
    comment: str | None = None


def _safe_filename(filename: str) -> str:
    base = PurePosixPath(filename).name or "file"
    # Replace path separators just in case.
    return base.replace("/", "_").replace("\\", "_")


async def handle_upload_bill_of_lading(
    cmd: UploadBillOfLadingCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    program = await support_repository.get_program_by_id(session, cmd.program_id)
    if program is None:
        raise SupportProgramNotFoundError(cmd.program_id)

    file = cmd.file
    if not file.data:
        raise InvalidUploadError("Пустой файл")
    if len(file.data) > MAX_BILL_OF_LADING_SIZE:
        raise InvalidUploadError("Размер файла превышает допустимый лимит")

    safe_name = _safe_filename(file.filename)
    ext = PurePosixPath(safe_name).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise InvalidUploadError(
            "Допускаются только файлы PDF, DOC, DOCX, PPTX"
        )
    if file.content_type and file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidUploadError(
            f"Неподдерживаемый тип файла: {file.content_type}"
        )

    key = (
        f"support-programs/{cmd.program_id}/bol/{uuid.uuid4().hex}_{safe_name}"
    )
    content_type = file.content_type or "application/octet-stream"
    url = await storage.put(key, file.data, content_type)

    saved = await support_repository.insert_bill_of_lading(
        session,
        program_id=cmd.program_id,
        bill_date=cmd.bill_date,
        file_name=safe_name,
        file_path=url,
        file_size=len(file.data),
        comment=cmd.comment,
    )

    refreshed = await support_repository.get_program_by_id(session, cmd.program_id)
    assert refreshed is not None
    return {
        "message": "Файл накладной загружен",
        "support_program": refreshed,
        "bill_of_lading": saved,
    }
