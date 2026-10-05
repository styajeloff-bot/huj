"""Public storefront routes for constructed pages."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.storefront_pages import (
    GetPublicStorefrontPageQuery,
    handle_get_public_storefront_page,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.schemas.storefront_pages import StorefrontPublicPageResponse

router = APIRouter()
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


def _http(exc: ServiceError | DomainError) -> HTTPException:
    service_error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    return HTTPException(status_code=service_error.status_code, detail=str(service_error))


def _make_page_response(data: dict[str, Any], if_none_match: str | None) -> Response:
    encoded = jsonable_encoder(data)
    body_bytes = json.dumps(encoded, sort_keys=True).encode("utf-8")
    etag = f'W/"{hashlib.sha256(body_bytes).hexdigest()}"'

    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=60, stale-while-revalidate=300",
    }

    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers=headers)

    return JSONResponse(
        content=encoded,
        headers=headers,
    )


@router.get(
    "/api/v1/storefront/pages/{page_key}",
    response_model=StorefrontPublicPageResponse,
    summary="Публичный макет страницы основной витрины",
    description="Возвращает опубликованный макет страницы для дефолтной витрины. Если страница не настроена, возвращает fallback_layout=True.",
)
async def get_default_storefront_public_page(
    page_key: str,
    session: DatabaseSession,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    try:
        data = await handle_get_public_storefront_page(
            GetPublicStorefrontPageQuery(storefront_slug=None, page_key=page_key),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return _make_page_response(data, if_none_match)


@router.get(
    "/api/v1/storefronts/{storefront_slug}/pages/{page_key}",
    response_model=StorefrontPublicPageResponse,
    summary="Публичный макет страницы дочерней витрины",
    description="Возвращает опубликованный макет страницы по slug витрины и ключу страницы.",
)
async def get_storefront_public_page(
    storefront_slug: str,
    page_key: str,
    session: DatabaseSession,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    try:
        data = await handle_get_public_storefront_page(
            GetPublicStorefrontPageQuery(
                storefront_slug=storefront_slug, page_key=page_key
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return _make_page_response(data, if_none_match)
