"""Queries for effective section visibility matrices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.section_visibility import (
    GLOBAL_SECTION_VISIBILITY_SCOPES,
    STOREFRONT_SECTION_VISIBILITY_SCOPES,
    InvalidSectionVisibilityScopeError,
    InvalidSectionVisibilityTargetError,
    get_section_visibility_defaults,
    validate_section_visibility_target,
)
from infrastructure.repositories.section_visibility_repository import (
    SectionVisibilityOverride,
    list_visibility_overrides,
)
from infrastructure.repositories.storefront_page_repository import get_custom_page_keys


class SectionVisibilityItem(TypedDict):
    key: str
    is_visible: bool


class SectionVisibilityMatrix(TypedDict):
    scope: str
    storefront_id: UUID | None
    sections: list[SectionVisibilityItem]


class SectionVisibilityList(TypedDict):
    items: list[SectionVisibilityMatrix]


@dataclass(frozen=True, slots=True)
class GetSectionVisibilityQuery:
    scope: str
    storefront_id: UUID | None = None
    actor_user_id: UUID | None = None
    actor_company_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ListSectionVisibilityQuery:
    """Select either the global matrix or all matrices of one storefront."""

    storefront_id: UUID | None = None


def _matrix_for_scope(
    scope: str,
    storefront_id: UUID | None,
    overrides: list[SectionVisibilityOverride],
    custom_page_keys: set[str] | None = None,
) -> SectionVisibilityMatrix:
    stored = {
        row["section_key"]: row["is_visible"]
        for row in overrides
        if row["scope"] == scope
    }
    defaults = get_section_visibility_defaults(scope)
    sections = [
        SectionVisibilityItem(
            key=section_key,
            is_visible=stored.get(section_key, default),
        )
        for section_key, default in defaults.items()
    ]
    if scope == "public" and custom_page_keys:
        sections.extend(
            SectionVisibilityItem(
                key=key,
                is_visible=stored.get(key, True),
            )
            for key in sorted(custom_page_keys)
            if key not in defaults
        )
    return SectionVisibilityMatrix(
        scope=scope,
        storefront_id=storefront_id,
        sections=sections,
    )


async def handle_get_section_visibility(
    query: GetSectionVisibilityQuery,
    session: AsyncSession,
) -> SectionVisibilityMatrix:
    try:
        scope, storefront_id = validate_section_visibility_target(
            query.scope,
            query.storefront_id,
        )
    except (
        InvalidSectionVisibilityScopeError,
        InvalidSectionVisibilityTargetError,
    ) as exc:
        raise ServiceError(str(exc), status_code=422) from exc
    overrides = await list_visibility_overrides(
        session,
        (scope,),
        storefront_id=storefront_id,
    )
    custom_page_keys: set[str] | None = None
    if scope == "public" and storefront_id is not None:
        custom_page_keys = await get_custom_page_keys(session, storefront_id)

    matrix = _matrix_for_scope(
        scope,
        storefront_id,
        overrides,
        custom_page_keys=custom_page_keys,
    )

    if (
        query.actor_company_id is not None
        and query.actor_user_id is not None
        and scope in ("dealer", "distributor")
    ):
        from infrastructure.repositories.user_company_access_repository import (
            get_actor_section_access,
        )

        personal = await get_actor_section_access(
            session, query.actor_user_id, query.actor_company_id, scope
        )
        code_to_keys: dict[str, list[str]] = {
            "applications": ["applications"],
            "warehouses": ["warehouses", "inventory"],
            "vehicle_exchange": ["exchange", "exchange_import"],
            "employees": ["employees"],
            "catalog_management": ["special_equipment_catalog"],
            "analytics": ["distributor_analytics", "reports", "stats"],
            "incentive_programs": ["support"],
        }
        denied_keys: set[str] = set()
        for code, keys in code_to_keys.items():
            if not personal.get(code, True):
                denied_keys.update(keys)
        if not personal.get("monetization_income", True) and not personal.get(
            "monetization_expense", True
        ):
            denied_keys.add("monetization")

        for item in matrix["sections"]:
            if item["key"] in denied_keys:
                item["is_visible"] = False

    return matrix


async def handle_list_section_visibility(
    query: ListSectionVisibilityQuery,
    session: AsyncSession,
) -> SectionVisibilityList:
    scopes = (
        STOREFRONT_SECTION_VISIBILITY_SCOPES
        if query.storefront_id is not None
        else GLOBAL_SECTION_VISIBILITY_SCOPES
    )
    overrides = await list_visibility_overrides(
        session,
        scopes,
        storefront_id=query.storefront_id,
    )
    custom_page_keys: set[str] | None = None
    if query.storefront_id is not None:
        custom_page_keys = await get_custom_page_keys(session, query.storefront_id)

    return SectionVisibilityList(
        items=[
            _matrix_for_scope(
                scope,
                query.storefront_id,
                overrides,
                custom_page_keys=custom_page_keys if scope == "public" else None,
            )
            for scope in scopes
        ]
    )
