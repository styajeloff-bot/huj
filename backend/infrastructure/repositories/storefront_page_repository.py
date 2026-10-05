"""Persistence operations for storefront constructor pages, revisions, and templates."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefront_pages import (
    StorefrontPageAlreadyExistsError,
    StorefrontPageNotFoundError,
    StorefrontPageRevisionNotFoundError,
    StorefrontPageVersionConflictError,
)
from infrastructure.models.storefront_pages import (
    StorefrontPage,
    StorefrontPageRevision,
    StorefrontTemplate,
)
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User
from infrastructure.repository_timing import timed_repository


class StorefrontPageRecord(TypedDict):
    id: UUID
    storefront_id: UUID
    page_key: str
    title: str
    slug: str | None
    is_system: bool
    status: str
    version: int
    has_unpublished_draft: bool
    draft_layout: dict[str, Any]
    published_layout: dict[str, Any] | None
    updated_by: UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StorefrontPageRevisionRecord(TypedDict):
    id: UUID
    page_id: UUID
    version: int
    summary: str | None
    created_by: UUID | None
    created_by_name: str | None
    layout_snapshot: dict[str, Any]
    created_at: datetime


class StorefrontTemplateRecord(TypedDict):
    id: UUID
    code: str
    name: str
    description: str | None
    category: str
    preview_image_url: str | None
    layout: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _to_page_record(page: StorefrontPage) -> StorefrontPageRecord:
    has_unpublished_draft = (
        page.published_layout is None or page.published_layout != page.draft_layout
    )
    return StorefrontPageRecord(
        id=page.id,
        storefront_id=page.storefront_id,
        page_key=page.page_key,
        title=page.title,
        slug=page.slug,
        is_system=page.is_system,
        status=page.status,
        version=page.version,
        has_unpublished_draft=has_unpublished_draft,
        draft_layout=page.draft_layout,
        published_layout=page.published_layout,
        updated_by=page.updated_by,
        published_at=page.published_at,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def _to_template_record(template: StorefrontTemplate) -> StorefrontTemplateRecord:
    return StorefrontTemplateRecord(
        id=template.id,
        code=template.code,
        name=template.name,
        description=template.description,
        category=template.category,
        preview_image_url=template.preview_image_url,
        layout=template.layout,
        is_active=template.is_active,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


async def _ensure_default_pages(
    session: AsyncSession, storefront_id: UUID
) -> None:
    """Ensure system 'home', 'about', and 'special_equipment_catalog' pages exist for the storefront."""
    existing_keys = set(
        (
            await session.execute(
                select(StorefrontPage.page_key).where(
                    StorefrontPage.storefront_id == storefront_id
                )
            )
        ).scalars()
    )

    if "home" not in existing_keys:
        home_template = (
            await session.execute(
                select(StorefrontTemplate.layout).where(
                    StorefrontTemplate.code == "classic-leasing"
                )
            )
        ).scalar_one_or_none()
        home_layout = (
            copy.deepcopy(home_template)
            if home_template is not None
            else {
                "settings": {"title": "Главная страница"},
                "sections": [],
            }
        )
        home_page = StorefrontPage(
            id=uuid4(),
            storefront_id=storefront_id,
            page_key="home",
            title="Главная страница",
            slug=None,
            is_system=True,
            status="draft",
            version=1,
            draft_layout=home_layout,
            published_layout=None,
        )
        session.add(home_page)

    if "about" not in existing_keys:
        about_layout = {
            "settings": {"title": "О компании"},
            "sections": [
                {
                    "id": str(uuid4()),
                    "name": "О компании",
                    "layout_type": "container",
                    "styles": {"padding_top": "48px", "padding_bottom": "48px"},
                    "columns": [
                        {
                            "id": str(uuid4()),
                            "width": 12,
                            "widgets": [
                                {
                                    "id": str(uuid4()),
                                    "type": "rich_text",
                                    "is_hidden": False,
                                    "props": {
                                        "content": "<h2>О нашей компании</h2><p>Надежные финансовые решения для вашего бизнеса.</p>"
                                    },
                                    "styles": {},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        about_page = StorefrontPage(
            id=uuid4(),
            storefront_id=storefront_id,
            page_key="about",
            title="О нас",
            slug="about",
            is_system=True,
            status="draft",
            version=1,
            draft_layout=about_layout,
            published_layout=None,
        )
        session.add(about_page)

    if "special_equipment_catalog" not in existing_keys:
        catalog_layout = {
            "settings": {"title": "Транспортные средства"},
            "sections": [
                {
                    "id": str(uuid4()),
                    "name": "Каталог техники",
                    "layout_type": "container",
                    "styles": {"padding_top": "32px", "padding_bottom": "48px"},
                    "columns": [
                        {
                            "id": str(uuid4()),
                            "width": 12,
                            "widgets": [
                                {
                                    "id": str(uuid4()),
                                    "type": "product_showcase",
                                    "is_hidden": False,
                                    "props": {
                                        "title": "Каталог техники",
                                        "limit": 12,
                                        "show_filters": True,
                                    },
                                    "styles": {},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        catalog_page = StorefrontPage(
            id=uuid4(),
            storefront_id=storefront_id,
            page_key="special_equipment_catalog",
            title="Транспортные средства",
            slug="special-equipment",
            is_system=True,
            status="draft",
            version=1,
            draft_layout=catalog_layout,
            published_layout=None,
        )
        session.add(catalog_page)

    if (
        "home" not in existing_keys
        or "about" not in existing_keys
        or "special_equipment_catalog" not in existing_keys
    ):
        await session.flush()


@timed_repository
async def list_pages_for_storefront(
    session: AsyncSession, storefront_id: UUID
) -> list[StorefrontPageRecord]:
    """List all pages for a storefront, seeding default system pages if missing."""
    await _ensure_default_pages(session, storefront_id)

    stmt = (
        select(StorefrontPage)
        .where(StorefrontPage.storefront_id == storefront_id)
        .order_by(StorefrontPage.is_system.desc(), StorefrontPage.created_at.asc())
    )
    result = await session.execute(stmt)
    pages = result.scalars().all()
    return [_to_page_record(p) for p in pages]


@timed_repository
async def get_page_by_id(
    session: AsyncSession, storefront_id: UUID, page_id: UUID
) -> StorefrontPageRecord | None:
    stmt = select(StorefrontPage).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.id == page_id,
    )
    result = await session.execute(stmt)
    page = result.scalar_one_or_none()
    return _to_page_record(page) if page is not None else None


@timed_repository
async def get_page_by_key(
    session: AsyncSession, storefront_id: UUID, page_key: str
) -> StorefrontPageRecord | None:
    stmt = select(StorefrontPage).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.page_key == page_key,
    )
    result = await session.execute(stmt)
    page = result.scalar_one_or_none()
    if page is None and page_key in ("home", "about", "special_equipment_catalog"):
        await _ensure_default_pages(session, storefront_id)
        result = await session.execute(stmt)
        page = result.scalar_one_or_none()

    if page is None:
        return await get_page_by_slug(session, storefront_id, page_key)

    return _to_page_record(page)


@timed_repository
async def get_page_by_slug(
    session: AsyncSession, storefront_id: UUID, slug: str
) -> StorefrontPageRecord | None:
    stmt = select(StorefrontPage).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.slug == slug,
    )
    result = await session.execute(stmt)
    page = result.scalar_one_or_none()
    if page is None and slug in ("about", "special-equipment"):
        await _ensure_default_pages(session, storefront_id)
        result = await session.execute(stmt)
        page = result.scalar_one_or_none()

    return _to_page_record(page) if page is not None else None


@timed_repository
async def create_page(
    session: AsyncSession,
    storefront_id: UUID,
    title: str,
    page_key: str,
    slug: str | None,
    layout: dict[str, Any],
    is_system: bool,
    user_id: UUID | None,
) -> StorefrontPageRecord:
    existing = await session.execute(
        select(StorefrontPage.id).where(
            StorefrontPage.storefront_id == storefront_id,
            StorefrontPage.page_key == page_key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise StorefrontPageAlreadyExistsError(page_key)

    page = StorefrontPage(
        id=uuid4(),
        storefront_id=storefront_id,
        page_key=page_key,
        title=title,
        slug=slug,
        is_system=is_system,
        status="draft",
        version=1,
        draft_layout=layout,
        published_layout=None,
        updated_by=user_id,
    )
    session.add(page)
    await session.flush()
    return _to_page_record(page)


@timed_repository
async def update_page_metadata(
    session: AsyncSession,
    storefront_id: UUID,
    page_id: UUID,
    title: str | None = None,
    slug: str | None = None,
) -> StorefrontPageRecord:
    stmt = (
        select(StorefrontPage)
        .where(
            StorefrontPage.storefront_id == storefront_id,
            StorefrontPage.id == page_id,
        )
        .with_for_update()
    )
    result = await session.execute(stmt)
    page = result.scalar_one_or_none()
    if page is None:
        raise StorefrontPageNotFoundError(page_id)

    if title is not None:
        page.title = title
    if slug is not None:
        page.slug = slug
    page.updated_at = datetime.now(UTC)

    await session.flush()
    return _to_page_record(page)


@timed_repository
async def get_custom_page_keys(
    session: AsyncSession, storefront_id: UUID
) -> set[str]:
    stmt = select(StorefrontPage.page_key).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.is_system.is_(False),
    )
    result = await session.execute(stmt)
    return set(result.scalars().all())


@timed_repository
async def save_draft(
    session: AsyncSession,
    storefront_id: UUID,
    page_id: UUID,
    expected_version: int,
    draft_layout: dict[str, Any],
    summary: str | None,
    user_id: UUID | None,
    title: str | None = None,
) -> StorefrontPageRecord:
    stmt = select(StorefrontPage).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.id == page_id,
    ).with_for_update()
    result = await session.execute(stmt)
    page = result.scalar_one_or_none()
    if page is None:
        raise StorefrontPageNotFoundError(page_id)

    if page.version != expected_version:
        raise StorefrontPageVersionConflictError(page.version, expected_version)

    # Save revision snapshot
    revision = StorefrontPageRevision(
        id=uuid4(),
        page_id=page.id,
        version=page.version,
        summary=summary,
        layout_snapshot=page.draft_layout,
        created_by=user_id,
    )
    session.add(revision)

    page.draft_layout = draft_layout
    if title is not None:
        page.title = title
    page.version += 1
    page.updated_by = user_id
    page.updated_at = datetime.now(UTC)

    await session.flush()
    return _to_page_record(page)


@timed_repository
async def publish_page(
    session: AsyncSession,
    storefront_id: UUID,
    page_id: UUID,
    expected_version: int,
    user_id: UUID | None,
) -> StorefrontPageRecord:
    stmt = select(StorefrontPage).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.id == page_id,
    ).with_for_update()
    result = await session.execute(stmt)
    page = result.scalar_one_or_none()
    if page is None:
        raise StorefrontPageNotFoundError(page_id)

    if page.version != expected_version:
        raise StorefrontPageVersionConflictError(page.version, expected_version)

    now = datetime.now(UTC)
    page.published_layout = copy.deepcopy(page.draft_layout)
    page.status = "published"
    page.published_at = now
    page.version += 1
    page.updated_by = user_id
    page.updated_at = now

    # Invalidate storefront cache by incrementing storefront.version
    await session.execute(
        update(Storefront)
        .where(Storefront.id == storefront_id)
        .values(
            version=Storefront.version + 1,
            updated_at=now,
        )
    )

    await session.flush()
    return _to_page_record(page)


@timed_repository
async def list_revisions(
    session: AsyncSession, page_id: UUID
) -> list[StorefrontPageRevisionRecord]:
    stmt = (
        select(
            StorefrontPageRevision,
            User.name.label("user_name"),
            User.email.label("user_email"),
        )
        .outerjoin(User, StorefrontPageRevision.created_by == User.id)
        .where(StorefrontPageRevision.page_id == page_id)
        .order_by(StorefrontPageRevision.version.desc())
    )
    rows = (await session.execute(stmt)).all()
    results: list[StorefrontPageRevisionRecord] = []
    for rev, u_name, u_email in rows:
        display_name = u_name or u_email
        results.append(
            StorefrontPageRevisionRecord(
                id=rev.id,
                page_id=rev.page_id,
                version=rev.version,
                summary=rev.summary,
                created_by=rev.created_by,
                created_by_name=display_name,
                layout_snapshot=rev.layout_snapshot,
                created_at=rev.created_at,
            )
        )
    return results


@timed_repository
async def restore_revision(
    session: AsyncSession,
    storefront_id: UUID,
    page_id: UUID,
    revision_id: UUID,
    expected_version: int,
    user_id: UUID | None,
) -> StorefrontPageRecord:
    page_stmt = select(StorefrontPage).where(
        StorefrontPage.storefront_id == storefront_id,
        StorefrontPage.id == page_id,
    ).with_for_update()
    page = (await session.execute(page_stmt)).scalar_one_or_none()
    if page is None:
        raise StorefrontPageNotFoundError(page_id)

    if page.version != expected_version:
        raise StorefrontPageVersionConflictError(page.version, expected_version)

    rev_stmt = select(StorefrontPageRevision).where(
        StorefrontPageRevision.id == revision_id,
        StorefrontPageRevision.page_id == page_id,
    )
    revision = (await session.execute(rev_stmt)).scalar_one_or_none()
    if revision is None:
        raise StorefrontPageRevisionNotFoundError(revision_id)

    # Save revision snapshot of current draft before restoring
    backup_rev = StorefrontPageRevision(
        id=uuid4(),
        page_id=page.id,
        version=page.version,
        summary=f"Автоматический снимок перед восстановлением версии {revision.version}",
        layout_snapshot=page.draft_layout,
        created_by=user_id,
    )
    session.add(backup_rev)

    page.draft_layout = copy.deepcopy(revision.layout_snapshot)
    page.version += 1
    page.updated_by = user_id
    page.updated_at = datetime.now(UTC)

    await session.flush()
    return _to_page_record(page)


@timed_repository
async def list_templates(session: AsyncSession) -> list[StorefrontTemplateRecord]:
    stmt = (
        select(StorefrontTemplate)
        .where(StorefrontTemplate.is_active.is_(True))
        .order_by(StorefrontTemplate.name.asc())
    )
    templates = (await session.execute(stmt)).scalars().all()
    return [_to_template_record(t) for t in templates]


@timed_repository
async def get_template_by_code(
    session: AsyncSession, code: str
) -> StorefrontTemplateRecord | None:
    stmt = select(StorefrontTemplate).where(
        StorefrontTemplate.code == code,
        StorefrontTemplate.is_active.is_(True),
    )
    template = (await session.execute(stmt)).scalar_one_or_none()
    return _to_template_record(template) if template is not None else None
