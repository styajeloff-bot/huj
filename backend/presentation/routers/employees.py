"""Employees router — endpoints for managing company employees and permissions.

Routes:
- GET /api/v1/employees — list employees with filters and visibility rules
- POST /api/v1/employees — create or link employee
- GET /api/v1/employees/lookup/warehouses — search company warehouses
- GET /api/v1/employees/lookup/brands — search equipment brands
- GET /api/v1/employees/lookup/dealers — search distributor dealers
- GET /api/v1/employees/lookup/colleagues — search colleagues in company
- GET /api/v1/employees/{user_id}/{company_id}/access-settings — get personal access settings
- PUT /api/v1/employees/{user_id}/{company_id}/access-settings — update personal access settings
- PUT /api/v1/employees/{user_id}/{company_id} — update employee
- PATCH /api/v1/employees/{user_id}/{company_id}/deactivate — soft-deactivate employee
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.employees_v2 import (
    CreateEmployeeCommand,
    DeactivateEmployeeCommand,
    UpdateEmployeeAccessSettingsCommand,
    UpdateEmployeeCommand,
    handle_create_employee,
    handle_deactivate_employee,
    handle_update_employee,
    handle_update_employee_access_settings,
)
from application.errors import ServiceError, domain_to_http
from application.queries.employees import (
    GetEmployeeAccessSettingsQuery,
    ListEmployeesQuery,
    LookupBrandsQuery,
    LookupColleaguesQuery,
    LookupDealersQuery,
    LookupWarehousesQuery,
    handle_employee_filter_options,
    handle_get_employee_access_settings,
    handle_list_employees,
    handle_lookup_brands,
    handle_lookup_colleagues,
    handle_lookup_dealers,
    handle_lookup_warehouses,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user
from presentation.schemas.employees import (
    CreateEmployeeRequest,
    DeactivateEmployeeResponse,
    EmployeeAccessSettingsOut,
    EmployeeFilterOptionsResponse,
    EmployeeListOut,
    EmployeeOut,
    EmployeeRole,
    EmployeesListResponse,
    LookupResponse,
    UpdateEmployeeAccessSettingsRequest,
    UpdateEmployeeRequest,
)

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _extract_actor(current_user: dict[str, Any]) -> tuple[UUID, str, UUID | None]:
    raw_uid = current_user["id"]
    actor_user_id = UUID(str(raw_uid))
    raw_cid = current_user.get("active_company_id") or current_user.get("company_id")
    actor_company_id = UUID(str(raw_cid)) if raw_cid else None
    actor_role = str(current_user.get("active_role") or current_user.get("role") or "")
    return actor_user_id, actor_role, actor_company_id


@router.get(
    "",
    response_model=EmployeesListResponse,
    summary="Список сотрудников",
    description=(
        "Возвращает список сотрудников с фильтрацией, пагинацией и правами "
        "редактирования в соответствии с правилами видимости роли текущего пользователя."
    ),
)
async def list_employees(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    company_id: Annotated[UUID | None, Query(description="Фильтр по компании")] = None,
    position_id: Annotated[
        UUID | None, Query(description="Фильтр по должности")
    ] = None,
    role: Annotated[EmployeeRole | None, Query(description="Роль сотрудника")] = None,
    distributor_id: UUID | None = None,
    dealer_id: UUID | None = None,
    brand_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    name: Annotated[str | None, Query(description="Поиск по ФИО")] = None,
    phone: Annotated[str | None, Query(description="Поиск по телефону")] = None,
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    per_page: Annotated[
        int, Query(ge=1, le=100, description="Количество элементов на странице")
    ] = 20,
) -> EmployeesListResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    from application.permissions import check_section_access

    if not await check_section_access(
        session,
        user_id=actor_user_id,
        company_id=actor_company_id,
        role=actor_role,
        section_code="employees",
    ):
        raise HTTPException(status_code=403, detail="У вас нет доступа к этому разделу")

    query = ListEmployeesQuery(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        filter_company_id=company_id,
        position_id=position_id,
        role=role,
        distributor_id=distributor_id,
        dealer_id=dealer_id,
        brand_id=brand_id,
        warehouse_id=warehouse_id,
        name=name,
        phone=phone,
        page=page,
        per_page=per_page,
    )
    try:
        items, total = await handle_list_employees(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    return EmployeesListResponse(
        items=[EmployeeListOut.model_validate(x) for x in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/filter-options",
    response_model=EmployeeFilterOptionsResponse,
    summary="Фильтры списка сотрудников",
    description="Возвращает объекты доступных сотрудников по всем страницам с учётом выбранной роли.",
)
async def employee_filter_options(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    role: EmployeeRole | None = None,
) -> JSONResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    from application.permissions import check_section_access

    if not await check_section_access(
        session,
        user_id=actor_user_id,
        company_id=actor_company_id,
        role=actor_role,
        section_code="employees",
    ):
        raise HTTPException(status_code=403, detail="У вас нет доступа к этому разделу")
    query = ListEmployeesQuery(actor_user_id, actor_role, actor_company_id, role=role)
    try:
        result = await handle_employee_filter_options(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(
        content=jsonable_encoder(EmployeeFilterOptionsResponse.model_validate(result))
    )


@router.post(
    "",
    response_model=EmployeeOut,
    status_code=201,
    summary="Создать сотрудника",
    description=(
        "Создаёт пользователя (если отсутствует) и связывает его с указанной компанией. "
        "Доступно администраторам компании и сотрудникам CarCraft."
    ),
)
async def create_employee(
    body: CreateEmployeeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> EmployeeOut:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    cmd = CreateEmployeeCommand(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        name=body.name,
        phone=body.phone,
        additional_phone=body.additional_phone,
        company_id=body.company_id,
        role=body.role,
        position_id=body.position_id,
        can_view_applications=body.can_view_applications,
        can_create_applications=body.can_create_applications,
        can_create_employees=body.can_create_employees,
        is_active=body.is_active,
    )
    try:
        result = await handle_create_employee(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    await session.commit()
    return EmployeeOut.model_validate(result)


# --- Lookup endpoints for access rules selectors ---


@router.get(
    "/lookup/warehouses",
    response_model=LookupResponse,
    summary="Поиск складов",
    description="Поиск складов компании с фильтрацией по правам вызывающего.",
)
async def lookup_warehouses(
    company_id: Annotated[UUID, Query(description="ID компании")],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    q: Annotated[str | None, Query(description="Поисковая строка")] = None,
) -> LookupResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    query = LookupWarehousesQuery(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        company_id=company_id,
        q=q,
    )
    try:
        result = await handle_lookup_warehouses(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    return LookupResponse.model_validate(result)


@router.get(
    "/lookup/brands",
    response_model=LookupResponse,
    summary="Поиск брендов/марок",
    description="Поиск марок спецтехники и автомобилей.",
)
async def lookup_brands(
    company_id: Annotated[UUID, Query(description="ID компании")],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    q: Annotated[str | None, Query(description="Поисковая строка")] = None,
) -> LookupResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    query = LookupBrandsQuery(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        company_id=company_id,
        q=q,
    )
    try:
        result = await handle_lookup_brands(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    return LookupResponse.model_validate(result)


@router.get(
    "/lookup/dealers",
    response_model=LookupResponse,
    summary="Поиск дилеров дистрибьютора",
    description="Поиск дилерских компаний, связанных с данным дистрибьютором.",
)
async def lookup_dealers(
    distributor_company_id: Annotated[
        UUID, Query(description="ID компании дистрибьютора")
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    q: Annotated[str | None, Query(description="Поисковая строка")] = None,
) -> LookupResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    query = LookupDealersQuery(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        distributor_company_id=distributor_company_id,
        q=q,
    )
    try:
        result = await handle_lookup_dealers(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    return LookupResponse.model_validate(result)


@router.get(
    "/lookup/colleagues",
    response_model=LookupResponse,
    summary="Поиск коллег компании",
    description="Поиск сотрудников компании для правил доступа к заявкам.",
)
async def lookup_colleagues(
    company_id: Annotated[UUID, Query(description="ID компании")],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    exclude_user_id: Annotated[
        UUID | None, Query(description="Исключить ID пользователя")
    ] = None,
    q: Annotated[str | None, Query(description="Поисковая строка")] = None,
) -> LookupResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    query = LookupColleaguesQuery(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        company_id=company_id,
        exclude_user_id=exclude_user_id,
        q=q,
    )
    try:
        result = await handle_lookup_colleagues(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    return LookupResponse.model_validate(result)


# --- Access settings endpoints ---


@router.get(
    "/{user_id}/{company_id}/access-settings",
    response_model=EmployeeAccessSettingsOut,
    summary="Получить настройки прав доступа сотрудника",
    description=(
        "Возвращает объектные правила, доступ к разделам и допустимые опции выбора "
        "для настраивающего пользователя."
    ),
)
async def get_employee_access_settings(
    user_id: Annotated[UUID, Path(description="ID пользователя")],
    company_id: Annotated[UUID, Path(description="ID компании")],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> EmployeeAccessSettingsOut:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    query = GetEmployeeAccessSettingsQuery(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        user_id=user_id,
        company_id=company_id,
    )
    try:
        result = await handle_get_employee_access_settings(query, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    return EmployeeAccessSettingsOut.model_validate(result)


@router.put(
    "/{user_id}/{company_id}/access-settings",
    response_model=EmployeeAccessSettingsOut,
    summary="Сохранить настройки прав доступа сотрудника",
    description=(
        "Обновляет персональные правила доступа, доступ к разделам и флаг создания сотрудников. "
        "Проверяет делегирование прав (анти-эскалацию)."
    ),
)
async def update_employee_access_settings(
    user_id: Annotated[UUID, Path(description="ID пользователя")],
    company_id: Annotated[UUID, Path(description="ID компании")],
    body: UpdateEmployeeAccessSettingsRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> EmployeeAccessSettingsOut:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    cmd = UpdateEmployeeAccessSettingsCommand(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        user_id=user_id,
        company_id=company_id,
        additional_phone=body.additional_phone,
        can_create_employees=body.can_create_employees,
        rules=body.rules,
        sections=body.sections,
    )
    try:
        result = await handle_update_employee_access_settings(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    await session.commit()
    return EmployeeAccessSettingsOut.model_validate(result)


@router.put(
    "/{user_id}/{company_id}",
    response_model=EmployeeOut,
    status_code=200,
    summary="Редактировать сотрудника",
    description=(
        "Обновляет данные сотрудника и его связь с компанией. "
        "Дистрибьютор не может редактировать сотрудников дилеров."
    ),
)
async def update_employee(
    user_id: Annotated[UUID, Path(description="ID пользователя")],
    company_id: Annotated[UUID, Path(description="ID компании")],
    body: UpdateEmployeeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> EmployeeOut:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    cmd = UpdateEmployeeCommand(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        user_id=user_id,
        company_id=company_id,
        name=body.name,
        phone=body.phone,
        additional_phone=body.additional_phone,
        role=body.role,
        position_id=body.position_id,
        can_view_applications=body.can_view_applications,
        can_create_applications=body.can_create_applications,
        can_create_employees=body.can_create_employees,
        is_active=body.is_active,
    )
    try:
        result = await handle_update_employee(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    await session.commit()
    return EmployeeOut.model_validate(result)


@router.patch(
    "/{user_id}/{company_id}/deactivate",
    response_model=DeactivateEmployeeResponse,
    status_code=200,
    summary="Отключить сотрудника",
    description=(
        "Деактивирует связь сотрудника с компанией (user_companies.is_active = false). "
        "Учётная запись пользователя не затрагивается."
    ),
)
async def deactivate_employee(
    user_id: Annotated[UUID, Path(description="ID пользователя")],
    company_id: Annotated[UUID, Path(description="ID компании")],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> DeactivateEmployeeResponse:
    actor_user_id, actor_role, actor_company_id = _extract_actor(current_user)
    cmd = DeactivateEmployeeCommand(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        user_id=user_id,
        company_id=company_id,
    )
    try:
        await handle_deactivate_employee(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc

    await session.commit()
    return DeactivateEmployeeResponse(success=True, message="Сотрудник деактивирован")
