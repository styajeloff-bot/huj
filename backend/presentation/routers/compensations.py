"""Compensation routes."""
from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.compensations import (
    CancelSupportCompensationsCommand,
    CreateBulkCompensationsCommand,
    CreateCompensationCommand,
    RecalculateCompensationsCommand,
    UpdateCompensationStatusCommand,
    UploadCompensationDocumentCommand,
    handle_cancel_support_compensations,
    handle_create_bulk_compensations,
    handle_create_compensation,
    handle_download_compensation_document,
    handle_recalculate_compensations,
    handle_update_compensation_status,
    handle_upload_compensation_document,
)
from application.errors import ServiceError, domain_to_http
from application.queries.compensations import (
    GetCompensationQuery,
    GetCompensationsBySupportQuery,
    ListCompensationsQuery,
    handle_get_compensation,
    handle_get_compensations_by_support,
    handle_list_compensations,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.schemas.compensations import (
    CancelCompensationsResponse,
    CompensationDocumentUploadResponse,
    CompensationResponse,
    CompensationsListResponse,
    CompensationsResponse,
    CreateBulkCompensationsRequest,
    CreateCompensationRequest,
    RecalculateRequest,
    RecalculateResponse,
    UpdateCompensationStatusRequest,
)

router = APIRouter()

_any_authenticated = get_current_user
# Create/recalculate compensations — granted to employees, dealers, and
# distributors (they all hold `compensations:write`).
_admin_or_dealer_or_distributor = require_scopes("compensations:write")
# Employee-only admin action (bulk cancellation of support compensations).
_admin_only = require_scopes("compensations:admin")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _uuid_query_filter(value: str | None, label: str) -> UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return UUID(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{label} должен быть UUID в формате xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        ) from exc


def _text_query_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _disposition_headers(filename: str) -> dict[str, str]:
    ascii_fallback = (
        filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    )
    encoded = quote(filename, safe="")
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_fallback}"; '
            f"filename*=UTF-8''{encoded}"
        ),
        "X-Content-Type-Options": "nosniff",
    }


