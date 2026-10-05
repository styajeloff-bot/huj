"""Section visibility routes for public and authenticated navigation."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.section_visibility import (
    SectionVisibilityUpdate,
    UpdateSectionVisibilityCommand,
    handle_update_section_visibility,
)
from application.queries.section_visibility import (
    GetSectionVisibilityQuery,
    ListSectionVisibilityQuery,
    handle_get_section_visibility,
    handle_list_section_visibility,
)
from application.queries.storefronts import (
    GetStorefrontQuery,
    handle_get_storefront,
)
from domain.section_visibility import (
    GlobalSectionVisibilityScope,
    StorefrontSectionVisibilityScope,
)
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.schemas.section_visibility import (
    SectionVisibilityListResponse,
    SectionVisibilityResponse,
    UpdateSectionVisibilityRequest,
)

router = APIRouter()

WorkspaceUser = Annotated[
    dict[str, Any],
    Depends(
        require_roles(
            "carcraft_employee",
            "leasing_company",
            "dealer",
            "distributor",
        )
    ),
]
EmployeeUser = Annotated[
    dict[str, Any],
    Depends(require_roles("carcraft_employee")),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
PublicCatalogScope = Annotated[CatalogScope, Depends(resolve_catalog_scope)]


@router.get(
    "/section-visibility/public",
    response_model=SectionVisibilityResponse,
    summary="Видимость разделов публичного сайта",
    description=(
        "Без аутентификации возвращает полную матрицу публичной навигации. "
        "Для отсутствующих настроек используются безопасные значения по умолчанию."
    ),
)
@router.get(
    "/storefronts/{storefront_slug}/section-visibility/public",
    response_model=SectionVisibilityResponse,
    summary="Видимость разделов публичной витрины",
    description=(
        "Без аутентификации возвращает полную независимую матрицу публичной "
        "навигации активной витрины."
    ),
)
async def get_public_section_visibility(
    scope: PublicCatalogScope,
    session: DatabaseSession,
) -> JSONResponse:
    result = await handle_get_section_visibility(
        GetSectionVisibilityQuery(scope="public", storefront_id=scope.id),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/workspace/section-visibility",
    response_model=SectionVisibilityResponse,
    summary="Видимость разделов текущей роли",
    description=(
        "Возвращает полную матрицу настраиваемых разделов workspace для "
        "сотрудника Carcraft, лизинговой компании, дилера или дистрибьютора. "
        "Для отсутствующих настроек используются значения своей области."
    ),
)
@router.get(
    "/storefronts/{storefront_slug}/workspace/section-visibility",
    response_model=SectionVisibilityResponse,
    summary="Видимость разделов workspace витрины",
    description=(
        "Возвращает матрицу workspace активной витрины для бизнес-роли. "
        "Для сотрудника Carcraft матрица остаётся глобальной."
    ),
)
async def get_workspace_section_visibility(
    user: WorkspaceUser,
    scope: PublicCatalogScope,
    session: DatabaseSession,
) -> JSONResponse:
    role = str(user["role"])
    raw_cid = user.get("active_company_id") or user.get("company_id")
    actor_company_id = UUID(str(raw_cid)) if raw_cid else None
    result = await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope=role,
            storefront_id=None if role == "carcraft_employee" else scope.id,
            actor_user_id=UUID(str(user["id"])),
            actor_company_id=actor_company_id,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/admin/section-visibility",
    response_model=SectionVisibilityListResponse,
    summary="[admin] Матрица видимости разделов",
    description=(
        "Возвращает полные глобальные матрицы административной и ролевой "
        "навигации. Публичные витрины настраиваются отдельными ресурсами."
    ),
)
async def list_section_visibility(
    _user: EmployeeUser,
    session: DatabaseSession,
) -> JSONResponse:
    result = await handle_list_section_visibility(
        ListSectionVisibilityQuery(),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/admin/storefronts/{storefront_id}/section-visibility",
    response_model=SectionVisibilityListResponse,
    summary="[admin] Матрицы видимости разделов витрины",
    description=(
        "Возвращает полные матрицы public, лизинговой компании, дилера и "
        "дистрибьютора указанной витрины, включая неактивную."
    ),
)
async def get_storefront_section_visibility(
    storefront_id: UUID,
    _user: EmployeeUser,
    session: DatabaseSession,
) -> JSONResponse:
    await handle_get_storefront(GetStorefrontQuery(storefront_id), session)
    result = await handle_list_section_visibility(
        ListSectionVisibilityQuery(storefront_id=storefront_id),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/admin/storefronts/{storefront_id}/section-visibility/{scope}",
    response_model=SectionVisibilityResponse,
    summary="[admin] Обновить видимость разделов витрины",
    description=(
        "Частично обновляет одну storefront-scoped матрицу указанной витрины "
        "и возвращает полный итоговый ресурс."
    ),
)
async def update_storefront_section_visibility(
    storefront_id: UUID,
    scope: StorefrontSectionVisibilityScope,
    body: UpdateSectionVisibilityRequest,
    user: EmployeeUser,
    session: DatabaseSession,
) -> JSONResponse:
    await handle_get_storefront(GetStorefrontQuery(storefront_id), session)
    result = await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope=scope,
            storefront_id=storefront_id,
            sections=tuple(
                SectionVisibilityUpdate(
                    key=item.key,
                    is_visible=item.is_visible,
                )
                for item in body.sections
            ),
            updated_by=UUID(str(user["id"])),
        ),
        session,
    )
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/admin/section-visibility/{scope}",
    response_model=SectionVisibilityResponse,
    summary="[admin] Обновить видимость разделов",
    description=(
        "Частично обновляет видимость разделов выбранной области и возвращает "
        "полную итоговую матрицу. Доступно только сотрудникам Carcraft."
    ),
)
async def update_section_visibility(
    scope: GlobalSectionVisibilityScope,
    body: UpdateSectionVisibilityRequest,
    user: EmployeeUser,
    session: DatabaseSession,
) -> JSONResponse:
    result = await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope=scope,
            sections=tuple(
                SectionVisibilityUpdate(
                    key=item.key,
                    is_visible=item.is_visible,
                )
                for item in body.sections
            ),
            updated_by=UUID(str(user["id"])),
        ),
        session,
    )
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
