"""Document endpoints — Phase 10 R4 unified REST surface.

Collapses the legacy Express-era footprint (6 upload paths, 3 download/
preview paths, 4 listing variants) to a resource-native shape:

* ``POST   /documents``                      — unified multipart upload
* ``GET    /documents?scope=user|company``   — unified listing
* ``GET    /documents/{id}/content``         — unified download/preview
* ``POST   /documents/{id}/reviews``         — review (renamed from leasing-review)
* ``PATCH  /documents/{id}/status``          — status change (was PUT)

Owner-scoped: route scopes constrain which roles may hit each endpoint;
ownership per-row is enforced by the ``Document`` aggregate in the
command handlers.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.documents import (
    ChangeDocumentStatusCommand,
    RestoreDocumentCommand,
    SoftDeleteDocumentCommand,
    UploadDocumentCommand,
    UploadDocumentForApplicationCommand,
    UploadDocumentVersionCommand,
    UploadedDocumentFile,
    handle_change_document_status,
    handle_restore_document,
    handle_soft_delete_document,
    handle_upload_document,
    handle_upload_document_for_application,
    handle_upload_document_version,
)
from application.document_recognition import (
    SessionFactory,
    default_session_factory,
)
from application.errors import ServiceError, domain_to_http
from application.queries.applications.resolve_leasing_company import (
    ResolveLeasingCompanyQuery,
    handle_resolve_leasing_company,
)
from application.queries.documents import (
    DownloadDocumentQuery,
    GetDocumentQuery,
    ListDocumentsQuery,
    ListDocumentTypesQuery,
    ListDocumentVersionsQuery,
    ListUserDocumentsEnhancedQuery,
    ListUserRequirementsQuery,
    handle_download_document,
    handle_get_document,
    handle_list_document_types,
    handle_list_document_versions,
    handle_list_documents,
    handle_list_user_documents_enhanced,
    handle_list_user_requirements,
)
from application.queries.sopd_cache import (
    SopdPdfPending,
    SopdPdfReady,
    resolve_sopd_pdf,
    wait_for_sopd_pdf,
)
from domain.errors import (
    DomainError,
)
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import (
    DOCUMENTS_READ,
    DOCUMENTS_REVIEW,
    DOCUMENTS_WRITE,
)
from infrastructure.services.object_storage import get_object_storage
from infrastructure.services.sopd_renderer import load_fallback_sopd_pdf
from presentation.dependencies.auth import require_scopes
from presentation.dependencies.leasing_context import get_leasing_context
from presentation.dependencies.notification_company_context import (
    get_notification_company_context,
)
from presentation.dependencies.notification_database import get_db
from presentation.schemas.documents import (
    ChangeDocumentStatusRequest,
    ChangeDocumentStatusResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentTypesResponse,
    DocumentVersionsResponse,
    RequirementsByLcRequest,
    RestoreDocumentResponse,
    SoftDeleteDocumentResponse,
    UploadDocumentsResponse,
    UserRequirementsResponse,
)

logger = logging.getLogger("carcraft-backend")

router = APIRouter()

_read_access = require_scopes(DOCUMENTS_READ)
_write_access = require_scopes(DOCUMENTS_WRITE)
_review_access = require_scopes(DOCUMENTS_REVIEW)

# 50 MB hard ceiling — per-document-type limits live on document_types.
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# Matches the former Express multer limit (``upload.array('files', 20)``).
_MAX_MULTI_UPLOAD_FILES = 20
# A response to one explicit document request is one atomic package.
_MAX_REQUEST_RESPONSE_FILES = 10

# The .docx is the editable source; per-request PDFs are rendered by the
# taskiq worker (see application/tasks/sopd.py) and cached in S3 keyed
# by (template_hash, context_hash). The "blank" template is the same
# pipeline with an empty context — warmed up at startup.
_SOPD_DOWNLOAD_FILENAME = "СОПД.pdf"
_SOPD_RENDER_RETRY_AFTER_SECONDS = 3
# If the render worker takes longer than this on a cache miss, fall
# through to the static fallback PDF rather than bouncing the client
# back with a 202 «Документ готовится…». TODO(tender-demo): revisit
# after the tender video — for real prod we might want to keep the 202
# behaviour and show a proper progress UI.
_SOPD_DOWNLOAD_WAIT_SECONDS = 3.0


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _resolve_lc_id(
    session: AsyncSession, user: dict[str, Any]
) -> UUID | None:
    return cast(
        "UUID | None",
        await handle_resolve_leasing_company(
        ResolveLeasingCompanyQuery(
            company_id=user.get("company_id"),
            role=str(user.get("role") or ""),
        ),
        session,
        ),
    )


# ---------------------------------------------------------------------------
# Static SOPD download (kept — non-resource template file)
# ---------------------------------------------------------------------------


@router.get(
    "/sopd/download",
    summary="Скачать шаблон СОПД",
    description=(
        "Возвращает PDF шаблона Согласия на обработку персональных "
        "данных. Шаблон .md заполняется через Jinja2 и "
        "конвертируется в PDF taskiq-воркером (WeasyPrint); результат кэшируется в "
        "S3 по ключу `(template_hash, context_hash)`. Если PDF ещё не "
        "готов — отвечает `202` c `Retry-After` и ставит задачу рендера "
        "в очередь. Без паспортных данных (пустой контекст) возвращается "
        "единый «пустой» экземпляр для всех пользователей."
    ),
    responses={
        200: {"content": {"application/pdf": {}}},
        202: {
            "description": (
                "PDF ещё не отрендерен; повторите запрос через "
                "Retry-After секунд"
            )
        },
        404: {"description": "Шаблон .md не установлен в образе"},
    },
    dependencies=[Depends(_read_access)],
)
async def download_sopd(
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        result = await resolve_sopd_pdf(
            session=session, storage=storage, context={}
        )
        if isinstance(result, SopdPdfReady):
            return Response(
                content=result.data,
                media_type="application/pdf",
                headers=_disposition_headers(
                    _SOPD_DOWNLOAD_FILENAME, disposition="attachment"
                ),
            )
        if isinstance(result, SopdPdfPending):
            pdf_bytes = await wait_for_sopd_pdf(
                session=session,
                storage=storage,
                context={},
                timeout_seconds=_SOPD_DOWNLOAD_WAIT_SECONDS,
            )
            if pdf_bytes is not None:
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers=_disposition_headers(
                        _SOPD_DOWNLOAD_FILENAME, disposition="attachment"
                    ),
                )
    except Exception as exc:
        logger.warning("sopd_download_falling_back_to_static: %s", exc)
        result = None

    # TODO(tender-demo): remove this fallback after the tender video.
    # Any render failure or missing template serves the static sopd.pdf
    # instead of a 4xx/5xx so the demo never shows an error screen.
    fallback = load_fallback_sopd_pdf()
    if fallback is not None:
        logger.info(
            "sopd_download_served_fallback state=%s",
            type(result).__name__ if result is not None else "exception",
        )
        return Response(
            content=fallback,
            media_type="application/pdf",
            headers=_disposition_headers(
                _SOPD_DOWNLOAD_FILENAME, disposition="attachment"
            ),
        )
    raise HTTPException(status_code=404, detail="Шаблон СОПД не найден")


# ---------------------------------------------------------------------------
# Reference data — types / requirements
# ---------------------------------------------------------------------------


@router.get(
    "/types",
    response_model=DocumentTypesResponse,
    summary="Справочник типов документов",
    description=(
        "Возвращает весь список `document_types` с параметрами "
        "(допустимые MIME, максимальный размер, auto_approve). Использу"
        "ется фронтом для рендеринга селектора типа при загрузке."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_document_types_endpoint(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_document_types(
        ListDocumentTypesQuery(), session
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/requirements",
    response_model=UserRequirementsResponse,
    summary="Требования по документам для пользователя",
    description=(
        "Агрегированный список требований по документам из всех ЛК, "
        "встречающихся в заявках пользователя. Каждое требование раз"
        "мечено `existing_document_id` / `existing_status` если у "
        "компании уже есть загруженный документ такого типа."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_user_requirements_endpoint(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_user_requirements(
        ListUserRequirementsQuery(
            actor_user_id=user["id"],
            actor_role=str(user.get("role") or ""),
            actor_company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/requirements",
    response_model=UserRequirementsResponse,
    summary="Требования по документам по заданным ЛК",
    description=(
        "Возвращает агрегированный список требований по документам для "
        "явно переданного набора `leasing_company_ids`. Полезно когда "
        "пользователь ещё не создал заявку, но хочет увидеть, какие "
        "документы понадобятся при выборе конкретных ЛК."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_user_requirements_by_lc_endpoint(
    body: RequirementsByLcRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_user_requirements(
        ListUserRequirementsQuery(
            actor_user_id=user["id"],
            actor_role=str(user.get("role") or ""),
            actor_company_id=user.get("company_id"),
            leasing_company_ids=list(body.leasing_company_ids),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Collection — unified listing with ?scope / ?enhanced
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="Документы пользователя / компании",
    description=(
        "Унифицированная выдача документов. Параметры:\n"
        "* `scope=user|company` — scope выборки (оба эквивалентны и "
        "возвращают документы company_id текущего пользователя; "
        "«user» оставлен как semantic alias);\n"
        "* `enhanced=true` — расширенная форма с агрегированным "
        "списком `requirements` (тип ответа — `UserDocumentsEnhancedResponse`).\n"
        "Возвращаются только текущие версии документов."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_documents(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[
        Literal["user", "company"], Query(description="Scope выборки.")
    ] = "company",
    enhanced: Annotated[
        bool,
        Query(description="Вернуть enhanced-форму с requirements."),
    ] = False,
) -> JSONResponse:
    # `scope` is accepted for REST symmetry; both "user" and "company"
    # resolve to the company scope of the current user (они эквивалентны
    # в текущей модели).
    _ = scope
    if enhanced:
        enhanced_result = await handle_list_user_documents_enhanced(
            ListUserDocumentsEnhancedQuery(
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
        return JSONResponse(content=jsonable_encoder(enhanced_result))
    result = await handle_list_documents(
        ListDocumentsQuery(
            actor_user_id=user["id"],
            actor_role=str(user.get("role") or ""),
            actor_company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Single-document read
# ---------------------------------------------------------------------------


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Получить документ по id",
    description=(
        "Доступно владельцу документа (по company_id), сотруднику и ЛК "
        "если документ привязан к заявке этой ЛК."
    ),
    dependencies=[Depends(_read_access)],
)
async def get_document(
    document_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_get_document(
            GetDocumentQuery(
                document_id=document_id,
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


# ---------------------------------------------------------------------------
# Unified upload (replaces 6 legacy upload endpoints)
# ---------------------------------------------------------------------------


async def _read_upload(file: UploadFile) -> UploadedDocumentFile:
    payload = await file.read()
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Файл {file.filename or 'file'} превышает допустимый размер"
            ),
        )
    return UploadedDocumentFile(
        filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        data=payload,
    )


@router.post(
    "/",
    status_code=201,
    response_model=UploadDocumentsResponse,
    summary="Загрузить один или несколько документов",
    description=(
        "Единая ручка загрузки — multipart/form-data. Поля:\n"
        "* `files` — один или несколько файлов (до 20);\n"
        "* `document_type` — type_code для загрузки без ocr=true "
        "и без parent_document_id. Требуется когда файл один;\n"
        "* `document_types` — JSON- или comma-separated массив type_code'ов "
        "той же длины, что и `files` (альтернатива одиночному `document_type`);\n"
        "* `application_id` — привязать документ(ы) к заявке через "
        "`document_applications` M2M (upload-for-application);\n"
        "* `document_request_id` — ответить на запрос с комплектом до 10 файлов; "
        "требует `application_id`, UUID-заголовок `Idempotency-Key`; "
        "тип берётся из сохранённого запроса; для разрешённых типов ТЗ №41 файл необязателен. `user_titles` — JSON-массив названий файлов. `form_data` — JSON-строка только "
        "для формы этого запроса;\n"
        "* `parent_document_id` — если указан, создаётся новая версия "
        "документа (version-flow). Допустим только один файл, "
        "`document_type` / `application_id` игнорируются;\n"
        "* `ocr` — форсирует распознавание документа (fire-and-forget).\n\n"
        "Ошибки: если переданы оба `parent_document_id` и "
        "`application_id` — 422. Тип документа обязателен при обычной "
        "загрузке и при upload-for-application."
    ),
    dependencies=[Depends(_write_access)],
)
async def upload_documents(
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    files: Annotated[list[UploadFile] | None, File()] = None,
    document_type: Annotated[str | None, Form()] = None,
    document_types: Annotated[str | None, Form()] = None,
    application_id: Annotated[uuid.UUID | None, Form()] = None,
    document_request_id: Annotated[UUID | None, Form()] = None,
    parent_document_id: Annotated[uuid.UUID | None, Form()] = None,
    ocr: Annotated[bool, Form()] = False,
    period_label: Annotated[str | None, Form()] = None,
    period_labels: Annotated[str | None, Form()] = None,
    form_data: Annotated[str | None, Form(description="JSON-объект данных формы запрошенного документа.")] = None,
    idempotency_key: Annotated[UUID | None, Header(alias="Idempotency-Key")] = None,
    user_titles: Annotated[str | None, Form(description="JSON-массив пользовательских названий файлов ответа.")] = None,
) -> JSONResponse:
    files = files or []
    parsed_user_titles = _parse_user_titles(user_titles, document_request_id, len(files))
    _validate_upload_request(
        files=files,
        application_id=application_id,
        document_request_id=document_request_id,
        parent_document_id=parent_document_id,
        idempotency_key=idempotency_key,
    )
    parsed_form_data = _parse_request_form_data(form_data, document_request_id)
    types_list = (
        [""]
        if document_request_id is not None
        else _resolve_document_types(
            files_count=len(files),
            document_type=document_type,
            document_types=document_types,
            parent_flow=parent_document_id is not None,
        )
    )
    period_list = _resolve_period_labels(
        files_count=len(files),
        period_label=period_label,
        period_labels=period_labels,
    )
    uploaded_files = [await _read_upload(f) for f in files]

    # ``ocr=true`` wires the fire-and-forget recognition pipeline by passing a
    # session factory to the upload commands — the commands themselves
    # decide whether the document_type actually supports recognition.
    factory: SessionFactory | None = (
        default_session_factory() if ocr else None
    )

    uploaded_storage_keys: list[str] = []
    try:
        documents = await _dispatch_upload(
            user=user,
            session=session,
            storage=storage,
            uploaded_files=uploaded_files,
            types_list=types_list,
            parent_document_id=parent_document_id,
            application_id=application_id,
            document_request_id=document_request_id,
            factory=factory,
            period_list=period_list,
            form_data=parsed_form_data,
            user_titles=parsed_user_titles,
            idempotency_key=str(idempotency_key) if idempotency_key is not None else None,
            uploaded_storage_keys=uploaded_storage_keys,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        if document_request_id is not None:
            await _delete_uploaded_objects_quietly(storage, uploaded_storage_keys)
        raise _http(exc)
    except Exception:
        if document_request_id is not None:
            await _delete_uploaded_objects_quietly(storage, uploaded_storage_keys)
        raise
    payload: dict[str, Any] = {
        "documents": documents,
        "total": len(documents),
    }
    if application_id is not None:
        payload["application_id"] = application_id
    return JSONResponse(
        content=jsonable_encoder(payload),
        status_code=201,
    )


def _validate_upload_request(
    *,
    files: list[UploadFile],
    application_id: uuid.UUID | None,
    document_request_id: UUID | None,
    parent_document_id: UUID | None,
    idempotency_key: UUID | None,
) -> None:
    if not files and document_request_id is None:
        raise HTTPException(status_code=400, detail="Файлы не загружены")
    if len(files) > _MAX_MULTI_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"За один запрос можно загрузить не более "
                f"{_MAX_MULTI_UPLOAD_FILES} файлов"
            ),
        )
    if parent_document_id is not None and application_id is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Поля parent_document_id и application_id взаимно исключают "
                "друг друга"
            ),
        )
    if document_request_id is not None:
        if application_id is None:
            raise HTTPException(
                status_code=422,
                detail="Для document_request_id необходим application_id",
            )
        if len(files) > _MAX_REQUEST_RESPONSE_FILES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Для document_request_id можно загрузить от 1 до "
                    f"{_MAX_REQUEST_RESPONSE_FILES} файлов"
                ),
            )
        if idempotency_key is None:
            raise HTTPException(status_code=422, detail="Для document_request_id обязателен UUID Idempotency-Key")


def _parse_request_form_data(raw: str | None, document_request_id: UUID | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if document_request_id is None:
        raise HTTPException(status_code=422, detail="form_data допустимо только для document_request_id")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="form_data должен быть JSON-объектом") from None
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="form_data должен быть JSON-объектом")
    return value


async def _delete_uploaded_objects_quietly(storage: ObjectStorage, keys: list[str]) -> None:
    """Compensate only objects created by this request; preserve its error."""
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logger.exception("failed to compensate uploaded request response key=%s", key)


async def _dispatch_upload(
    *,
    user: dict[str, Any],
    session: AsyncSession,
    storage: ObjectStorage,
    uploaded_files: list[UploadedDocumentFile],
    types_list: list[str],
    parent_document_id: UUID | None,
    application_id: uuid.UUID | None,
    document_request_id: UUID | None,
    factory: SessionFactory | None,
    period_list: list[str | None],
    form_data: dict[str, Any] | None,
    user_titles: list[str] | None,
    idempotency_key: str | None,
    uploaded_storage_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Route the upload to the right per-file handler based on flow flags."""
    if parent_document_id is not None:
        return await _upload_version_flow(
            user=user,
            session=session,
            storage=storage,
            upload=uploaded_files[0],
            parent_document_id=parent_document_id,
        )
    if application_id is not None:
        return await _upload_for_application_flow(
            user=user,
            session=session,
            storage=storage,
            uploaded_files=uploaded_files,
            types_list=types_list,
            application_id=application_id,
            document_request_id=document_request_id,
            factory=factory,
            period_list=period_list,
            form_data=form_data,
            user_titles=user_titles,
            idempotency_key=idempotency_key,
            uploaded_storage_keys=uploaded_storage_keys,
        )
    return await _upload_plain_flow(
        user=user,
        session=session,
        storage=storage,
        uploaded_files=uploaded_files,
        types_list=types_list,
        factory=factory,
    )


