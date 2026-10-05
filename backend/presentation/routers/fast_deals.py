"""Fast deal registration API: ``/api/v1/fast-deals`` (+ VIN lookup of the catalog).

Thin HTTP layer over the ``fast_deals`` use cases. Every mutation requires the parent's
``If-Match`` (428 when absent, 412 when stale); the router commits only after the use
case succeeded, so any error leaves nothing behind. Money is returned as exact decimal
strings. Static paths are declared before ``/{deal_id}`` to keep them reachable.
"""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.fast_deals.assignees import SetAssigneesCommand, handle_set_assignees
from application.commands.fast_deals.cancel_deal import (
    CancelFastDealCommand,
    handle_cancel_fast_deal,
)
from application.commands.fast_deals.create_deal import (
    CreateFastDealCommand,
    handle_create_fast_deal,
)
from application.commands.fast_deals.dd_flow import (
    LcConfirmCommand,
    LcRejectCommand,
    SelectOfferCommand,
    SendToLeasingCompaniesCommand,
    SubmitOfferCommand,
    WithdrawSelectionCommand,
    handle_lc_confirm,
    handle_lc_reject,
    handle_select_offer,
    handle_send_to_leasing_companies,
    handle_submit_offer,
    handle_withdraw_selection,
)
from application.commands.fast_deals.delete_deal import (
    DeleteFastDealCommand,
    handle_delete_fast_deal,
)
from application.commands.fast_deals.dl_flow import (
    AcceptChangesCommand,
    DealerConfirmCommand,
    DealerRejectCommand,
    RejectChangesCommand,
    SendChangesCommand,
    SendToDealersCommand,
    handle_accept_changes,
    handle_dealer_confirm,
    handle_dealer_reject,
    handle_reject_changes,
    handle_send_changes,
    handle_send_to_dealers,
)
from application.commands.fast_deals.files import (
    UploadedFile,
    UploadFilesCommand,
    handle_upload_files,
)
from application.commands.fast_deals.leasing_terms import (
    UpdateLeasingTermsCommand,
    handle_update_leasing_terms,
)
from application.commands.fast_deals.options import SetOptionsCommand, handle_set_options
from application.commands.fast_deals.price_adjustment import (
    PriceAdjustmentCommand,
    handle_price_adjustment,
)
from application.commands.fast_deals.supports import (
    ApplyApprovedSupportCommand,
    ApplySupportProgramCommand,
    DecideSupportCommand,
    RemoveAppliedSupportCommand,
    RequestSupportCommand,
    handle_apply_approved_support,
    handle_apply_support_program,
    handle_decide_support,
    handle_remove_applied_support,
    handle_request_support,
)
from application.commands.fast_deals.vehicles import (
    AddVehicleCommand,
    PatchVehicleCommand,
    RemoveVehicleCommand,
    handle_add_vehicle,
    handle_patch_vehicle,
    handle_remove_vehicle,
)
from application.fast_deals.actor import Actor
from application.queries.fast_deals.catalog import (
    handle_lookup,
    handle_vehicle_candidates,
    handle_vin_lookup,
)
from application.queries.fast_deals.files import (
    handle_assignable_employees,
    handle_download_archive,
    handle_download_file,
)
from application.queries.fast_deals.list_deals import (
    handle_filter_options,
    handle_get_fast_deal,
    handle_list_fast_deals,
)
from application.queries.fast_deals.support_programs import handle_support_programs
from domain.fast_deals.errors import FastDealFileTooLargeError, FastDealValidationError
from domain.fast_deals.values import MAX_FILE_BYTES, MAX_UPLOAD_FILES, FileKind
from domain.services.object_storage import ObjectStorage
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_roles
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.fast_deals import (
    AddVehicleBody,
    ApplySupportProgramBody,
    AssignableEmployeesResponse,
    AssigneesBody,
    CancelBody,
    ConfirmBody,
    CreateFastDealBody,
    FastDealCardResponse,
    FastDealListResponse,
    FilterOptionsResponse,
    LeasingTermsBody,
    OfferBody,
    OptionsBody,
    PatchVehicleBody,
    PriceAdjustmentBody,
    ReasonBody,
    SendChangesBody,
    SendToDealersResponse,
    SendToLeasingCompaniesBody,
    SupportDecisionBody,
    SupportProgramsResponse,
    SupportRequestBody,
    UploadFilesResponse,
    VinLookupResponse,
    to_wire,
)

