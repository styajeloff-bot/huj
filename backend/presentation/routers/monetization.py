"""Internal monetization API; no public endpoint can create a financial deal."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization import deals, files, programs, requests
from application.commands.monetization.reference_documents import (
    replace_reference_documents,
)
from application.errors import ServiceError, domain_to_http
from application.queries.monetization import views
from application.queries.monetization.catalog import lookup_catalog as query_catalog
from application.queries.monetization.reference_documents import (
    list_reference_documents,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_roles
from presentation.dependencies.document_registry_snapshot import get_read_snapshot
from presentation.dependencies.notification_database import get_db
from presentation.schemas import monetization as schemas
from presentation.schemas.monetization_catalog import (
    CatalogMarksOut,
    CatalogModelsOut,
    CatalogModificationsOut,
    CatalogTrimsOut,
)

router = APIRouter()
_reader = require_roles("carcraft_employee", "dealer", "distributor", "leasing_company")
_admin = require_roles("carcraft_employee")
_dealer = require_roles("dealer")
_leasing = require_roles("leasing_company")
Session = Annotated[AsyncSession, Depends(get_db)]
ReadSession = Annotated[AsyncSession, Depends(get_read_snapshot)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


async def read_actor(user: Annotated[dict[str, Any], Depends(_reader)],
                     session: Session, notification_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    try:
        return await views.resolve_actor(session, user, notification_company_id)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc


async def snapshot_actor(user: Annotated[dict[str, Any], Depends(_reader)],
                         session: ReadSession, notification_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    return await read_actor(user, session, notification_company_id)


async def commission_actor(user: Annotated[dict[str, Any], Depends(_reader)],
                     session: Session, notification_company_id: UUID | None = Query(None),
                     leasing_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    try:
        return await views.resolve_actor(session, user, notification_company_id, leasing_company_id)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc


async def admin_actor(user: Annotated[dict[str, Any], Depends(_admin)],
                      session: Session, notification_company_id: UUID | None = Query(None),
                     leasing_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    try:
        return await views.resolve_actor(session, user, notification_company_id, leasing_company_id)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc


async def dealer_actor(user: Annotated[dict[str, Any], Depends(_dealer)],
                       session: Session, notification_company_id: UUID | None = Query(None),
                     leasing_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    try:
        return await views.resolve_actor(session, user, notification_company_id, leasing_company_id)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc


async def leasing_actor(user: Annotated[dict[str, Any], Depends(_leasing)],
                        session: Session, notification_company_id: UUID | None = Query(None),
                     leasing_company_id: UUID | None = Query(None)) -> dict[str, Any]:
    try:
        return await views.resolve_actor(session, user, notification_company_id, leasing_company_id)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc


Reader = Annotated[dict[str, Any], Depends(read_actor)]
SnapshotReader = Annotated[dict[str, Any], Depends(snapshot_actor)]
CommissionReader = Annotated[dict[str, Any], Depends(commission_actor)]
Admin = Annotated[dict[str, Any], Depends(admin_actor)]
Dealer = Annotated[dict[str, Any], Depends(dealer_actor)]
Leasing = Annotated[dict[str, Any], Depends(leasing_actor)]


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(exc.status_code, detail=str(exc))


async def _call(operation: Awaitable[dict[str, Any]], schema: type[BaseModel],
                session: AsyncSession, *, write: bool = False,
                key: str | None = None, status_code: int = 200,
                location: str | None = None) -> JSONResponse:
    try:
        result = await operation
        data = result[key] if key else result
        body = schema.model_validate(data).model_dump(mode="json")
        if write:
            await session.commit()
    except (ServiceError, DomainError) as exc:
        if write:
            await session.rollback()
        raise _http(exc) from exc
    except Exception:
        if write:
            await session.rollback()
        raise
    headers = {"Location": f"{location}/{body['id']}" if "id" in body else location} if location else None
    return JSONResponse(body, status_code=status_code, headers=headers)


@router.get(
    "/api/v1/admin/monetization/programs", response_model=schemas.ProgramListOut,
    summary="Условия монетизации", description="Внутренний список по правам компании; суммы не возвращаются.",
)
async def list_programs(
    actor: Reader, session: Session, page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100), status: str | None = None,
    leasing_company_id: UUID | None = None, brand: str | None = None,
    source_type: str | None = None,
) -> JSONResponse:
    return await _call(views.list_programs(
        session, actor, filters={"status": status, "leasing_company_id": leasing_company_id,
                                "brand": brand, "source_type": source_type},
        page=page, page_size=page_size), schemas.ProgramListOut, session)


@router.post(
    "/api/v1/admin/monetization/programs", response_model=schemas.ProgramOut, status_code=201,
    summary="Создать условия монетизации",
    description="Только сотрудник Carcraft. Независимые расходы и доходы по источникам.",
)
async def create_program(payload: schemas.ProgramInput, actor: Admin,
                         session: Session) -> JSONResponse:
    return await _call(programs.create_program(session, payload.model_dump(), actor),
                       schemas.ProgramOut, session, write=True, key="program",
                       status_code=201, location="/api/v1/admin/monetization/programs")


@router.get(
    "/api/v1/admin/monetization/programs/{program_id}", response_model=schemas.ProgramOut,
    summary="Карточка условий монетизации",
    description="Финансовые строки доступны администратору и соответствующему участнику.",
)
async def get_program(program_id: UUID, actor: SnapshotReader, session: ReadSession) -> JSONResponse:
    return await _call(views.get_program(session, program_id, actor), schemas.ProgramOut, session)


@router.patch(
    "/api/v1/admin/monetization/programs/{program_id}", response_model=schemas.ProgramOut,
    summary="Активировать или отключить условия",
    description="Только сотрудник Carcraft. Зафиксированные сделки не пересчитываются.",
)
async def change_status(program_id: UUID, payload: schemas.ProgramStatusInput,
                        actor: Admin, session: Session) -> JSONResponse:
    return await _call(programs.change_program_status(session, program_id, payload.status, actor),
                       schemas.ProgramOut, session, write=True, key="program")


@router.get(
    "/api/v1/monetization/lookups/catalog",
    response_model=CatalogMarksOut | CatalogModelsOut | CatalogModificationsOut | CatalogTrimsOut,
    summary="Справочник автомобилей для условий монетизации",
    description="Полный зарегистрированный каталог для внутренних ролей, без ограничения наличием или витриной.",
)
async def lookup_catalog(
    _actor: Reader, session: Session, fields: Literal["marks", "models", "modifications", "trims"],
    mark_id: str | None = Query(None, max_length=5000),
    model_id: str | None = Query(None, max_length=50),
    modification_id: UUID | None = Query(None),
) -> JSONResponse:
    response_schema: type[BaseModel] = CatalogMarksOut
    if fields == "models":
        response_schema = CatalogModelsOut
    elif fields == "modifications":
        response_schema = CatalogModificationsOut
    elif fields == "trims":
        response_schema = CatalogTrimsOut
    return await _call(
        query_catalog(session, fields, mark_id, model_id, modification_id),
        response_schema, session,
    )


@router.get(
    "/api/v1/monetization/lookups/companies", response_model=schemas.CompanyLookupOut,
    summary="Компании для монетизации",
    description=("Поиск зарегистрированных компаний по названию или ИНН; ID ЛК канонический. "
                 "Дилеры и дистрибьюторы фильтруются по выбранной противоположной компании "
                 "через прямую связь или активную группу без расширения прав пользователя."),
)
async def lookup_companies(actor: Reader, session: Session,
                           kind: Literal["leasing", "dealer", "distributor", "client"],
                           q: str = Query("", max_length=255),
                           distributor_company_id: UUID | None = None,
                           dealer_company_id: UUID | None = None) -> JSONResponse:
    return await _call(views.lookup_companies(
        session, actor, kind, q, distributor_company_id, dealer_company_id,
    ), schemas.CompanyLookupOut, session)


@router.get(
    "/api/v1/monetization/lookups/supports", response_model=schemas.SupportLookupOut,
    summary="Программы стимулирования для условий",
    description="Доступные поддержки с необязательным фильтром по дистрибьютору и существующими ограничениями видимости программ.",
)
async def lookup_supports(actor: Reader, session: Session,
                          q: str = Query("", max_length=255),
                          distributor_company_id: UUID | None = None) -> JSONResponse:
    return await _call(views.lookup_supports(session, actor, q, distributor_company_id),
                       schemas.SupportLookupOut, session)


@router.get(
    "/api/v1/monetization/lookups/supports/{support_id}", response_model=schemas.SupportOut,
    summary="Документы и совместимость программы",
    description="Информационное представление существующей программы; без её изменения.",
)
async def get_support(support_id: UUID, actor: Reader, session: Session) -> JSONResponse:
    return await _call(views.get_support(session, support_id, actor), schemas.SupportOut, session)


@router.get(
    "/api/v1/monetization/deals", response_model=schemas.DealListOut,
    summary="Сделки монетизации", description="Только сделки компании и её видимые финансовые строки.",
)
async def list_deals(
    actor: Reader, session: Session, *, page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100), status: str | None = None,
    source_type: str | None = None, dealer_company_id: UUID | None = None,
    brand: str | None = Query(None, max_length=100),
    client_company_id: UUID | None = None,
) -> JSONResponse:
    return await _call(views.list_deals(
        session, actor, filters={"status": status, "source_type": source_type,
                                "dealer_company_id": dealer_company_id,
                                "client_company_id": client_company_id, "brand": brand},
        page=page, page_size=page_size), schemas.DealListOut, session)


@router.get(
    "/api/v1/monetization/deals/{deal_id}", response_model=schemas.DealOut,
    summary="Карточка сделки монетизации",
    description="Снимок сумм, документы и подтверждения. Клиентам доступ запрещён.",
)
async def get_deal(deal_id: UUID, actor: Reader, session: Session) -> JSONResponse:
    return await _call(views.get_deal(session, deal_id, actor), schemas.DealOut, session)


@router.post(
    "/api/v1/monetization/deals/{deal_id}/confirm", response_model=schemas.DealOut,
    summary="Подтвердить свою сторону сделки",
    description="ЛК и дилер подтверждают всегда, дистрибьютор — при участии. Требуется актуальная версия сумм.",
    dependencies=[Depends(require_roles("leasing_company", "dealer", "distributor"))],
)
async def confirm_party(deal_id: UUID, payload: schemas.RevisionInput,
                        actor: Reader, session: Session) -> JSONResponse:
    return await _call(deals.confirm(session, deal_id, actor, payload.revision),
                       schemas.DealOut, session, write=True, key="deal")


@router.post(
    "/api/v1/admin/monetization/deals/{deal_id}/confirm", response_model=schemas.DealOut,
    summary="Финально подтвердить монетизацию",
    description="Сотрудник Carcraft переводит сделку в Оплачено после подтверждения всех применимых сторон.",
)
async def confirm_final(deal_id: UUID, payload: schemas.RevisionInput,
                        actor: Admin, session: Session) -> JSONResponse:
    return await _call(deals.confirm(session, deal_id, actor, payload.revision),
                       schemas.DealOut, session, write=True, key="deal")


@router.post(
    "/api/v1/admin/monetization/deals/{deal_id}/adjust-conditions",
    response_model=schemas.AdjustmentOut, summary="Изменить суммы монетизации сделки",
    description="Только сотрудник Carcraft. Атомарная правка с историей и сбросом подтверждений.",
)
async def adjust_deal(deal_id: UUID, payload: schemas.AdjustmentInput,
                      actor: Admin, session: Session) -> JSONResponse:
    return await _call(deals.adjust(session, deal_id, actor, payload.revision,
                                   [item.model_dump() for item in payload.items]),
                       schemas.AdjustmentOut, session, write=True, key="deal")


async def _upload(entity_id: UUID, actor: dict[str, Any], session: AsyncSession,
                  storage: ObjectStorage, uploads: list[UploadFile], *,
                  kind: str, revision: int | None = None) -> JSONResponse:
    stored_keys: list[str] = []
    try:
        if len(uploads) > files.MAX_FILES:
            raise ServiceError("Выберите не более 10 файлов", 400)  # noqa: TRY301
        payload = [files.Upload(item.filename or "", await item.read(files.MAX_FILE_BYTES + 1))
                   for item in uploads]
        result = await files.upload_files(session, entity_id, actor, payload, storage,
                                          kind=kind, revision=revision)
        stored_keys = result["stored_keys"]
        body = schemas.DocumentListOut.model_validate(result).model_dump(mode="json")
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        await files.cleanup_uploads(storage, stored_keys)
        raise _http(exc) from exc
    except Exception:
        await session.rollback()
        await files.cleanup_uploads(storage, stored_keys)
        raise
    return JSONResponse(body)


@router.post(
    "/api/v1/admin/monetization/programs/{program_id}/contracts",
    response_model=schemas.DocumentListOut, summary="Приложить договор к условиям",
    description="Необязательные договоры; сотрудник Carcraft, до 10 файлов по 20 МБ.",
)
async def upload_contracts(program_id: UUID, actor: Admin, session: Session, storage: Storage,
                           uploads: Annotated[list[UploadFile], File(alias="files")]) -> JSONResponse:
    return await _upload(program_id, actor, session, storage, uploads, kind="contracts")


@router.post(
    "/api/v1/monetization/deals/{deal_id}/documents", response_model=schemas.DocumentListOut,
    summary="Приложить документы стороны",
    description="Необязательные документы применимой стороны или администратора с версией расчёта.",
)
async def upload_documents(
    deal_id: UUID, actor: Reader, session: Session, storage: Storage,
    uploads: Annotated[list[UploadFile], File(alias="files")],
    revision: Annotated[int, Form(ge=1)],
) -> JSONResponse:
    return await _upload(deal_id, actor, session, storage, uploads, kind="deals", revision=revision)


@router.get(
    "/api/v1/monetization/files/{kind}/{document_id}", response_model=None,
    summary="Скачать документ монетизации",
    description="Проверяет права компании к родительской сделке, условиям или программе поддержки.",
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_document(kind: Literal["contracts", "deals", "supports"],
                            document_id: UUID, actor: Reader,
                            session: Session, storage: Storage) -> Response:
    try:
        document = await files.download_file(session, document_id, actor, storage, kind)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return Response(document["data"], media_type=document["content_type"], headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document['filename'], safe='')}",
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.get(
    "/api/v1/monetization/applications/{application_id}/condition-requests",
    response_model=schemas.ConditionRequestListOut, summary="Запросы дополнительной комиссии",
    description="Все статусы запросов по заявке в пределах компании инициатора или адресата.",
)
async def list_requests(application_id: UUID, actor: CommissionReader, session: Session) -> JSONResponse:
    return await _call(views.list_condition_requests(session, application_id, actor),
                       schemas.ConditionRequestListOut, session)


@router.post(
    "/api/v1/dealer/monetization/applications/{application_id}/condition-requests",
    response_model=schemas.ConditionRequestCreatedOut, status_code=201,
    summary="Запросить дополнительную комиссию",
    description="Дилер своей заявки отправляет отдельный запрос каждой ЛК только до первой связи LCA.",
)
async def create_requests(application_id: UUID, payload: schemas.ConditionRequestInput,
                          actor: Dealer, session: Session) -> JSONResponse:
    return await _call(requests.create_requests(session, application_id, actor, payload.model_dump()),
                       schemas.ConditionRequestCreatedOut, session, write=True, status_code=201,
                       location=f"/api/v1/monetization/applications/{application_id}/condition-requests")


@router.post(
    "/api/v1/leasing-company/monetization/condition-requests/{request_id}/respond",
    response_model=schemas.ConditionRequestOut, summary="Ответить на запрос комиссии",
    description="Только адресат ЛК: принять, отклонить либо предложить встречное условие.",
)
async def respond_request(request_id: UUID, payload: schemas.ConditionResponseInput,
                          actor: Leasing, session: Session) -> JSONResponse:
    return await _call(requests.respond(session, request_id, actor, payload.model_dump()),
                       schemas.ConditionRequestOut, session, write=True, key="request")


@router.post(
    "/api/v1/dealer/monetization/condition-requests/{request_id}/decision",
    response_model=schemas.ConditionRequestOut, summary="Решение по встречной комиссии",
    description="Только дилер инициатор явно принимает или отклоняет встречное условие ЛК.",
)
async def decide_request(request_id: UUID, payload: schemas.ConditionDecisionInput,
                         actor: Dealer, session: Session) -> JSONResponse:
    return await _call(requests.decide(session, request_id, actor, payload.decision),
                       schemas.ConditionRequestOut, session, write=True, key="request")

@router.get(
    "/api/v1/monetization/condition-requests", response_model=schemas.ConditionRequestInboxOut,
    summary="Входящие запросы комиссии",
    description="Переговоры компании, включая заявки до создания связи с ЛК.",
)
async def list_condition_request_inbox(
    actor: CommissionReader, session: Session, page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> JSONResponse:
    return await _call(views.list_condition_request_inbox(
        session, actor, page=page, page_size=page_size), schemas.ConditionRequestInboxOut, session)


@router.get(
    "/api/v1/admin/monetization/programs/{program_id}/reference-documents",
    response_model=schemas.ReferenceDocumentsOut, summary="Документы условий из справочника",
    description="Проверяет доступ к условиям и отдельно к каждому документу справочника.",
)
async def get_reference_documents(program_id: UUID, actor: SnapshotReader, session: ReadSession) -> JSONResponse:
    return await _call(list_reference_documents(session, program_id, actor),
                       schemas.ReferenceDocumentsOut, session)


@router.patch(
    "/api/v1/admin/monetization/programs/{program_id}/reference-documents",
    response_model=schemas.ReferenceDocumentsOut, summary="Изменить документы условий",
    description="Только сотрудник Carcraft. Проверяет новые связи и атомарно заменяет список без изменения финансов.",
)
async def patch_reference_documents(program_id: UUID, payload: schemas.ReferenceDocumentsInput,
                                    actor: Admin, session: Session) -> JSONResponse:
    return await _call(replace_reference_documents(session, program_id, payload.document_ids, actor),
                       schemas.ReferenceDocumentsOut, session, write=True)
