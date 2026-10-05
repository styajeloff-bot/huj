"""Leasing applications API (Phase 3).

Owner-scoped: scopes limit *which roles* can hit each endpoint, and the
domain entity ``LeasingApplication`` enforces ownership per-row.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.application_create_idempotency import (
    begin_application_create,
    finish_application_create,
)
from application.commands.application_vehicles import (
    AssignApplicationVehicleEmployeesCommand,
    handle_assign_application_vehicle_employees,
)
from application.commands.applications import (
    ApplicationItemUpdate,
    ApplicationVehiclePayload,
    AssignApplicationEmployeesCommand,
    AttachDocumentsToApplicationCommand,
    ChangeStatusCommand,
    CreateDraftCommand,
    UpdateAdditionalOptionsCommand,
    UpdateApplicationItemsCommand,
    UpdateCompanyCommand,
    UpdateConditionsCommand,
    UpdateLeasingCompaniesCommand,
    UpdateQuestionnaireCommand,
    UpdateVehiclesCommand,
    handle_assign_application_employees,
    handle_attach_documents_to_application,
    handle_change_status,
    handle_create_draft,
    handle_update_additional_options,
    handle_update_application_items,
    handle_update_company,
    handle_update_conditions,
    handle_update_leasing_companies,
    handle_update_questionnaire,
    handle_update_vehicles,
)
from application.commands.applications.distribute_dealer import (
    DistributeDealerCommand,
    handle_distribute_dealer,
)
from application.commands.leasing_response_client_decision import (
    ClientProposalDecisionCommand,
    handle_client_proposal_decision,
)
from application.commands.select_leasing_company import (
    SelectLeasingCompanyCommand,
    handle_select_leasing_company,
)
from application.commands.sopd_passport_snapshots import (
    PassportServiceError,
    PassportUploadPage,
    begin_manual_snapshot,
    expected_full_name_for_application_signer,
    require_application_signer_snapshot,
)
from application.commands.sopd_passport_snapshots import (
    confirm as confirm_passport_snapshot,
)
from application.commands.sopd_passport_snapshots import (
    recognize as recognize_passport_snapshot,
)
from application.commands.sopd_passport_snapshots import (
    response as passport_snapshot_response,
)
from application.commands.sopd_passport_snapshots import (
    save_draft as save_passport_draft,
)
from application.errors import ServiceError, domain_to_http
from application.queries.application_employees import (
    SearchApplicationEmployeesQuery,
    handle_search_application_employees,
)
from application.queries.application_references import (
    ListLeasingRegionsQuery,
    handle_list_leasing_purposes,
    handle_list_leasing_regions,
)
from application.queries.application_vehicles import (
    SearchApplicationVehicleEmployeesQuery,
    handle_search_application_vehicle_employees,
)
from application.queries.applications import (
    ExportApplicationQuery,
    GetApplicationQuery,
    GetSopdSignerCandidatesQuery,
    ListApplicationsQuery,
    ResolveLeasingCompanyQuery,
    handle_export_application_pdf,
    handle_get_application,
    handle_get_sopd_signer_candidates,
    handle_list_applications,
    handle_resolve_leasing_company,
)
from application.queries.applications.get_application import ApplicationAccessQuery
from application.queries.documents import (
    DownloadApplicationArchiveQuery,
    ListDocumentRequestsQuery,
    ListDocumentRequirementsQuery,
    ListDocumentsForApplicationQuery,
    handle_download_application_archive,
    handle_list_document_requests,
    handle_list_document_requirements,
    handle_list_documents_for_application,
)
from application.queries.leasing_response import (
    GetClientLeasingResponsesQuery,
    handle_get_client_leasing_responses,
)
from application.queries.leasing_response_pdf import (
    GetLcResponsePdfQuery,
    handle_get_lc_response_pdf,
)
from application.queries.sopd_cache import (
    SopdPdfPending,
    SopdPdfReady,
    resolve_sopd_pdf,
)
from application.queries.sopd_status import (
    GetSopdStatusQuery,
    handle_get_sopd_status,
)
from domain.application_sources import SOURCE_VIEW_ROLES
from domain.dealer_distribution import DistributionItem
from domain.errors import DomainError
from domain.services.company_lookup import CompanyLookupProvider
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import (
    APPLICATIONS_READ,
    APPLICATIONS_WRITE,
    DOCUMENTS_READ,
)
from domain.storefronts import CatalogScope
from infrastructure.services.company_lookup import get_company_lookup_provider
from infrastructure.services.object_storage import get_object_storage
from presentation.assignment_errors import assignment_error_response
from presentation.dependencies.auth import (
    get_current_user,
    require_roles,
    require_scopes,
)
from presentation.dependencies.leasing_context import get_leasing_context
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.schemas.applications import (
    AdditionalOptionsUpdateRequest,
    AdditionalOptionsUpdateResponse,
    ApplicationDetailResponse,
    ApplicationEmployeeSearchResponse,
    ApplicationListResponse,
    ApplicationSubresourceResponse,
    AssignApplicationEmployeesRequest,
    AssignApplicationEmployeesResponse,
    AssignApplicationVehicleEmployeesResponse,
    AttachDocumentsRequest,
    AttachDocumentsResponse,
    ClientProposalDecisionRequest,
    ClientProposalDecisionResponse,
    CreateApplicationInitRequest,
    CreateApplicationInitResponse,
    LeasingPurposesResponse,
    LeasingRegionsResponse,
    QuestionnaireUpdateResponse,
    SelectLeasingCompanyResponse,
    SopdSignerCandidatesResponse,
    SopdStatusListResponse,
    StatusUpdateRequest,
    StatusUpdateResponse,
    UpdateApplicationItemsRequest,
    UpdateApplicationItemsResponse,
    UpdateCompanyRequest,
    UpdateConditionsRequest,
    UpdateLeasingCompaniesRequest,
    UpdateQuestionnaireRequest,
    UpdateVehiclesRequest,
    application_commerce_money_to_wire,
)
from presentation.schemas.dealer_distribution import (
    DealerDistributionRequest,
    DealerDistributionResponse,
)
from presentation.schemas.documents import (
    DocumentForApplicationResponse,
    DocumentRequestsResponse,
)
from presentation.schemas.leasing import ClientLeasingResponsesResponse
from presentation.schemas.signatures import (
    SopdPassportFieldsRequest,
    SopdPassportSnapshotResponse,
)

router = APIRouter()

_read_access = require_scopes(APPLICATIONS_READ)
_write_access = require_scopes(APPLICATIONS_WRITE)
_documents_read_access = require_scopes(DOCUMENTS_READ)
_additional_options_write_access = require_roles(
    "dealer",
    "distributor",
    "leasing_company",
)
_employee_assignment_roles = require_roles(
    "dealer",
    "distributor",
    "carcraft_employee",
)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _application_json(result: dict[str, Any], actor_role: str | None) -> JSONResponse:
    if actor_role not in SOURCE_VIEW_ROLES:
        result.pop("source_type", None)
        application = result.get("application")
        if isinstance(application, dict):
            application.pop("source_type", None)
    return JSONResponse(content=jsonable_encoder(result))


async def _resolve_lc_id(session: AsyncSession, user: dict[str, Any]) -> UUID | None:
    return await handle_resolve_leasing_company(
        ResolveLeasingCompanyQuery(
            company_id=user.get("company_id"),
            role=str(user.get("role") or ""),
        ),
        session,
    )


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


@router.post(
    "/{application_id}/dealer-distributions",
    response_model=DealerDistributionResponse,
    summary="Распределить количество автомобилей дилеру",
    description="Дистрибьютор атомарно распределяет неназначенный остаток нескольких позиций своего склада. request_id обеспечивает безопасный повтор операции.",
    dependencies=[Depends(require_roles("distributor"))],
)
async def distribute_application_dealer(
    application_id: UUID,
    body: DealerDistributionRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_distribute_dealer(
            DistributeDealerCommand(
                application_id=application_id,
                dealer_id=body.dealer_id,
                request_id=body.request_id,
                items=tuple(
                    DistributionItem(
                        item.application_vehicle_id,
                        item.quantity,
                        item.expected_unassigned_quantity,
                    )
                    for item in body.items
                ),
                actor_id=user["id"],
                actor_role=user["role"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        return assignment_error_response(exc)
    except Exception:
        await session.rollback()
        raise
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/",
    response_model=ApplicationListResponse,
    include_in_schema=False,
    dependencies=[Depends(_read_access)],
)
@router.get(
    "",
    response_model=ApplicationListResponse,
    summary="Список заявок пользователя",
    description=(
        "Возвращает заявки, доступные текущему пользователю: "
        "клиенту — созданные им и разрешённые для текущей компании, "
        "дилеру — созданные им или его компанией, "
        "лизинговой компании — где их LC выбрана; сотруднику — все."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_applications(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    kind: Literal["application", "fast_deal"] | None = Query(
        default=None,
        description=(
            "Вид строк: `application` — обычные заявки, `fast_deal` — быстрая "
            "регистрация сделки. Без параметра — объединённый список; фильтр "
            "статуса или источника обычной заявки исключает fast deals."
        ),
    ),
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_list_applications(
            ListApplicationsQuery(
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
                status=status,
                source_type=source_type,
                search=search,
                kind=kind,
                page=page,
                limit=limit,
                include_authored_client_applications=(
                    user.get("notification_company_id") is None
                ),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    ApplicationListResponse.model_validate(result)
    payload = {
        **result,
        "applications": [
            application_commerce_money_to_wire(application)
            for application in result["applications"]
        ],
    }
    return JSONResponse(content=jsonable_encoder(payload))


@router.get(
    "/leasing-purposes",
    response_model=LeasingPurposesResponse,
    summary="Справочник целей приобретения ТС",
    description="Возвращает справочник целей приобретения ТС для формы заявки.",
    dependencies=[Depends(_read_access)],
)
async def list_leasing_purposes_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_leasing_purposes(session)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/leasing-regions",
    response_model=LeasingRegionsResponse,
    summary="Справочник регионов ТС",
    description=(
        "Возвращает регионы для формы заявки. Query-параметр q фильтрует "
        "по названию или номеру региона."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_leasing_regions_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
    q: str | None = Query(default=None, description="Часть названия региона"),
) -> JSONResponse:
    result = await handle_list_leasing_regions(ListLeasingRegionsQuery(q=q), session)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}",
    response_model=ApplicationDetailResponse,
    summary="Детали заявки",
    description=(
        "Возвращает заявку со всеми связанными сущностями: предметы сделки "
        "(`vehicle` и `special_equipment`), анкета, расчёты, статусы ЛК, "
        "комментарии и названия ЛК. Поле `vehicles` сохранено для обратной "
        "совместимости, общий контракт находится в `items`."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_application(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_get_application(
            GetApplicationQuery(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    ApplicationDetailResponse.model_validate(result)
    payload = application_commerce_money_to_wire(result)
    return JSONResponse(content=jsonable_encoder(payload))


_PASSPORT_TYPES = frozenset({"image/jpeg", "image/jpg", "image/png"})


async def _passport_page(file: UploadFile | None, label: str) -> PassportUploadPage:
    if file is None:
        raise HTTPException(422, "passport_main и passport_registration должны передаваться вместе")
    if (file.content_type or "").lower() not in _PASSPORT_TYPES:
        raise HTTPException(422, f"{label}: допустимы только JPG / PNG")
    data = await file.read()
    if not data:
        raise HTTPException(422, f"{label}: файл не должен быть пустым")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, f"{label} превышает допустимый размер (10 МБ)")
    return PassportUploadPage(data, file.filename or f"{label}.jpg", file.content_type or "image/jpeg")


async def _snapshot_access(
    *, application_id: UUID, signer_key: str, user: dict[str, Any], session: AsyncSession,
    provider: CompanyLookupProvider, allow_bound_request: bool = False,
) -> dict[str, Any] | None:
    return await require_application_signer_snapshot(
        session,
        access=ApplicationAccessQuery(
            application_id=application_id, actor_id=user["id"], actor_role=str(user.get("role") or ""),
            actor_company_id=user.get("company_id"), actor_leasing_company_id=await _resolve_lc_id(session, user),
        ), signer_key=signer_key, provider=provider, allow_bound_request=allow_bound_request,
    )


def _require_passport_snapshot(snapshot: dict[str, Any] | None, *, confirmed: bool = False) -> dict[str, Any]:
    if snapshot is None:
        raise ServiceError("Снимок паспорта не найден", 404)
    if confirmed and not snapshot.get("confirmed_fields"):
        raise ServiceError("Подтверждённый снимок паспорта отсутствует", 409)
    if confirmed and snapshot.get("has_unsaved_changes"):
        raise ServiceError("Есть несохранённые изменения паспортных данных", 409)
    if confirmed and snapshot.get("signature_request_id") is None:
        raise ServiceError("Сначала создайте запрос на подписание СОПД", 409)
    return snapshot


@router.get(
    "/{application_id}/sopd-signers/{signer_key}/passport",
    response_model=SopdPassportSnapshotResponse,
    summary="Получить снимок паспорта кандидата СОПД",
    description="Проверяет доступ к заявке и принадлежность opaque signerKey актуальному кандидату.",
    dependencies=[Depends(_read_access)],
)
async def get_application_signer_passport(
    application_id: UUID, signer_key: str, user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)], provider: Annotated[CompanyLookupProvider, Depends(get_company_lookup_provider)],
) -> JSONResponse:
    try:
        snapshot = await _snapshot_access(application_id=application_id, signer_key=signer_key, user=user, session=session, provider=provider)
        snapshot = _require_passport_snapshot(snapshot)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(passport_snapshot_response(snapshot)))


@router.patch(
    "/{application_id}/sopd-signers/{signer_key}/passport/draft",
    response_model=SopdPassportSnapshotResponse,
    summary="Сохранить черновик паспорта кандидата СОПД",
    description="Сохраняет fields как черновик и блокирует действия до подтверждения.",
    dependencies=[Depends(_write_access)],
)
async def patch_application_signer_passport_draft(
    application_id: UUID, signer_key: str, payload: SopdPassportFieldsRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)], session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[CompanyLookupProvider, Depends(get_company_lookup_provider)],
) -> JSONResponse:
    try:
        snapshot = await _snapshot_access(application_id=application_id, signer_key=signer_key, user=user, session=session, provider=provider)
        if snapshot is None:
            access = ApplicationAccessQuery(
                application_id=application_id, actor_id=user["id"], actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"), actor_leasing_company_id=await _resolve_lc_id(session, user),
            )
            expected_full_name = await expected_full_name_for_application_signer(
                session, access=access, signer_key=signer_key, provider=provider,
            )
            snapshot = await begin_manual_snapshot(
                session, application_id=application_id, signer_key=signer_key,
                owner_user_id=user["id"], expected_full_name=expected_full_name,
            )
        result = await save_passport_draft(session, snapshot, payload.fields, payload.edited_fields)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{application_id}/sopd-signers/{signer_key}/passport",
    response_model=SopdPassportSnapshotResponse,
    summary="Подтвердить паспорт кандидата СОПД",
    description="Валидирует fields и фиксирует подтверждённый снимок для приглашения или бумажного пути.",
    dependencies=[Depends(_write_access)],
)
async def confirm_application_signer_passport(
    application_id: UUID, signer_key: str, payload: SopdPassportFieldsRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)], session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[CompanyLookupProvider, Depends(get_company_lookup_provider)],
) -> JSONResponse:
    try:
        snapshot = await _snapshot_access(application_id=application_id, signer_key=signer_key, user=user, session=session, provider=provider)
        if snapshot is None:
            access = ApplicationAccessQuery(
                application_id=application_id, actor_id=user["id"], actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"), actor_leasing_company_id=await _resolve_lc_id(session, user),
            )
            expected_full_name = await expected_full_name_for_application_signer(
                session, access=access, signer_key=signer_key, provider=provider,
            )
            snapshot = await begin_manual_snapshot(
                session, application_id=application_id, signer_key=signer_key,
                owner_user_id=user["id"], expected_full_name=expected_full_name,
            )
        result = await confirm_passport_snapshot(session, snapshot, payload.fields, payload.edited_fields)
    except PassportServiceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "fields": exc.fields},
        ) from exc
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{application_id}/sopd-signers/{signer_key}/passport-recognition",
    response_model=SopdPassportSnapshotResponse,
    summary="Распознать паспорт кандидата СОПД",
    description="Сохраняет технический raw-кэш и полный scoped снимок до создания приглашения.",
    dependencies=[Depends(_write_access)],
)
async def recognize_application_signer_passport(
    application_id: UUID, signer_key: str, user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)], provider: Annotated[CompanyLookupProvider, Depends(get_company_lookup_provider)],
    passport_main: Annotated[UploadFile | None, File()] = None, passport_registration: Annotated[UploadFile | None, File()] = None,
) -> JSONResponse:
    main = await _passport_page(passport_main, "passport_main")
    registration = await _passport_page(passport_registration, "passport_registration")
    try:
        await _snapshot_access(application_id=application_id, signer_key=signer_key, user=user, session=session, provider=provider)
        access = ApplicationAccessQuery(
            application_id=application_id,
            actor_id=user["id"],
            actor_role=str(user.get("role") or ""),
            actor_company_id=user.get("company_id"),
            actor_leasing_company_id=await _resolve_lc_id(session, user),
        )
        expected_full_name = await expected_full_name_for_application_signer(
            session, access=access, signer_key=signer_key, provider=provider,
        )
        result = await recognize_passport_snapshot(
            session, application_id=application_id, signer_key=signer_key, owner_user_id=user["id"],
            passport_main=main, passport_registration=registration,
            expected_full_name=expected_full_name,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/sopd-signers/{signer_key}/paper-sopd",
    summary="Скачать заполненное бумажное СОПД кандидата",
    description="Uses only the current owner's confirmed passport snapshot bound to its SOPD signature request.",
    dependencies=[Depends(_read_access)],
    responses={200: {"content": {"application/pdf": {}}}, 409: {"description": "Паспорт не подтверждён или имеет черновые изменения"}},
)
async def download_application_signer_paper_sopd(
    application_id: UUID, signer_key: str, user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)], provider: Annotated[CompanyLookupProvider, Depends(get_company_lookup_provider)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        snapshot = await _snapshot_access(application_id=application_id, signer_key=signer_key, user=user, session=session, provider=provider, allow_bound_request=True)
        snapshot = _require_passport_snapshot(snapshot, confirmed=True)
        fields = snapshot["confirmed_fields"]
        def text(key: str) -> str:
            return str(fields.get(key) or "").strip()
        context = {"full_name": " ".join(x for x in (text("surname"), text("name"), text("patronymic")) if x), "gender": "Мужской" if text("gender") == "male" else "Женский" if text("gender") == "female" else "", "birth_date": text("birthDate"), "birth_place": text("birthPlace"), "passport_series_number": " ".join(x for x in (text("passportSeries"), text("passportNumber")) if x), "passport_issued_by": text("givenWhom"), "passport_issued_at": text("givenDate"), "passport_code": text("code")}
        rendered = await resolve_sopd_pdf(session=session, storage=storage, context=context)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    if isinstance(rendered, SopdPdfReady):
        return Response(content=rendered.data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="СОПД.pdf"', "X-Content-Type-Options": "nosniff"})
    if isinstance(rendered, SopdPdfPending):
        return Response(status_code=202, headers={"Retry-After": "3"})
    raise HTTPException(503, "Не удалось сформировать СОПД")


@router.get(
    "/{application_id}/sopd-signer-candidates",
    response_model=SopdSignerCandidatesResponse,
    summary="Кандидаты на подписание СОПД",
    description=(
        "Возвращает кандидатов на подписание СОПД для заявки. Доступ "
        "проверяется по тем же правилам, что и у детального запроса заявки; "
        "обращение к внешнему справочнику выполняется только после проверки."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_sopd_signer_candidates(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    lookup_provider: Annotated[
        CompanyLookupProvider, Depends(get_company_lookup_provider)
    ],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_get_sopd_signer_candidates(
            GetSopdSignerCandidatesQuery(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
                company_lookup_provider=lookup_provider,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    SopdSignerCandidatesResponse.model_validate(result)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/vehicles/{application_vehicle_id}/employees/search",
    response_model=ApplicationEmployeeSearchResponse,
    summary="Поиск сотрудников дилера для автомобиля заявки",
    description=(
        "Ищет активных сотрудников компании-дилера, назначенной указанному "
        "автомобилю. Дилер работает только со своей строкой, дистрибьютор — "
        "со строкой автомобиля на своём складе."
    ),
    dependencies=[Depends(_employee_assignment_roles)],
)
async def search_application_vehicle_employees(
    application_id: UUID,
    application_vehicle_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    query: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    try:
        result = await handle_search_application_vehicle_employees(
            SearchApplicationVehicleEmployeesQuery(
                application_id=application_id,
                application_vehicle_id=application_vehicle_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                query=query,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{application_id}/vehicles/{application_vehicle_id}/employees",
    response_model=AssignApplicationVehicleEmployeesResponse,
    summary="Назначить сотрудников автомобиля заявки",
    description=(
        "Частично изменяет основного и/или дополнительного сотрудника "
        "конкретного автомобиля. Сотрудники должны принадлежать назначенному "
        "этому автомобилю дилеру; null очищает соответствующее поле."
    ),
    dependencies=[Depends(_employee_assignment_roles)],
)
async def assign_application_vehicle_employees(
    application_id: UUID,
    application_vehicle_id: UUID,
    body: AssignApplicationEmployeesRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    fields_set = body.model_fields_set
    try:
        result = await handle_assign_application_vehicle_employees(
            AssignApplicationVehicleEmployeesCommand(
                application_id=application_id,
                application_vehicle_id=application_vehicle_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                update_primary="primary_employee_id" in fields_set,
                primary_employee_id=body.primary_employee_id,
                update_additional="additional_employee_id" in fields_set,
                additional_employee_id=body.additional_employee_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/employees/search",
    response_model=ApplicationEmployeeSearchResponse,
    summary="Поиск сотрудников для заявки",
    description=(
        "Ищет активных пользователей текущей компании по основной связи "
        "users.company_id и дополнительным связям user_companies. "
        "Доступ: назначенный дилер, дистрибьютор со своим складским ТС в "
        "заявке и сотрудник Carcraft после общей проверки доступа."
    ),
    dependencies=[Depends(_employee_assignment_roles)],
)
async def search_application_employees(
    application_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    query: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    try:
        result = await handle_search_application_employees(
            SearchApplicationEmployeesQuery(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                query=query,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{application_id}/employees",
    response_model=AssignApplicationEmployeesResponse,
    summary="Назначить сотрудников заявки",
    description=(
        "Частично и сразу сохраняет основного и/или дополнительного "
        "сотрудника. Переданный UUID должен принадлежать активному "
        "пользователю текущей компании; null очищает соответствующее поле."
    ),
    dependencies=[Depends(_employee_assignment_roles)],
)
async def assign_application_employees(
    application_id: UUID,
    body: AssignApplicationEmployeesRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    fields_set = body.model_fields_set
    try:
        result = await handle_assign_application_employees(
            AssignApplicationEmployeesCommand(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                update_primary="primary_employee_id" in fields_set,
                primary_employee_id=body.primary_employee_id,
                update_additional="additional_employee_id" in fields_set,
                additional_employee_id=body.additional_employee_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


@router.get(
    "/{application_id}/leasing-responses",
    response_model=ClientLeasingResponsesResponse,
    summary="Ответы лизинговых на заявку (для клиента)",
    description=(
        "Список финализированных ответов ЛК (одобрено/отказано) с КП и "
        "PDF. Для каждого параметра выдаётся пара «запрошено / предложено»."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_client_leasing_responses_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_get_client_leasing_responses(
            GetClientLeasingResponsesQuery(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/export.pdf",
    summary="Экспорт заявки в PDF",
    description=(
        "Единый читаемый PDF со всеми данными заявки: контакты, компания, "
        "анкета, учредители, бенефициары, автомобили, условия лизинга, "
        "список приложенных документов. Требует доступа к заявке; экспорт "
        "недоступен дилеру, получившему через распределение неполный состав заявки."
    ),
    dependencies=[Depends(_read_access)],
    response_class=Response,
)
async def export_application_pdf(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    lc_id = await _resolve_lc_id(session, user)
    try:
        data = await handle_export_application_pdf(
            ExportApplicationQuery(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="application-{application_id}.pdf"'
            )
        },
    )


@router.post(
    "/draft",
    status_code=201,
    response_model=CreateApplicationInitResponse,
    summary="Создать черновик заявки",
    description=(
        "Создаёт черновик заявки из условий корзины. Комментарии строк "
        "оборудования и услуг на этом шаге всегда сохраняются как null."
    ),
    dependencies=[Depends(_write_access)],
)
@router.post(
    "",
    status_code=201,
    response_model=CreateApplicationInitResponse,
    summary="Создать заявку",
    description=(
        "Создаёт запись заявки из условий корзины: компания, автомобили "
        "и optional расчёт. После создания заявка получает id и номер, "
        "остаётся редактируемой клиентом до момента распределения в ЛК."
    ),
    dependencies=[Depends(_write_access)],
)
async def create_application(
    body: CreateApplicationInitRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
) -> JSONResponse:
    calc = (
        body.calculation.model_dump(exclude_none=True)
        if body.calculation is not None
        else None
    )
    company = (
        body.company.model_dump(exclude_none=True) if body.company is not None else None
    )
    cmd = CreateDraftCommand(
        source_type=body.source_type,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        company_id=body.company_id,
        company=company,
        name=body.name,
        email=body.email,
        vehicles=[_payload_from_schema(v) for v in body.vehicles],
        calculation=calc,
        scope=scope,
    )
    endpoint = "POST /api/v1/applications"
    try:
        replay = await begin_application_create(
            session,
            endpoint=endpoint,
            key=idempotency_key,
            payload=body.model_dump(mode="json"),
        )
        if replay is not None:
            return _application_json(replay, user.get("role"))
        result = await handle_create_draft(cmd, session)
        result = CreateApplicationInitResponse.model_validate(result).model_dump(mode="json")
        if result.get("source_type") is None:
            result.pop("source_type", None)
        await finish_application_create(
            session,
            endpoint=endpoint,
            key=idempotency_key,
            result=result,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
        headers={"Location": f"/api/v1/applications/{result['application_id']}"},
    )


@router.put(
    "/{application_id}/items",
    response_model=UpdateApplicationItemsResponse,
    summary="Обновить параметры позиций заявки",
    dependencies=[Depends(_write_access)],
)
async def update_application_items(
    application_id: UUID,
    body: UpdateApplicationItemsRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_update_application_items(
            UpdateApplicationItemsCommand(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                items=[ApplicationItemUpdate(**item.model_dump()) for item in body.items],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Status / submit-documents
# ---------------------------------------------------------------------------


@router.put(
    "/{application_id}/status",
    response_model=StatusUpdateResponse,
    summary="Обновить статус заявки",
    description=(
        "Валидирует переход статуса через aggregate root. Недопустимый "
        "переход — 400. Доступ к не своей заявке — 403."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_status(
    application_id: uuid.UUID,
    body: StatusUpdateRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_change_status(
            ChangeStatusCommand(
                application_id=application_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                new_status=body.status,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


# ---------------------------------------------------------------------------
# Sub-resource PUTs — Phase 16 draft-first checkout flow
# Each PUT patches a single facet of a draft application. Guard:
# ``ensure_editable`` on the domain entity (status=pending_distribution +
# no LC-dispatch rows).
# ---------------------------------------------------------------------------


@router.put(
    "/{application_id}/conditions",
    response_model=ApplicationSubresourceResponse,
    summary="Обновить финансовые условия заявки",
    description=(
        "Частичный апдейт: принимает любое подмножество полей "
        "(`down_payment`, `lease_term_months`, …). Отвергается для заявок, "
        "которые уже отправлены админом в лизинговые компании."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_conditions(
    application_id: uuid.UUID,
    body: UpdateConditionsRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = UpdateConditionsCommand(
        application_id=application_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        total_amount=body.total_amount,
        down_payment=body.down_payment,
        down_payment_percent=body.down_payment_percent,
        lease_term_months=body.lease_term_months,
        monthly_payment=body.monthly_payment,
        total_cost=body.total_cost,
        markup=body.markup,
        rate=body.rate,
        total_interest=body.total_interest,
        buyout_amount=body.buyout_amount,
        vat_refund=body.vat_refund,
        profit_tax_savings=body.profit_tax_savings,
        total_savings=body.total_savings,
        selected_support=body.selected_support,
        support_per_vehicle=body.support_per_vehicle,
        support_per_program=body.support_per_program,
        support_program_details=body.support_program_details,
        calculations_per_vehicle=body.calculations_per_vehicle,
    )
    try:
        result = await handle_update_conditions(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


@router.put(
    "/{application_id}/company",
    response_model=ApplicationSubresourceResponse,
    summary="Сменить компанию заявки",
    description=(
        "Меняет `company_id` на черновике. Новая компания должна существовать."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_company(
    application_id: uuid.UUID,
    body: UpdateCompanyRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = UpdateCompanyCommand(
        application_id=application_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        company_id=body.company_id,
    )
    try:
        result = await handle_update_company(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


@router.put(
    "/{application_id}/vehicles",
    response_model=ApplicationSubresourceResponse,
    summary="Заменить автомобили заявки",
    description=(
        "Полностью перезаписывает состав `application_vehicles` + расчёты по "
        "каждому ТС. Полный replace — используется, когда пользователь меняет "
        "корзину в процессе заполнения заявки."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_vehicles(
    application_id: uuid.UUID,
    body: UpdateVehiclesRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = UpdateVehiclesCommand(
        application_id=application_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        vehicles=[_payload_from_schema(v) for v in body.vehicles],
        vehicle_calculations=body.vehicle_calculations,
    )
    try:
        result = await handle_update_vehicles(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


@router.put(
    "/{application_id}/leasing-companies",
    response_model=ApplicationSubresourceResponse,
    summary="Обновить выбранные лизинговые компании",
    description=(
        "Замещает `selected_leasing_companies` целиком. Дубликаты "
        "схлопываются; несуществующие `leasing_company_id` — 404."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_leasing_companies(
    application_id: uuid.UUID,
    body: UpdateLeasingCompaniesRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = UpdateLeasingCompaniesCommand(
        application_id=application_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        leasing_company_ids=list(body.leasing_company_ids),
    )
    try:
        result = await handle_update_leasing_companies(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


@router.patch(
    "/{application_id}/additional-options",
    response_model=AdditionalOptionsUpdateResponse,
    summary="Обновить доп. оборудование и услуги",
    description=(
        "Дилер, дистрибьютор или лизинговая компания атомарно сохраняет "
        "каталожные позиции, их подтвержденные цены и комментарии для одной "
        "машины заявки. Итоговая стоимость машины и заявки пересчитывается."
    ),
    dependencies=[Depends(_additional_options_write_access)],
)
async def update_additional_options(
    application_id: uuid.UUID,
    body: AdditionalOptionsUpdateRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    cmd = UpdateAdditionalOptionsCommand(
        application_id=application_id,
        application_vehicle_id=body.application_vehicle_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        actor_leasing_company_id=lc_id,
        equipments=jsonable_encoder(body.equipments),
        services=jsonable_encoder(body.services),
    )
    try:
        result = await handle_update_additional_options(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return _application_json(result, user.get("role"))


@router.post(
    "/{application_id}/documents/attach",
    response_model=AttachDocumentsResponse,
    summary="Прилинковать ранее загруженные документы к заявке",
    description=(
        "Связывает существующие записи `documents` с заявкой через "
        "`document_applications` M2M. Принимает список `document_ids` "
        "(те же, что шаг 4 выбрал в `selectedDocuments`). Документы чужой "
        "компании молча пропускаются, несуществующие — тоже. Идемпотентно — "
        "повторный вызов тем же списком ничего не меняет."
    ),
    dependencies=[Depends(_write_access)],
)
async def attach_documents_to_application(
    application_id: uuid.UUID,
    body: AttachDocumentsRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = AttachDocumentsToApplicationCommand(
        application_id=application_id,
        document_ids=list(body.document_ids),
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
    )
    try:
        result = await handle_attach_documents_to_application(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/{application_id}/questionnaire",
    response_model=QuestionnaireUpdateResponse,
    summary="Обновить анкету заявки",
    description=(
        "Upsert всех полей анкеты. Принимает произвольный JSON — поля "
        "фильтруются по колонкам `application_questionnaires`."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_questionnaire(
    application_id: uuid.UUID,
    body: UpdateQuestionnaireRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = UpdateQuestionnaireCommand(
        application_id=application_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        payload=body.model_dump(),
    )
    try:
        result = await handle_update_questionnaire(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# /requested-documents and /submit-documents were deleted in Phase 15 H3:
# frontend switched to `GET /applications/{id}/documents?requested=true`
# in Phase 10 R4 and never called /submit-documents.
# VIN assignment moved to /api/v1/application-vehicles/{id} (Phase 13 R13c).
# See presentation/routers/application_vehicles.py for PATCH + GET
# available-vins with role-dispatch inside the handler.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Nested documents (moved here from /documents in Phase 10 R4)
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/document-requests",
    response_model=DocumentRequestsResponse,
    summary="История запросов документов",
    description=(
        "Возвращает фактическую историю запросов документов, сгруппированную "
        "по batch. Клиент видит запросы всех ЛК по своей заявке, ЛК — только "
        "собственные запросы, сотрудник Carcraft — всю историю."
    ),
    dependencies=[Depends(_documents_read_access)],
)
async def list_application_document_requests(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_list_document_requests(
            ListDocumentRequestsQuery(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/documents",
    response_model=DocumentForApplicationResponse,
    summary="Документы заявки",
    description=(
        "Возвращает документы заявки (через `document_applications` M2M "
        "или `related_application_id`). Параметр `requested=true` "
        "возвращает агрегированный список требований ЛК по заявке "
        "с пометкой уже загруженных документов (формат "
        "`DocumentRequirementsResponse`)."
    ),
    dependencies=[Depends(_documents_read_access)],
)
async def list_application_documents(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    requested: Annotated[
        bool,
        Query(description="Вернуть перечень требований ЛК вместо документов."),
    ] = False,
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        if requested:
            requirements = await handle_list_document_requirements(
                ListDocumentRequirementsQuery(
                    application_id=application_id,
                    actor_user_id=user["id"],
                    actor_role=str(user.get("role") or ""),
                    actor_company_id=user.get("company_id"),
                    actor_leasing_company_id=lc_id,
                ),
                session,
            )
            return JSONResponse(content=jsonable_encoder(requirements))
        result = await handle_list_documents_for_application(
            ListDocumentsForApplicationQuery(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{application_id}/documents/archive",
    summary="Скачать все документы заявки одним ZIP",
    description=(
        "Собирает in-memory ZIP из всех документов, привязанных к "
        "заявке, и возвращает его через `StreamingResponse`. "
        "Авторизация — как у `GET /{id}/documents`."
    ),
    responses={
        200: {"content": {"application/zip": {}}},
        403: {"description": "Нет доступа к заявке"},
        404: {"description": "Заявка не найдена"},
    },
    response_class=StreamingResponse,
    dependencies=[Depends(_documents_read_access)],
)
async def download_application_documents_archive(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> StreamingResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        archive = await handle_download_application_archive(
            DownloadApplicationArchiveQuery(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)

    def _stream() -> Any:
        yield archive.data

    headers = {
        "Content-Disposition": (f'attachment; filename="{archive.filename}"'),
        "X-Content-Type-Options": "nosniff",
        "X-Archive-Included-Count": str(archive.included_count),
    }
    return StreamingResponse(
        _stream(),
        media_type="application/zip",
        headers=headers,
    )


@router.get(
    "/{application_id}/sopd-status",
    response_model=SopdStatusListResponse,
    summary="Статус подписанных СОПД для заявки",
    description="Возвращает последний статус СОПД для каждого подписанта (гендиректор + учредители) по заявке.",
    dependencies=[Depends(_read_access)],
)
async def get_sopd_status(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        lc_id = await _resolve_lc_id(session, user)
        items = await handle_get_sopd_status(
            GetSopdStatusQuery(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder({"items": items}))


@router.get(
    "/{application_id}/leasing-responses/{leasing_company_id}/pdf",
    summary="Скачать PDF ответа ЛК по заявке",
    description=(
        "Генерирует PDF из данных заявки, конкретной LCA и КП. "
        "Если передан `proposal_kind`, PDF строится только по этому типу КП. "
        "Доступ — те же роли, что и `/applications/{id}` "
        "(client/dealer/employee/distributor). PDF недоступен дилеру, "
        "получившему через распределение неполный состав заявки."
    ),
    dependencies=[Depends(_read_access)],
    response_class=Response,
)
async def download_lc_response_pdf(
    application_id: uuid.UUID,
    leasing_company_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    proposal_kind: Annotated[
        Literal["preliminary", "final"] | None,
        Query(description="Тип КП для PDF конкретной строки условий."),
    ] = None,
    lca_id: Annotated[
        UUID | None,
        Query(
            description="ID LCA для точного выбора строки КП при нескольких LCA одной ЛК."
        ),
    ] = None,
) -> Response:
    lc_id = await _resolve_lc_id(session, user)
    try:
        payload = await handle_get_lc_response_pdf(
            GetLcResponsePdfQuery(
                application_id=application_id,
                leasing_company_id=leasing_company_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=lc_id,
                proposal_kind=proposal_kind,
                lca_id=lca_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=payload.data,
        media_type=payload.content_type,
        headers={
            "Content-Disposition": (f'attachment; filename="{payload.file_name}"'),
        },
    )


@router.post(
    "/{application_id}/proposals/{proposal_id}/decision",
    response_model=ClientProposalDecisionResponse,
    summary="Решение клиента по КП (Принять / Отказаться)",
    description=(
        "Клиент принимает или отклоняет одно КП лизинговой компании. "
        "Reject переводит соответствующую LCA в статус `closed` "
        "(«Клиент отказался»). Доступ — только владельцам компании, "
        "к которой привязана заявка."
    ),
    dependencies=[Depends(_write_access)],
)
async def client_proposal_decision(
    application_id: uuid.UUID,
    proposal_id: UUID,
    body: ClientProposalDecisionRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = ClientProposalDecisionCommand(
        application_id=application_id,
        proposal_id=proposal_id,
        actor_id=user["id"],
        actor_role=str(user.get("role") or ""),
        actor_company_id=user.get("company_id"),
        action=body.action,
        comment=body.comment,
    )
    try:
        result = await handle_client_proposal_decision(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{application_id}/lca/{lca_id}/select",
    response_model=SelectLeasingCompanyResponse,
    summary="Клиент выбирает лизинговую компанию (итоговое КП)",
    description=(
        "Переводит выбранный оффер (LeasingCompanyApplication) в статус "
        "selected_lc. Доступно владельцу заявки для офферов в статусах "
        "approved_final / approved_final_another_cond."
    ),
    dependencies=[Depends(_write_access)],
)
async def select_leasing_company_endpoint(
    application_id: uuid.UUID,
    lca_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_select_leasing_company(
            SelectLeasingCompanyCommand(
                application_id=application_id,
                lca_id=lca_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


def _payload_from_schema(
    v: Any,
) -> ApplicationVehiclePayload:
    equipments = [
        {**item, "comment": None} for item in jsonable_encoder(v.equipments or [])
    ]
    services = [
        {**item, "comment": None} for item in jsonable_encoder(v.services or [])
    ]
    pid = getattr(v, "product_id", getattr(v, "vehicle_id", None))
    v_kw = "product_id" if "product_id" in getattr(ApplicationVehiclePayload, "__dataclass_fields__", {}) else "vehicle_id"
    return ApplicationVehiclePayload(
        modification_id=v.modification_id,
        quantity=v.quantity,
        allow_overstock=v.allow_overstock,
        custom_price=v.custom_price,
        comment=v.comment,
        equipments=equipments,
        services=services,
        leasing_purpose=v.leasing_purpose,
        leasing_purposes=v.leasing_purposes,
        regions=v.regions or ([v.region] if v.region else []),
        is_model_order=v.is_model_order,
        **{v_kw: pid},
    )