async def _upload_version_flow(
    *,
    user: dict[str, Any],
    session: AsyncSession,
    storage: ObjectStorage,
    upload: UploadedDocumentFile,
    parent_document_id: UUID,
) -> list[dict[str, Any]]:
    result = await handle_upload_document_version(
        UploadDocumentVersionCommand(
            actor_user_id=user["id"],
            actor_company_id=user.get("company_id"),
            parent_document_id=parent_document_id,
            file_filename=upload.filename,
            file_content_type=upload.content_type,
            file_data=upload.data,
        ),
        session,
        storage,
    )
    doc = result.get("document")
    return [doc] if doc is not None else []


async def _upload_for_application_flow(
    *,
    user: dict[str, Any],
    session: AsyncSession,
    storage: ObjectStorage,
    uploaded_files: list[UploadedDocumentFile],
    types_list: list[str],
    application_id: uuid.UUID,
    document_request_id: UUID | None,
    factory: SessionFactory | None,
    period_list: list[str | None],
    form_data: dict[str, Any] | None,
    user_titles: list[str] | None,
    idempotency_key: str | None,
    uploaded_storage_keys: list[str] | None,
) -> list[dict[str, Any]]:
    if document_request_id is not None:
        result = await handle_upload_document_for_application(
            UploadDocumentForApplicationCommand(
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
                actor_role=str(user.get("role") or ""),
                application_id=application_id,
                document_type=None,
                file=None,
                files=uploaded_files,
                document_request_id=document_request_id,
                form_data=form_data,
                user_titles=user_titles,
                idempotency_key=idempotency_key,
                uploaded_storage_keys=uploaded_storage_keys,
            ),
            session,
            storage,
            session_factory=factory,
        )
        return list(result.get("documents") or [])

    documents: list[dict[str, Any]] = []
    for upload, dtype, period in zip(
        uploaded_files, types_list, period_list, strict=True
    ):
        result = await handle_upload_document_for_application(
            UploadDocumentForApplicationCommand(
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
                actor_role=str(user.get("role") or ""),
                application_id=application_id,
                document_type=dtype,
                file=upload,
                period_label=period,
                document_request_id=document_request_id,
                form_data=form_data,
                user_titles=user_titles,
                idempotency_key=idempotency_key,
                uploaded_storage_keys=uploaded_storage_keys,
            ),
            session,
            storage,
            session_factory=factory,
        )
        doc = result.get("document")
        if doc is not None:
            documents.append(doc)
    return documents


