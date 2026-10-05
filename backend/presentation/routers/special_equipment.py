"""Public REST resources for the corrected special-equipment catalog."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError, domain_to_http
from application.queries.special_equipment import (
    GetSpecialEquipmentMediaQuery,
    GetSpecialEquipmentProductQuery,
    ListCompatibleAttachmentsQuery,
    ListSpecialEquipmentProductImagesQuery,
    ListSpecialEquipmentProductsQuery,
    handle_get_media,
    handle_get_product,
    handle_list_categories,
    handle_list_compatible_attachments,
    handle_list_facets,
    handle_list_marks,
    handle_list_product_images,
    handle_list_products,
    handle_resolve_category_path,
)
from domain.errors import DomainError
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from infrastructure.services.object_storage import get_object_storage
from presentation.dependencies.rate_limit import rate_limit_special_equipment_catalog
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.errors import special_equipment_problem_response
from presentation.schemas.special_equipment import (
    SpecialEquipmentCategoriesResponse,
    SpecialEquipmentCategoryPathResponse,
    SpecialEquipmentCompatibleAttachmentsResponse,
    SpecialEquipmentFacets,
    SpecialEquipmentMarksResponse,
    SpecialEquipmentProductDetail,
    SpecialEquipmentProductImagesResponse,
    SpecialEquipmentProductsResponse,
)

router = APIRouter(dependencies=[rate_limit_special_equipment_catalog])
_Sort = Literal[
    "published_desc",
    "published_asc",
    "price_asc",
    "price_desc",
    "name_asc",
    "mileage_asc",
    "mileage_desc",
    "engine_hours_asc",
    "engine_hours_desc",
]


def _problem(exc: ServiceError | DomainError) -> JSONResponse:
    error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    code = error.code or {
        404: "RESOURCE_NOT_FOUND",
        409: "STATE_CONFLICT",
        422: "VALIDATION_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(error.status_code, "REQUEST_ERROR")
    return special_equipment_problem_response(
        status_code=error.status_code,
        detail=str(error),
        code=code,
        title={
            400: "Несовместимые фильтры",
            404: "Ресурс не найден",
            409: "Конфликт состояния",
            422: "Ошибка валидации",
            503: "Сервис временно недоступен",
        }.get(error.status_code, "Ошибка запроса"),
    )


def _query(
    *,
    category_path: str | None,
    mark_id: list[UUID] | None,
    model_id: list[UUID] | None,
    modification_id: list[UUID] | None,
    trim_id: list[UUID] | None,
    superstructure_id: list[UUID] | None,
    body_color_id: list[UUID] | None,
    interior_color_id: list[UUID] | None,
    availability: list[Literal["available", "on_order"]] | None,
    condition: Literal["new", "used"] | None,
    price_min: Decimal | None,
    price_max: Decimal | None,
    mileage_min: int | None,
    mileage_max: int | None,
    engine_hours_min: int | None,
    engine_hours_max: int | None,
    city_id: UUID | None,
    warehouse_id: UUID | None,
    min_in_stock: int | None,
    search: str | None,
    description_include: str | None,
    description_exclude: str | None,
    sort: _Sort,
    page: int,
    page_size: int,
    attribute: list[str] | None,
    scope: CatalogScope,
) -> ListSpecialEquipmentProductsQuery:
    return ListSpecialEquipmentProductsQuery(
        scope=scope,
        category_path=category_path,
        mark_ids=tuple(mark_id or ()),
        model_ids=tuple(model_id or ()),
        modification_ids=tuple(modification_id or ()),
        trim_ids=tuple(trim_id or ()),
        superstructure_ids=tuple(superstructure_id or ()),
        body_color_ids=tuple(body_color_id or ()),
        interior_color_ids=tuple(interior_color_id or ()),
        availability=tuple(availability or ()),
        condition=condition,
        price_min=price_min,
        price_max=price_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        engine_hours_min=engine_hours_min,
        engine_hours_max=engine_hours_max,
        city_id=city_id,
        warehouse_id=warehouse_id,
        min_in_stock=min_in_stock,
        search=search,
        description_include=description_include,
        description_exclude=description_exclude,
        sort=sort,
        page=page,
        page_size=page_size,
        attribute_tokens=tuple(attribute or ()),
    )


def _parse_range(header: str, size: int) -> tuple[int, int] | None:  # noqa: PLR0911
    if not header.startswith("bytes=") or "," in header:
        return None
    start_raw, separator, end_raw = header[6:].partition("-")
    if separator != "-":
        return None
    try:
        if not start_raw:
            suffix = int(end_raw)
            if suffix <= 0:
                return None
            return max(0, size - suffix), size - 1
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


def _media_response(
    obj: StoredObject,
    request: Request,
    filename: str,
    *,
    cache_control: str = "public, no-cache",
    etag_prefix: str = "media-sha256",
    vary: str | None = None,
) -> Response:
    etag = f'"{etag_prefix}-{hashlib.sha256(obj.data).hexdigest()}"'
    headers = {
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename}"',
        "ETag": etag,
    }
    if vary:
        headers["Vary"] = vary
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    range_header = request.headers.get("range")
    if range_header:
        byte_range = _parse_range(range_header, obj.size)
        if byte_range is None:
            headers["Content-Range"] = f"bytes */{obj.size}"
            return Response(status_code=416, headers=headers)
        start, end = byte_range
        payload = obj.data[start : end + 1]
        headers["Content-Range"] = f"bytes {start}-{end}/{obj.size}"
        headers["Content-Length"] = str(len(payload))
        return Response(
            content=payload,
            status_code=206,
            media_type=obj.content_type,
            headers=headers,
        )
    headers["Content-Length"] = str(obj.size)
    return Response(content=obj.data, media_type=obj.content_type, headers=headers)


@router.get(
    "/categories",
    response_model=SpecialEquipmentCategoriesResponse,
    summary="Граф категорий спецтехники",
    description=(
        "Возвращает активные узлы DAG, их parent_ids/child_ids и упорядоченные "
        "размещения дочерних категорий."
    ),
)
async def categories(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(await handle_list_categories(session)))


@router.get(
    "/categories/resolve",
    response_model=SpecialEquipmentCategoryPathResponse,
    summary="Проверить путь категории",
    description="Проверяет slash-separated root-to-category path по slug.",
)
async def resolve_category(
    path: Annotated[str, Query(min_length=1, max_length=1200)],
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        result = await handle_resolve_category_path(path, session)
    except (ServiceError, DomainError) as exc:
        return _problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/marks",
    response_model=SpecialEquipmentMarksResponse,
    summary="Марки спецтехники",
    description="Возвращает активные марки для публичного фильтра.",
)
async def marks(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(await handle_list_marks(session)))


@router.get(
    "/products",
    response_model=SpecialEquipmentProductsResponse,
    summary="Каталог спецтехники",
    description="Фильтрует товары в фактическом category_path и его подкатегориях.",
)
async def products(
    category_path: Annotated[str | None, Query(max_length=1200)] = None,
    mark_id: Annotated[list[UUID] | None, Query()] = None,
    model_id: Annotated[list[UUID] | None, Query()] = None,
    modification_id: Annotated[list[UUID] | None, Query()] = None,
    trim_id: Annotated[list[UUID] | None, Query()] = None,
    superstructure_id: Annotated[list[UUID] | None, Query()] = None,
    body_color_id: Annotated[list[UUID] | None, Query()] = None,
    interior_color_id: Annotated[list[UUID] | None, Query()] = None,
    availability: Annotated[
        list[Literal["available", "on_order"]] | None, Query()
    ] = None,
    condition: Literal["new", "used"] | None = None,
    price_min: Annotated[Decimal | None, Query(ge=0)] = None,
    price_max: Annotated[Decimal | None, Query(ge=0)] = None,
    mileage_min: Annotated[int | None, Query(ge=0)] = None,
    mileage_max: Annotated[int | None, Query(ge=0)] = None,
    engine_hours_min: Annotated[int | None, Query(ge=0)] = None,
    engine_hours_max: Annotated[int | None, Query(ge=0)] = None,
    city_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    min_in_stock: Annotated[int | None, Query(ge=0, le=100000)] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    description_include: Annotated[
        str | None, Query(min_length=1, max_length=500)
    ] = None,
    description_exclude: Annotated[
        str | None, Query(min_length=1, max_length=500)
    ] = None,
    sort: _Sort = "published_desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    attribute: Annotated[list[str] | None, Query()] = None,
    session: AsyncSession = Depends(get_db),
    scope: CatalogScope = Depends(resolve_catalog_scope),
) -> JSONResponse:
    query = _query(
        category_path=category_path,
        mark_id=mark_id,
        model_id=model_id,
        modification_id=modification_id,
        trim_id=trim_id,
        superstructure_id=superstructure_id,
        body_color_id=body_color_id,
        interior_color_id=interior_color_id,
        availability=availability,
        condition=condition,
        price_min=price_min,
        price_max=price_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        engine_hours_min=engine_hours_min,
        engine_hours_max=engine_hours_max,
        city_id=city_id,
        warehouse_id=warehouse_id,
        min_in_stock=min_in_stock,
        search=search,
        description_include=description_include,
        description_exclude=description_exclude,
        sort=sort,
        page=page,
        page_size=page_size,
        attribute=attribute,
        scope=scope,
    )
    try:
        result = await handle_list_products(query, session)
    except (ServiceError, DomainError) as exc:
        return _problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/facets",
    response_model=SpecialEquipmentFacets,
    summary="Фильтры спецтехники",
    description="Использует тот же category_path и scalar filters, что и listing.",
)
async def facets(
    category_path: Annotated[str | None, Query(max_length=1200)] = None,
    mark_id: Annotated[list[UUID] | None, Query()] = None,
    model_id: Annotated[list[UUID] | None, Query()] = None,
    modification_id: Annotated[list[UUID] | None, Query()] = None,
    trim_id: Annotated[list[UUID] | None, Query()] = None,
    superstructure_id: Annotated[list[UUID] | None, Query()] = None,
    body_color_id: Annotated[list[UUID] | None, Query()] = None,
    interior_color_id: Annotated[list[UUID] | None, Query()] = None,
    availability: Annotated[
        list[Literal["available", "on_order"]] | None, Query()
    ] = None,
    condition: Literal["new", "used"] | None = None,
    price_min: Annotated[Decimal | None, Query(ge=0)] = None,
    price_max: Annotated[Decimal | None, Query(ge=0)] = None,
    mileage_min: Annotated[int | None, Query(ge=0)] = None,
    mileage_max: Annotated[int | None, Query(ge=0)] = None,
    engine_hours_min: Annotated[int | None, Query(ge=0)] = None,
    engine_hours_max: Annotated[int | None, Query(ge=0)] = None,
    city_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    min_in_stock: Annotated[int | None, Query(ge=0, le=100000)] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    description_include: Annotated[
        str | None, Query(min_length=1, max_length=500)
    ] = None,
    description_exclude: Annotated[
        str | None, Query(min_length=1, max_length=500)
    ] = None,
    attribute: Annotated[list[str] | None, Query()] = None,
    session: AsyncSession = Depends(get_db),
    scope: CatalogScope = Depends(resolve_catalog_scope),
) -> JSONResponse:
    query = _query(
        category_path=category_path,
        mark_id=mark_id,
        model_id=model_id,
        modification_id=modification_id,
        trim_id=trim_id,
        superstructure_id=superstructure_id,
        body_color_id=body_color_id,
        interior_color_id=interior_color_id,
        availability=availability,
        condition=condition,
        price_min=price_min,
        price_max=price_max,
        mileage_min=mileage_min,
        mileage_max=mileage_max,
        engine_hours_min=engine_hours_min,
        engine_hours_max=engine_hours_max,
        city_id=city_id,
        warehouse_id=warehouse_id,
        min_in_stock=min_in_stock,
        search=search,
        description_include=description_include,
        description_exclude=description_exclude,
        sort="published_desc",
        page=1,
        page_size=1,
        attribute=attribute,
        scope=scope,
    )
    try:
        result = await handle_list_facets(query, session)
    except (ServiceError, DomainError) as exc:
        return _problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/products/{product_id}",
    response_model=SpecialEquipmentProductDetail,
    summary="Карточка спецтехники",
    description="При category_path валидирует ветку; без него поддерживает прямые/cart/favorite ссылки.",
)
async def product_detail(
    product_id: UUID,
    category_path: Annotated[
        str | None, Query(min_length=1, max_length=1200)
    ] = None,
    session: AsyncSession = Depends(get_db),
    scope: CatalogScope = Depends(resolve_catalog_scope),
) -> JSONResponse:
    try:
        result = await handle_get_product(
            GetSpecialEquipmentProductQuery(product_id, category_path, scope), session
        )
    except (ServiceError, DomainError) as exc:
        return _problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/products/{product_id}/compatible-attachments",
    response_model=SpecialEquipmentCompatibleAttachmentsResponse,
    summary="Совместимые надстройки",
    description="Возвращает опубликованные надстройки с количеством связанных единиц.",
)
async def compatible_attachments(
    product_id: UUID,
    session: AsyncSession = Depends(get_db),
    scope: CatalogScope = Depends(resolve_catalog_scope),
) -> JSONResponse:
    try:
        result = await handle_list_compatible_attachments(
            ListCompatibleAttachmentsQuery(product_id, scope), session
        )
    except (ServiceError, DomainError) as exc:
        return _problem(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/products/{product_id}/images",
    response_model=SpecialEquipmentProductImagesResponse,
    summary="Галерея товара",
    description="Возвращает только FastAPI content URLs.",
)
async def product_images(
    product_id: UUID, session: AsyncSession = Depends(get_db)
) -> JSONResponse:
    result = await handle_list_product_images(
        ListSpecialEquipmentProductImagesQuery(product_id), session
    )
    return JSONResponse(content=jsonable_encoder(result))


async def _content(
    *,
    query: GetSpecialEquipmentMediaQuery,
    request: Request,
    session: AsyncSession,
    storage: ObjectStorage,
) -> Response:
    try:
        key = await handle_get_media(query, session)
    except (ServiceError, DomainError) as exc:
        return _problem(exc)
    obj = await storage.get(key)
    if obj is None:
        return _problem(ServiceError("Изображение не найдено", status_code=404))
    return _media_response(obj, request, f"{query.media_id}.webp")


@router.get(
    "/categories/{category_id}/image/content",
    response_model=None,
    summary="Изображение категории",
    description="FastAPI proxy для изображения активной категории.",
)
async def category_image(
    category_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    return await _content(
        query=GetSpecialEquipmentMediaQuery("category", category_id),
        request=request,
        session=session,
        storage=storage,
    )


@router.get(
    "/images/{image_id}/content",
    response_model=None,
    summary="Изображение товара",
    description="FastAPI proxy для изображения опубликованного товара.",
)
async def product_image(
    image_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    return await _content(
        query=GetSpecialEquipmentMediaQuery("image", image_id),
        request=request,
        session=session,
        storage=storage,
    )
