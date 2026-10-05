"""Distributor admin routes — vehicles + applications + bulk Excel import.

Mounts under ``/api/v1/distributor`` from main.py. Requires the
``vehicles:admin`` scope (granted to ``carcraft_employee`` and
``distributor``); the in-handler ``DistributorScope`` further restricts
distributor users to their own vehicles.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.distributor import (
    AddVehicleToApplicationCommand,
    AssignDealerCommand,
    BulkDeleteDistributorVehiclesCommand,
    BulkImportDistributorVehiclesCommand,
    BulkUpdateDistributorVehiclesCommand,
    CreateDistributorVehicleCommand,
    DeleteDistributorVehicleCommand,
    PreviewImportDistributorVehiclesCommand,
    RemoveApplicationVehicleCommand,
    ReplaceApplicationVehicleCommand,
    UpdateDealerStatusCommand,
    UpdateDistributorVehicleCommand,
    handle_add_vehicle_to_application,
    handle_assign_dealer,
    handle_bulk_delete_distributor_vehicles,
    handle_bulk_import_distributor_vehicles,
    handle_bulk_update_distributor_vehicles,
    handle_create_distributor_vehicle,
    handle_delete_distributor_vehicle,
    handle_preview_import_distributor_vehicles,
    handle_remove_application_vehicle,
    handle_replace_application_vehicle,
    handle_update_dealer_status,
    handle_update_distributor_vehicle,
)
from application.errors import ServiceError, domain_to_http
from application.queries.distributor import (
    ExportDistributorVehiclesQuery,
    GetDistributorVehicleHistoryQuery,
    GetDistributorVehiclesByIdsQuery,
    GetModelOrdersStatsQuery,
    ListApplicationVehiclesQuery,
    ListAvailableVehiclesForAppQuery,
    ListDistributorApplicationsGroupedQuery,
    ListDistributorApplicationsQuery,
    ListDistributorBrandsQuery,
    ListDistributorDealersQuery,
    ListDistributorSupportProgramsQuery,
    ListDistributorVehiclesQuery,
    handle_export_distributor_vehicles,
    handle_get_distributor_vehicle_history,
    handle_get_distributor_vehicles_by_ids,
    handle_get_model_orders_stats,
    handle_list_application_vehicles,
    handle_list_available_vehicles_for_app,
    handle_list_distributor_applications,
    handle_list_distributor_applications_grouped,
    handle_list_distributor_brands,
    handle_list_distributor_dealers,
    handle_list_distributor_support_programs,
    handle_list_distributor_vehicles,
)
from application.queries.distributor_dealer_assignment import (
    ListAssignableDealerGroupsQuery,
    handle_list_assignable_dealer_groups,
)
from domain.errors import DomainError
from domain.services.scopes import VEHICLES_ADMIN
from infrastructure.database import get_db
from infrastructure.services.excel_io import write_workbook
from presentation.assignment_errors import assignment_error_response
from presentation.dependencies.auth import (
    get_current_user,
    require_roles,
    require_scopes,
)
from presentation.dependencies.export_format import (
    ExportFormat,
    export_format_dep,
)
from presentation.schemas.distributor import (
    AddApplicationVehicleRequest,
    AssignableDealerGroupsResponse,
    AssignDealerRequest,
    AssignDealerResponse,
    AvailableVehiclesForAppResponse,
    DistributorApplicationsGroupedResponse,
    DistributorApplicationsListResponse,
    DistributorApplicationVehiclesResponse,
    DistributorBrandsResponse,
    DistributorBulkDeleteResponse,
    DistributorBulkImportResponse,
    DistributorBulkUpdateResponse,
    DistributorDealerPatchRequest,
    DistributorDealerPatchResponse,
    DistributorDealersListResponse,
    DistributorMessageResponse,
    DistributorSupportProgramsListResponse,
    DistributorVehicleCreateRequest,
    DistributorVehicleHistoryResponse,
    DistributorVehicleListResponse,
    DistributorVehicleResponse,
    DistributorVehiclesDeleteRequest,
    DistributorVehiclesPatchRequest,
    DistributorVehicleUpdateRequest,
    ImportPreviewResponse,
    ModelOrdersStatsResponse,
    ReplaceApplicationVehicleRequest,
)

router = APIRouter()

_authorized = require_scopes(VEHICLES_ADMIN)
_distributor_only = require_roles("distributor")

_ALLOWED_EXCEL_EXTENSIONS = (".xlsx", ".xls")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _validate_excel_filename(filename: str | None) -> None:
    if not filename or not filename.lower().endswith(_ALLOWED_EXCEL_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только файлы .xlsx и .xls",
        )


async def _dealers_to_xlsx(dealers: list[dict[str, Any]]) -> bytes:
    """Serialize a distributor dealers list into xlsx bytes."""
    headers: list[str] = [
        "id",
        "email",
        "name",
        "phone",
        "role",
        "company_id",
    ]
    rows: list[list[Any]] = [
        [
            str(d.get("id") or ""),
            d.get("email") or "",
            d.get("name") or "",
            d.get("phone") or "",
            d.get("role") or "",
            str(d.get("company_id") or ""),
        ]
        for d in dealers
    ]
    return cast("bytes", await write_workbook(headers, rows, sheet_name="Дилеры"))


async def _analytics_to_xlsx(analytics: dict[str, Any]) -> bytes:
    """Serialize distributor analytics (three tables) into xlsx bytes.

    The analytics payload contains three dimensions: by_status (dict),
    by_mark (list of ``{mark, count}``) and timeline (list of
    ``{period, count}``). Since :func:`write_workbook` takes a single
    header+rows pair, we flatten all three into one sheet with a
    ``section`` column.
    """
    headers: list[str] = ["section", "key", "count"]
    rows: list[list[Any]] = []
    by_status = analytics.get("by_status") or {}
    if isinstance(by_status, dict):
        rows.extend(
            ["by_status", str(status), count] for status, count in by_status.items()
        )
    by_mark = analytics.get("by_mark") or []
    if isinstance(by_mark, list):
        rows.extend(
            ["by_mark", item.get("mark") or "", item.get("count") or 0]
            for item in by_mark
        )
    timeline = analytics.get("timeline") or []
    if isinstance(timeline, list):
        rows.extend(
            ["timeline", item.get("period") or "", item.get("count") or 0]
            for item in timeline
        )
    return cast("bytes", await write_workbook(headers, rows, sheet_name="Аналитика"))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Support programs / dealers
# ---------------------------------------------------------------------------


@router.get(
    "/dealer-groups",
    response_model=AssignableDealerGroupsResponse,
    summary="[distributor] Группы дилеров для назначения",
    description=(
        "Возвращает активные группы текущего дистрибьютора с активными "
        "дилерскими компаниями и брендами их складов. `applicationId` "
        "дополнительно проверяет, что в заявке есть ТС на складе актёра."
    ),
    dependencies=[Depends(_distributor_only)],
)
async def list_assignable_dealer_groups(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    application_id: Annotated[
        UUID | None,
        Query(alias="applicationId"),
    ] = None,
    brand: str | None = Query(default=None, max_length=100),
) -> JSONResponse:
    try:
        result = await handle_list_assignable_dealer_groups(
            ListAssignableDealerGroupsQuery(
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                application_id=application_id,
                brand=brand,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/support-programs",
    response_model=DistributorSupportProgramsListResponse,
    summary="[distributor] Программы поддержки распределителя",
    description=(
        "Read-only список программ поддержки, связанных с "
        "distributor_id текущего пользователя."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_support_programs(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> JSONResponse:
    try:
        result = await handle_list_distributor_support_programs(
            ListDistributorSupportProgramsQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                actor_company_id=user.get("company_id"),
                page=page,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/dealers",
    response_model=DistributorDealersListResponse,
    summary="[distributor] Дилеры в скоупе распределителя",
    description=(
        "Список уникальных владельцев автомобилей в скоупе распределителя. "
        "carcraft_employee получает всех дилеров системы; distributor "
        "получает запись себя (по тривиальному mapping).\n\n"
        "Параметр `?format=xlsx` возвращает xlsx с одним листом "
        "(id, email, name, phone, role, company_id)."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_dealers(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
) -> JSONResponse | StreamingResponse:
    try:
        result = await handle_list_distributor_dealers(
            ListDistributorDealersQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                page=page,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    if fmt == "json":
        return JSONResponse(content=jsonable_encoder(result))
    if fmt == "csv":
        raise HTTPException(
            status_code=422,
            detail="Формат `csv` не поддерживается для списка дилеров",
        )
    content = await _dealers_to_xlsx(list(result.get("dealers") or []))
    return StreamingResponse(
        iter([content]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="dealers.xlsx"'},
    )


@router.patch(
    "/dealers/{dealer_id}",
    response_model=DistributorDealerPatchResponse,
    summary="[distributor] Обновить дилера (активация / деактивация)",
    description=(
        "Частичное обновление дилера в скоупе распределителя. В текущей "
        "версии поддерживается поле `status` со значениями "
        "`active` / `inactive`. Замена RPC-эндпоинта "
        "`POST /distributor/dealers/:id/status`."
    ),
    dependencies=[Depends(_authorized)],
)
async def patch_dealer(
    dealer_id: UUID,
    body: DistributorDealerPatchRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    if body.status is None:
        raise HTTPException(status_code=422, detail="Поле `status` обязательно")
    try:
        result = await handle_update_dealer_status(
            UpdateDealerStatusCommand(
                dealer_id=dealer_id,
                status=body.status,
                actor_id=user["id"],
                actor_role=str(user["role"]),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Applications: grouped + export + per-application vehicles
# ---------------------------------------------------------------------------


@router.patch(
    "/leasing-applications/{application_id}",
    status_code=201,
    response_model=AssignDealerResponse,
    summary="[distributor] Устаревшее назначение дилера на заявку",
    deprecated=True,
    description=(
        "Возвращает 409. Для назначения используйте POST "
        "/api/v1/applications/{application_id}/dealer-distributions "
        "с количеством, ожидаемым остатком и request_id."
    ),
    dependencies=[Depends(_distributor_only)],
)
async def assign_dealer_to_application(
    application_id: UUID,
    body: AssignDealerRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_assign_dealer(
            AssignDealerCommand(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                dealer_group_id=body.dealer_group_id,
                dealer_company_id=body.dealer_company_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result), status_code=201)


@router.get(
    "/applications-grouped",
    response_model=DistributorApplicationsGroupedResponse,
    summary="[distributor] Заявки, сгруппированные по статусу",
    description=(
        "Возвращает словарь {status: [applications]} для заявок, "
        "затрагивающих автомобили распределителя."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_applications_grouped(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=500, ge=1, le=2000),
) -> JSONResponse:
    try:
        result = await handle_list_distributor_applications_grouped(
            ListDistributorApplicationsGroupedQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                page=page,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/applications/{application_id}/vehicles",
    response_model=DistributorApplicationVehiclesResponse,
    summary="[distributor] Автомобили в заявке",
    description=(
        "Возвращает vehicles, привязанные к заявке и попадающие в скоуп распределителя."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_application_vehicles(
    application_id: uuid.UUID,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_list_application_vehicles(
            ListApplicationVehiclesQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                application_id=application_id,
                company_id=user.get("company_id") or user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/applications/{application_id}/vehicles",
    response_model=DistributorMessageResponse,
    summary="[distributor] Добавить автомобиль в заявку",
    description=(
        "Прикрепляет vehicle (в скоупе) к заявке. vehicle помечается "
        "статусом `reserved`. Недоступные автомобили отклоняются с 409."
    ),
    dependencies=[Depends(_authorized)],
)
async def add_application_vehicle(
    application_id: uuid.UUID,
    body: AddApplicationVehicleRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_add_vehicle_to_application(
            AddVehicleToApplicationCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                application_id=application_id,
                vehicle_id=body.vehicle_id,
                quantity=body.quantity,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/applications/{application_id}/pdf",
    summary="[distributor] PDF-отчёт по заявке",
    description=(
        "**NOT IMPLEMENTED.** В окружении отсутствуют библиотеки "
        "`reportlab` / `weasyprint`; эндпоинт возвращает 501. Пропущено "
        "на уровне Phase 7a G3."
    ),
    status_code=501,
    dependencies=[Depends(_authorized)],
)
async def get_application_pdf(
    application_id: uuid.UUID, _user: Annotated[dict, Depends(get_current_user)]
) -> JSONResponse:
    _ = application_id  # required by FastAPI path binding
    raise HTTPException(
        status_code=501,
        detail=(
            "PDF-экспорт не реализован: в зависимостях отсутствует "
            "reportlab/weasyprint."
        ),
    )


@router.get(
    "/available-vehicles-for-app",
    response_model=AvailableVehiclesForAppResponse,
    summary="[distributor] Автомобили для добавления в заявку",
    description=(
        "Только автомобили со статусом `available` в скоупе распределителя. "
        "Опциональные фильтры по марке/модели."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_available_vehicles(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    mark_id: str | None = Query(default=None),
    model_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> JSONResponse:
    try:
        result = await handle_list_available_vehicles_for_app(
            ListAvailableVehiclesForAppQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                mark_id=mark_id,
                model_id=model_id,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Model orders
# ---------------------------------------------------------------------------


@router.get(
    "/model-orders/stats",
    response_model=ModelOrdersStatsResponse,
    summary="[distributor] Счётчики model-orders",
    description="Pending / assigned / total для model-orders в скоупе.",
    dependencies=[Depends(_authorized)],
)
async def get_model_orders_stats(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_model_orders_stats(
            GetModelOrdersStatsQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


# VIN assignment on model-order rows moved to
# PATCH /api/v1/application-vehicles/{id} (Phase 13 R13c). See
# presentation/routers/application_vehicles.py.


# ---------------------------------------------------------------------------
# Application-vehicles mutations
# ---------------------------------------------------------------------------


@router.put(
    "/application-vehicles/{application_vehicle_id}/replace",
    response_model=DistributorMessageResponse,
    summary="[distributor] Заменить автомобиль в заявке",
    description=(
        "Меняет vehicle_id в существующей application_vehicles-строке. "
        "Старый автомобиль возвращается в `available`, новый — в `reserved`."
    ),
    dependencies=[Depends(_authorized)],
)
async def replace_application_vehicle(
    application_vehicle_id: UUID,
    body: ReplaceApplicationVehicleRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_replace_application_vehicle(
            ReplaceApplicationVehicleCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                application_vehicle_id=application_vehicle_id,
                new_vehicle_id=body.new_vehicle_id,
                company_id=user.get("company_id") or user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/application-vehicles/{application_vehicle_id}",
    response_model=DistributorMessageResponse,
    summary="[distributor] Удалить автомобиль из заявки",
    description=(
        "Удаляет application_vehicles-запись; связанный vehicle "
        "возвращается в статус `available`."
    ),
    dependencies=[Depends(_authorized)],
)
async def delete_application_vehicle(
    application_vehicle_id: UUID,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_remove_application_vehicle(
            RemoveApplicationVehicleCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                application_vehicle_id=application_vehicle_id,
                company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


@router.get(
    "/vehicles",
    response_model=DistributorVehicleListResponse,
    summary="[distributor] Список автомобилей в скоупе распределителя",
    description=(
        "Постранично возвращает автомобили распределителя с фильтрами "
        "по статусу и поиску, плюс сортировкой. carcraft_employee видит "
        "все автомобили; distributor — только свои (по dealer_id).\n\n"
        "Если указан повторяющийся параметр `ids` — возвращает **только** "
        "автомобили с этими ids (batch-read, как замена RPC "
        "`POST /vehicles/bulk-details`). Все ids должны быть в скоупе "
        "актора; иначе 403/404.\n\n"
        "Параметры `?format=xlsx` и `?format=csv` возвращают файл с "
        "полным списком в скоупе (фильтры status/search применяются, "
        "ids/пагинация игнорируются)."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_vehicles(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    ids: Annotated[list[UUID], Query(default_factory=list)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
) -> JSONResponse | StreamingResponse:
    if fmt in {"xlsx", "csv"}:
        try:
            export_result = await handle_export_distributor_vehicles(
                ExportDistributorVehiclesQuery(
                    actor_id=user["id"],
                    actor_role=str(user["role"]),
                    export_format=fmt,
                    status=status,
                    search=search,
                ),
                session,
            )
        except (ServiceError, DomainError) as exc:
            raise _http(exc)
        return StreamingResponse(
            iter([export_result["content"]]),
            media_type=export_result["mime_type"],
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{export_result["filename"]}"'
                )
            },
        )
    try:
        if ids:
            batch = await handle_get_distributor_vehicles_by_ids(
                GetDistributorVehiclesByIdsQuery(
                    actor_id=user["id"],
                    actor_role=str(user["role"]),
                    company_id=user.get("company_id") or user["id"],
                    vehicle_ids=list(ids),
                ),
                session,
            )
            return JSONResponse(content=jsonable_encoder(batch))
        result = await handle_list_distributor_vehicles(
            ListDistributorVehiclesQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                page=page,
                limit=limit,
                status=status,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/vehicles",
    status_code=201,
    response_model=DistributorVehicleResponse,
    summary="[distributor] Создать автомобиль",
    description=(
        "Создаёт автомобиль в скоупе распределителя. Поле dealer_id "
        "должно указывать на связанного дилера; если дилер один, может "
        "быть выбрано автоматически."
    ),
    dependencies=[Depends(_authorized)],
)
async def create_vehicle(
    body: DistributorVehicleCreateRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_distributor_vehicle(
            CreateDistributorVehicleCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id"),
                vin=body.vin,
                mark_id=body.mark_id,
                model_id=body.model_id,
                generation_id=body.generation_id,
                configuration_id=body.configuration_id,
                complectation_id=body.complectation_id,
                year=body.year,
                base_price=body.base_price,
                special_price=body.special_price,
                discount_price=body.discount_price,
                color=body.color,
                color_inter=body.color_inter,
                status=body.status,
                is_available=body.is_available,
                dealer_id=body.dealer_id,
                images=body.images,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "vehicle": jsonable_encoder(result),
            "message": "Автомобиль успешно добавлен",
        },
        status_code=201,
        headers={"Location": f"/api/v1/distributor/vehicles/{result['id']}"},
    )


# NOTE: bulk-import, export, import etc. MUST be registered before the
# `/vehicles/{vehicle_id}` routes — FastAPI matches routes in declaration
# order, and those literal paths would otherwise be parsed as int path
# params. The collection-level PATCH/DELETE use the plain `/vehicles`
# path and therefore do not collide.


@router.patch(
    "/vehicles",
    response_model=DistributorBulkUpdateResponse,
    summary="[distributor] Массовое обновление автомобилей",
    description=(
        "Атомарное обновление цены / статуса / доступности по списку "
        "ids. Тело: `{ids: [int, ...], patch: {status?, base_price?, "
        "special_price?, discount_price?, is_available?}}`. Если хоть один id не в скоупе "
        "или статусный переход недопустим (например sold → available) — "
        "отклоняется вся пачка. Замена устаревших RPC "
        "`PUT/POST /vehicles/bulk-update`."
    ),
    dependencies=[Depends(_authorized)],
)
async def bulk_update_vehicles(
    body: DistributorVehiclesPatchRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    update_fields = body.patch
    fields_set: set[str] = set(update_fields.model_fields_set)
    try:
        result = await handle_bulk_update_distributor_vehicles(
            BulkUpdateDistributorVehiclesCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                vehicle_ids=list(body.ids),
                status=update_fields.status,
                base_price=update_fields.base_price,
                special_price=update_fields.special_price,
                discount_price=update_fields.discount_price,
                is_available=update_fields.is_available,
                fields_set=fields_set,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/vehicles",
    response_model=DistributorBulkDeleteResponse,
    summary="[distributor] Массовое удаление автомобилей",
    description=(
        "Атомарное удаление автомобилей по списку ids. Тело: "
        "`{ids: [int, ...]}`. Любой id не в скоупе или отсутствующий "
        "в БД отклоняет всю пачку. Замена устаревшего RPC "
        "`POST /vehicles/bulk-delete`."
    ),
    dependencies=[Depends(_authorized)],
)
async def bulk_delete_vehicles(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: Annotated[DistributorVehiclesDeleteRequest, Body(...)],
) -> JSONResponse:
    try:
        result = await handle_bulk_delete_distributor_vehicles(
            BulkDeleteDistributorVehiclesCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                vehicle_ids=list(body.ids),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/vehicles/import",
    response_model=DistributorBulkImportResponse,
    summary="[distributor] Импорт автомобилей из Excel",
    description=(
        "Загружает .xlsx со списком автомобилей. Принимаются заголовки "
        "VIN, Марка, Модель, Поколение, Год, Цвет, Базовая цена, Специальная "
        "цена, Цена со скидкой, Статус (или их латинские эквиваленты). Невалидные "
        "строки возвращаются в массиве errors с указанием row и причины. "
        "Файлы крупнее 10 МБ или больше 5000 строк отклоняются — для них "
        "предусмотрен фоновый импорт."
    ),
    dependencies=[Depends(_authorized)],
)
async def import_vehicles(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    _validate_excel_filename(file.filename)
    file_bytes = await file.read()
    try:
        result = await handle_bulk_import_distributor_vehicles(
            BulkImportDistributorVehiclesCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                file_bytes=file_bytes,
                filename=file.filename,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/vehicles/import-preview",
    response_model=ImportPreviewResponse,
    summary="[distributor] Предпросмотр импорта (dry-run)",
    description=(
        "Парсит xlsx и возвращает статистику + образец первых 10 строк. "
        "В БД не пишет. Используется UI для подтверждения перед реальным "
        "импортом."
    ),
    dependencies=[Depends(_authorized)],
)
async def preview_import_vehicles(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    _validate_excel_filename(file.filename)
    file_bytes = await file.read()
    try:
        result = await handle_preview_import_distributor_vehicles(
            PreviewImportDistributorVehiclesCommand(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                file_bytes=file_bytes,
                filename=file.filename,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/vehicles/import-template",
    summary="[distributor] Скачать xlsx-шаблон для импорта",
    description=(
        "Возвращает пустой xlsx с примером заголовков и одной образцовой "
        "строкой — шаблон для массового импорта автомобилей."
    ),
    response_class=StreamingResponse,
    dependencies=[Depends(_authorized)],
)
async def download_import_template(
    _user: Annotated[dict, Depends(get_current_user)],
) -> StreamingResponse:
    headers: list[str] = [
        "VIN",
        "Марка",
        "Модель",
        "Поколение",
        "Год",
        "Цвет",
        "Базовая цена",
        "Специальная цена",
        "Цена со скидкой",
        "Статус",
    ]
    rows: list[list[Any]] = [
        [
            "EXAMPLE12345678901",
            "Toyota",
            "Camry",
            "XV70",
            2024,
            "Белый",
            3500000,
            3450000,
            3300000,
            "В наличии",
        ]
    ]
    content = await write_workbook(headers, rows, sheet_name="Шаблон")
    return StreamingResponse(
        iter([content]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="vehicle_import_template.xlsx"'
            )
        },
    )


@router.get(
    "/vehicles/brands",
    response_model=DistributorBrandsResponse,
    summary="[distributor] Список марок автомобилей в скоупе",
    description=(
        "Плоский список distinct имён марок (строки, отсортированные по "
        "алфавиту) для автомобилей, попадающих в скоуп распределителя. "
        "Используется UI инвентаризации для dropdown'а выборочной "
        "проверки. Возвращает `{brands: [...]}`."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_brands(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_list_distributor_brands(
            ListDistributorBrandsQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/vehicles/{vehicle_id}/history",
    response_model=DistributorVehicleHistoryResponse,
    summary="[distributor] История изменений автомобиля",
    description=(
        "Минимальная история (created / updated), выведенная из "
        "`vehicles.created_at` и `vehicles.updated_at`. Специализированной "
        "таблицы status-history для транспорта пока нет — схема ответа "
        "совместима с будущей более богатой реализацией. Скоуп "
        "распределителя проверяется: foreign vehicle → 403."
    ),
    dependencies=[Depends(_authorized)],
)
async def get_vehicle_history(
    vehicle_id: UUID,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_distributor_vehicle_history(
            GetDistributorVehicleHistoryQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                vehicle_id=vehicle_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


# VIN assignment was consolidated into
# PATCH /api/v1/application-vehicles/{id} (Phase 13 R13c). See
# presentation/routers/application_vehicles.py. The distributor-scoped
# PUT /vehicles/{id}/vin was removed in Phase 15 H2.


@router.put(
    "/vehicles/{vehicle_id}",
    response_model=DistributorVehicleResponse,
    summary="[distributor] Обновить автомобиль",
    description=(
        "Частичное обновление автомобиля в скоупе распределителя. "
        "Применяются только переданные поля."
    ),
    dependencies=[Depends(_authorized)],
)
async def update_vehicle(
    vehicle_id: UUID,
    body: DistributorVehicleUpdateRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_distributor_vehicle(
            UpdateDistributorVehicleCommand(
                vehicle_id=vehicle_id,
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                fields_set=set(body.model_fields_set),
                vin=body.vin,
                dealer_id=body.dealer_id,
                mark_id=body.mark_id,
                model_id=body.model_id,
                generation_id=body.generation_id,
                configuration_id=body.configuration_id,
                complectation_id=body.complectation_id,
                year=body.year,
                base_price=body.base_price,
                special_price=body.special_price,
                discount_price=body.discount_price,
                color=body.color,
                color_inter=body.color_inter,
                status=body.status,
                is_available=body.is_available,
                images=body.images,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "vehicle": jsonable_encoder(result),
            "message": "Автомобиль успешно обновлён",
        }
    )


@router.delete(
    "/vehicles/{vehicle_id}",
    response_model=DistributorMessageResponse,
    summary="[distributor] Удалить автомобиль",
    description=(
        "Удаляет автомобиль в скоупе распределителя. Для чужих автомобилей "
        "возвращает 403."
    ),
    dependencies=[Depends(_authorized)],
)
async def delete_vehicle(
    vehicle_id: UUID,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_delete_distributor_vehicle(
            DeleteDistributorVehicleCommand(
                vehicle_id=vehicle_id,
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@router.get(
    "/applications",
    response_model=DistributorApplicationsListResponse,
    summary="[distributor] Список заявок, затрагивающих авто распределителя",
    description=(
        "Лизинговые заявки, в которых участвует хотя бы один автомобиль "
        "из скоупа распределителя. Поддерживает фильтр по статусу и "
        "пагинацию."
    ),
    dependencies=[Depends(_authorized)],
)
async def list_applications(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None),
) -> JSONResponse:
    try:
        result = await handle_list_distributor_applications(
            ListDistributorApplicationsQuery(
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id") or user["id"],
                page=page,
                limit=limit,
                status=status,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


__all__: list[Any] = ["router"]
