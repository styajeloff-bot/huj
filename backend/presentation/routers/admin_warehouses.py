"""Role-scoped reads and administrative writes for warehouses and cities."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.cities import (
    CreateCityCommand,
    handle_create_city,
)
from application.commands.vehicles.admin_deletion import (
    VehicleDeletionError,
    handle_bulk_delete_warehouse_vehicles,
    handle_unbind_all_warehouse_vehicles,
)
from application.commands.warehouses import (
    AddVehicleToWarehouseCommand,
    BindVehiclesByMarkCommand,
    BulkAddVehiclesToWarehouseCommand,
    CreateAccessRulesCommand,
    CreateWarehouseCommand,
    DeleteAccessRuleCommand,
    DeleteWarehouseCommand,
    RemoveVehicleFromWarehouseCommand,
    UpdateAccessRuleCommand,
    UpdateWarehouseCommand,
    WarehouseDeleteBlockedError,
    handle_add_vehicle_to_warehouse,
    handle_bind_vehicles_by_mark,
    handle_bulk_add_vehicles_to_warehouse,
    handle_cascade_delete_warehouse,
    handle_create_access_rules,
    handle_create_warehouse,
    handle_delete_access_rule,
    handle_delete_warehouse,
    handle_delete_warehouse_integrity_fallback,
    handle_preview_warehouse_cascade_delete,
    handle_remove_vehicle_from_warehouse,
    handle_update_access_rule,
    handle_update_warehouse,
    publish_warehouse_status_events,
)
from application.commands.warehouses.validate_form import WarehouseFormValidationError
from application.errors import ServiceError, domain_to_http
from application.queries.cities import (
    ListCitiesQuery,
    handle_list_cities,
)
from application.queries.vehicles.deletion_check import handle_warehouse_deletion_check
from application.queries.warehouses import (
    GetWarehouseQuery,
    ListAccessRulesQuery,
    ListWarehouseBrandsQuery,
    ListWarehousesQuery,
    ListWarehouseVehiclesQuery,
    handle_get_warehouse,
    handle_list_access_rules,
    handle_list_warehouse_brands,
    handle_list_warehouse_vehicles,
    handle_list_warehouses,
)
from application.queries.warehouses.form_options import (
    handle_list_warehouse_form_categories,
    handle_list_warehouse_form_marks,
)
from domain.errors import DomainError
from domain.services.scopes import WAREHOUSES_ADMIN, WAREHOUSES_READ
from domain.values import WarehouseStatus
from infrastructure.database import get_db
from presentation.dependencies.auth import (
    get_current_user,
    require_roles,
    require_scopes,
)
from presentation.schemas.admin import WarehouseBrandsResponse
from presentation.schemas.admin_warehouses import (
    AddVehicleResponse,
    AddVehicleToWarehouseRequest,
    BindByMarkRequest,
    BindByMarkResponse,
    BulkAddVehiclesToWarehouseRequest,
    BulkAddVehiclesToWarehouseResponse,
    CityCreateRequest,
    CityListResponse,
    CityResponse,
    CreateWarehouseAccessRulesRequest,
    MessageResponse,
    UpdateWarehouseAccessRuleRequest,
    WarehouseAccessRuleListResponse,
    WarehouseAccessRuleResponse,
    WarehouseCascadeDeleteRequest,
    WarehouseCascadeDeleteResponse,
    WarehouseCategoriesResponse,
    WarehouseCreateRequest,
    WarehouseDeletePreviewResponse,
    WarehouseDeleteProblem,
    WarehouseListResponse,
    WarehouseMarksResponse,
    WarehouseProblem,
    WarehouseResponse,
    WarehouseUpdateRequest,
    WarehouseVehiclesListResponse,
)
from presentation.schemas.vehicle_deletion import (
    WarehouseBulkDeleteRequest,
    WarehouseBulkDeleteResponse,
    WarehouseDeletionCheckResponse,
    WarehouseUnbindRequest,
    WarehouseUnbindResponse,
)
from presentation.vehicle_deletion_errors import vehicle_deletion_error

router = APIRouter()

_warehouse_read = require_scopes(WAREHOUSES_READ)
_warehouse_admin = require_scopes(WAREHOUSES_ADMIN)
_vehicle_deletion_admin = require_roles("carcraft_employee")
_WAREHOUSE_READ_ACCESS_DESCRIPTION = (
    "Требуется scope `warehouses:read`. Роли и область доступа: "
    "`carcraft_employee` — все склады; `distributor` — склады связанных "
    "дилеров; `dealer` — только склады собственной компании (без компании "
    "выборка пуста)."
)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    return HTTPException(status_code=error.status_code, detail=str(error))


def _warehouse_problem(exc: ServiceError | DomainError) -> JSONResponse:
    if isinstance(exc, WarehouseFormValidationError):
        return JSONResponse(status_code=422, content={"detail": [{"loc": ["body", exc.field], "msg": str(exc), "type": "value_error"}]})
    error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    body = WarehouseProblem(
        type="about:blank",
        title={
            404: "Warehouse not found",
            409: "Warehouse conflict",
            422: "Warehouse validation error",
        }.get(error.status_code, "Warehouse request error"),
        status=error.status_code,
        detail=str(error),
    )
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def _warehouse_delete_problem(
    blocking_dependencies: dict[str, int],
) -> JSONResponse:
    body = WarehouseDeleteProblem(
        type="warehouse-has-dependencies",
        title="Warehouse deletion blocked",
        status=409,
        detail="Warehouse has blocking dependencies",
        blockingDependencies=blocking_dependencies,
    )
    return JSONResponse(
        status_code=409,
        content=body.model_dump(mode="json", by_alias=True),
        media_type="application/problem+json",
    )


# ---------------------------------------------------------------------------
# Distinct warehouse brands (filter helper)
#
# Declared BEFORE `/warehouses/{warehouse_id}` so that the static path
# wins routing even if ``warehouse_id`` ever broadens from int to str.
# ---------------------------------------------------------------------------


@router.get(
    "/warehouses/brands",
    response_model=WarehouseBrandsResponse,
    summary="[warehouses] Уникальные бренды складов",
    description=(
        "Возвращает отсортированный список уникальных значений поля "
        "`brand` из таблицы `warehouses`. Используется для построения "
        "фильтра брендов. Список ограничен доступными пользователю складами. "
        f"{_WAREHOUSE_READ_ACCESS_DESCRIPTION}"
    ),
    dependencies=[Depends(_warehouse_read)],
)
async def list_warehouse_brands_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    result = await handle_list_warehouse_brands(
        ListWarehouseBrandsQuery(
            actor_id=user["id"],
            actor_role=str(user["role"]),
            company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------


@router.get(
    "/cities",
    response_model=CityListResponse,
    summary="[warehouses] Список городов",
    description=(
        "Возвращает все города, отсортированные по имени; справочник городов "
        "не фильтруется по компании. "
        f"{_WAREHOUSE_READ_ACCESS_DESCRIPTION}"
    ),
    dependencies=[Depends(_warehouse_read)],
)
async def list_cities(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_cities(ListCitiesQuery(), session)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/cities",
    status_code=201,
    response_model=CityResponse,
    summary="[admin] Создать город",
    description="Создаёт город с уникальным названием. При дубликате — 409.",
    dependencies=[Depends(_warehouse_admin)],
)
async def create_city(
    body: CityCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_city(
            CreateCityCommand(name=body.name), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "city": jsonable_encoder(result),
            "message": "Город создан",
        },
        status_code=201,
        headers={"Location": f"/api/v1/admin/cities/{result['id']}"},
    )


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------


@router.get(
    "/warehouses",
    response_model=WarehouseListResponse,
    summary="[warehouses] Список складов",
    description=(
        "Постранично возвращает доступные пользователю склады с фильтрами "
        "по адресу, марке и городу. "
        f"{_WAREHOUSE_READ_ACCESS_DESCRIPTION}"
    ),
    dependencies=[Depends(_warehouse_read)],
)
async def list_warehouses(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=1000),
    search: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    brand_id: Annotated[UUID | None, Query()] = None,
    city_id: Annotated[UUID | None, Query()] = None,
    access_type: Annotated[str | None, Query()] = None,
    owner_company_id: Annotated[UUID | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    status: Annotated[WarehouseStatus | None, Query()] = None,
) -> JSONResponse:
    result = await handle_list_warehouses(
        ListWarehousesQuery(
            page=page,
            limit=limit,
            search=search,
            brand=brand,
            brand_id=brand_id,
            city_id=city_id,
            access_type=access_type,
            owner_company_id=owner_company_id,
            is_active=is_active,
            status=status,
            actor_id=user["id"],
            actor_role=str(user["role"]),
            company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Warehouse Access Rules
#
# Declared BEFORE `/warehouses/{warehouse_id}` so that `/warehouses/access-rules`
# is not matched as a warehouse_id path parameter.
# Supports both `/warehouses/access-rules` and alias `/warehouse-access-rules`.
# ---------------------------------------------------------------------------


@router.get(
    "/warehouses/access-rules",
    response_model=WarehouseAccessRuleListResponse,
    summary="[warehouses] Список правил доступа к складам",
    description="Постранично возвращает правила доступа к складам.",
    dependencies=[Depends(_warehouse_read)],
)
@router.get(
    "/warehouse-access-rules",
    response_model=WarehouseAccessRuleListResponse,
    summary="[warehouses] Список правил доступа к складам (алиас)",
    description="Постранично возвращает правила доступа к складам.",
    dependencies=[Depends(_warehouse_read)],
)
async def list_access_rules_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=1000),
    warehouse_id: Annotated[UUID | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> JSONResponse:
    result = await handle_list_access_rules(
        ListAccessRulesQuery(
            page=page,
            limit=limit,
            warehouse_id=warehouse_id,
            is_active=is_active,
            actor_id=user["id"],
            actor_role=str(user["role"]),
            company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/warehouses/access-rules",
    status_code=201,
    response_model=dict,
    summary="[admin] Создать/обновить правила доступа",
    description="Создаёт или обновляет правила доступа к складу для дилеров или группы дилеров.",
    dependencies=[Depends(_warehouse_admin)],
)
@router.post(
    "/warehouse-access-rules",
    status_code=201,
    response_model=dict,
    summary="[admin] Создать/обновить правила доступа (алиас)",
    description="Создаёт или обновляет правила доступа к складу для дилеров или группы дилеров.",
    dependencies=[Depends(_warehouse_admin)],
)
async def create_access_rules_endpoint(
    body: CreateWarehouseAccessRulesRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    user_companies = [user["company_id"]] if user.get("company_id") else []
    try:
        rules = await handle_create_access_rules(
            CreateAccessRulesCommand(
                warehouse_id=body.warehouse_id,
                mode=body.mode,
                dealers=[d.model_dump() for d in body.dealers],
                dealer_group_id=body.dealer_group_id,
                group_access_type=body.group_access_type or "B",
                site_id=body.site_id,
                brand_id=body.brand_id,
                actor_role=str(user["role"]),
                actor_company_ids=user_companies,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    return JSONResponse(
        content={
            "rules": jsonable_encoder(rules),
            "message": "Правила доступа успешно сохранены",
        },
        status_code=201,
    )


@router.patch(
    "/warehouses/access-rules/{rule_id}",
    response_model=WarehouseAccessRuleResponse,
    summary="[admin] Изменить правило доступа к складу",
    description="Изменяет тип доступа или флаг активности правила.",
    dependencies=[Depends(_warehouse_admin)],
)
@router.put(
    "/warehouses/access-rules/{rule_id}",
    response_model=WarehouseAccessRuleResponse,
    summary="[admin] Изменить правило доступа к складу (PUT)",
    description="Изменяет тип доступа или флаг активности правила.",
    dependencies=[Depends(_warehouse_admin)],
)
@router.patch(
    "/warehouse-access-rules/{rule_id}",
    response_model=WarehouseAccessRuleResponse,
    summary="[admin] Изменить правило доступа к складу (алиас PATCH)",
    description="Изменяет тип доступа или флаг активности правила.",
    dependencies=[Depends(_warehouse_admin)],
)
@router.put(
    "/warehouse-access-rules/{rule_id}",
    response_model=WarehouseAccessRuleResponse,
    summary="[admin] Изменить правило доступа к складу (алиас PUT)",
    description="Изменяет тип доступа или флаг активности правила.",
    dependencies=[Depends(_warehouse_admin)],
)
async def update_access_rule_endpoint(
    rule_id: UUID,
    body: UpdateWarehouseAccessRuleRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    user_companies = [user["company_id"]] if user.get("company_id") else []
    try:
        updated = await handle_update_access_rule(
            UpdateAccessRuleCommand(
                rule_id=rule_id,
                warehouse_access_type=body.warehouse_access_type,
                is_active=body.is_active,
                actor_role=str(user["role"]),
                actor_company_ids=user_companies,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    return JSONResponse(
        content={
            "rule": jsonable_encoder(updated),
            "message": "Правило доступа обновлено",
        }
    )


@router.delete(
    "/warehouses/access-rules/{rule_id}",
    status_code=204,
    summary="[admin] Удалить правило доступа к складу",
    description="Удаляет правило доступа (за исключением базового типа A).",
    dependencies=[Depends(_warehouse_admin)],
)
@router.delete(
    "/warehouse-access-rules/{rule_id}",
    status_code=204,
    summary="[admin] Удалить правило доступа к складу (алиас)",
    description="Удаляет правило доступа (за исключением базового типа A).",
    dependencies=[Depends(_warehouse_admin)],
)
async def delete_access_rule_endpoint(
    rule_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> Response:
    user_companies = [user["company_id"]] if user.get("company_id") else []
    try:
        deleted = await handle_delete_access_rule(
            DeleteAccessRuleCommand(
                rule_id=rule_id,
                actor_role=str(user["role"]),
                actor_company_ids=user_companies,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    if not deleted:
        raise HTTPException(status_code=404, detail="Правило доступа не найдено")
    await session.commit()
    return Response(status_code=204)


@router.get(
    "/warehouses/marks",
    response_model=WarehouseMarksResponse,
    summary="[admin] Марки ТС для формы склада",
    description="Постраничный поиск по части названия среди активных марок справочника. Требуется scope warehouses:admin, как для создания и редактирования склада.",
    dependencies=[Depends(_warehouse_admin)],
)
async def list_warehouse_form_marks(
    session: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JSONResponse:
    result = await handle_list_warehouse_form_marks(session, search=search, page=page, limit=limit)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/warehouses/categories",
    response_model=WarehouseCategoriesResponse,
    summary="[admin] Категории ТС выбранных марок",
    description="Постраничный поиск активных категорий, связанных с активными моделями или модификациями хотя бы одной выбранной марки. Без марок список пуст. Требуется scope warehouses:admin, как для создания и редактирования склада.",
    dependencies=[Depends(_warehouse_admin)],
)
async def list_warehouse_form_categories(
    session: Annotated[AsyncSession, Depends(get_db)],
    brand_ids: Annotated[list[UUID] | None, Query()] = None,
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JSONResponse:
    result = await handle_list_warehouse_form_categories(session, brand_ids=brand_ids or [], search=search, page=page, limit=limit)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseResponse,
    summary="[warehouses] Склад по id",
    description=(
        "Возвращает доступный пользователю склад по идентификатору. "
        "Если склад отсутствует или находится вне области доступа, возвращает "
        "404. "
        f"{_WAREHOUSE_READ_ACCESS_DESCRIPTION}"
    ),
    dependencies=[Depends(_warehouse_read)],
)
async def get_warehouse(
    warehouse_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    try:
        result = await handle_get_warehouse(
            GetWarehouseQuery(
                warehouse_id=warehouse_id,
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    return JSONResponse(content={"warehouse": jsonable_encoder(result)})


@router.post(
    "/warehouses",
    status_code=201,
    response_model=WarehouseResponse,
    summary="[admin] Создать склад",
    description="Создаёт склад.",
    dependencies=[Depends(_warehouse_admin)],
)
async def create_warehouse(
    body: WarehouseCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    user_companies = [user["company_id"]] if user.get("company_id") else []
    try:
        result = await handle_create_warehouse(
            CreateWarehouseCommand(
                name=body.name,
                owner_company_id=body.owner_company_id,
                owner_company_type=body.owner_company_type,
                address=body.address,
                city_id=body.city_id,
                brand_ids=body.brand_ids,
                category_id=body.category_id,
                is_active=body.is_active,
                actor_role=str(user["role"]),
                actor_company_ids=user_companies,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    publish_warehouse_status_events(result["status_events"])
    return JSONResponse(
        content={
            "warehouse": jsonable_encoder(result["warehouse"]),
            "message": "Склад успешно создан",
        },
        status_code=201,
        headers={
            "Location": (
                f"/api/v1/admin/warehouses/{result['warehouse']['id']}"
            )
        },
    )


@router.put(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseResponse,
    summary="[admin] Обновить склад",
    description=(
        "Частичное обновление: применяются только переданные поля."
    ),
    dependencies=[Depends(_warehouse_admin)],
)
async def update_warehouse(
    warehouse_id: UUID,
    body: WarehouseUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    fields_set = body.model_fields_set
    user_companies = [user["company_id"]] if user.get("company_id") else []
    try:
        result = await handle_update_warehouse(
            UpdateWarehouseCommand(
                warehouse_id=warehouse_id,
                name=body.name,
                owner_company_id=body.owner_company_id,
                owner_company_type=body.owner_company_type,
                address=body.address,
                city_id=body.city_id,
                brand_ids=body.brand_ids,
                category_id=body.category_id,
                is_active=body.is_active,
                update_city="city_id" in fields_set,
                update_brands="brand_ids" in fields_set,
                update_category="category_id" in fields_set,
                update_owner_company="owner_company_id" in fields_set,
                actor_role=str(user["role"]),
                actor_company_ids=user_companies,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    publish_warehouse_status_events(result["status_events"])
    return JSONResponse(
        content={
            "warehouse": jsonable_encoder(result["warehouse"]),
            "message": "Склад успешно обновлён",
        }
    )



@router.delete(
    "/warehouses/{warehouse_id}",
    status_code=204,
    response_model=None,
    responses={409: {"model": WarehouseDeleteProblem}},
    summary="[admin] Удалить склад",
    description=(
        "Удаляет склад без зависимостей. При зависимостях возвращает 409 "
        "application/problem+json с количеством записей в каждой группе."
    ),
    dependencies=[Depends(_warehouse_admin)],
)
async def delete_warehouse(
    warehouse_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    cmd = DeleteWarehouseCommand(warehouse_id=warehouse_id)
    try:
        result = await handle_delete_warehouse(cmd, session)
    except WarehouseDeleteBlockedError as exc:
        await session.rollback()
        return _warehouse_delete_problem(exc.blocking_dependencies)
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        return _warehouse_problem(exc)
    except IntegrityError as exc:
        await session.rollback()
        dependencies = await handle_delete_warehouse_integrity_fallback(
            exc, cmd, session
        )
        if dependencies is None:
            raise
        await session.rollback()
        return _warehouse_delete_problem(dependencies)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        dependencies = await handle_delete_warehouse_integrity_fallback(
            exc, cmd, session
        )
        if dependencies is None:
            raise
        await session.rollback()
        return _warehouse_delete_problem(dependencies)

    publish_warehouse_status_events(result["status_events"])
    return Response(status_code=204)


@router.get(
    "/warehouses/{warehouse_id}/delete-preview",
    response_model=WarehouseDeletePreviewResponse,
    summary="[admin] Предпросмотр каскадного удаления склада",
    description=(
        "Рассчитывает граф каскадного удаления склада, удаляемые и сохраняемые "
        "объекты, бизнес-блокеры и токен подтверждения. Только carcraft_employee."
    ),
    dependencies=[Depends(_vehicle_deletion_admin)],
)
async def delete_preview_warehouse(
    warehouse_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        preview = await handle_preview_warehouse_cascade_delete(warehouse_id, session)
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    return JSONResponse(content=jsonable_encoder(preview))


@router.post(
    "/warehouses/{warehouse_id}/cascade-delete",
    response_model=WarehouseCascadeDeleteResponse,
    summary="[admin] Каскадное удаление склада",
    description=(
        "Выполняет атомарное каскадное удаление склада, его объявлений и допустимых "
        "справочников при валидации подтверждения УДАЛИТЬ и токена предпросмотра. "
        "Только carcraft_employee."
    ),
    dependencies=[Depends(_vehicle_deletion_admin)],
)
async def cascade_delete_warehouse(
    warehouse_id: UUID,
    body: WarehouseCascadeDeleteRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> JSONResponse:
    try:
        result = await handle_cascade_delete_warehouse(
            warehouse_id=warehouse_id,
            confirmation=body.confirmation,
            preview_token=body.preview_token,
            user_id=user["id"],
            session=session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        return _warehouse_problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Vehicle ↔ warehouse bindings
# ---------------------------------------------------------------------------


@router.get(
    "/warehouses/{warehouse_id}/vehicles",
    response_model=WarehouseVehiclesListResponse,
    summary="[warehouses] Автомобили склада",
    description=(
        "Постранично возвращает автомобили доступного пользователю склада. "
        "Если склад отсутствует или находится вне области доступа, возвращает "
        "404. "
        f"{_WAREHOUSE_READ_ACCESS_DESCRIPTION}"
    ),
    dependencies=[Depends(_warehouse_read)],
)
async def list_warehouse_vehicles(
    warehouse_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=1000),
    status: str | None = Query(default=None, pattern="^(available|reserved|sold)$"),
) -> JSONResponse:
    try:
        result = await handle_list_warehouse_vehicles(
            ListWarehouseVehiclesQuery(
                warehouse_id=warehouse_id,
                page=page,
                limit=limit,
                status=status,
                actor_id=user["id"],
                actor_role=str(user["role"]),
                company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/warehouses/{warehouse_id}/vehicles/bulk",
    status_code=201,
    response_model=BulkAddVehiclesToWarehouseResponse,
    summary="[admin] Массово привязать выбранные автомобили к складу",
    description=(
        "Привязывает выбранные непривязанные автомобили к складу. "
        "Уже занятые при конкурентном изменении состояния пропускаются; "
        "автомобили между складами не переносятся."
    ),
    dependencies=[Depends(_warehouse_admin)],
)
async def bulk_add_vehicles_to_warehouse(
    warehouse_id: UUID,
    body: BulkAddVehiclesToWarehouseRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_bulk_add_vehicles_to_warehouse(
            BulkAddVehiclesToWarehouseCommand(
                warehouse_id=warehouse_id, vehicle_ids=body.vehicle_ids
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    except IntegrityError:
        await session.rollback()
        return _warehouse_problem(
            ServiceError(
                "Состояние склада или выбранных автомобилей изменилось. "
                "Обновите список и повторите попытку.",
                status_code=409,
            )
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return _warehouse_problem(
            ServiceError(
                "Состояние склада или выбранных автомобилей изменилось. "
                "Обновите список и повторите попытку.",
                status_code=409,
            )
        )
    return JSONResponse(content=jsonable_encoder(result), status_code=201)


@router.post(
    "/warehouses/{warehouse_id}/vehicles",
    status_code=201,
    response_model=AddVehicleResponse,
    summary="[admin] Привязать автомобиль к складу",
    description=(
        "Привязывает один автомобиль к складу. Если автомобиль уже привязан "
        "(к этому или другому складу) — возвращает 409."
    ),
    dependencies=[Depends(_warehouse_admin)],
)
async def add_vehicle_to_warehouse(
    warehouse_id: UUID,
    body: AddVehicleToWarehouseRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_add_vehicle_to_warehouse(
            AddVehicleToWarehouseCommand(
                warehouse_id=warehouse_id, vehicle_id=body.vehicle_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
    )


@router.get(
    "/warehouses/{warehouse_id}/vehicles/deletion-check",
    response_model=WarehouseDeletionCheckResponse,
    summary="[admin] Сводка удаления автомобилей склада",
    description="Только carcraft_employee. Проверяет весь склад независимо от пагинации и фильтров.",
    dependencies=[Depends(_vehicle_deletion_admin)],
)
async def check_warehouse_vehicle_deletion(
    warehouse_id: UUID, session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_warehouse_deletion_check(session, warehouse_id)
    except VehicleDeletionError as exc:
        return vehicle_deletion_error(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/warehouses/{warehouse_id}/vehicles",
    response_model=WarehouseUnbindResponse,
    summary="[admin] Отвязать все автомобили склада",
    description="Только carcraft_employee. Требует confirmed=true; сохраняет карточки и историю перемещений.",
    dependencies=[Depends(_vehicle_deletion_admin)],
)
async def unbind_all_warehouse_vehicles(
    warehouse_id: UUID, session: Annotated[AsyncSession, Depends(get_db)],
    body: Annotated[WarehouseUnbindRequest | None, Body()] = None,
) -> JSONResponse:
    try:
        result = await handle_unbind_all_warehouse_vehicles(session, warehouse_id, body.confirmed if body else False)
        await session.commit()
    except VehicleDeletionError as exc:
        await session.rollback()
        return vehicle_deletion_error(exc)
    except Exception:
        await session.rollback()
        raise
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/warehouses/{warehouse_id}/vehicles/bulk-delete",
    response_model=WarehouseBulkDeleteResponse,
    summary="[admin] Удалить разрешённые автомобили склада",
    description="Только carcraft_employee. Требует confirmed=true и УДАЛИТЬ. Блокеры пропускаются; технический сбой откатывает всю операцию.",
    dependencies=[Depends(_vehicle_deletion_admin)],
)
async def bulk_delete_warehouse_vehicles(
    warehouse_id: UUID, session: Annotated[AsyncSession, Depends(get_db)],
    body: Annotated[WarehouseBulkDeleteRequest | None, Body()] = None,
) -> JSONResponse:
    try:
        result = await handle_bulk_delete_warehouse_vehicles(
            session, warehouse_id, body.confirmed if body else False,
            body.confirmation if body else None,
        )
        await session.commit()
    except VehicleDeletionError as exc:
        await session.rollback()
        return vehicle_deletion_error(exc)
    except Exception:
        await session.rollback()
        raise
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/warehouses/{warehouse_id}/vehicles/{vehicle_id}",
    response_model=MessageResponse,
    summary="[admin] Снять привязку автомобиля",
    description=(
        "Удаляет привязку автомобиля к складу. 404 если привязки не было."
    ),
    dependencies=[Depends(_warehouse_admin)],
)
async def remove_vehicle_from_warehouse(
    warehouse_id: UUID,
    vehicle_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_remove_vehicle_from_warehouse(
            RemoveVehicleFromWarehouseCommand(
                warehouse_id=warehouse_id, vehicle_id=vehicle_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/warehouses/{warehouse_id}/vehicles/bind-by-mark",
    response_model=BindByMarkResponse,
    summary="[admin] Массовая привязка автомобилей марки",
    description=(
        "Находит все автомобили указанной марки без привязки к складу и "
        "массово привязывает их к выбранному складу."
    ),
    dependencies=[Depends(_warehouse_admin)],
)
async def bind_vehicles_by_mark(
    warehouse_id: UUID,
    body: BindByMarkRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_bind_vehicles_by_mark(
            BindVehiclesByMarkCommand(
                warehouse_id=warehouse_id, mark_id=body.mark_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return _warehouse_problem(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
