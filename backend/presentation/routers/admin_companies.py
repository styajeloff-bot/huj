"""Admin routes for /api/v1/admin/companies (Phase 6 — F2)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_companies import (
    AdminUpdateCompanyCommand,
    CreateCompanyCommand,
    CreateContractorCommand,
    CreateContractorLinkCommand,
    DeleteContractorLinkCommand,
    ImportContractorLinksCommand,
    LinkDistributorDealerCommand,
    SetContractorLeasingCompaniesCommand,
    SetDistributorBrandsCommand,
    SetLeasingCompanyContractorsCommand,
    UnlinkDistributorDealerCommand,
    UpdateContractorCommand,
    handle_admin_update_company,
    handle_create_company,
    handle_create_contractor,
    handle_create_contractor_link,
    handle_delete_contractor_link,
    handle_import_contractor_links,
    handle_link_distributor_dealer,
    handle_list_contractor_leasing_company_links,
    handle_list_leasing_company_contractor_links,
    handle_set_contractor_leasing_companies,
    handle_set_distributor_brands,
    handle_set_leasing_company_contractors,
    handle_unlink_distributor_dealer,
    handle_update_contractor,
)
from application.errors import ServiceError, domain_to_http
from application.queries.admin_companies import (
    CompareCompanyChangeHistoryQuery,
    GetDistributorBrandsQuery,
    GetDistributorInventoryBrandsQuery,
    ListCompanyChangeHistoryQuery,
    ListContractorLinksQuery,
    ListContractorsQuery,
    ListDistributorDealersQuery,
    handle_compare_company_change_history,
    handle_get_distributor_brands,
    handle_get_distributor_inventory_brands,
    handle_list_company_change_history,
    handle_list_contractor_links,
    handle_list_contractors,
    handle_list_distributor_dealers,
)
from domain.errors import DomainError
from domain.services.company_lookup import CompanyLookupProvider
from domain.services.scopes import COMPANIES_ADMIN
from infrastructure.database import get_db
from infrastructure.messaging.dwh_events import emit_company_changed
from infrastructure.services.company_lookup import (
    get_company_lookup_provider,
)
from presentation.dependencies.auth import require_scopes
from presentation.schemas.admin import CompanyCreateRequest, CompanyResponse
from presentation.schemas.companies import (
    AdminCompanyTypeTransitionConflictResponse,
    AdminCompanyUpdateRequest,
    AdminCompanyUpdateResponse,
    CompanyChangeHistoryComparisonResponse,
    CompanyChangeHistoryResponse,
    ContractorIdsRequest,
    ContractorImportResponse,
    ContractorLinksListResponse,
    ContractorLinksResponse,
    ContractorListResponse,
    CreateContractorLinkRequest,
    CreateContractorLinkResponse,
    CreateContractorRequest,
    CreateContractorResponse,
    DistributorBrandsRequest,
    DistributorBrandsResponse,
    DistributorDealersListResponse,
    DistributorInventoryBrandsResponse,
    LeasingCompanyIdsRequest,
    LinkDistributorDealerRequest,
    LinkDistributorDealerResponse,
    UnlinkDistributorDealerResponse,
    UpdateContractorRequest,
    UpdateContractorResponse,
)

router = APIRouter()

_employee_only = require_scopes(COMPANIES_ADMIN)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    if isinstance(exc, ServiceError) and exc.code == "TYPE_TRANSITION_CONFLICT":
        blockers = getattr(exc, "blockers", [])
        return HTTPException(
            status_code=409,
            detail={
                "detail": str(exc),
                "code": exc.code,
                "field_errors": [
                    {
                        "field": "company_type",
                        "code": "type_transition_conflict",
                        "message": str(exc),
                        "blockers": blockers,
                    }
                ],
                "blockers": blockers,
            },
        )
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/{company_id}/change-history",
    response_model=CompanyChangeHistoryResponse,
    summary="[admin] История изменений реквизитов компании",
    description="Возвращает версии указанной компании в обратном хронологическом порядке; требует scope `companies:admin`.",
    dependencies=[Depends(_employee_only)],
)
async def get_company_change_history(
    company_id: Annotated[UUID, Path()], session: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100), cursor: str | None = Query(default=None),
) -> JSONResponse:
    try:
        result = await handle_list_company_change_history(ListCompanyChangeHistoryQuery(company_id, limit, cursor), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{company_id}/change-history/compare",
    response_model=CompanyChangeHistoryComparisonResponse,
    summary="[admin] Сравнить версии истории компании",
    description="Сервер вычисляет differences base/target; target должна быть строго позже base.",
    dependencies=[Depends(_employee_only)],
)
async def compare_company_change_history(
    company_id: Annotated[UUID, Path()], session: Annotated[AsyncSession, Depends(get_db)],
    base_id: UUID = Query(), target_id: UUID = Query(),
) -> JSONResponse:
    try:
        result = await handle_compare_company_change_history(CompareCompanyChangeHistoryQuery(company_id, base_id, target_id), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{company_id}/distributor-brands",
    response_model=DistributorBrandsResponse,
    summary="[admin] Марки компании-дистрибьютора",
    description=(
        "Возвращает полный справочник автомобильных марок и активные марки "
        "выбранной компании. Доступно только сотрудникам CarCraft."
    ),
    dependencies=[Depends(_employee_only)],
)
async def get_distributor_brands(
    company_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_distributor_brands(
            GetDistributorBrandsQuery(company_id=company_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{company_id}/distributor-inventory-brands",
    response_model=DistributorInventoryBrandsResponse,
    summary="[admin] Марки автомобилей дилеров дистрибьютора",
    description=(
        "Возвращает марки ТС связанных дилеров, включая активные группы дилеров. "
        "Принадлежность ТС определяется по владельцу склада с резервной связью "
        "через дилера ТС. При отсутствии автомобилей список пуст; ручные настройки "
        "марок дистрибьютора не используются. Доступно только сотрудникам CarCraft."
    ),
    dependencies=[Depends(_employee_only)],
)
async def get_distributor_inventory_brands(
    company_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_distributor_inventory_brands(
            GetDistributorInventoryBrandsQuery(company_id=company_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/{company_id}/distributor-brands",
    response_model=DistributorBrandsResponse,
    summary="[admin] Сохранить марки компании-дистрибьютора",
    description=(
        "Атомарно заменяет активный набор марок: удалённые связи мягко "
        "деактивируются, повторно выбранные реактивируются. Доступно только "
        "сотрудникам CarCraft."
    ),
    dependencies=[Depends(_employee_only)],
)
async def set_distributor_brands(
    company_id: Annotated[UUID, Path()],
    body: DistributorBrandsRequest,
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_set_distributor_brands(
            SetDistributorBrandsCommand(
                company_id=company_id,
                actor_user_id=user["id"],
                brand_ids=body.brand_ids,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "",
    status_code=201,
    response_model=CompanyResponse,
    summary="[admin] Создать компанию",
    description=(
        "Создаёт компанию по ИНН с опциональным обогащением из внешнего справочника "
        "(short_name / legal_address / director_full_name / OKVED). "
        "Для `leasing_company` / `distributor` создаётся связанный подтип."
    ),
    dependencies=[Depends(_employee_only)],
)
async def create_company(
    body: CompanyCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    lookup_provider: Annotated[
        CompanyLookupProvider, Depends(get_company_lookup_provider)
    ],
) -> JSONResponse:
    try:
        result = await handle_create_company(
            CreateCompanyCommand(
                inn=body.inn,
                company_type=body.company_type,
                name=body.name,
                kpp=body.kpp,
                ogrn=body.ogrn,
                legal_address=body.legal_address,
                phone=body.phone,
                email=body.email,
            ),
            session,
            lookup_provider,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "company": jsonable_encoder(result),
            "message": "Компания успешно создана",
        },
        status_code=201,
        headers={"Location": f"/api/v1/admin/companies/{result['id']}"},
    )


@router.get(
    "/contractors",
    response_model=ContractorListResponse,
    summary="[admin] Список подрядчиков",
    description=(
        "Возвращает справочник `contractors`. Поддерживает фильтры по "
        "названию подрядчика и ИНН."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_contractors(
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    contractor_name: str | None = Query(default=None),
    inn: str | None = Query(default=None),
) -> JSONResponse:
    result = await handle_list_contractors(
        ListContractorsQuery(
            page=page,
            limit=limit,
            contractor_name=contractor_name,
            inn=inn,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/contractors",
    status_code=201,
    response_model=CreateContractorResponse,
    summary="[admin] Создать подрядчика",
    description=(
        "Создаёт подрядчика в справочнике по ИНН. Если подрядчик с таким "
        "ИНН уже есть, возвращает существующую запись без дубля."
    ),
    dependencies=[Depends(_employee_only)],
)
async def create_contractor(
    body: CreateContractorRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_contractor(
            CreateContractorCommand(
                contractor_name=body.contractor_name,
                contractor_inn=body.contractor_inn,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
        headers={
            "Location": (
                "/api/v1/admin/companies/contractors/"
                f"{result['contractor']['id']}"
            )
        },
    )


@router.get(
    "/contractors/links",
    response_model=ContractorLinksListResponse,
    summary="[admin] Список связей ЛК с подрядчиками",
    description=(
        "Возвращает связи `leasing_company_contractors` с данными ЛК и "
        "подрядчика. Поддерживает фильтры по ЛК, названию подрядчика и ИНН."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_contractor_links(
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    leasing_company_id: UUID | None = Query(default=None),
    contractor_name: str | None = Query(default=None),
    inn: str | None = Query(default=None),
) -> JSONResponse:
    result = await handle_list_contractor_links(
        ListContractorLinksQuery(
            page=page,
            limit=limit,
            leasing_company_id=leasing_company_id,
            contractor_name=contractor_name,
            inn=inn,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/contractors/links",
    status_code=201,
    response_model=CreateContractorLinkResponse,
    summary="[admin] Создать связь ЛК с подрядчиком",
    description=(
        "Находит или создаёт подрядчика по ИНН, затем создаёт связь с "
        "`leasing_companies.id`. Повторная пара возвращается без дубля."
    ),
    dependencies=[Depends(_employee_only)],
)
async def create_contractor_link(
    body: CreateContractorLinkRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_contractor_link(
            CreateContractorLinkCommand(
                leasing_company_id=body.leasing_company_id,
                contractor_name=body.contractor_name,
                contractor_inn=body.contractor_inn,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
        headers={
            "Location": (
                f"/api/v1/admin/companies/contractors/{result['item']['id']}"
            )
        },
    )


@router.get(
    "/leasing-companies/{leasing_company_id}/contractors",
    response_model=ContractorLinksResponse,
    summary="[admin] Подрядчики лизинговой компании",
    description="Возвращает текущие связи выбранной ЛК с подрядчиками.",
    dependencies=[Depends(_employee_only)],
)
async def list_leasing_company_contractors(
    leasing_company_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_list_leasing_company_contractor_links(
            leasing_company_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/leasing-companies/{leasing_company_id}/contractors",
    response_model=ContractorLinksResponse,
    summary="[admin] Синхронизировать подрядчиков ЛК",
    description=(
        "Заменяет полный набор связей указанной ЛК на переданный список "
        "`contractor_ids`."
    ),
    dependencies=[Depends(_employee_only)],
)
async def set_leasing_company_contractors(
    leasing_company_id: Annotated[UUID, Path()],
    body: ContractorIdsRequest,
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_set_leasing_company_contractors(
            SetLeasingCompanyContractorsCommand(
                leasing_company_id=leasing_company_id,
                actor_user_id=user["id"],
                contractor_ids=body.contractor_ids,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/contractors/{contractor_id}/leasing-companies",
    response_model=ContractorLinksResponse,
    summary="[admin] ЛК подрядчика",
    description="Возвращает текущие связи выбранного подрядчика с ЛК.",
    dependencies=[Depends(_employee_only)],
)
async def list_contractor_leasing_companies(
    contractor_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_list_contractor_leasing_company_links(
            contractor_id, session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/contractors/{contractor_id}/leasing-companies",
    response_model=ContractorLinksResponse,
    summary="[admin] Синхронизировать ЛК подрядчика",
    description=(
        "Заменяет полный набор связей указанного подрядчика на переданный "
        "список `leasing_company_ids`."
    ),
    dependencies=[Depends(_employee_only)],
)
async def set_contractor_leasing_companies(
    contractor_id: Annotated[UUID, Path()],
    body: LeasingCompanyIdsRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_set_contractor_leasing_companies(
            SetContractorLeasingCompaniesCommand(
                contractor_id=contractor_id,
                leasing_company_ids=body.leasing_company_ids,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/contractors/{contractor_id}",
    response_model=UpdateContractorResponse,
    summary="[admin] Обновить название подрядчика",
    description="Обновляет только `contractors.name`; ИНН подрядчика неизменяем.",
    dependencies=[Depends(_employee_only)],
)
async def update_contractor(
    contractor_id: Annotated[UUID, Path()],
    body: UpdateContractorRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_contractor(
            UpdateContractorCommand(contractor_id=contractor_id, name=body.name),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/contractors/links/{link_id}",
    status_code=204,
    summary="[admin] Отвязать подрядчика от ЛК",
    description=(
        "Удаляет только связь `leasing_company_contractors`; запись "
        "`contractors` остаётся в каталоге."
    ),
    dependencies=[Depends(_employee_only)],
)
async def delete_contractor_link(
    link_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await handle_delete_contractor_link(
            DeleteContractorLinkCommand(link_id=link_id), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/contractors/import",
    response_model=ContractorImportResponse,
    summary="[admin] Импорт связей ЛК с подрядчиками из Excel",
    description=(
        "Принимает .xlsx/.xls с колонками `leasing_company_inn`, "
        "`contractor_name`, `contractor_inn`. Если ЛК не найдена по ИНН, "
        "строка попадает в ошибки и пропускается."
    ),
    dependencies=[Depends(_employee_only)],
)
async def import_contractor_links(
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> JSONResponse:
    data = await file.read()
    try:
        result = await handle_import_contractor_links(
            ImportContractorLinksCommand(
                filename=file.filename or "contractors.xlsx",
                data=data,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/distributors/{distributor_company_id}/dealers",
    response_model=DistributorDealersListResponse,
    summary="[admin] Список дилеров дистрибьютора",
    description=(
        "Возвращает список компаний-дилеров, привязанных к указанному "
        "дистрибьютору, с пагинацией."
    ),
    dependencies=[Depends(_employee_only)],
)
async def list_distributor_dealers(
    distributor_company_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> JSONResponse:
    try:
        result = await handle_list_distributor_dealers(
            ListDistributorDealersQuery(
                distributor_company_id=distributor_company_id,
                page=page,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/distributors/{distributor_company_id}/dealers",
    response_model=LinkDistributorDealerResponse,
    summary="[admin] Привязать дилера к дистрибьютору",
    description=(
        "Создаёт связь между дистрибьютором и дилером. "
        "У дилера может быть только один дистрибьютор."
    ),
    dependencies=[Depends(_employee_only)],
)
async def link_distributor_dealer(
    distributor_company_id: Annotated[UUID, Path()],
    body: LinkDistributorDealerRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_link_distributor_dealer(
            LinkDistributorDealerCommand(
                distributor_company_id=distributor_company_id,
                dealer_company_id=body.dealer_company_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/distributors/{distributor_company_id}/dealers/{dealer_company_id}",
    response_model=UnlinkDistributorDealerResponse,
    summary="[admin] Отвязать дилера от дистрибьютора",
    description="Удаляет связь между дистрибьютором и дилером.",
    dependencies=[Depends(_employee_only)],
)
async def unlink_distributor_dealer(
    distributor_company_id: Annotated[UUID, Path()],
    dealer_company_id: Annotated[UUID, Path()],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_unlink_distributor_dealer(
            UnlinkDistributorDealerCommand(
                distributor_company_id=distributor_company_id,
                dealer_company_id=dealer_company_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{company_id}",
    response_model=AdminCompanyUpdateResponse,
    responses={409: {"model": AdminCompanyTypeTransitionConflictResponse}},
    summary="[admin] Частично обновить компанию",
    description=(
        "Обновляет только переданные реквизиты и контакты компании. Доступно "
        "субъекту со scope `companies:admin`; деактивация сохраняет стандартный "
        "каскад пользователей и типовых записей компании."
    ),
    dependencies=[Depends(_employee_only)],
)
async def update_admin_company(
    company_id: Annotated[UUID, Path()],
    body: AdminCompanyUpdateRequest,
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_admin_update_company(
            AdminUpdateCompanyCommand(
                company_id=company_id,
                actor_id=user["id"],
                data=body.model_dump(exclude_unset=True),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc) from exc
    event_payload = result.pop("company_changed_event")
    await session.commit()
    if event_payload is not None:
        emit_company_changed(event_payload)
    return JSONResponse(content=jsonable_encoder(result))
