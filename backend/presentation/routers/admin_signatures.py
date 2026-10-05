"""Admin-side signature_request routes (carcraft_employee only)."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.sign_document import (
    CancelSignatureCommand,
    handle_cancel_signature,
)
from application.errors import ServiceError, domain_to_http
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles

router = APIRouter()
_ADMIN = require_roles("carcraft_employee")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post(
    "/signatures/{request_id}/cancel",
    summary="Отменить запрос на подпись",
    description=(
        "Переводит pending → cancelled (например, при отклонении заявки). "
        "Доступно только `carcraft_employee`. Уже подписанные документы "
        "возвращают 409."
    ),
)
async def cancel_signature_admin(
    request_id: Annotated[UUID, Path()],
    _user: Annotated[dict[str, Any], Depends(_ADMIN)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        cancelled = await handle_cancel_signature(
            CancelSignatureCommand(request_id=request_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder({"request": cancelled}))
