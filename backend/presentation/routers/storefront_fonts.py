"""Administrator font catalog and immutable public font content routes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.storefront_fonts import (
    DeleteStorefrontFontCommand,
    UpdateStorefrontFontCommand,
    UploadStorefrontFontCommand,
    compensate_storefront_font_upload,
    handle_delete_storefront_font,
    handle_update_storefront_font,
    handle_upload_storefront_font,
)
from application.errors import ServiceError, domain_to_http
from application.queries.storefront_fonts import (
    GetStorefrontFontContentQuery,
    ListStorefrontFontsQuery,
    handle_get_storefront_font_content,
    handle_list_storefront_fonts,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage
from domain.services.scopes import STOREFRONTS_ADMIN
from domain.storefronts import (
    MAX_STOREFRONT_FONT_BYTES,
)
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.auth import require_scopes
from presentation.schemas.storefront_fonts import (
    StorefrontFontListResponse,
    StorefrontFontPatchRequest,
    StorefrontFontResource,
)

router = APIRouter()
AdminUser = Annotated[dict[str, Any], Depends(require_scopes(STOREFRONTS_ADMIN))]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]


def _http(exc: ServiceError | DomainError) -> HTTPException:
    service_error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    return HTTPException(status_code=service_error.status_code, detail=str(service_error))


def _font_payload(font: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": font["id"],
        "name": font["name"],
        "description": font["description"],
        "original_filename": font["original_filename"],
        "content_type": font["content_type"],
        "size_bytes": font["size_bytes"],
        "checksum_sha256": font["checksum_sha256"],
        "storefront_usage_count": font["storefront_usage_count"],
        "created_at": font["created_at"],
        "updated_at": font["updated_at"],
    }


@router.get(
    "/api/v1/admin/storefront-fonts",
    response_model=StorefrontFontListResponse,
    summary="[admin] Список шрифтов витрин",
    description=(
        "Возвращает общий каталог загруженных шрифтов и количество использующих "
        "каждый шрифт витрин. Требует право управления витринами."
    ),
)
async def list_admin_storefront_fonts(
    _user: AdminUser, session: DatabaseSession
) -> JSONResponse:
    result = await handle_list_storefront_fonts(ListStorefrontFontsQuery(), session)
    return JSONResponse(
        content=jsonable_encoder(
            {"items": [_font_payload(font) for font in result["items"]]}
        )
    )


@router.post(
    "/api/v1/admin/storefront-fonts",
    response_model=StorefrontFontResource,
    status_code=status.HTTP_201_CREATED,
    summary="[admin] Загрузить шрифт витрин",
    description=(
        "Проверяет WOFF2, WOFF, TTF или OTF по содержимому, нормализует в WOFF2 "
        "и создаёт общую запись каталога. Требует право управления витринами."
    ),
)
async def upload_admin_storefront_font(
    user: AdminUser,
    session: DatabaseSession,
    storage: Storage,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()],
    description: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    data = await file.read(MAX_STOREFRONT_FONT_BYTES + 1)
    try:
        result = await handle_upload_storefront_font(
            UploadStorefrontFontCommand(
                name=name,
                description=description,
                original_filename=file.filename,
                data=data,
                created_by=UUID(str(user["id"])),
            ),
            session,
            storage,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    font = result["font"]
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await compensate_storefront_font_upload(font["id"], storage)
        raise
    return JSONResponse(
        content=jsonable_encoder(_font_payload(font)),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": f"/api/v1/admin/storefront-fonts/{font['id']}"},
    )


@router.patch(
    "/api/v1/admin/storefront-fonts/{font_id}",
    response_model=StorefrontFontResource,
    summary="[admin] Изменить шрифт витрин",
    description=(
        "Меняет название и/или описание без замены файла. Требует право управления "
        "витринами."
    ),
)
async def patch_admin_storefront_font(
    font_id: UUID,
    body: StorefrontFontPatchRequest,
    _user: AdminUser,
    session: DatabaseSession,
) -> JSONResponse:
    try:
        result = await handle_update_storefront_font(
            UpdateStorefrontFontCommand(
                font_id=font_id,
                name=body.name,
                description=body.description,
                update_name="name" in body.model_fields_set,
                update_description="description" in body.model_fields_set,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(_font_payload(result["font"])))


@router.delete(
    "/api/v1/admin/storefront-fonts/{font_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="[admin] Удалить шрифт витрин",
    description=(
        "Атомарно переводит использующие шрифт витрины на Mulish, увеличивает их "
        "версии и удаляет файл. Требует право управления витринами."
    ),
)
async def delete_admin_storefront_font(
    font_id: UUID,
    _user: AdminUser,
    session: DatabaseSession,
    storage: Storage,
) -> Response:
    try:
        await handle_delete_storefront_font(
            DeleteStorefrontFontCommand(font_id), session, storage
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if if_none_match is None:
        return False
    for candidate in if_none_match.split(","):
        normalized = candidate.strip()
        if normalized == "*":
            return True
        if normalized.startswith("W/"):
            normalized = normalized[2:].strip()
        if normalized == etag:
            return True
    return False


@router.get(
    "/api/v1/storefront-fonts/{font_id}/content",
    response_model=None,
    summary="Содержимое шрифта витрины",
    description=(
        "Публично возвращает только нормализованный WOFF2-файл по UUID с "
        "неизменяемым годовым кешированием и условным ETag-ответом."
    ),
    responses={
        200: {"content": {"font/woff2": {}}},
        304: {"description": "Содержимое не изменилось"},
        404: {"description": "Шрифт не найден"},
    },
)
async def get_storefront_font_content(
    font_id: UUID,
    session: DatabaseSession,
    storage: Storage,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    try:
        content = await handle_get_storefront_font_content(
            GetStorefrontFontContentQuery(font_id), session, storage
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    etag = f'"{content["checksum_sha256"]}"'
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if _etag_matches(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(
        content=content["stored"].data,
        media_type="font/woff2",
        headers=headers,
    )