_ROLES = ("dealer", "leasing_company", "distributor", "carcraft_employee")

router = APIRouter(dependencies=[Depends(require_roles(*_ROLES))])
# Catalog VIN lookup lives under the special-equipment prefix but is private to cabinets.
vin_lookup_router = APIRouter(dependencies=[Depends(require_roles(*_ROLES))])

_User = Annotated[dict[str, Any], Depends(get_notification_company_context)]
_Session = Annotated[AsyncSession, Depends(get_db)]
_IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description='Версия сделки из `ETag`/поля `etag` карточки: "<id>:<version>"',
    ),
]
_Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
_CARD_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "Сделка не найдена или недоступна"},
    409: {"description": "Конфликт состояния, резерва или уникальности"},
    412: {"description": "Версия сделки устарела"},
    428: {"description": "Не передан заголовок If-Match"},
}


def _actor(user: dict[str, Any]) -> Actor:
    return Actor.from_context(user)


def _card_response(result: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    """Card (or a result carrying it) with the ``ETag`` of the fresh version."""
    deal = result.get("deal") or {}
    headers = {"ETag": str(deal["etag"])} if deal.get("etag") else None
    return JSONResponse(content=to_wire(result), status_code=status_code, headers=headers)


async def _commit(session: AsyncSession, result: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    await session.commit()
    return _card_response(result, status_code=status_code)


async def _read_limited(upload: UploadFile) -> bytes:
    """Read at most the allowed size; larger files are refused without buffering them all."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise FastDealFileTooLargeError(
                f"Файл «{upload.filename or 'без имени'}» больше допустимых 50 МБ"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _attachment(filename: str) -> str:
    safe = filename.replace("\\", "_").replace('"', "'").replace("\r", " ").replace("\n", " ")
    return f"attachment; filename=\"{safe.encode('ascii', 'replace').decode()}\"; filename*=UTF-8''{quote(filename)}"


# ================================================================== catalog (VIN lookup)

@vin_lookup_router.get(
    "/vin-lookup",
    response_model=VinLookupResponse,
    summary="Поиск техники по VIN для регистрации сделки",
    description=(
        "Дилеру ищет только по VIN на физически собственных складах, лизинговой "
        "компании — по всем опубликованным объявлениям. Область определяет сервер. "
        "Некорректный VIN — 400."
    ),
)
async def vin_lookup(
    user: _User, session: _Session, vin: Annotated[str, Query(min_length=1, max_length=64)],
) -> JSONResponse:
    result = await handle_vin_lookup(_actor(user), vin, session)
    return JSONResponse(content=to_wire(result))


# ================================================================== lists and lookups

@router.get(
    "",
    response_model=FastDealListResponse,
    summary="Список сделок",
    description=(
        "Доступные пользователю сделки (серверное ограничение по стороне, автору, "
        "ответственным и администратору компании); затем применяются фильтры. "
        "`page>=1`, `page_size` 1–100 (по умолчанию 20)."
    ),
)
async def list_fast_deals(
    user: _User,
    session: _Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    number: str | None = None,
    client_inn: str | None = None,
    client_company_id: UUID | None = None,
    leasing_company_id: UUID | None = None,
    dealer_company_id: UUID | None = None,
    source_type: Annotated[str | None, Query(pattern="^(dealer_to_leasing|leasing_to_dealer)$")] = None,
    status: str | None = None,
) -> JSONResponse:
    filters = {
        key: value
        for key, value in {
            "number": number,
            "client_inn": client_inn,
            "client_company_id": client_company_id,
            "leasing_company_id": leasing_company_id,
            "dealer_company_id": dealer_company_id,
            "source_type": source_type,
            "status": status,
        }.items()
        if value is not None
    }
    result = await handle_list_fast_deals(_actor(user), filters, page, page_size, session)
    return JSONResponse(content=to_wire(result))


@router.post(
    "",
    status_code=201,
    response_model=FastDealCardResponse,
    summary="Создать сделку (черновик)",
    description=(
        "Создаёт черновик. Направление определяется ролью: дилер → DD, ЛК → DL. "
        "Клиент — `company_id` существующей компании ЛИБО выбранный объект `company`; "
        "обязателен телефон `+7XXXXXXXXXX`. Клиент не получает аккаунт, SMS или доступ."
    ),
)
async def create_fast_deal(body: CreateFastDealBody, user: _User, session: _Session) -> JSONResponse:
    result = await handle_create_fast_deal(
        CreateFastDealCommand(
            actor=_actor(user),
            company_id=body.company_id,
            company=body.company.model_dump(exclude_none=True) if body.company else None,
            client_phone=body.client_phone,
        ),
        session,
    )
    await session.commit()
    response = _card_response(result, status_code=201)
    response.headers["Location"] = f"/api/v1/fast-deals/{result['deal']['id']}"
    return response


@router.get(
    "/filter-options",
    response_model=FilterOptionsResponse,
    summary="Значения фильтров списка",
    description="Компании из доступных пользователю сделок: клиенты, ЛК, дилеры.",
)
async def filter_options(user: _User, session: _Session) -> JSONResponse:
    return JSONResponse(content=to_wire(await handle_filter_options(_actor(user), session)))


@router.get(
    "/vehicle-candidates",
    summary="Таблица выбора техники",
    description=(
        "Каталожные единицы для добавления в сделку с фильтрами VIN, склад, марка, модель. "
        "Дилеру — собственные склады, ЛК — все опубликованные объявления."
    ),
)
async def vehicle_candidates(
    user: _User,
    session: _Session,
    vin: str | None = None,
    warehouse_id: UUID | None = None,
    mark_id: UUID | None = None,
    model_id: UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    filters = {
        key: value
        for key, value in {
            "vin": vin, "warehouse_id": warehouse_id, "mark_id": mark_id, "model_id": model_id,
        }.items()
        if value is not None
    }
    result = await handle_vehicle_candidates(_actor(user), filters, page, page_size, session)
    return JSONResponse(content=to_wire(result))


@router.get(
    "/lookups/{kind}",
    summary="Справочники формы сделки",
    description=(
        "`kind`: leasing-companies, dealers, categories, marks, models, modifications, trims, "
        "colors, equipments, services, purposes, regions, similar-models. Параметры: `q`, "
        "`category_id`, `mark_id`, `model_id`, `modification_id`."
    ),
)
async def lookups(
    kind: str,
    user: _User,
    session: _Session,
    q: str | None = None,
    category_id: UUID | None = None,
    mark_id: UUID | None = None,
    model_id: UUID | None = None,
    modification_id: UUID | None = None,
) -> JSONResponse:
    params = {
        key: value
        for key, value in {
            "q": q, "category_id": category_id, "mark_id": mark_id, "model_id": model_id,
            "modification_id": modification_id,
        }.items()
        if value is not None
    }
    result = await handle_lookup(_actor(user), kind, params, session)
    return JSONResponse(content=to_wire(result))


# =========================================================== child resources by own id

@router.patch(
    "/support-requests/{request_id}",
    response_model=FastDealCardResponse,
    summary="Решение дистрибьютора по запросу поддержки",
    description=(
        "Отклонить (`cancelled`), предварительно согласовать (`pre_approved`, цена не меняется) "
        "или согласовать (`approved`, `decided_amount`). If-Match — версия родительской сделки."
    ),
    responses=_CARD_ERRORS,
)
async def decide_support(
    request_id: UUID, body: SupportDecisionBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_decide_support(
        DecideSupportCommand(
            actor=_actor(user), request_id=request_id, if_match=if_match, status=body.status,
            decided_amount=body.decided_amount, comment=body.comment,
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/lc-applications/{lc_application_id}/offer",
    response_model=FastDealCardResponse,
    summary="Коммерческое предложение ЛК (DD)",
    description=(
        "Одно КП на запись ЛК в цикле. Обязательны сумма финансирования, аванс, срок, платёж и "
        "стоимость договора; остальные условия и PDF необязательны."
    ),
    responses=_CARD_ERRORS,
)
async def submit_offer(
    lc_application_id: UUID, body: OfferBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_submit_offer(
        SubmitOfferCommand(
            actor=_actor(user), lc_application_id=lc_application_id, if_match=if_match,
            body=body.model_dump(),
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/lc-applications/{lc_application_id}/select",
    response_model=FastDealCardResponse,
    summary="Дилер выбирает КП (DD)",
    description="Выбирает действующее КП; остальные приглашения закрываются, сделка ждёт финального подтверждения ЛК.",
    responses=_CARD_ERRORS,
)
async def select_offer(
    lc_application_id: UUID, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_select_offer(
        SelectOfferCommand(actor=_actor(user), lc_application_id=lc_application_id, if_match=if_match),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/lc-applications/{lc_application_id}/confirm",
    response_model=FastDealCardResponse,
    summary="Финальное подтверждение выбранной ЛК (DD)",
    description="Фиксирует итоговые условия и сумму, завершает резервы, создаёт компенсации и монетизацию.",
    responses=_CARD_ERRORS,
)
async def lc_confirm(
    lc_application_id: UUID, user: _User, session: _Session,
    body: ConfirmBody | None = None, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_lc_confirm(
        LcConfirmCommand(
            actor=_actor(user), lc_application_id=lc_application_id, if_match=if_match,
            file_ids=list(body.file_ids) if body else [],
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/lc-applications/{lc_application_id}/reject",
    response_model=FastDealCardResponse,
    summary="Отказ ЛК (DD)",
    description="Причина обязательна. Если допустимых ЛК не осталось, сделка отклоняется, резервы освобождаются.",
    responses=_CARD_ERRORS,
)
async def lc_reject(
    lc_application_id: UUID, body: ReasonBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_lc_reject(
        LcRejectCommand(
            actor=_actor(user), lc_application_id=lc_application_id, if_match=if_match,
            reason=body.reason,
        ),
        session,
    )
    return await _commit(session, result)


# ====================================================================== deal resources

@router.get(
    "/{deal_id}",
    response_model=FastDealCardResponse,
    summary="Карточка сделки",
    description=(
        "Карточка в проекции вызывающей стороны: `allowed_actions`, `version`, `etag` и заголовок "
        "`ETag`. Для ЛК поддержки отсутствуют целиком. Чужая сделка — 404."
    ),
)
async def get_fast_deal(deal_id: UUID, user: _User, session: _Session) -> JSONResponse:
    return _card_response(await handle_get_fast_deal(_actor(user), deal_id, session))


@router.delete(
    "/{deal_id}",
    status_code=204,
    response_model=None,
    summary="Удалить черновик",
    description="Только никогда не отправлявшийся черновик (`sent_at IS NULL`); файлы удаляются из хранилища.",
    responses=_CARD_ERRORS,
)
async def delete_fast_deal(
    deal_id: UUID, user: _User, session: _Session, storage: _Storage, if_match: _IfMatch = None,
) -> Response:
    await handle_delete_fast_deal(
        DeleteFastDealCommand(actor=_actor(user), deal_id=deal_id, if_match=if_match), session, storage,
    )
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/{deal_id}/vehicles",
    status_code=201,
    response_model=FastDealCardResponse,
    summary="Добавить позицию",
    description=(
        "Каталожная (`product`) или ручная (`manual`) позиция — отдельная единица с VIN, без количества. "
        "`is_reservable` вычисляет сервер."
    ),
    responses=_CARD_ERRORS,
)
async def add_vehicle(
    deal_id: UUID, body: AddVehicleBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_add_vehicle(
        AddVehicleCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            body=body.model_dump(exclude_unset=True),
        ),
        session,
    )
    return await _commit(session, result, status_code=201)


@router.patch(
    "/{deal_id}/vehicles/{vehicle_id}",
    response_model=FastDealCardResponse,
    summary="Изменить или заменить позицию",
    description="Допустимые поля либо `replace_with` (взаимоисключающие). Каталожные значения не принимаются как доверенные.",
    responses=_CARD_ERRORS,
)
async def patch_vehicle(
    deal_id: UUID, vehicle_id: UUID, body: PatchVehicleBody, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_patch_vehicle(
        PatchVehicleCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match,
            body=body.model_dump(exclude_unset=True),
        ),
        session,
    )
    return await _commit(session, result)


@router.delete(
    "/{deal_id}/vehicles/{vehicle_id}",
    response_model=FastDealCardResponse,
    summary="Удалить позицию",
    description="В отправленной сделке — мягкое удаление (`removed`), резерв освобождается, при необходимости сброс сделки.",
    responses=_CARD_ERRORS,
)
async def remove_vehicle(
    deal_id: UUID, vehicle_id: UUID, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_remove_vehicle(
        RemoveVehicleCommand(actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match),
        session,
    )
    return await _commit(session, result)


@router.patch(
    "/{deal_id}/vehicles/{vehicle_id}/price-adjustment",
    response_model=FastDealCardResponse,
    summary="Скидка или наценка позиции",
    description="`discount` (DD, DL) либо `markup` (DL) и положительная сумма; `type` и `amount` = null очищают корректировку.",
    responses=_CARD_ERRORS,
)
async def price_adjustment(
    deal_id: UUID, vehicle_id: UUID, body: PriceAdjustmentBody, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_price_adjustment(
        PriceAdjustmentCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match,
            adjustment_type=body.type, amount=body.amount,
        ),
        session,
    )
    return await _commit(session, result)


@router.put(
    "/{deal_id}/vehicles/{vehicle_id}/options",
    response_model=FastDealCardResponse,
    summary="Опции позиции",
    description="Полная атомарная замена оборудования, услуг, назначений и регионов.",
    responses=_CARD_ERRORS,
)
async def set_options(
    deal_id: UUID, vehicle_id: UUID, body: OptionsBody, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_set_options(
        SetOptionsCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match,
            equipments=[item.model_dump() for item in body.equipments],
            services=[item.model_dump() for item in body.services],
            purposes=list(body.purposes), regions=list(body.regions),
        ),
        session,
    )
    return await _commit(session, result)


@router.get(
    "/{deal_id}/vehicles/{vehicle_id}/support-programs",
    response_model=SupportProgramsResponse,
    summary="Программы поддержки позиции",
    description="Доступно только стороне дилера. Для ЛК маршрут недоступен.",
)
async def support_programs(deal_id: UUID, vehicle_id: UUID, user: _User, session: _Session) -> JSONResponse:
    result = await handle_support_programs(_actor(user), deal_id, vehicle_id, session)
    return JSONResponse(content=to_wire(result))


@router.post(
    "/{deal_id}/vehicles/{vehicle_id}/applied-supports",
    response_model=FastDealCardResponse,
    summary="Применить программу поддержки",
    description="Сервер сам считает сумму и совместимость; поддержка учитывается ровно один раз.",
    responses=_CARD_ERRORS,
)
async def apply_support_program(
    deal_id: UUID, vehicle_id: UUID, body: ApplySupportProgramBody, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_apply_support_program(
        ApplySupportProgramCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match,
            support_program_id=body.support_program_id,
        ),
        session,
    )
    return await _commit(session, result)


@router.delete(
    "/{deal_id}/vehicles/{vehicle_id}/applied-supports/{applied_id}",
    response_model=FastDealCardResponse,
    summary="Снять применённую программу",
    description="Пересчёт цены; в отправленной сделке DD — обычный сброс в черновик.",
    responses=_CARD_ERRORS,
)
async def remove_applied_support(
    deal_id: UUID, vehicle_id: UUID, applied_id: UUID, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_remove_applied_support(
        RemoveAppliedSupportCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, applied_id=applied_id,
            if_match=if_match,
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/vehicles/{vehicle_id}/support-requests",
    status_code=201,
    response_model=FastDealCardResponse,
    summary="Запрос дополнительной поддержки",
    description=(
        "Дилер запрашивает сумму у своего дистрибьютора (по связи дилер → дистрибьютор и марке). "
        "Один открытый запрос на позицию; отправленный запрос не редактируется и не отзывается."
    ),
    responses=_CARD_ERRORS,
)
async def request_support(
    deal_id: UUID, vehicle_id: UUID, body: SupportRequestBody, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_request_support(
        RequestSupportCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match,
            amount=body.amount, comment=body.comment,
        ),
        session,
    )
    return await _commit(session, result, status_code=201)


@router.post(
    "/{deal_id}/vehicles/{vehicle_id}/apply-support",
    response_model=FastDealCardResponse,
    summary="Учесть согласованную поддержку",
    description="После отправки цена автоматически не меняется; действие учитывает сумму (DD — сброс, DL — цикл изменений).",
    responses=_CARD_ERRORS,
)
async def apply_approved_support(
    deal_id: UUID, vehicle_id: UUID, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_apply_approved_support(
        ApplyApprovedSupportCommand(
            actor=_actor(user), deal_id=deal_id, vehicle_id=vehicle_id, if_match=if_match,
        ),
        session,
    )
    return await _commit(session, result)


@router.patch(
    "/{deal_id}/leasing-terms",
    response_model=FastDealCardResponse,
    summary="Условия лизинга",
    description=(
        "Аванс в рублях ИЛИ процентах, срок 12–84 месяца, ручной ежемесячный платёж (иначе расчёт "
        "калькулятором), выкупной платёж. Противоречивый ввод отклоняется."
    ),
    responses=_CARD_ERRORS,
)
async def update_leasing_terms(
    deal_id: UUID, body: LeasingTermsBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_update_leasing_terms(
        UpdateLeasingTermsCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            down_payment=body.down_payment, down_payment_percent=body.down_payment_percent,
            lease_term_months=body.lease_term_months, monthly_payment=body.monthly_payment,
            buyout_amount=body.buyout_amount,
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/send-to-leasing-companies",
    response_model=FastDealCardResponse,
    summary="Отправить в лизинговые компании (DD)",
    description="Непустой уникальный список ЛК. Все резервы берутся атомарно: конфликт хотя бы одной единицы — 409 без частичных изменений.",
    responses=_CARD_ERRORS,
)
async def send_to_leasing_companies(
    deal_id: UUID, body: SendToLeasingCompaniesBody, user: _User, session: _Session,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_send_to_leasing_companies(
        SendToLeasingCompaniesCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            leasing_company_ids=list(body.leasing_company_ids),
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/withdraw-selection",
    response_model=FastDealCardResponse,
    summary="Снять выбор КП (DD)",
    description="Восстанавливает состояния приглашений: валидные КП — `offer_sent`, остальные — `pending_review`.",
    responses=_CARD_ERRORS,
)
async def withdraw_selection(
    deal_id: UUID, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_withdraw_selection(
        WithdrawSelectionCommand(actor=_actor(user), deal_id=deal_id, if_match=if_match), session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/send-to-dealers",
    response_model=SendToDealersResponse,
    summary="Отправить дилерам (DL)",
    description=(
        "Первая отправка атомарно делит сделку по дилерам: исходные ID и номер — у первого дилера, "
        "остальные получают новые; `group_id` у всех равен исходному ID. Повторная отправка после "
        "отказа идёт тому же дилеру без нового разделения."
    ),
    responses=_CARD_ERRORS,
)
async def send_to_dealers(
    deal_id: UUID, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_send_to_dealers(
        SendToDealersCommand(actor=_actor(user), deal_id=deal_id, if_match=if_match), session,
    )
    await session.commit()
    return JSONResponse(content=to_wire(result))


@router.post(
    "/{deal_id}/confirm",
    response_model=FastDealCardResponse,
    summary="Дилер подтверждает без изменений (DL)",
    description="Доступно, пока нет неотправленных изменений дилера.",
    responses=_CARD_ERRORS,
)
async def dealer_confirm(
    deal_id: UUID, user: _User, session: _Session, body: ConfirmBody | None = None,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_dealer_confirm(
        DealerConfirmCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            file_ids=list(body.file_ids) if body else [],
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/send-changes",
    response_model=FastDealCardResponse,
    summary="Дилер отправляет изменения (DL)",
    description="Отправляет изменения лизинговой компании; сделка ждёт её решения.",
    responses=_CARD_ERRORS,
)
async def send_changes(
    deal_id: UUID, user: _User, session: _Session, body: SendChangesBody | None = None,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_send_changes(
        SendChangesCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            comment=body.comment if body else None,
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/changes/accept",
    response_model=FastDealCardResponse,
    summary="ЛК принимает изменения (DL)",
    description="Сделка подтверждается без дополнительного подтверждения дилером.",
    responses=_CARD_ERRORS,
)
async def accept_changes(
    deal_id: UUID, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_accept_changes(
        AcceptChangesCommand(actor=_actor(user), deal_id=deal_id, if_match=if_match), session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/changes/reject",
    response_model=FastDealCardResponse,
    summary="ЛК отклоняет изменения (DL)",
    description="Причина обязательна. Сделка отклоняется, резервы освобождаются; ЛК может исправить её и отправить снова.",
    responses=_CARD_ERRORS,
)
async def reject_changes(
    deal_id: UUID, body: ReasonBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_reject_changes(
        RejectChangesCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match, reason=body.reason,
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/reject",
    response_model=FastDealCardResponse,
    summary="Дилер отказывает (DL)",
    description="Причина обязательна. Сделка отклоняется, резервы освобождаются.",
    responses=_CARD_ERRORS,
)
async def dealer_reject(
    deal_id: UUID, body: ReasonBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_dealer_reject(
        DealerRejectCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match, reason=body.reason,
        ),
        session,
    )
    return await _commit(session, result)


@router.post(
    "/{deal_id}/cancel",
    response_model=FastDealCardResponse,
    summary="Отменить сделку",
    description="Инициатор отменяет незавершённую сделку. Отмена необратима, резервы освобождаются.",
    responses=_CARD_ERRORS,
)
async def cancel_fast_deal(
    deal_id: UUID, user: _User, session: _Session, body: CancelBody | None = None,
    if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_cancel_fast_deal(
        CancelFastDealCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            reason=body.reason if body else None,
        ),
        session,
    )
    return await _commit(session, result)


@router.get(
    "/{deal_id}/files/archive",
    response_model=None,
    summary="ZIP доступных файлов",
    description="Архив только файлов, которые читать разрешено вызывающему; ACL проверяется для каждого файла.",
)
async def download_archive(
    deal_id: UUID, user: _User, session: _Session, storage: _Storage,
) -> Response:
    archive = await handle_download_archive(_actor(user), deal_id, session, storage)
    return Response(
        content=archive.data,
        media_type="application/zip",
        headers={
            "Content-Disposition": _attachment(archive.filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{deal_id}/files/{file_id}",
    response_model=None,
    summary="Скачать файл",
    description="Приватный объект выдаётся только после проверки ACL; прямой ID не обходит права.",
)
async def download_file(
    deal_id: UUID, file_id: UUID, user: _User, session: _Session, storage: _Storage,
) -> Response:
    stored = await handle_download_file(_actor(user), deal_id, file_id, session, storage)
    return Response(
        content=stored.data,
        media_type=stored.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": _attachment(stored.filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{deal_id}/files",
    status_code=201,
    response_model=UploadFilesResponse,
    summary="Загрузить файлы",
    description=(
        "Multipart: до 20 файлов за запрос, каждый до 50 МБ, не пустой. `kind`: deal_main, deal_additional, "
        "lc_offer_pdf, vehicle_offer. Для deal_additional дилера DD — адресные ЛК (`addressee_company_ids`); "
        "для vehicle_offer — `fast_deal_vehicle_id` (только ЛК); для lc_offer_pdf — `lc_application_id`. "
        "Доступно до confirmed/cancelled."
    ),
    responses=_CARD_ERRORS,
)
async def upload_files(
    deal_id: UUID,
    user: _User,
    session: _Session,
    storage: _Storage,
    kind: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    addressee_company_ids: Annotated[list[UUID] | None, Form()] = None,
    fast_deal_vehicle_id: Annotated[UUID | None, Form()] = None,
    lc_application_id: Annotated[UUID | None, Form()] = None,
    if_match: _IfMatch = None,
) -> JSONResponse:
    if kind not in {item.value for item in FileKind}:
        raise FastDealValidationError("Неизвестный вид файла", field="kind")
    if not files:
        raise FastDealValidationError("Выберите файлы для загрузки", field="files")
    if len(files) > MAX_UPLOAD_FILES:
        raise FastDealValidationError(
            f"За один запрос можно загрузить не более {MAX_UPLOAD_FILES} файлов", field="files"
        )
    uploaded: list[UploadedFile] = []
    for upload in files:
        data = await _read_limited(upload)
        if not data:
            raise FastDealValidationError(
                f"Файл «{upload.filename or 'без имени'}» пустой", field="files"
            )
        uploaded.append(
            UploadedFile(
                filename=upload.filename or "file",
                content_type=upload.content_type or "application/octet-stream",
                data=data,
            )
        )
    result = await handle_upload_files(
        UploadFilesCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match, kind=kind, files=uploaded,
            addressee_company_ids=list(addressee_company_ids or []),
            fast_deal_vehicle_id=fast_deal_vehicle_id, lc_application_id=lc_application_id,
        ),
        session,
        storage,
    )
    return await _commit(session, result, status_code=201)


@router.get(
    "/{deal_id}/assignable-employees",
    response_model=AssignableEmployeesResponse,
    summary="Сотрудники для назначения",
    description="Активные сотрудники своей компании; доступно администратору компании-стороны сделки.",
)
async def assignable_employees(deal_id: UUID, user: _User, session: _Session) -> JSONResponse:
    result = await handle_assignable_employees(_actor(user), deal_id, session)
    return JSONResponse(content=to_wire(result))


@router.put(
    "/{deal_id}/assignees",
    response_model=FastDealCardResponse,
    summary="Назначить ответственных своей стороны",
    description=(
        "Один основной и не более одного дополнительного ответственного из активных сотрудников своей "
        "компании. Переназначение допустимо в любом статусе, включая confirmed/cancelled (история и уведомление)."
    ),
    responses=_CARD_ERRORS,
)
async def set_assignees(
    deal_id: UUID, body: AssigneesBody, user: _User, session: _Session, if_match: _IfMatch = None,
) -> JSONResponse:
    result = await handle_set_assignees(
        SetAssigneesCommand(
            actor=_actor(user), deal_id=deal_id, if_match=if_match,
            primary_user_id=body.primary_user_id, additional_user_id=body.additional_user_id,
        ),
        session,
    )
    return await _commit(session, result)
