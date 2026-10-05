"""Public storefront context and administrator configuration routes."""

from __future__ import annotations

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.storefront_transfer import (
    ImportStorefrontSettingsCommand,
    handle_import_storefront_settings,
)
from application.commands.storefronts import (
    ClearStorefrontLogoCommand,
    CreateStorefrontCommand,
    UpdateStorefrontCommand,
    UploadStorefrontLogoCommand,
    handle_clear_storefront_logo,
    handle_create_storefront,
    handle_update_storefront,
    handle_upload_storefront_logo,
)
from application.errors import ServiceError, domain_to_http
from application.queries.storefront_transfer import (
    handle_export_storefront_settings,
    handle_preview_storefront_settings,
)
from application.queries.storefronts import (
    AdminStorefrontRecord,
    GetStorefrontLogoQuery,
    GetStorefrontQuery,
    ListStorefrontsQuery,
    PublicStorefrontRecord,
    ResolveStorefrontQuery,
    handle_get_public_storefront,
    handle_get_storefront,
    handle_get_storefront_logo,
    handle_list_storefronts,
    handle_resolve_storefront,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import STOREFRONTS_ADMIN
from domain.storefront_transfer import MAX_STOREFRONT_TRANSFER_BYTES
from domain.storefronts import (
    MAX_STOREFRONT_LOGO_BYTES,
    CatalogScope,
    PublicUIConfig,
    StorefrontAppearancePatch,
)
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_roles, require_scopes
from presentation.schemas.storefronts import (
    StorefrontAdminResponse,
    StorefrontCreateRequest,
    StorefrontListResponse,
    StorefrontPatchRequest,
    StorefrontPublicResponse,
    StorefrontSettingsExportResponse,
    StorefrontSettingsImportResponse,
    StorefrontSettingsPreviewResponse,
)

router = APIRouter()
AdminUser = Annotated[dict[str, Any], Depends(require_scopes(STOREFRONTS_ADMIN))]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
_transfer_admin = require_roles("carcraft_employee")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    service_error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    return HTTPException(
        status_code=service_error.status_code,
        detail=str(service_error),
    )


def _logo_url(scope: CatalogScope, has_logo: bool) -> str | None:
    if not has_logo:
        return None
    if scope.is_default:
        return "/api/v1/storefront/logo"
    return f"/api/v1/storefronts/{scope.slug}/logo"


def _effective_logo_url(scope: CatalogScope, has_logo: bool) -> str:
    return _logo_url(scope, has_logo) or "/images/logo.png"


def _public_payload(public: PublicStorefrontRecord) -> dict[str, Any]:
    scope = public["scope"]
    appearance = public["appearance"]
    font_id = appearance["font_id"]
    return {
        "id": scope.id,
        "slug": scope.slug,
        "version": scope.version,
        "is_default": scope.is_default,
        "logo_url": _effective_logo_url(scope, public["logo_storage_key"] is not None),
        "contact_email": public["contact_email"],
        "contact_phone": public["contact_phone"],
        "contact_phone_href": public["contact_phone_href"],
        "is_active": public["is_active"],
        "public_ui": public["public_ui"],
        "appearance": {
            "colors": appearance["colors"],
            "border_radius": appearance["border_radius"],
            "color_overrides": appearance["color_overrides"],
            "font": {
                "id": font_id,
                "family": public["font_family"],
                "url": (
                    f"/api/v1/storefront-fonts/{font_id}/content"
                    if font_id is not None
                    else None
                ),
            },
        },
    }


def _admin_payload(record: AdminStorefrontRecord) -> dict[str, Any]:
    scope = CatalogScope(
        id=record["id"],
        slug=record["slug"],
        version=record["version"],
        is_default=record["is_default"],
    )
    return {
        "id": record["id"],
        "slug": record["slug"],
        "version": record["version"],
        "is_default": record["is_default"],
        "is_active": record["is_active"],
        "warehouse_ids": record["warehouse_ids"],
        "contact_email": record["contact_email"],
        "contact_phone": record["contact_phone"],
        "effective_contact_email": record["effective_contact_email"],
        "effective_contact_phone": record["effective_contact_phone"],
        "effective_contact_phone_href": record["effective_contact_phone_href"],
        "effective_logo_url": _effective_logo_url(scope, record["has_effective_logo"]),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "logo_url": _logo_url(scope, record["logo_storage_key"] is not None),
        "public_ui": record["public_ui"],
        "appearance": record["appearance"],
    }


async def _resolve_public(
    slug: str | None, session: AsyncSession
) -> PublicStorefrontRecord:
    return await handle_get_public_storefront(ResolveStorefrontQuery(slug), session)


@router.get(
    "/api/v1/storefront",
    response_model=StorefrontPublicResponse,
    summary="Контекст основной витрины",
    description="Возвращает публичную идентичность и брендинг основной витрины.",
)
async def get_default_storefront_context(session: DatabaseSession) -> JSONResponse:
    try:
        public = await _resolve_public(None, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(_public_payload(public)))


@router.get(
    "/api/v1/storefronts/{storefront_slug}",
    response_model=StorefrontPublicResponse,
    summary="Контекст дочерней витрины",
    description="Возвращает только активную дочернюю витрину по её URL-slug.",
)
async def get_storefront_context(
    storefront_slug: str, session: DatabaseSession
) -> JSONResponse:
    try:
        public = await _resolve_public(storefront_slug, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(_public_payload(public)))


async def _logo_response(
    slug: str | None,
    session: AsyncSession,
    storage: ObjectStorage,
) -> Response:
    scope = await handle_resolve_storefront(ResolveStorefrontQuery(slug), session)
    stored = await handle_get_storefront_logo(
        GetStorefrontLogoQuery(scope.id), session, storage
    )
    return Response(
        content=stored.data,
        media_type=stored.content_type,
        headers={
            "Cache-Control": "public, max-age=0, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/api/v1/storefront/logo",
    summary="Логотип основной витрины",
    description="Возвращает проверенный оригинал растрового логотипа без преобразования.",
    responses={200: {"content": {"image/*": {}}}, 404: {"description": "Нет логотипа"}},
)
async def get_default_storefront_logo(
    session: DatabaseSession, storage: Storage
) -> Response:
    try:
        return await _logo_response(None, session, storage)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)


@router.get(
    "/api/v1/storefronts/{storefront_slug}/logo",
    summary="Логотип дочерней витрины",
    description="Возвращает проверенный оригинал растрового логотипа без преобразования.",
    responses={200: {"content": {"image/*": {}}}, 404: {"description": "Нет логотипа"}},
)
async def get_storefront_logo(
    storefront_slug: str, session: DatabaseSession, storage: Storage
) -> Response:
    try:
        return await _logo_response(storefront_slug, session, storage)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)


