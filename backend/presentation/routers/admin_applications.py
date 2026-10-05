"""Admin routes for /api/v1/admin/applications (Phase 6 — F2)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_applications import (
    AssignLeasingCompaniesToApplicationCommand,
    handle_assign_leasing_companies_to_application,
)
from application.commands.data_import import (
    UploadDataImportCommand,
    handle_upload_data_import,
)
from application.errors import ServiceError, domain_to_http
from application.queries.admin_applications import (
    GetAdminApplicationDetailQuery,
    ListAdminApplicationsQuery,
    ListAdminApplicationVehiclesQuery,
    ListApplicationPriceChangesQuery,
    handle_get_admin_application_detail,
    handle_list_admin_application_vehicles,
    handle_list_admin_applications,
    handle_list_application_price_changes,
)
from domain.errors import DomainError
from domain.services.scopes import ADMIN_APPLICATIONS
from presentation.dependencies.auth import require_scopes
from presentation.dependencies.csv_export import csv_streaming_response
from presentation.dependencies.export_format import ExportFormat, export_format_dep
from presentation.dependencies.notification_database import get_db
from presentation.schemas.admin import (
    AdminApplicationDetailResponse,
    AdminApplicationPriceChangesResponse,
    AdminApplicationsListResponse,
    AdminApplicationVehiclesListResponse,
    AssignLeasingCompaniesRequest,
    AssignLeasingCompaniesResponse,
)

router = APIRouter()

_employee_only = require_scopes(ADMIN_APPLICATIONS)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    detail = (
        exc.structured_payload()
        if exc.code == "PRICE_ON_REQUEST_PENDING"
        else None
    )
    return HTTPException(
        status_code=exc.status_code,
        detail=detail or str(exc),
    )


_APPLICATION_CSV_HEADERS = [
    "id",
    "display_number",
    "company_id",
    "name",
    "email",
    "status",
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_vehicles_price",
    "vehicles_count",
    "selected_leasing_companies",
    "selected_companies_names",
    "current_stage",
    "created_at",
    "updated_at",
]


@router.get(
    "",
    response_model=AdminApplicationsListResponse,
    summary="[admin] Список всех заявок",
    description=(
        "Полный листинг заявок для admin-UI. Ролевого фильтра нет — "
        "видны все заявки. Доступны фильтры по статусу и поиск. "
        "Поддерживает экспорт в CSV через ?format=csv."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_applications(
    session: Annotated[AsyncSession, Depends(get_db)],
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
) -> JSONResponse | StreamingResponse:
    export_limit = 10_000 if fmt in {"csv", "xlsx"} else limit
    try:
        result = await handle_list_admin_applications(
            ListAdminApplicationsQuery(
                page=1 if fmt in {"csv", "xlsx"} else page,
                limit=export_limit,
                status=status,
                search=search,
                source_type=source_type,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    if fmt == "json":
        return JSONResponse(content=jsonable_encoder(result))

    rows = result.get("applications", [])
    for row in rows:
        row["selected_leasing_companies"] = ", ".join(
            str(x) for x in (row.get("selected_leasing_companies") or [])
        )
        row["selected_companies_names"] = ", ".join(
            str(c.get("company_name", ""))
            for c in (row.get("selected_companies_info") or [])
        )
        for key in ("created_at", "updated_at"):
            val = row.get(key)
            if val is not None:
                row[key] = str(val)

    filename = f"applications_{datetime.now(UTC).strftime('%Y-%m-%d')}.csv"
    return csv_streaming_response(_APPLICATION_CSV_HEADERS, rows, filename)


@router.post(
    "/import",
    summary="[admin] Импорт LCA из CSV",
    description=(
        "Принимает CSV-файл с колонками: id, application_id, leasing_company_id, "
        "status, created_at. "
        "Если id указан и LCA существует — обновляет, иначе создаёт."
    ),
    status_code=202,
)
async def import_applications(
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    content = await file.read()
    try:
        result = await handle_upload_data_import(
            UploadDataImportCommand(
                kind="applications",
                file_bytes=content,
                filename=file.filename,
                user_id=user["id"],
            ),
            session,
        )
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse(content=result, status_code=202)


@router.get(
    "/{application_id}/price-changes",
    response_model=AdminApplicationPriceChangesResponse,
    summary="[admin] История изменения цен заявки",
    description=(
        "Возвращает append-only журнал цен, которые дилеры устанавливали для "
        "позиций спецтехники с режимом «Цена по запросу». Доступно только "
        "сотруднику CarCraft с правом управления заявками."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_application_price_changes(
    application_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    try:
        result = await handle_list_application_price_changes(
            ListApplicationPriceChangesQuery(
                application_id=application_id,
                limit=limit,
                offset=offset,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}",
    response_model=AdminApplicationDetailResponse,
    summary="[admin] Детали заявки",
    description=(
        "Возвращает фактическое дерево заявки для admin-UI: parent "
        "`leasing_applications`, дочерние `leasing_company_applications` и "
        "`leasing_proposals` под каждой LCA."
    ),
    dependencies=[Depends(_employee_only)],
)
async def get_application_detail(
    application_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_admin_application_detail(
            GetAdminApplicationDetailQuery(application_id=application_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/vehicles",
    response_model=AdminApplicationVehiclesListResponse,
    summary="[admin] Автомобили заявки",
    description=(
        "Возвращает список `application_vehicles` для заданной заявки. "
        "Это подмножество `GET /{application_id}` — без metadata заявки и "
        "связей ЛК. Удобно для админ-UI страниц назначения VIN и "
        "ассигнации дилера/дистрибьютора."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_application_vehicles(
    application_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_list_admin_application_vehicles(
            ListAdminApplicationVehiclesQuery(application_id=application_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/{application_id}/assign-leasing-companies",
    response_model=AssignLeasingCompaniesResponse,
    summary="[admin] Назначить ЛК на заявку",
    description=(
        "Admin назначает лизинговые компании на заявку. Обновляет "
        "`selected_leasing_companies` и создаёт недостающие записи в "
        "`leasing_company_applications` (status=under_review). Разрешено "
        "только для статусов draft / pending_distribution / submitted. "
        "Phase 4 D3 владеет дальнейшими per-LC переходами статусов."
    ),
    dependencies=[Depends(_employee_only)],
)
async def assign_leasing_companies(
    application_id: uuid.UUID,
    body: AssignLeasingCompaniesRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_assign_leasing_companies_to_application(
            AssignLeasingCompaniesToApplicationCommand(
                application_id=application_id,
                leasing_company_ids=list(body.leasing_company_ids),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
