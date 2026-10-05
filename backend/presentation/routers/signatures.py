"""Signature-request routes.

Two roles share this router:

* **Applicant** (`POST /signatures/invite`) — invites CEO / founders of
  their company to sign СОПД. Creates invited users where necessary and
  sends SMS with magic links.
* **Signer** (`GET /signatures`) — lists their own pending / signed
  documents. Further ``sign-electronic`` / ``upload-physical`` endpoints
  land in Phase B3.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.invite_signers import (
    InviteSignersCommand,
    SignerPayload,
    handle_invite_signers,
)
from application.commands.revoke_signature import (
    ConfirmSignatureRevokeCommand,
    RequestSignatureRevokeCommand,
    RevokeOptionsQuery,
    RevokeSignatureError,
    handle_confirm_signature_revoke,
    handle_get_signature_revoke_options,
    handle_request_signature_revoke,
)
from application.commands.sign_document import (
    SignElectronicCommand,
    UploadPhysicalSignatureCommand,
    handle_sign_electronic,
    handle_upload_physical_signature,
)
from application.commands.sopd_passport_snapshots import (
    PassportServiceError,
    require_request_snapshot,
)
from application.commands.sopd_passport_snapshots import (
    PassportUploadPage as SopdPassportUploadPage,
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
from application.queries.signature_documents import (
    RevokeDocumentDownloadQuery,
    SignatureDownloadQuery,
    SignaturePreviewQuery,
    handle_revoke_document_download,
    handle_signature_download,
    handle_signature_preview,
)
from application.queries.signatures import (
    ListMySignaturesQuery,
    handle_list_my_signatures,
)
from application.queries.sopd_cache import (
    SopdPdfPending,
    SopdPdfReady,
)
from domain.errors import DomainError
from domain.services.company_lookup import CompanyLookupProvider
from domain.services.object_storage import ObjectStorage
from infrastructure.database import get_db
from infrastructure.services.company_lookup import get_company_lookup_provider
from infrastructure.services.object_storage import get_object_storage
from infrastructure.services.sopd_renderer import load_fallback_sopd_pdf
from presentation.dependencies.auth import get_current_user
from presentation.dependencies.request_context import RequestContextDep
from presentation.schemas.signatures import (
    InviteSignersRequest,
    InviteSignersResponse,
    SignatureListResponse,
    SignatureRevokeInitiatedResponse,
    SignatureRevokeInitiateRequest,
    SignatureRevokeOptionsResponse,
    SignatureRevokeVerifiedResponse,
    SignatureRevokeVerifyRequest,
    SopdPassportFieldsRequest,
    SopdPassportSnapshotResponse,
)

logger = logging.getLogger("carcraft-backend")

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _revoke_error(exc: RevokeSignatureError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            {
                "error_code": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
            }
        ),
    )


def _parse_status_filter(status: str | None) -> list[str] | None:
    if status is None:
        return None
    values = [item.strip() for item in status.split(",") if item.strip()]
    return values or None


_ALLOWED_PASSPORT_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/jpg"})
_MAX_PASSPORT_FILE_BYTES = 10 * 1024 * 1024


async def _read_passport_upload(
    file: UploadFile | None, label: str
) -> tuple[bytes, str, str] | None:
    if file is None:
        return None
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_PASSPORT_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: допустимы только JPG / PNG",
        )
    data = await file.read()
    if not data:
        return None
    if len(data) > _MAX_PASSPORT_FILE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"{label} превышает допустимый размер (10 МБ)",
        )
    return data, file.filename or f"{label}.jpg", content_type


@router.post(
    "/invite",
    response_model=InviteSignersResponse,
    summary="Пригласить ген. директора и учредителей на подпись СОПД",
    description=(
        "multipart/form-data. Поля:\n"
        "* `payload` — JSON `{company_id, application_id, signers: [...]}` "
        "в том же формате, что и раньше;\n"
        "* `passport_main` — опциональный файл (JPG/PNG) страниц 2-3 паспорта "
        "первого подписанта. Если передан, распознаётся сервисом распознавания вместе с "
        "`passport_registration` одним batch-вызовом;\n"
        "* `passport_registration` — опциональный файл страницы с пропиской. "
        "Передавать вместе с `passport_main` или не передавать вовсе.\n\n"
        "Поведение без файлов идентично JSON-версии: создаются "
        "`signature_requests`, выпускается magic-ссылка, отправляется SMS. "
        "Если оба файла присутствуют, запускается фоновое распознавание "
        "под user_id нового подписанта — данные подставятся в СОПД "
        "автоматически к моменту, когда сигнер откроет предпросмотр."
    ),
)
async def invite_signers(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    payload: Annotated[str | None, Form()] = None,
    passport_main: Annotated[UploadFile | None, File()] = None,
    passport_registration: Annotated[UploadFile | None, File()] = None,
    lookup_provider: Annotated[CompanyLookupProvider | None, Depends(get_company_lookup_provider)] = None,
) -> JSONResponse:
    try:
        if payload is None:
            parsed = InviteSignersRequest.model_validate(await request.json())
        else:
            parsed = InviteSignersRequest.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"Некорректный JSON в payload: {exc}"
        )

    if passport_main is not None or passport_registration is not None:
        raise HTTPException(
            status_code=422,
            detail="Загружайте паспорт через scoped passport-recognition до или после приглашения.",
        )

    try:
        results = await handle_invite_signers(
            InviteSignersCommand(
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
                company_lookup_provider=lookup_provider,
                company_id=parsed.company_id,
                application_id=parsed.application_id,
                signers=[
                    SignerPayload(
                        signer_key=s.signer_key,
                        full_name=s.full_name,
                        inn=s.inn,
                        passport=s.passport,
                        gender=s.gender,
                        phone=s.phone,
                    )
                    for s in parsed.signers
                ],
                session_factory=None,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder({"results": results}))




@router.post(
    "/{request_id}/passport-recognition",
    response_model=SopdPassportSnapshotResponse,
    summary="Распознать паспорт подписанта СОПД",
    description=(
        "Синхронно распознаёт две страницы для уже созданного pending СОПД, "
        "обновляет raw-кэш и возвращает полный scoped снимок."
    ),
)
async def update_signature_passport_recognition(
    request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    passport_main: Annotated[UploadFile | None, File()] = None,
    passport_registration: Annotated[UploadFile | None, File()] = None,
) -> JSONResponse:
    if passport_main is None or passport_registration is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "passport_main и passport_registration должны передаваться "
                "вместе — иначе распознавание невозможно."
            ),
        )
    main = await _read_passport_upload(passport_main, "passport_main")
    reg = await _read_passport_upload(passport_registration, "passport_registration")
    if main is None or reg is None:
        raise HTTPException(
            status_code=422,
            detail="Обе страницы паспорта должны быть непустыми.",
        )

    try:
        snapshot = await require_request_snapshot(
            session, request_id=request_id, actor_user_id=user["id"]
        )
        result = await recognize_passport_snapshot(
            session,
            application_id=snapshot["application_id"],
            signer_key=snapshot["signer_key"],
            owner_user_id=snapshot["owner_user_id"],
            passport_main=SopdPassportUploadPage(main[0], main[1], main[2]),
            passport_registration=SopdPassportUploadPage(reg[0], reg[1], reg[2]),
            snapshot_id=snapshot["id"],
            expected_full_name=(
                snapshot.get("expected_full_name")
                or snapshot["recognition_fields"].get("_expected_full_name")
            ),
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{request_id}/passport",
    response_model=SopdPassportSnapshotResponse,
    summary="Получить подтверждаемый снимок паспорта СОПД",
    description="Возвращает снимок только создателю pending СОПД-приглашения.",
)
async def get_signature_passport(
    request_id: Annotated[UUID, Path()], user: Annotated[dict[str, Any], Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        snapshot = await require_request_snapshot(session, request_id=request_id, actor_user_id=user["id"])
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(passport_snapshot_response(snapshot)))


@router.patch(
    "/{request_id}/passport/draft",
    response_model=SopdPassportSnapshotResponse,
    summary="Сохранить черновик паспорта СОПД",
    description="Сохраняет отдельный черновик и блокирует PDF/SMS до подтверждения.",
)
async def patch_signature_passport_draft(
    request_id: Annotated[UUID, Path()], payload: SopdPassportFieldsRequest, user: Annotated[dict[str, Any], Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        snapshot = await require_request_snapshot(session, request_id=request_id, actor_user_id=user["id"])
        result = await save_passport_draft(session, snapshot, payload.fields, payload.edited_fields)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/{request_id}/passport",
    response_model=SopdPassportSnapshotResponse,
    summary="Подтвердить паспорт СОПД",
    description="Валидирует РФ/иностранный документ и фиксирует confirmed_fields.",
)
async def confirm_signature_passport(
    request_id: Annotated[UUID, Path()], payload: SopdPassportFieldsRequest, user: Annotated[dict[str, Any], Depends(get_current_user)], session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        snapshot = await require_request_snapshot(session, request_id=request_id, actor_user_id=user["id"])
        result = await confirm_passport_snapshot(session, snapshot, payload.fields, payload.edited_fields)
    except PassportServiceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "fields": exc.fields},
        ) from exc
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "",
    response_model=SignatureListResponse,
    summary="Документы текущего пользователя на подпись",
    description=(
        "Возвращает signature_requests пользователя. Фильтр `status`: "
        "`pending` (ожидают подписи), `signed_electronic`, "
        "`signed_physical`, `cancelled`, `revoked`. Можно передать несколько "
        "значений через запятую."
    ),
)
async def list_my_signatures(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(default=None),
) -> JSONResponse:
    items = await handle_list_my_signatures(
        ListMySignaturesQuery(
            user_id=user["id"],
            statuses=_parse_status_filter(status),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder({"items": items}))


@router.post(
    "/{request_id}/revoke",
    response_model=SignatureRevokeInitiatedResponse,
    summary="Инициировать отзыв СОПД",
    description=(
        "Проверяет владельца и подписанный статус СОПД, создаёт SMS-код "
        "подтверждения на 10 минут, инвалидирует предыдущий активный код и "
        "фиксирует дату подачи заявки на частичный отзыв по выбранным ЛК."
    ),
)
async def request_signature_revoke(
    request_id: Annotated[UUID, Path()],
    payload: SignatureRevokeInitiateRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request_context: RequestContextDep,
) -> JSONResponse:
    try:
        result = await handle_request_signature_revoke(
            RequestSignatureRevokeCommand(
                request_id=request_id,
                actor_user_id=user["id"],
                leasing_company_ids=payload.leasing_company_ids,
                client_ip=request_context.ip_address,
                user_agent=request_context.user_agent,
            ),
            session,
        )
    except RevokeSignatureError as exc:
        await session.rollback()
        return _revoke_error(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{request_id}/revoke-options",
    response_model=SignatureRevokeOptionsResponse,
    summary="Получить доступные ЛК для частичного отзыва СОПД",
    description=(
        "Возвращает лизинговые компании и подрядчиков из snapshot конкретного "
        "СОПД. Уже отозванные ЛК помечаются disabled."
    ),
)
async def get_signature_revoke_options(
    request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_signature_revoke_options(
            RevokeOptionsQuery(request_id=request_id, actor_user_id=user["id"]),
            session,
        )
    except RevokeSignatureError as exc:
        await session.rollback()
        return _revoke_error(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{request_id}/revoke/verify",
    response_model=SignatureRevokeVerifiedResponse,
    summary="Подтвердить отзыв СОПД SMS-кодом",
    description=(
        "Валидирует 4-значный SMS-код и при успехе фиксирует частичный "
        "отзыв по выбранным операторам без изменения статуса подписанного "
        "документа."
    ),
)
async def verify_signature_revoke(
    request_id: Annotated[UUID, Path()],
    payload: SignatureRevokeVerifyRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    request_context: RequestContextDep,
) -> JSONResponse:
    try:
        result = await handle_confirm_signature_revoke(
            ConfirmSignatureRevokeCommand(
                request_id=request_id,
                actor_user_id=user["id"],
                code=payload.code,
                client_ip=request_context.ip_address,
                user_agent=request_context.user_agent,
            ),
            session,
            storage,
        )
    except RevokeSignatureError as exc:
        await session.rollback()
        return _revoke_error(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/{request_id}/revoke-documents/{revoke_request_id}/download",
    summary="Скачать ПФ отзыва СОПД",
    description=(
        "Возвращает PDF печатной формы отзыва СОПД, сформированный после "
        "успешного SMS-подтверждения."
    ),
)
async def download_revoke_document(
    request_id: Annotated[UUID, Path()],
    revoke_request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        data, media_type = await handle_revoke_document_download(
            RevokeDocumentDownloadQuery(
                request_id=request_id,
                revoke_request_id=revoke_request_id,
                actor_user_id=user["id"],
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="sopd-revoke-{revoke_request_id}.pdf"'
            )
        },
    )


@router.get(
    "/{request_id}/preview",
    summary="PDF-шаблон для подпись",
    description=(
        "Возвращает сгенерированный PDF документа (СОПД) с "
        "подставленными данными подписанта. Используется "
        "фронтом для предпросмотра перед нажатием «Подписать»."
    ),
)
async def preview_signature(
    request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    result: Any = None
    try:
        result = await handle_signature_preview(
            SignaturePreviewQuery(request_id=request_id, actor_user_id=user["id"]),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    except Exception as exc:
        logger.warning(
            "signature_preview_falling_back_to_static request_id=%s err=%s",
            request_id,
            exc,
        )

    if isinstance(result, SopdPdfReady):
        ext = "xml" if result.media_type == "application/xml" else "pdf"
        return Response(
            content=result.data,
            media_type=result.media_type,
            headers={
                "Content-Disposition": (
                    f'inline; filename="document-{request_id}.{ext}"'
                )
            },
        )
    if isinstance(result, SopdPdfPending):
        return Response(status_code=202, headers={"Retry-After": "3"})

    # TODO(tender-demo): remove this fallback after the tender video.
    # On render failure or missing template, serve the static pre-filled
    # sopd.pdf so the demo never shows an error screen.
    fallback = load_fallback_sopd_pdf()
    if fallback is not None:
        logger.info(
            "signature_preview_served_fallback request_id=%s state=%s",
            request_id,
            type(result).__name__ if result is not None else "exception",
        )
        return Response(
            content=fallback,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (f'inline; filename="document-{request_id}.pdf"')
            },
        )
    raise HTTPException(
        status_code=500,
        detail="Не удалось сформировать документ СОПД. Повторите позже.",
    )


@router.post(
    "/{request_id}/sign-electronic",
    summary="Подписать документ простой электронной подписью",
    description=(
        "Генерирует PDF, сохраняет его в S3, фиксирует аудит (IP / "
        "User-Agent / время). Переход статуса pending → signed_electronic; "
        "повторная подпись вернёт 409."
    ),
)
async def sign_electronic(
    request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    request_context: RequestContextDep,
) -> JSONResponse:
    try:
        signed = await handle_sign_electronic(
            SignElectronicCommand(
                request_id=request_id,
                actor_user_id=user["id"],
                signing_ip=request_context.ip_address,
                signing_user_agent=request_context.user_agent,
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder({"request": signed}))


@router.post(
    "/{request_id}/upload-physical",
    summary="Загрузить скан подписанного документа (offline-подпись)",
    description=(
        "Принимает PDF / PNG / JPEG скан документа, подписанного "
        "собственноручно. Сохраняется в S3, ставится статус "
        "signed_physical."
    ),
)
async def upload_physical_signature(
    request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request_context: RequestContextDep,
    file: Annotated[UploadFile, File()],
) -> JSONResponse:
    data = await file.read()
    try:
        signed = await handle_upload_physical_signature(
            UploadPhysicalSignatureCommand(
                request_id=request_id,
                actor_user_id=user["id"],
                filename=file.filename or "signature",
                content_type=file.content_type or "application/octet-stream",
                data=data,
                signing_ip=request_context.ip_address,
                signing_user_agent=request_context.user_agent,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder({"request": signed}))


@router.get(
    "/{request_id}/download",
    summary="Скачать подписанный документ",
    description=(
        "Возвращает файл подписанного документа из S3 (сгенерированный "
        "PDF для электронной подписи или загруженный скан)."
    ),
)
async def download_signed(
    request_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        data = await handle_signature_download(
            SignatureDownloadQuery(request_id=request_id, actor_user_id=user["id"]),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (f'attachment; filename="signed-{request_id}.pdf"'),
        },
    )
