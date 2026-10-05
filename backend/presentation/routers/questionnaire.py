"""`/api/v1/questionnaire/:id` — upsert of legal-entity questionnaire.

The checkout flow on the frontend calls ``PUT /api/v1/questionnaire/{id}``
to persist legal-entity data (company details, bank, director identity)
attached to a leasing application. This router is a thin wrapper around
:mod:`application.commands.leasing_applications_lc.upsert_questionnaire`
— the heavy lifting lives there.

Ownership is enforced via the Phase 3 aggregate root (``LeasingApplication``).
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.leasing_applications_lc import (
    UpsertQuestionnaireCommand,
    handle_upsert_questionnaire,
)
from application.errors import ServiceError, domain_to_http
from application.queries.applications.get_application import ApplicationAccessQuery
from application.queries.applications.resolve_leasing_company import (
    ResolveLeasingCompanyQuery,
    handle_resolve_leasing_company,
)
from application.queries.questionnaire_consent_document import (
    read_questionnaire_consent_document,
)
from application.services.questionnaire import (
    authorized_refresh_questionnaire,
    read_questionnaire,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import APPLICATIONS_READ, APPLICATIONS_WRITE
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import get_current_user, require_scopes

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


class QuestionnairePayload(BaseModel):
    """Open-ended questionnaire body — keeps legacy shape untouched.

    The Express route accepted an arbitrary dict and filtered fields by
    the destination table's columns. We replicate that behaviour on the
    FastAPI side (see
    :func:`infrastructure.repositories.application_repository.upsert_questionnaire`).
    """

    model_config = ConfigDict(extra="allow")


class QuestionnaireResponse(BaseModel):
    completed: bool
    progress: int
    message: str


@router.put(
    "/{application_id}",
    response_model=QuestionnaireResponse,
    summary="Сохранить анкету заявки",
    description=(
        "Upsert анкеты (`application_questionnaires`) для заданной "
        "заявки. Пишется содержимое тела запроса (неизвестные поля "
        "отбрасываются), обновляется `questionnaire_progress` и "
        "`questionnaire_completed` родительской заявки. Ownership: "
        "проверяется через Phase 3 aggregate root `LeasingApplication`."
    ),
    dependencies=[Depends(require_scopes(APPLICATIONS_WRITE))],
)
async def upsert_questionnaire(
    application_id: uuid.UUID,
    body: QuestionnairePayload,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await handle_resolve_leasing_company(
        ResolveLeasingCompanyQuery(
            company_id=user.get("company_id"),
            role=str(user.get("role") or ""),
        ),
        session,
    )
    try:
        result = await handle_upsert_questionnaire(
            UpsertQuestionnaireCommand(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
                payload=body.model_dump(exclude_unset=False),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


class QuestionnaireDataResponse(BaseModel):
    questionnaire: dict[str, Any]


class QuestionnaireRefreshResponse(QuestionnaireDataResponse):
    sources: dict[str, str]


async def _access_query(application_id: uuid.UUID, user: dict[str, Any], session: AsyncSession) -> ApplicationAccessQuery:
    lc_id = await handle_resolve_leasing_company(ResolveLeasingCompanyQuery(company_id=user.get("company_id"), role=str(user.get("role") or "")), session)
    return ApplicationAccessQuery(application_id=application_id, actor_id=user["id"], actor_role=str(user.get("role") or ""), actor_company_id=user.get("company_id"), actor_leasing_company_id=lc_id)


@router.get("/{application_id}", response_model=QuestionnaireDataResponse, summary="Получить анкету заявки", description="Проверяет доступ к заявке. Для ЛК возвращает только разрешённые ей поля; технические источники исключены.", dependencies=[Depends(require_scopes(APPLICATIONS_READ))])
async def get_questionnaire(application_id: uuid.UUID, user: Annotated[dict[str, Any], Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db)]) -> JSONResponse:
    try:
        result = await read_questionnaire(session, await _access_query(application_id, user, session))
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.post("/{application_id}/refresh", response_model=QuestionnaireRefreshResponse, summary="Обновить автоматические сведения анкеты", description="Повторяет ФНС/DaData/ЕГРЮЛ с сохранением ручных значений. Требует право редактирования заявки; ошибки источника оставляют сохранённые сведения.", dependencies=[Depends(require_scopes(APPLICATIONS_WRITE))])
async def refresh_questionnaire(application_id: uuid.UUID, user: Annotated[dict[str, Any], Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db)]) -> JSONResponse:
    try:
        result = await authorized_refresh_questionnaire(session, await _access_query(application_id, user, session))
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/consents/{signature_request_id}/content",
    response_model=None,
    response_class=Response,
    summary="Открыть подписанный СОПД из анкеты",
    description=(
        "Читает существующий подписанный файл без изменения документа. Проверяет доступ "
        "к заявке и конкретному полю анкеты; для ЛК — область согласия и отзыв. "
        "Чужой, скрытый, отозванный или заменённый СОПД недоступен."
    ),
    dependencies=[Depends(require_scopes(APPLICATIONS_READ))],
)
async def get_questionnaire_consent_document(
    application_id: uuid.UUID,
    signature_request_id: uuid.UUID,
    field: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    disposition: Literal["inline", "attachment"] = "attachment",
) -> Response:
    try:
        result = await read_questionnaire_consent_document(
            session, storage, await _access_query(application_id, user, session),
            signature_request_id, field,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return Response(
        content=result.data,
        media_type=result.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{result.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