@router.get(
    "",
    response_model=CompensationsListResponse,
    summary="Реестр компенсаций",
    description=(
        "Возвращает список компенсаций с фильтрами. "
        "Админ видит все; остальные — только компенсации, в которых они являются "
        "плательщиком или получателем."
    ),
)
async def list_compensations(
    user: Annotated[dict, Depends(_any_authenticated)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    application_query: Annotated[
        str | None,
        Query(
            description="Номер заявки или UUID заявки для поиска в реестре компенсаций.",
        ),
    ] = None,
    support_query: Annotated[
        str | None,
        Query(
            description=(
                "Название применённой поддержки, UUID применённой поддержки "
                "или UUID исходной программы поддержки."
            ),
        ),
    ] = None,
    application_id: Annotated[
        str | None,
        Query(description="Точный UUID заявки. Для поиска по номеру используйте application_query."),
    ] = None,
    applied_support_id: Annotated[
        str | None,
        Query(description="Точный UUID применённой поддержки."),
    ] = None,
    status: str | None = None,
    payer: str | None = None,
    recipient: str | None = None,
    source: Annotated[
        str | None,
        Query(pattern="^(platform|exchange|fast_deal)$"),
    ] = None,
    due_date_from: Annotated[date | None, Query()] = None,
    due_date_to: Annotated[date | None, Query()] = None,
) -> JSONResponse:
    parsed_application_id = _uuid_query_filter(application_id, "ID заявки")
    parsed_support_id = _uuid_query_filter(
        applied_support_id, "ID применённой поддержки"
    )
    try:
        result = await handle_list_compensations(
            ListCompensationsQuery(
                user_role=user["role"],
                actor_company_id=user.get("company_id"),
                page=page,
                limit=limit,
                application_id=parsed_application_id,
                application_query=_text_query_filter(application_query),
                applied_support_id=parsed_support_id,
                support_query=_text_query_filter(support_query),
                status=status,
                payer=payer,
                recipient=recipient,
                source=source,
                due_date_from=due_date_from,
                due_date_to=due_date_to,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{compensation_id}",
    response_model=CompensationResponse,
    summary="Детали компенсации",
    description="Возвращает полную информацию по одной компенсации.",
)
async def get_compensation(
    compensation_id: UUID,
    user: Annotated[dict, Depends(_any_authenticated)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_compensation(
            GetCompensationQuery(
                compensation_id=compensation_id,
                user_role=user["role"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content={"compensation": jsonable_encoder(result)})


@router.post(
    "/{compensation_id}/documents",
    status_code=201,
    response_model=CompensationDocumentUploadResponse,
    summary="Загрузить документ компенсации",
    description=(
        "Загружает файл для акцепта, отказа или оплаты компенсации. "
        "Файл сохраняется в object storage, а вернувшийся объект нужно "
        "передать в `documents` при смене статуса компенсации."
    ),
)
async def upload_compensation_document(
    compensation_id: UUID,
    user: Annotated[dict, Depends(_any_authenticated)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    file: Annotated[UploadFile, File(...)],
    purpose: Annotated[
        Literal["acceptance", "rejection", "payment"],
        Form(description="Назначение файла: acceptance, rejection или payment."),
    ],
) -> JSONResponse:
    try:
        document = await handle_upload_compensation_document(
            UploadCompensationDocumentCommand(
                compensation_id=compensation_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                purpose=purpose,
                filename=file.filename or "document",
                content_type=file.content_type or "application/octet-stream",
                data=await file.read(),
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(
        content={"document": jsonable_encoder(document)},
        status_code=201,
    )


@router.get(
    "/{compensation_id}/documents/{document_id}/content",
    summary="Скачать документ компенсации",
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_compensation_document(
    compensation_id: UUID,
    document_id: str,
    user: Annotated[dict, Depends(_any_authenticated)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        document = await handle_download_compensation_document(
            compensation_id=compensation_id,
            document_id=document_id,
            actor_role=str(user.get("role") or ""),
            actor_company_id=user.get("company_id"),
            session=session,
            storage=storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=document.data,
        media_type=document.content_type,
        headers=_disposition_headers(document.filename),
    )


@router.get(
    "/support/{applied_support_id}",
    response_model=CompensationsResponse,
    summary="Компенсации по программе поддержки",
    description=(
        "Возвращает компенсации для прикреплённой программы поддержки "
        "(`applied_support`)."
    ),
)
async def get_compensations_by_support(
    applied_support_id: UUID,
    user: Annotated[dict, Depends(_any_authenticated)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_compensations_by_support(
            GetCompensationsBySupportQuery(
                applied_support_id=applied_support_id,
                user_role=user["role"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "",
    status_code=201,
    response_model=CompensationResponse,
    summary="Создать компенсацию",
    description="Создаёт одну компенсацию для применённой программы поддержки.",
)
async def create_compensation(
    body: CreateCompensationRequest,
    user: Annotated[dict, Depends(_admin_or_dealer_or_distributor)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_compensation(
            CreateCompensationCommand(
                applied_support_id=body.applied_support_id,
                application_id=body.application_id,
                vehicle_id=body.vehicle_id,
                payer=body.payer,
                recipient=body.recipient,
                calculation_base=body.calculation_base,
                calculation_base_amount=body.calculation_base_amount,
                value_type=body.value_type,
                value=body.value,
                min_amount=body.min_amount,
                max_amount=body.max_amount,
                min_percent=body.min_percent,
                max_percent=body.max_percent,
                payment_schedule_type=body.payment_schedule_type,
                payment_schedule_period=body.payment_schedule_period,
                payment_schedule_value=body.payment_schedule_value,
                comment=body.comment or "",
                created_by=user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"compensation": jsonable_encoder(result)}, status_code=201)


@router.patch(
    "",
    status_code=201,
    response_model=CompensationsResponse,
    summary="Batch-создание компенсаций для одной программы поддержки",
    description=(
        "Создаёт до 4 компенсаций для одной применённой программы поддержки "
        "за один запрос. Замена RPC-эндпоинта `POST /compensations/bulk` на "
        "коллекционный PATCH (REST §5)."
    ),
)
async def batch_create_compensations(
    body: CreateBulkCompensationsRequest,
    user: Annotated[dict, Depends(_admin_or_dealer_or_distributor)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_bulk_compensations(
            CreateBulkCompensationsCommand(
                applied_support_id=body.applied_support_id,
                application_id=body.application_id,
                vehicle_id=body.vehicle_id,
                compensations=[c.model_dump() for c in body.compensations],
                created_by=user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result), status_code=201)


@router.patch(
    "/{compensation_id}/status",
    response_model=CompensationResponse,
    summary="Обновить статус компенсации",
    description=(
        "Переводит компенсацию в новый статус: accepted, rejected, paid или "
        "cancelled. Для accepted/rejected можно передать reason/documents; "
        "для paid — paid_at/documents."
    ),
)
async def update_compensation_status(
    compensation_id: UUID,
    body: UpdateCompensationStatusRequest,
    user: Annotated[dict, Depends(_any_authenticated)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_compensation_status(
            UpdateCompensationStatusCommand(
                compensation_id=compensation_id,
                status=body.status,
                actor_role=user["role"],
                paid_at=body.paid_at,
                documents=body.documents,
                reason=body.reason,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"compensation": jsonable_encoder(result)})


@router.delete(
    "/support/{applied_support_id}",
    response_model=CancelCompensationsResponse,
    summary="Отменить компенсации программы поддержки",
    description=(
        "Soft-cancel всех under_review/accepted/overdue компенсаций, привязанных к "
        "прикреплённой программе поддержки (applied_support). "
        "Оплаченные компенсации остаются без изменений и возвращаются "
        "в массиве `warnings`. Замена RPC-эндпоинта "
        "`POST /compensations/support/:id/cancel`."
    ),
)
async def cancel_support_compensations(
    applied_support_id: UUID,
    _user: Annotated[dict, Depends(_admin_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_cancel_support_compensations(
            CancelSupportCompensationsCommand(
                applied_support_id=applied_support_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/recalculate",
    response_model=RecalculateResponse,
    summary="Пересчитать компенсации",
    description=(
        "Пересчитывает суммы компенсаций при изменении параметров сделки. "
        "Оплаченные компенсации не меняют итоговую сумму."
    ),
)
async def recalculate_compensations(
    body: RecalculateRequest,
    _user: Annotated[dict, Depends(_admin_or_dealer_or_distributor)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        results = await handle_recalculate_compensations(
            RecalculateCompensationsCommand(
                applied_support_id=body.applied_support_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"compensations": jsonable_encoder(results)})