async def _upload_plain_flow(
    *,
    user: dict[str, Any],
    session: AsyncSession,
    storage: ObjectStorage,
    uploaded_files: list[UploadedDocumentFile],
    types_list: list[str],
    factory: SessionFactory | None,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for upload, dtype in zip(uploaded_files, types_list, strict=True):
        result = await handle_upload_document(
            UploadDocumentCommand(
                actor_user_id=user["id"],
                actor_company_id=user.get("company_id"),
                document_type=dtype,
                file=upload,
            ),
            session,
            storage,
            session_factory=factory,
        )
        doc = result.get("document")
        if doc is not None:
            documents.append(doc)
    return documents


def _resolve_period_labels(
    *,
    files_count: int,
    period_label: str | None,
    period_labels: str | None,
) -> list[str | None]:
    """Materialise per-file ``period_label`` strings (NULL allowed).

    Mirrors the document-types resolver but every value is optional. The
    array variant must align 1:1 with ``files`` when provided.
    """
    if period_labels:
        parsed = _parse_types_field(period_labels)
        if len(parsed) != files_count:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Количество значений period_labels не совпадает с "
                    "количеством файлов"
                ),
            )
        return [(p or None) for p in parsed]
    if period_label is not None:
        return [period_label or None] * files_count
    return [None] * files_count