@router.get(
    "/api/v1/admin/storefronts",
    response_model=StorefrontListResponse,
    summary="[admin] Список витрин",
    description="Возвращает основную и дочерние витрины вместе со складами.",
)
async def list_admin_storefronts(
    _user: AdminUser, session: DatabaseSession
) -> JSONResponse:
    result = await handle_list_storefronts(ListStorefrontsQuery(), session)
    return JSONResponse(
        content=jsonable_encoder(
            {"items": [_admin_payload(item) for item in result["items"]]}
        )
    )


@router.post(
    "/api/v1/admin/storefronts",
    response_model=StorefrontAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[admin] Создать витрину",
    description="Создаёт уникальный URL-slug и привязывает активные склады.",
)
async def create_admin_storefront(
    body: StorefrontCreateRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        created = await handle_create_storefront(
            CreateStorefrontCommand(
                slug=body.slug,
                warehouse_ids=tuple(body.warehouse_ids),
                created_by=UUID(str(user["id"])),
                is_active=body.is_active,
                contact_email=body.contact_email,
                contact_phone=body.contact_phone,
            ),
            session,
        )
        record = await handle_get_storefront(GetStorefrontQuery(created["id"]), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(_admin_payload(record)),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/api/v1/admin/storefronts/{record['id']}"},
    )


@router.get(
    "/api/v1/admin/storefronts/{storefront_id}",
    response_model=StorefrontAdminResponse,
    summary="[admin] Получить витрину",
    description="Возвращает параметры витрины по её идентификатору.",
)
async def get_admin_storefront(
    storefront_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        record = await handle_get_storefront(GetStorefrontQuery(storefront_id), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(_admin_payload(record)))


@router.patch(
    "/api/v1/admin/storefronts/{storefront_id}",
    response_model=StorefrontAdminResponse,
    summary="[admin] Изменить витрину",
    description=(
        "Обновляет URL, активность, полный набор складов или публичную UI-конфигурацию "
        "витрины. Выбор главной страницы атомарно включает её видимость."
    ),
)
async def patch_admin_storefront(
    storefront_id: UUID,
    body: StorefrontPatchRequest,
    user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        updated = await handle_update_storefront(
            UpdateStorefrontCommand(
                storefront_id=storefront_id,
                updated_by=UUID(str(user["id"])),
                slug=body.slug,
                warehouse_ids=(
                    tuple(body.warehouse_ids)
                    if body.warehouse_ids is not None
                    else None
                ),
                is_active=body.is_active,
                contact_email=body.contact_email,
                contact_phone=body.contact_phone,
                update_contact_email="contact_email" in body.model_fields_set,
                update_contact_phone="contact_phone" in body.model_fields_set,
                public_ui=(
                    cast("PublicUIConfig", body.public_ui.model_dump())
                    if body.public_ui is not None
                    else None
                ),
                appearance=(
                    cast(
                        "StorefrontAppearancePatch",
                        body.appearance.model_dump(exclude_unset=True),
                    )
                    if body.appearance is not None
                    else None
                ),
            ),
            session,
        )
        record = await handle_get_storefront(GetStorefrontQuery(updated["id"]), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(_admin_payload(record)))


@router.put(
    "/api/v1/admin/storefronts/{storefront_id}/logo",
    response_model=StorefrontAdminResponse,
    summary="[admin] Загрузить логотип",
    description=(
        "Проверяет статичный JPEG, PNG или WebP до 5 МиБ и сохраняет оригинал "
        "без изменения разрешения, качества и метаданных. MIME должен соответствовать файлу."
    ),
)
async def upload_admin_storefront_logo(
    storefront_id: UUID,
    file: UploadFile,
    _user: AdminUser,
    session: DatabaseSession,
    storage: Storage,
) -> JSONResponse:
    content_type = file.content_type or "application/octet-stream"
    data = await file.read(MAX_STOREFRONT_LOGO_BYTES + 1)
    try:
        updated = await handle_upload_storefront_logo(
            UploadStorefrontLogoCommand(
                storefront_id=storefront_id,
                content_type=content_type,
                data=data,
            ),
            session,
            storage,
        )
        record = await handle_get_storefront(GetStorefrontQuery(updated["id"]), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(_admin_payload(record)))


@router.delete(
    "/api/v1/admin/storefronts/{storefront_id}/logo",
    response_model=StorefrontAdminResponse,
    summary="[admin] Удалить логотип витрины",
    description=(
        "Удаляет собственный логотип; дочерняя витрина наследует логотип основной."
    ),
)
async def clear_admin_storefront_logo(
    storefront_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
    storage: Storage,
) -> JSONResponse:
    try:
        updated = await handle_clear_storefront_logo(
            ClearStorefrontLogoCommand(storefront_id), session, storage
        )
        record = await handle_get_storefront(GetStorefrontQuery(updated["id"]), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(_admin_payload(record)))


async def _read_settings_file(file: UploadFile) -> bytes:
    data = await file.read(MAX_STOREFRONT_TRANSFER_BYTES + 1)
    if len(data) > MAX_STOREFRONT_TRANSFER_BYTES:
        raise HTTPException(status_code=413, detail="JSON-файл превышает 20 MiB")
    return data


@router.get(
    "/api/v1/admin/storefronts/settings/export",
    response_model=StorefrontSettingsExportResponse,
    summary="[admin] Экспорт настроек всех витрин",
    description="JSON со словарём slug, собственными настройками и оригиналами логотипов; без складов и шрифтов. Максимум 20 MiB.",
    dependencies=[Depends(_transfer_admin)],
)
async def export_admin_storefront_settings(
    _user: AdminUser, session: DatabaseSession, storage: Storage,
) -> Response:
    try:
        data = await handle_export_storefront_settings(session, storage)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return Response(
        content=data, media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="storefront-settings.json"', "Cache-Control": "no-store"},
    )


@router.post(
    "/api/v1/admin/storefronts/settings/preview",
    response_model=StorefrontSettingsPreviewResponse,
    summary="[admin] Предпросмотр импорта настроек витрин",
    description="Проверяет multipart file без изменения БД/S3. Возвращает действия и token на 15 минут для этого пользователя, файла и состояния витрин.",
    dependencies=[Depends(_transfer_admin)],
)
async def preview_admin_storefront_settings(
    file: UploadFile, user: AdminUser, session: DatabaseSession,
) -> JSONResponse:
    data = await _read_settings_file(file)
    try:
        result = await handle_preview_storefront_settings(data, UUID(str(user["id"])), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(result), headers={"Cache-Control": "no-store"})


@router.post(
    "/api/v1/admin/storefronts/settings/import",
    response_model=StorefrontSettingsImportResponse,
    summary="[admin] Импортировать настройки выбранных витрин",
    description="Multipart file, preview_token и confirmed=true. Весь пакет БД атомарен; 409 требует нового предпросмотра. Новые витрины выключены и не имеют складов.",
    dependencies=[Depends(_transfer_admin)],
)
async def import_admin_storefront_settings(
    file: UploadFile, user: AdminUser, session: DatabaseSession, storage: Storage,
    preview_token: Annotated[str, Form()] = "",
    confirmed: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    data = await _read_settings_file(file)
    try:
        result = await handle_import_storefront_settings(
            ImportStorefrontSettingsCommand(
                data=data, preview_token=preview_token, confirmed=confirmed == "true",
                actor_id=UUID(str(user["id"])),
            ),
            session, storage,
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.rollback()
        raise _http(exc) from exc
    except Exception:
        await session.rollback()
        raise
    return JSONResponse(content=jsonable_encoder(result), headers={"Cache-Control": "no-store"})
