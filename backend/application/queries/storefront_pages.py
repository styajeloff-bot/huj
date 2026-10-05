"""Queries and handlers for storefront constructor pages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefront_pages import (
    InvalidPagePresetError,
    StorefrontPageNotFoundError,
)
from domain.storefronts import StorefrontNotFoundError
from infrastructure.repositories.storefront_page_repository import (
    StorefrontPageRecord,
    StorefrontPageRevisionRecord,
    StorefrontTemplateRecord,
    get_page_by_id,
    get_page_by_key,
    get_page_by_slug,
    list_pages_for_storefront,
    list_revisions,
    list_templates,
)
from infrastructure.repositories.storefront_repository import (
    get_default_storefront,
    get_storefront_by_slug,
)


@dataclass(frozen=True)
class ListStorefrontPagesQuery:
    storefront_id: UUID


@dataclass(frozen=True)
class GetStorefrontPageQuery:
    storefront_id: UUID
    page_id: UUID


@dataclass(frozen=True)
class GetPublicStorefrontPageQuery:
    storefront_slug: str | None
    page_key: str


@dataclass(frozen=True)
class ListStorefrontPageRevisionsQuery:
    storefront_id: UUID
    page_id: UUID


@dataclass(frozen=True)
class ExportStorefrontPagePresetQuery:
    storefront_id: UUID
    page_id: UUID


@dataclass(frozen=True)
class PreviewStorefrontPagePresetQuery:
    preset_data: dict[str, Any]


@dataclass(frozen=True)
class ListStorefrontTemplatesQuery:
    pass


async def handle_list_storefront_pages(
    query: ListStorefrontPagesQuery, session: AsyncSession
) -> list[StorefrontPageRecord]:
    return cast(
        "list[StorefrontPageRecord]",
        await list_pages_for_storefront(session, query.storefront_id),
    )


async def handle_get_storefront_page(
    query: GetStorefrontPageQuery, session: AsyncSession
) -> dict[str, Any]:
    page = await get_page_by_id(session, query.storefront_id, query.page_id)
    if page is None:
        raise StorefrontPageNotFoundError(query.page_id)

    revisions = await list_revisions(session, query.page_id)
    return {
        **page,
        "revisions": revisions,
    }


async def handle_get_public_storefront_page(
    query: GetPublicStorefrontPageQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.storefront_slug is None:
        storefront = await get_default_storefront(session)
    else:
        storefront = await get_storefront_by_slug(session, query.storefront_slug)

    if storefront is None:
        raise StorefrontNotFoundError()

    page = await get_page_by_key(session, storefront["id"], query.page_key)
    if page is None:
        page = await get_page_by_slug(session, storefront["id"], query.page_key)

    if page is None or page["published_layout"] is None:
        return {
            "page_key": page["page_key"] if page is not None else query.page_key,
            "title": page["title"] if page is not None else query.page_key,
            "fallback_layout": True,
            "layout": None,
            "published_at": None,
            "version": page["version"] if page is not None else 1,
        }

    return {
        "page_key": page["page_key"],
        "title": page["title"],
        "fallback_layout": False,
        "layout": page["published_layout"],
        "published_at": page["published_at"],
        "version": page["version"],
    }


async def handle_list_storefront_page_revisions(
    query: ListStorefrontPageRevisionsQuery, session: AsyncSession
) -> list[StorefrontPageRevisionRecord]:
    page = await get_page_by_id(session, query.storefront_id, query.page_id)
    if page is None:
        raise StorefrontPageNotFoundError(query.page_id)

    return cast(
        "list[StorefrontPageRevisionRecord]",
        await list_revisions(session, query.page_id),
    )


async def handle_export_storefront_page_preset(
    query: ExportStorefrontPagePresetQuery, session: AsyncSession
) -> dict[str, Any]:
    page = await get_page_by_id(session, query.storefront_id, query.page_id)
    if page is None:
        raise StorefrontPageNotFoundError(query.page_id)

    return {
        "schema_version": "1.0",
        "page_key": page["page_key"],
        "title": page["title"],
        "layout": page["draft_layout"],
        "exported_at": datetime.now(UTC),
    }


def handle_preview_storefront_page_preset(
    query: PreviewStorefrontPagePresetQuery,
) -> dict[str, Any]:
    data = query.preset_data
    if not isinstance(data, dict):
        raise InvalidPagePresetError("Данные пресета должны быть JSON-объектом")

    # If wrapped in export schema, unwrap layout
    layout = data.get("layout", data)
    if not isinstance(layout, dict):
        raise InvalidPagePresetError("Структура макета не найдена в файле пресета")

    sections = layout.get("sections")
    if not isinstance(sections, list):
        raise InvalidPagePresetError("В макете отсутствует список секций ('sections')")

    widgets_count = 0
    widget_types_set: set[str] = set()

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        cols = sec.get("columns", [])
        if not isinstance(cols, list):
            continue
        for col in cols:
            if not isinstance(col, dict):
                continue
            widgets = col.get("widgets", [])
            if not isinstance(widgets, list):
                continue
            for w in widgets:
                if isinstance(w, dict) and "type" in w:
                    widgets_count += 1
                    widget_types_set.add(str(w["type"]))

    schema_version = str(data.get("schema_version", "1.0"))

    return {
        "is_valid": True,
        "schema_version": schema_version,
        "sections_count": len(sections),
        "widgets_count": widgets_count,
        "widget_types": sorted(widget_types_set),
        "warnings": [],
    }


async def handle_list_storefront_templates(
    _query: ListStorefrontTemplatesQuery, session: AsyncSession
) -> list[StorefrontTemplateRecord]:
    return cast(
        "list[StorefrontTemplateRecord]",
        await list_templates(session),
    )
