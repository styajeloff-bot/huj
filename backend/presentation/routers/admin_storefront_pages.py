"""Administrator routes for storefront constructor (Page Builder)."""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.storefront_pages import (
    CreateStorefrontPageCommand,
    ImportStorefrontPagePresetCommand,
    PublishStorefrontPageCommand,
    RestoreStorefrontPageRevisionCommand,
    SaveStorefrontPageDraftCommand,
    UpdateStorefrontPageMetadataCommand,
    UploadStorefrontBuilderMediaCommand,
    handle_create_storefront_page,
    handle_import_storefront_page_preset,
    handle_publish_storefront_page,
    handle_restore_storefront_page_revision,
    handle_save_storefront_page_draft,
    handle_update_storefront_page_metadata,
    handle_upload_storefront_builder_media,
)
from application.errors import ServiceError, domain_to_http
from application.queries.storefront_pages import (
    ExportStorefrontPagePresetQuery,
    GetStorefrontPageQuery,
    ListStorefrontPageRevisionsQuery,
    ListStorefrontPagesQuery,
    ListStorefrontTemplatesQuery,
    PreviewStorefrontPagePresetQuery,
    handle_export_storefront_page_preset,
    handle_get_storefront_page,
    handle_list_storefront_page_revisions,
    handle_list_storefront_pages,
    handle_list_storefront_templates,
    handle_preview_storefront_page_preset,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import STOREFRONTS_ADMIN
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_scopes
from presentation.schemas.storefront_pages import (
    StorefrontBuilderMediaUploadResponse,
    StorefrontPageCreateRequest,
    StorefrontPageDetailResponse,
    StorefrontPageDraftSaveRequest,
    StorefrontPageListResponse,
    StorefrontPagePublishRequest,
    StorefrontPageResource,
    StorefrontPageRevisionListResponse,
    StorefrontPageUpdateRequest,
    StorefrontPresetExportResponse,
    StorefrontPresetImportRequest,
    StorefrontPresetPreviewResponse,
    StorefrontTemplateListResponse,
)

router = APIRouter()
AdminUser = Annotated[dict[str, Any], Depends(require_scopes(STOREFRONTS_ADMIN))]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


def _http(exc: ServiceError | DomainError) -> HTTPException:
    service_error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    detail: Any = str(service_error)
    if service_error.code:
        detail = {"error": str(service_error), "code": service_error.code}
    return HTTPException(
        status_code=service_error.status_code,
        detail=detail,
    )


@router.get(
    "",
    response_model=StorefrontPageListResponse,
    summary="[admin] Список страниц витрины",
    description="Возвращает список всех сконструированных и системных страниц витрины.",
)
async def list_admin_storefront_pages(
    storefront_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        pages = await handle_list_storefront_pages(
            ListStorefrontPagesQuery(storefront_id=storefront_id),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder({"items": pages}))


@router.post(
    "",
    response_model=StorefrontPageResource,
    status_code=status.HTTP_201_CREATED,
    summary="[admin] Создать кастомную страницу витрины",
    description="Создает новую страницу в конструкторе с опциональным применением шаблона.",
)
async def create_admin_storefront_page(
    storefront_id: UUID,
    body: StorefrontPageCreateRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        page = await handle_create_storefront_page(
            CreateStorefrontPageCommand(
                storefront_id=storefront_id,
                title=body.title,
                page_key=body.page_key,
                slug=body.slug,
                template_code=body.template_code,
                user_id=UUID(str(user["id"])),
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    return JSONResponse(
        content=jsonable_encoder(page),
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/templates",
    response_model=StorefrontTemplateListResponse,
    summary="[admin] Библиотека готовых шаблонов витрин",
    description="Возвращает каталог доступных готовых шаблонов страниц.",
)
async def list_admin_storefront_templates(
    _storefront_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        templates = await handle_list_storefront_templates(
            ListStorefrontTemplatesQuery(),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder({"items": templates}))


@router.post(
    "/import-preview",
    response_model=StorefrontPresetPreviewResponse,
    summary="[admin] Предпросмотр и валидация импортируемого пресета",
    description="Валидирует структуру JSON-пресета, подсчитывает блоки и выявляет предупреждения.",
)
async def preview_admin_storefront_preset(
    _storefront_id: UUID,
    preset: dict[str, Any],
    _user: AdminUser,
) -> JSONResponse:
    try:
        preview = handle_preview_storefront_page_preset(
            PreviewStorefrontPagePresetQuery(preset_data=preset)
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(preview))


@router.post(
    "/builder/media",
    response_model=StorefrontBuilderMediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[admin] Загрузка медиа-файла для конструктора страниц",
    description="Загружает изображение (JPEG, PNG, WebP, SVG до 10 МБ) в S3 и возвращает URL.",
)
async def upload_admin_storefront_builder_media(
    storefront_id: UUID,
    file: UploadFile,
    _user: AdminUser,
    storage: Storage,
) -> JSONResponse:
    try:
        data = await file.read()
        res = await handle_upload_storefront_builder_media(
            UploadStorefrontBuilderMediaCommand(
                storefront_id=storefront_id,
                filename=file.filename or "media.png",
                content_type=file.content_type or "image/png",
                data=data,
            ),
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(
        content=jsonable_encoder(res),
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/{page_id}",
    response_model=StorefrontPageDetailResponse,
    summary="[admin] Детали страницы для Конструктора",
    description="Возвращает полное дерево макета, черновик, опубликованную версию и историю ревизий.",
)
async def get_admin_storefront_page(
    storefront_id: UUID,
    page_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        detail = await handle_get_storefront_page(
            GetStorefrontPageQuery(storefront_id=storefront_id, page_id=page_id),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(detail))


@router.patch(
    "/{page_id}",
    response_model=StorefrontPageResource,
    summary="[admin] Обновить метаданные страницы",
    description="Обновляет название и/или slug страницы витрины.",
)
async def update_admin_storefront_page(
    storefront_id: UUID,
    page_id: UUID,
    body: StorefrontPageUpdateRequest,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        page = await handle_update_storefront_page_metadata(
            UpdateStorefrontPageMetadataCommand(
                storefront_id=storefront_id,
                page_id=page_id,
                title=body.title,
                slug=body.slug,
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(page))


@router.put(
    "/{page_id}/draft",
    response_model=StorefrontPageResource,
    summary="[admin] Сохранить черновик страницы",
    description="Атомарно сохраняет черновик макета с защитой от конфликтов версий и созданием ревизии.",
)
async def save_admin_storefront_page_draft(
    storefront_id: UUID,
    page_id: UUID,
    body: StorefrontPageDraftSaveRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        page = await handle_save_storefront_page_draft(
            SaveStorefrontPageDraftCommand(
                storefront_id=storefront_id,
                page_id=page_id,
                expected_version=body.expected_version,
                draft_layout=body.draft_layout,
                summary=body.summary,
                user_id=UUID(str(user["id"])),
                title=body.title,
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(page))


@router.post(
    "/{page_id}/publish",
    response_model=StorefrontPageResource,
    summary="[admin] Опубликовать страницу на публичную витрину",
    description="Копирует черновик в опубликованный макет и увеличивает версию витрины для инвалидации кеша.",
)
async def publish_admin_storefront_page(
    storefront_id: UUID,
    page_id: UUID,
    body: StorefrontPagePublishRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        page = await handle_publish_storefront_page(
            PublishStorefrontPageCommand(
                storefront_id=storefront_id,
                page_id=page_id,
                expected_version=body.expected_version,
                user_id=UUID(str(user["id"])),
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(page))


@router.get(
    "/{page_id}/revisions",
    response_model=StorefrontPageRevisionListResponse,
    summary="[admin] История ревизий страницы",
    description="Возвращает список сохраненных снимков страницы с авторами и описаниями.",
)
async def list_admin_storefront_page_revisions(
    storefront_id: UUID,
    page_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        revisions = await handle_list_storefront_page_revisions(
            ListStorefrontPageRevisionsQuery(
                storefront_id=storefront_id, page_id=page_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder({"items": revisions}))


@router.post(
    "/{page_id}/revisions/{revision_id}/restore",
    response_model=StorefrontPageResource,
    summary="[admin] Восстановить черновик из ревизии",
    description="Восстанавливает состояние черновика из выбранного архивного снимка.",
)
async def restore_admin_storefront_page_revision(
    storefront_id: UUID,
    page_id: UUID,
    revision_id: UUID,
    body: StorefrontPagePublishRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        page = await handle_restore_storefront_page_revision(
            RestoreStorefrontPageRevisionCommand(
                storefront_id=storefront_id,
                page_id=page_id,
                revision_id=revision_id,
                expected_version=body.expected_version,
                user_id=UUID(str(user["id"])),
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(page))


@router.get(
    "/{page_id}/export",
    response_model=StorefrontPresetExportResponse,
    summary="[admin] Экспорт пресета страницы",
    description="Выгружает текущий макет страницы в структурированный JSON пресет для переноса.",
)
async def export_admin_storefront_page_preset(
    storefront_id: UUID,
    page_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
) -> Response:
    try:
        preset = await handle_export_storefront_page_preset(
            ExportStorefrontPagePresetQuery(
                storefront_id=storefront_id, page_id=page_id
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)

    filename = f"storefront-page-{preset['page_key']}-preset.json"
    content = json.dumps(jsonable_encoder(preset), ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{page_id}/import",
    response_model=StorefrontPageResource,
    summary="[admin] Применить импортированный пресет к черновику",
    description="Атомарно перезаписывает черновик страницы макетом из пресета.",
)
async def import_admin_storefront_page_preset(
    storefront_id: UUID,
    page_id: UUID,
    body: StorefrontPresetImportRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        page = await handle_import_storefront_page_preset(
            ImportStorefrontPagePresetCommand(
                storefront_id=storefront_id,
                page_id=page_id,
                preset_data=body.preset_data,
                expected_version=body.expected_version,
                summary=body.summary,
                user_id=UUID(str(user["id"])),
            ),
            session,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(page))


builder_media_router = APIRouter()


@builder_media_router.post(
    "/api/v1/admin/storefronts/{storefront_id}/builder/media",
    response_model=StorefrontBuilderMediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[admin] Загрузка медиа-файла для конструктора страниц (прямой путь)",
)
async def upload_admin_storefront_builder_media_alias(
    storefront_id: UUID,
    file: UploadFile,
    _user: AdminUser,
    storage: Storage,
) -> JSONResponse:
    return await upload_admin_storefront_builder_media(
        storefront_id=storefront_id,
        file=file,
        _user=_user,
        storage=storage,
    )

