"""Upload XML accounting reports — normalize and persist row-level data.

POST /api/v1/accounting/upload-xml
    multipart/form-data, accepts .xml file
    Returns JSON summary with INN, year, period, per-form row counts.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.services.accounting_upload_service import upload_xml
from domain.services.object_storage import ObjectStorage
from domain.services.xml_accounting.errors import (
    UnsupportedReportError,
    XMLValidationError,
)
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_scopes

logger = logging.getLogger("carcraft-backend")
router = APIRouter()

_ACCOUNTING_WRITE = require_scopes("accounting:write")


@router.post(
    "/upload-xml",
    summary="Загрузить XML бухгалтерской отчётности",
    description=(
        "Принимает файл экспорта 1C (XML) с бухгалтерской отчётностью, "
        "парсит все формы (баланс, ОФР, ОДДС, изменения капитала) и "
        "сохраняет нормализованные строки в БД (upsert). "
        "Также сохраняет исходный XML-файл в хранилище объектов и "
        "привязывает его к заявке, если передан ``application_id``."
    ),
)
async def upload_accounting_xml(
    file: Annotated[UploadFile, File(description="XML файл бухгалтерской отчётности")],
    _user: Annotated[dict[str, Any], Depends(_ACCOUNTING_WRITE)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    application_id: Annotated[str | None, Form(description="ID заявки для привязки файла")] = None,
) -> JSONResponse:
    """Handle XML upload, parse, persist and store raw file."""
    if not file.filename or not file.filename.lower().endswith(".xml"):
        return JSONResponse(
            status_code=400,
            content={"detail": "Ожидается файл с расширением .xml"},
        )

    content = await file.read()
    if not content:
        return JSONResponse(
            status_code=400,
            content={"detail": "Файл пуст"},
        )

    company_id = _user.get("company_id")
    if not company_id:
        return JSONResponse(
            status_code=400,
            content={"detail": "Не удалось определить компанию пользователя"},
        )

    app_uuid: uuid.UUID | None = None
    if application_id:
        try:
            app_uuid = uuid.UUID(application_id)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Неверный формат application_id"},
            )

    try:
        result = await upload_xml(
            session,
            content,
            filename=file.filename or "report.xml",
            storage=storage,
            company_id=company_id,
            application_id=app_uuid,
        )
        await session.commit()
    except (UnsupportedReportError, XMLValidationError) as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        await session.rollback()
        logger.exception("XML accounting upload failed")
        raise

    return JSONResponse(content=jsonable_encoder(result))