def _resolve_document_types(
    *,
    files_count: int,
    document_type: str | None,
    document_types: str | None,
    parent_flow: bool,
) -> list[str]:
    """Materialise the list of type codes for each uploaded file."""
    if parent_flow:
        # Version-flow inherits the parent's document_type.
        return [""]
    if document_types:
        parsed = _parse_types_field(document_types)
        if len(parsed) != files_count:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Количество значений document_types не совпадает с "
                    "количеством файлов"
                ),
            )
        return parsed
    if document_type is None:
        raise HTTPException(
            status_code=422,
            detail="Поле document_type или document_types обязательно",
        )
    return [document_type] * files_count


def _parse_types_field(raw: str) -> list[str]:
    import json as _json

    trimmed = raw.strip()
    if not trimmed:
        return []
    if trimmed.startswith("["):
        try:
            parsed = _json.loads(trimmed)
        except _json.JSONDecodeError as err:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Поле document_types должно быть корректным JSON-массивом"
                    " или списком через запятую"
                ),
            ) from err
        if not isinstance(parsed, list):
            raise HTTPException(
                status_code=422,
                detail="Поле document_types должно быть JSON-массивом",
            )
        return [str(item) for item in parsed]
    return [part.strip() for part in trimmed.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@router.get(
    "/{document_id}/versions",
    response_model=DocumentVersionsResponse,
    summary="Версии документа",
    description=(
        "Возвращает все версии документа (root + дочерние записи). "
        "Доступ — как у `GET /{id}`."
    ),
    dependencies=[Depends(_read_access)],
)
async def list_versions_endpoint(
    document_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    lc_id = await _resolve_lc_id(session, user)
    try:
        result = await handle_list_document_versions(
            ListDocumentVersionsQuery(
                document_id=document_id,
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


# ---------------------------------------------------------------------------
# Status change — PATCH (was PUT)
# ---------------------------------------------------------------------------


@router.patch(
    "/{document_id}/status",
    response_model=ChangeDocumentStatusResponse,
    summary="Изменить статус документа",
    description=(
        "Доступно только сотрудникам Carcraft. Переходы валидируются "
        "через aggregate root: pending → approved | rejected | "
        "revision_required."
    ),
    dependencies=[Depends(_review_access)],
)
async def change_status(
    document_id: UUID,
    body: ChangeDocumentStatusRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_change_document_status(
            ChangeDocumentStatusCommand(
                document_id=document_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                new_status=body.status,
                comments=body.comments,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Reviews (renamed from leasing-review)
# ---------------------------------------------------------------------------


@router.post(
    "/{document_id}/reviews",
    response_model=ChangeDocumentStatusResponse,
    summary="Создать запись ревью документа",
    description=(
        "Nested коллекция ревью — делегирует в `change_document_status` "
        "handler и возвращает обновлённый документ. Замена старого "
        "маршрута `POST /{id}/leasing-review`. Доступ — только "
        "carcraft_employee / leasing_company ревьюерам."
    ),
    dependencies=[Depends(_review_access)],
)
async def create_document_review(
    document_id: UUID,
    body: ChangeDocumentStatusRequest,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_change_document_status(
            ChangeDocumentStatusCommand(
                document_id=document_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                new_status=body.status,
                comments=body.comments,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Soft-delete / restore
# ---------------------------------------------------------------------------


@router.delete(
    "/{document_id}",
    response_model=SoftDeleteDocumentResponse,
    summary="Удалить документ (soft-delete)",
    description=(
        "Мягкое удаление: помечает текущую версию как "
        "`is_current_version=False` и пишет запись в истории. "
        "Доступно владельцу документа и сотруднику Carcraft."
    ),
    dependencies=[Depends(_write_access)],
)
async def delete_document(
    document_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_soft_delete_document(
            SoftDeleteDocumentCommand(
                document_id=document_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/{document_id}/restore",
    response_model=RestoreDocumentResponse,
    summary="Восстановить удалённый документ",
    description=(
        "Возвращает документ к виду `is_current_version=True`. Если в "
        "цепочке уже есть другая «текущая» версия — она будет отмечена "
        "неактуальной. Доступно владельцу и сотруднику Carcraft."
    ),
    dependencies=[Depends(_write_access)],
)
async def restore_document_endpoint(
    document_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_notification_company_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_restore_document(
            RestoreDocumentCommand(
                document_id=document_id,
                actor_user_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Unified content (replaces /download, /preview, /download/{id})
# ---------------------------------------------------------------------------


def _disposition_headers(
    filename: str, *, disposition: str
) -> dict[str, str]:
    # HTTP headers are transported as latin-1, so non-ASCII filenames
    # (e.g. «СОПД.pdf») must be sent via RFC 5987's ``filename*=UTF-8''…``
    # form. We also keep a sanitised ASCII ``filename="…"`` for
    # ancient clients that don't understand the extended form.
    from urllib.parse import quote

    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    encoded = quote(filename, safe="")
    return {
        "Content-Disposition": (
            f'{disposition}; filename="{ascii_fallback}"; '
            f"filename*=UTF-8''{encoded}"
        ),
        "X-Content-Type-Options": "nosniff",
    }


@router.get(
    "/{document_id}/content",
    summary="Скачать или предпросмотреть содержимое документа",
    description=(
        "Возвращает бинарное содержимое документа. Параметр "
        "`disposition=attachment` (по умолчанию) — заголовок "
        "`Content-Disposition: attachment`; `inline` — подходит для "
        "предпросмотра в браузере. Авторизация — как у `GET /{id}`."
    ),
    responses={
        200: {"content": {"application/octet-stream": {}}},
        403: {"description": "Нет доступа к документу"},
        404: {"description": "Документ не найден"},
    },
    dependencies=[Depends(_read_access)],
)
async def get_document_content(
    document_id: UUID,
    user: Annotated[dict[str, Any], Depends(get_leasing_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    disposition: Annotated[
        Literal["attachment", "inline"],
        Query(description="Content-Disposition — attachment | inline."),
    ] = "attachment",
) -> Response:
    lc_id = await _resolve_lc_id(session, user)
    try:
        doc = await handle_download_document(
            DownloadDocumentQuery(
                document_id=document_id,
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
    return Response(
        content=doc.data,
        media_type=doc.content_type,
        headers=_disposition_headers(
            doc.filename, disposition=disposition
        ),
    )


def _parse_user_titles(raw: str | None, request_id: UUID | None, count: int) -> list[str] | None:
    if raw is None:
        return None
    if request_id is None:
        raise HTTPException(status_code=422, detail="user_titles допустимо только для ответа на запрос")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="user_titles должен быть JSON-массивом строк") from None
    if (
        not isinstance(value, list) or len(value) != count
        or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 255 for item in value)
    ):
        raise HTTPException(status_code=422, detail="Укажите название из 1–255 символов для каждого файла")
    return [item.strip() for item in value]
