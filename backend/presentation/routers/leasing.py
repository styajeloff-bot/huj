"""LC workflow API.

Endpoints scoped to the leasing-company cabinet: directory reads, the
review queue, and the response workflow (commercial proposals, PDF,
final decision). Access control is a combination of JWT scope
(``APPLICATIONS_READ`` / ``LEASING_REVIEW``) plus an in-handler role
check — LC actions are gated to role ``leasing_company`` (or
``carcraft_employee`` for admin override).

The legacy approve / reject / request-documents endpoints have been
replaced with the proposal-based response flow.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_documents import (
    RequirementInput,
    UpdateRequirementsCommand,
    handle_update_requirements,
)
from application.commands.leasing.approve_application_document import (
    ApproveApplicationDocumentCommand,
    handle_approve_application_document,
)
from application.commands.leasing.confirm_deal import (
    ConfirmDealCommand,
    handle_confirm_deal,
    publish_confirm_deal_events,
)
from application.commands.leasing.issue_application import (
    IssueApplicationCommand,
    handle_issue_application,
)
from application.commands.leasing.request_documents import (
    RequestDocumentsCommand,
    RequestedDocument,
    handle_request_documents,
)
from application.commands.leasing.take_in_work import (
    TakeInWorkCommand,
    handle_take_in_work,
)
from application.commands.leasing_response import (
    DeleteProposalCommand,
    RemoveProposalPdfCommand,
    RemoveResponsePdfCommand,
    SubmitDecisionCommand,
    UploadProposalPdfCommand,
    UploadResponsePdfCommand,
    UpsertProposalCommand,
    handle_delete_proposal,
    handle_get_proposal_pdf,
    handle_remove_proposal_pdf,
    handle_remove_response_pdf,
    handle_submit_decision,
    handle_upload_proposal_pdf,
    handle_upload_response_pdf,
    handle_upsert_proposal,
)
from application.errors import ServiceError, domain_to_http
from application.queries.application_documents import (
    ListLcRequirementsQuery,
    handle_list_lc_requirements,
)
from application.queries.leasing import (
    ListLcApplicationsQuery,
    ListLeasingCompaniesQuery,
    handle_list_lc_applications,
    handle_list_leasing_companies,
)
from application.queries.leasing_response import (
    GetFinancialBundleQuery,
    GetLcApplicationDocumentsQuery,
    GetLcResponseStateQuery,
    handle_get_financial_bundle,
    handle_get_lc_application_documents,
    handle_get_lc_response_state,
)
from application.services.questionnaire_delivery import get_settings, save_settings
from domain.errors import (
    DomainError,
    LeasingCompanyBindingNotConfiguredError,
)
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import APPLICATIONS_READ, LEASING_REVIEW
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import (
    get_current_user,
    require_roles,
    require_scopes,
)
from presentation.dependencies.leasing_context import (
    can_review_leasing_context,
    get_leasing_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.application_documents import (
    ListLcRequirementsResponse,
    UpdateRequirementsBody,
    UpdateRequirementsResponse,
)
from presentation.schemas.applications import application_commerce_money_to_wire
from presentation.schemas.leasing import (
    ApproveApplicationDocumentRequest,
    ApproveApplicationDocumentResponse,
    ConfirmDealRequest,
    ConfirmDealResponse,
    FinancialBundleResponse,
    LcApplicationDocumentsResponse,
    LcApplicationsListResponse,
    LcResponseStateResponse,
    LeasingCompaniesResponse,
    ProposalOut,
    ProposalParams,
    RequestDocumentsRequest,
    RequestDocumentsResponse,
    SubmitDecisionRequest,
    SubmitDecisionResponse,
    TakeInWorkResponse,
    UploadResponsePdfResponse,
)
from presentation.schemas.questionnaire_settings import (
    QuestionnaireSettingsBody,
    QuestionnaireSettingsResponse,
)

router = APIRouter()

_read_access = require_scopes(APPLICATIONS_READ)
_write_access = require_scopes(LEASING_REVIEW)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _lc_context(
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    _authorized: Annotated[
        dict[str, Any], Depends(require_roles("leasing_company", "carcraft_employee"))
    ],
) -> dict[str, Any]:
    return user


async def _lc_review_context(
    user: Annotated[dict[str, Any], Depends(_lc_context)],
) -> dict[str, Any]:
    if not can_review_leasing_context(user):
        raise HTTPException(
            status_code=403, detail="Нет прав на изменение заявки этой ЛК"
        )
    return user


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------


@router.get(
    "/companies",
    response_model=LeasingCompaniesResponse,
    summary="Список активных лизинговых компаний",
    description=(
        "Публичный справочник активных ЛК — используется в dealer/client "
        "UI для выбора лизинговой компании при создании заявки. Требует "
        "только авторизацию (любая роль)."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_leasing_companies_endpoint(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_leasing_companies(ListLeasingCompaniesQuery(), session)
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# LC cabinet — review queue
# ---------------------------------------------------------------------------


@router.get(
    "/applications",
    response_model=LcApplicationsListResponse,
    summary="Заявки, доступные ЛК для ревью",
    description=(
        "Возвращает заявки, у которых есть связь с текущей ЛК. Фильтруется "
        "по статусу LCA. Доступно только роли `leasing_company`."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_lc_applications_endpoint(
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    kind: Annotated[
        Literal["application", "fast_deal"] | None,
        Query(
            description=(
                "Вид строк: `application` — обычные заявки, `fast_deal` — быстрая "
                "регистрация сделки. Без параметра — объединённый список; фильтр "
                "статуса или источника обычной заявки исключает fast deals."
            )
        ),
    ] = None,
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        result = await handle_list_lc_applications(
            ListLcApplicationsQuery(
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_leasing_company_id=lc_id,
                actor_company_id=user.get("company_id"),
                status=status,
                source_type=source_type,
                search=search,
                kind=kind,
                page=page,
                limit=limit,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Response workflow (LC cabinet)
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{application_id}/financial-bundle",
    response_model=FinancialBundleResponse,
    summary="Финотчётность и анкета (дубликат шага №2)",
    description=(
        "Возвращает анкету заявки (реквизиты, директора, учредители, "
        "бенефициары) и последнюю бухгалтерскую отчётность по ИНН. Доступ "
        "только ЛК, в которую отправлена заявка."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_financial_bundle_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    if lc_id is None:
        raise _http(LeasingCompanyBindingNotConfiguredError())
    try:
        result = await handle_get_financial_bundle(
            GetFinancialBundleQuery(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/applications/{application_id}/documents",
    response_model=LcApplicationDocumentsResponse,
    summary="Прикреплённые документы заявки",
    description=(
        "Полный список документов, прикреплённых к заявке (через "
        "related_application_id или document_applications), с русскими "
        "названиями из document_types и пометкой периода (год/квартал) "
        "для документов с period_label. Доступ только ЛК, в которую "
        "отправлена заявка."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_lc_application_documents_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    if lc_id is None:
        raise _http(LeasingCompanyBindingNotConfiguredError())
    try:
        result = await handle_get_lc_application_documents(
            GetLcApplicationDocumentsQuery(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/applications/{application_id}/documents/{document_id}/status",
    response_model=ApproveApplicationDocumentResponse,
    summary="Одобрить документ заявки для текущей ЛК",
    description=(
        "Атомарно переводит только связь текущей ЛК с документом заявки из "
        "`submitted` в `approved`; глобальный статус документа не меняется."
    ),
    dependencies=[Depends(_write_access)],
)
async def approve_application_document_endpoint(
    application_id: uuid.UUID,
    document_id: uuid.UUID,
    _body: ApproveApplicationDocumentRequest,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_approve_application_document(
            ApproveApplicationDocumentCommand(
                application_id=application_id,
                document_id=document_id,
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
                actor_leasing_company_id=user.get("leasing_company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/applications/{application_id}/response",
    response_model=LcResponseStateResponse,
    summary="Текущее состояние ответа ЛК на заявку",
    description=(
        "Возвращает связь LCA, исходные параметры заявки и список КП, "
        "которые ЛК уже подготовила. До submit состояние видно только ЛК."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_response_state_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    if lc_id is None:
        raise _http(LeasingCompanyBindingNotConfiguredError())
    try:
        result = await handle_get_lc_response_state(
            GetLcResponseStateQuery(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    LcResponseStateResponse.model_validate(result)
    application = result.get("application")
    payload = {
        **result,
        "can_review": can_review_leasing_context(user),
        "application": (
            application_commerce_money_to_wire(application)
            if isinstance(application, dict)
            else application
        ),
    }
    return JSONResponse(content=jsonable_encoder(payload))


@router.put(
    "/applications/{application_id}/proposals/{kind}",
    response_model=ProposalOut,
    summary="Создать или обновить КП (preliminary / final)",
    description=(
        "Один слот на kind. PUT — upsert полей; пустые поля можно слать "
        "как `null`. Запрещено после submit."
    ),
    dependencies=[Depends(_write_access)],
)
async def upsert_proposal_endpoint(
    application_id: uuid.UUID,
    kind: str,
    body: ProposalParams,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    params = body.model_dump(exclude_unset=True)
    try:
        result = await handle_upsert_proposal(
            UpsertProposalCommand(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                kind=kind,
                params=params,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/applications/{application_id}/proposals/{kind}",
    summary="Удалить КП слота",
    description="Удаляет КП выбранного kind. Запрещено после submit.",
    dependencies=[Depends(_write_access)],
    status_code=204,
)
async def delete_proposal_endpoint(
    application_id: uuid.UUID,
    kind: str,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        await handle_delete_proposal(
            DeleteProposalCommand(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                kind=kind,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=None, status_code=204)


@router.post(
    "/applications/{application_id}/proposals/{kind}/pdf",
    response_model=UploadResponsePdfResponse,
    summary="Загрузить PDF конкретного КП",
    description="Загружает или заменяет PDF предварительного либо итогового КП. Лимит 10 МБ.",
    dependencies=[Depends(_write_access)],
)
async def upload_proposal_pdf_endpoint(
    application_id: uuid.UUID,
    kind: str,
    file: Annotated[UploadFile, File(...)],
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> JSONResponse:
    try:
        result = await handle_upload_proposal_pdf(
            UploadProposalPdfCommand(
                application_id=application_id,
                actor_leasing_company_id=user.get("leasing_company_id"),
                kind=kind,
                file_name=file.filename or "proposal.pdf",
                content_type=file.content_type or "application/pdf",
                data=await file.read(),
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/applications/{application_id}/proposals/{kind}/pdf",
    summary="Удалить PDF конкретного КП",
    description="Удаляет PDF только выбранного предварительного либо итогового КП.",
    dependencies=[Depends(_write_access)],
    status_code=204,
)
async def remove_proposal_pdf_endpoint(
    application_id: uuid.UUID,
    kind: str,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        await handle_remove_proposal_pdf(
            RemoveProposalPdfCommand(
                application_id=application_id,
                actor_leasing_company_id=user.get("leasing_company_id"),
                kind=kind,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return Response(status_code=204)


@router.get(
    "/applications/{application_id}/proposals/{kind}/pdf",
    summary="Открыть PDF конкретного КП",
    description="Безопасно отдаёт PDF выбранного КП только лизинговой компании-владельцу.",
    dependencies=[Depends(_read_access)],
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_proposal_pdf_endpoint(
    application_id: uuid.UUID,
    kind: str,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        data, file_name = await handle_get_proposal_pdf(
            application_id, user.get("leasing_company_id"), kind, session, storage
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{file_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/applications/{application_id}/response-pdf",
    response_model=UploadResponsePdfResponse,
    summary="Загрузить PDF-ответ ЛК",
    description=(
        "Один PDF на ответ. Загрузка нового файла заменяет предыдущий. "
        "Лимит 10 МБ; запрещено после submit."
    ),
    dependencies=[Depends(_write_access)],
)
async def upload_response_pdf_endpoint(
    application_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    data = await file.read()
    try:
        result = await handle_upload_response_pdf(
            UploadResponsePdfCommand(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                file_name=file.filename or "response.pdf",
                content_type=file.content_type or "application/pdf",
                data=data,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.delete(
    "/applications/{application_id}/response-pdf",
    summary="Удалить PDF-ответ ЛК",
    description="Снимает PDF с ответа. Запрещено после submit.",
    dependencies=[Depends(_write_access)],
    status_code=204,
)
async def remove_response_pdf_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        await handle_remove_response_pdf(
            RemoveResponsePdfCommand(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=None, status_code=204)


@router.put(
    "/applications/{application_id}/decision",
    response_model=SubmitDecisionResponse,
    summary="Финальное решение ЛК (Одобрить / Отказать)",
    description=(
        "Approve требует хотя бы одного полностью заполненного КП. "
        "Reject требует комментарий. После submit состояние ответа "
        "становится видно клиенту, ему уходит уведомление."
    ),
    dependencies=[Depends(_write_access)],
)
async def submit_decision_endpoint(
    application_id: uuid.UUID,
    body: SubmitDecisionRequest,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        result = await handle_submit_decision(
            SubmitDecisionCommand(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_leasing_company_id=lc_id,
                action=body.action,
                decision_comment=body.decision_comment,
                kind=body.kind,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)

    await session.commit()

    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/applications/{application_id}/confirm-deal",
    response_model=ConfirmDealResponse,
    summary="Подтвердить сделку с выбранной ЛК",
    description=(
        "Доступно только выбранной клиентом ЛК в статусе `selected_lc`. "
        "Переводит LCA в `deal`, родительскую заявку в `issued` и безопасно "
        "повторяется после успешного подтверждения."
    ),
    dependencies=[Depends(_write_access)],
    status_code=200,
)
async def confirm_deal_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: ConfirmDealRequest | None = None,
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    deal_date = body.deal_date if body is not None else None
    vehicles = [v.model_dump() for v in body.vehicles] if body is not None else []
    documents = [d.model_dump() for d in body.documents] if body is not None else []
    try:
        result = await handle_confirm_deal(
            ConfirmDealCommand(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_leasing_company_id=lc_id,
                deal_date=deal_date,
                vehicles=vehicles,
                documents=documents,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    await publish_confirm_deal_events(result)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/applications/{application_id}/issue",
    summary="Отметить заявку как Выдано",
    description=(
        "Доступно только когда LCA в статусе `approved_final` и клиент принял "
        "итоговое КП (`client_decision_action='accepted'`). Переводит LCA "
        "в `deal` и каскадирует статус родительской заявки в `issued`. "
        "Для строк спецтехники атомарно создаёт идемпотентные лизинговые "
        "заказы и графики платежей; повторный вызов возвращает те же заказы."
    ),
    dependencies=[Depends(_write_access)],
    status_code=200,
)
async def issue_application_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        result = await handle_issue_application(
            IssueApplicationCommand(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/applications/{application_id}/take-in-work",
    response_model=TakeInWorkResponse,
    summary="Взять заявку в работу",
    description=(
        "Переводит заявку из статуса `submitted` в `under_review` для "
        "вызывающей ЛК. Повторный запрос возвращает актуальный статус без "
        "повторного перехода. Требуются права записи в выбранной компании."
    ),
    dependencies=[Depends(_write_access)],
    status_code=200,
)
async def take_in_work_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        result = await handle_take_in_work(
            TakeInWorkCommand(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/applications/{application_id}/request-documents",
    response_model=RequestDocumentsResponse,
    summary="Запросить дополнительные документы у клиента",
    description=(
        "ЛК отмечает заявку как «требуются документы», создаёт batch "
        "запросов и сохраняет slug'и последнего batch в "
        "`leasing_applications.requested_documents`. LCA переходит в "
        "`documents_required`. Повторный batch сохраняет ожидающие запросы "
        "предыдущих batch и доступен до финального решения ЛК."
    ),
    dependencies=[Depends(_write_access)],
)
async def request_documents_endpoint(
    application_id: uuid.UUID,
    body: RequestDocumentsRequest,
    user: Annotated[dict[str, Any], Depends(_lc_review_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    try:
        result = await handle_request_documents(
            RequestDocumentsCommand(
                application_id=application_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_leasing_company_id=lc_id,
                requested_documents=[
                    RequestedDocument(
                        source=document.source,
                        display_name=document.display_name,
                        document_type=document.document_type,
                    )
                    for document in body.requested_documents
                ],
                comments=body.comments,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/applications/{application_id}/accounting-pdf",
    summary="Скачать PDF бухгалтерской отчётности (последний год)",
    description=(
        "Редиректит на ссылку из ФНС-провайдера для последнего "
        "доступного отчётного года. 404 — если отчётности по этому ИНН нет."
    ),
    dependencies=[Depends(_read_access)],
)
async def download_accounting_pdf_endpoint(
    application_id: uuid.UUID,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    lc_id = user.get("leasing_company_id")
    if lc_id is None:
        raise _http(LeasingCompanyBindingNotConfiguredError())
    try:
        bundle = await handle_get_financial_bundle(
            GetFinancialBundleQuery(
                application_id=application_id,
                actor_leasing_company_id=lc_id,
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    accounting = bundle.get("accounting_report") or {}
    year_files = accounting.get("year_files") or []
    pdf_url: str | None = None
    if isinstance(year_files, list):
        for yf in year_files:
            if isinstance(yf, dict) and yf.get("pdf_url"):
                pdf_url = str(yf["pdf_url"])
                break
    if not pdf_url:
        raise HTTPException(
            status_code=404,
            detail="Бухгалтерская отчётность по этой компании не опубликована",
        )
    return RedirectResponse(url=pdf_url, status_code=302)


# ---------------------------------------------------------------------------
# Document requirements aliases (kept for the LC document-management UI)
# ---------------------------------------------------------------------------


@router.get(
    "/document-requirements",
    response_model=ListLcRequirementsResponse,
    summary="Требования документов для текущей ЛК",
    description=(
        "Alias для фронтенда: возвращает требования по документам для "
        "лизинговой компании вызывающего пользователя."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_document_requirements_alias(
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    if lc_id is None:
        raise _http(LeasingCompanyBindingNotConfiguredError())
    try:
        result = await handle_list_lc_requirements(
            ListLcRequirementsQuery(
                leasing_company_id=lc_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_leasing_company_id=lc_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/document-requirements",
    response_model=UpdateRequirementsResponse,
    summary="Обновить требования документов для текущей ЛК",
    description=(
        "Alias для фронтенда: заменяет список требований ЛК текущего пользователя."
    ),
    dependencies=[Depends(_write_access)],
)
async def update_document_requirements_alias(
    body: UpdateRequirementsBody,
    user: Annotated[dict[str, Any], Depends(_lc_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = user.get("leasing_company_id")
    if lc_id is None:
        raise _http(LeasingCompanyBindingNotConfiguredError())
    try:
        result = await handle_update_requirements(
            UpdateRequirementsCommand(
                leasing_company_id=lc_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_leasing_company_id=lc_id,
                requirements=[
                    RequirementInput(
                        document_type=item.document_type,
                        document_type_id=item.document_type_id,
                        is_required=item.is_required,
                        is_mandatory=item.is_mandatory,
                        sort_order=item.sort_order,
                    )
                    for item in body.requirements
                ],
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/companies/{leasing_company_id}/questionnaire-settings",
    response_model=QuestionnaireSettingsResponse,
    summary="Настройки полей анкеты для ЛК",
    description="Возвращает видимость и обязательность бизнес-полей анкеты. Доступно аутентифицированным участникам заполнения заявки.",
    dependencies=[Depends(get_current_user)],
)
async def get_questionnaire_settings(
    leasing_company_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await get_settings(session, leasing_company_id)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.put(
    "/companies/{leasing_company_id}/questionnaire-settings",
    response_model=QuestionnaireSettingsResponse,
    summary="Настроить поля анкеты для ЛК",
    description="carcraft_employee заменяет переопределения полей выбранной ЛК. Неуказанные поля включены и необязательны; выключенное поле нельзя сделать обязательным.",
    dependencies=[Depends(require_roles("carcraft_employee"))],
)
async def put_questionnaire_settings(
    leasing_company_id: uuid.UUID,
    body: QuestionnaireSettingsBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await save_settings(
            session, leasing_company_id, [item.model_dump() for item in body.fields]
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
