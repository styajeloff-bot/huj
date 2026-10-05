"""Commands for section visibility overrides."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.section_visibility import (
    GetSectionVisibilityQuery,
    ListSectionVisibilityQuery,
    SectionVisibilityMatrix,
    handle_get_section_visibility,
    handle_list_section_visibility,
)
from domain.section_visibility import (
    InvalidSectionVisibilityKeyError,
    InvalidSectionVisibilityScopeError,
    InvalidSectionVisibilityTargetError,
    validate_section_visibility_key,
    validate_section_visibility_target,
)
from domain.storefronts import (
    DEFAULT_STOREFRONT_ID,
    CurrentHomePageHiddenError,
    StorefrontNotFoundError,
)
from infrastructure.repositories.section_visibility_repository import (
    upsert_visibility_overrides,
)
from infrastructure.repositories.storefront_page_repository import get_custom_page_keys
from infrastructure.repositories.storefront_repository import lock_storefront_by_id


@dataclass(frozen=True, slots=True)
class SectionVisibilityUpdate:
    key: str
    is_visible: bool


@dataclass(frozen=True, slots=True)
class UpdateSectionVisibilityCommand:
    scope: str
    sections: tuple[SectionVisibilityUpdate, ...]
    updated_by: UUID
    storefront_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InitializeStorefrontSectionVisibilityCommand:
    storefront_id: UUID
    updated_by: UUID


async def handle_initialize_storefront_section_visibility(
    command: InitializeStorefrontSectionVisibilityCommand,
    session: AsyncSession,
) -> None:
    """Materialize all independent scoped snapshots for a new storefront."""
    default_matrices = await handle_list_section_visibility(
        ListSectionVisibilityQuery(storefront_id=DEFAULT_STOREFRONT_ID),
        session,
    )
    for matrix in default_matrices["items"]:
        updates = {item["key"]: item["is_visible"] for item in matrix["sections"]}
        await upsert_visibility_overrides(
            session,
            matrix["scope"],
            updates,
            command.updated_by,
            storefront_id=command.storefront_id,
        )


async def handle_update_section_visibility(
    command: UpdateSectionVisibilityCommand,
    session: AsyncSession,
) -> SectionVisibilityMatrix:
    if not command.sections:
        raise ServiceError(
            "Передайте хотя бы один раздел для обновления",
            status_code=422,
        )

    try:
        scope, storefront_id = validate_section_visibility_target(
            command.scope,
            command.storefront_id,
        )
        allowed_custom_keys: set[str] | None = None
        if command.scope == "public" and command.storefront_id is not None:
            allowed_custom_keys = await get_custom_page_keys(
                session, command.storefront_id
            )
        updates: dict[str, bool] = {}
        for item in command.sections:
            validate_section_visibility_key(
                scope, item.key, allowed_custom_keys=allowed_custom_keys
            )
            if item.key in updates:
                raise ServiceError(
                    f"Раздел {item.key!r} указан более одного раза",
                    status_code=422,
                )
            updates[item.key] = item.is_visible
    except (
        InvalidSectionVisibilityScopeError,
        InvalidSectionVisibilityKeyError,
        InvalidSectionVisibilityTargetError,
    ) as exc:
        raise ServiceError(str(exc), status_code=422) from exc

    if storefront_id is not None:
        # All storefront scopes acquire the parent before visibility writes,
        # matching settings import and avoiding a table/FK lock-order cycle.
        storefront = await lock_storefront_by_id(session, storefront_id)
        if storefront is None:
            raise StorefrontNotFoundError
        home_page_key = storefront["public_ui"]["home_page_key"]
        if scope == "public" and home_page_key != "home" and updates.get(home_page_key) is False:
            raise CurrentHomePageHiddenError(home_page_key)

    await upsert_visibility_overrides(
        session,
        scope,
        updates,
        command.updated_by,
        storefront_id=storefront_id,
    )
    return await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope=scope,
            storefront_id=storefront_id,
        ),
        session,
    )
