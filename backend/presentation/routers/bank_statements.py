"""Bank statement upload and analytics routes."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.bank_statement_analytics import (
    GetBankStatementAnalyticsQuery,
    handle_get_bank_statement_analytics,
)
from application.queries.leasing import ResolveActorLcQuery, handle_resolve_actor_lc
from application.services.bank_statement_upload_service import (
    BankStatementUploadFile,
    upload_bank_statements,
)
from domain.errors import DomainError
from domain.services.bank_statements.errors import BankStatementParseError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import APPLICATIONS_WRITE
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_scopes
from presentation.schemas.bank_statements import (
    BankStatementAnalyticsResponse,
    BankStatementUploadResponse,
)

logger = logging.getLogger("carcraft-backend")
router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _resolve_actor_lc(
    session: AsyncSession, user: dict[str, Any]
) -> UUID | None:
    return await handle_resolve_actor_lc(
        ResolveActorLcQuery(
            user_id=user["id"],
            role=str(user.get("role") or ""),
        ),
        session,
    )


@router.post(
    "/uploads",
    response_model=BankStatementUploadResponse,
    summary="Загрузить банковскую выписку",
    description=(
        "Принимает один или несколько .txt файлов 1CClientBankExchange, "
        "сохраняет исходный файл как документ, распознает операции через "
        "carcraft-bor и сохраняет счета клиента и транзакции."
    ),
)
async def upload_bank_statement_files(
    files: Annotated[list[UploadFile], File(description="TXT банковские выписки")],
    user: Annotated[dict[str, Any], Depends(require_scopes(APPLICATIONS_WRITE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    application_id: Annotated[UUID | None, Form(description="ID заявки")] = None,
) -> JSONResponse:
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".txt"):
            raise HTTPException(
                status_code=400,
                detail="Неверный формат. Загрузите файл в формате .txt",
            )

    uploaded: list[BankStatementUploadFile] = []
    for file in files:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Файл пуст")
        uploaded.append(
            BankStatementUploadFile(filename=file.filename or "statement.txt", data=data)
        )

    actor_company_id_raw = user.get("company_id")
    actor_company_id = (
        UUID(str(actor_company_id_raw)) if actor_company_id_raw else None
    )

    try:
        result = await upload_bank_statements(
            session,
            files=uploaded,
            storage=storage,
            actor_user_id=UUID(str(user["id"])),
            actor_role=str(user.get("role") or ""),
            actor_company_id=actor_company_id,
            application_id=application_id,
        )
        await session.commit()
    except BankStatementParseError:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail="Файл не является банковской выпиской. Проверьте содержимое файла",
        )
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    except Exception:
        await session.rollback()
        logger.exception("Bank statement upload failed")
        raise

    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/companies/{company_id}/analytics",
    response_model=BankStatementAnalyticsResponse,
    summary="Аналитика банковских выписок компании",
    description=(
        "Возвращает агрегированный dashboard по загруженным банковским "
        "выпискам: счета, период, KPI, cashflow, структуру расходов и "
        "топ контрагентов."
    ),
)
async def get_bank_statement_analytics(
    company_id: UUID,
    user: Annotated[dict[str, Any], Depends(require_scopes("accounting:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        actor_user = dict(user)
        actor_user["leasing_company_id"] = await _resolve_actor_lc(session, user)
        result = await handle_get_bank_statement_analytics(
            GetBankStatementAnalyticsQuery(company_id=company_id),
            session,
            actor_user,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))
