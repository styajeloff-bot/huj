"""/api/v1/client/* — favorites and saved calculations.

After Phase 15 H3 the former ``/client/profile/*`` phone-change
endpoints, ``/saved-calculations`` (duplicate of ``/calculations``) and
``/favorites/{id}/check`` are removed. Phone-change lives at
``POST /users/me/phone-change{,/verify}``; the frontend tracks favourite
state in the pinia store instead of per-vehicle checks.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.client import (
    AddFavoriteCommand,
    BulkRemoveFavoritesCommand,
    ClearFavoritesCommand,
    DeleteSavedCalculationCommand,
    RemoveFavoriteCommand,
    SaveCalculationCommand,
    handle_add_favorite,
    handle_bulk_remove_favorites,
    handle_clear_favorites,
    handle_delete_saved_calculation,
    handle_remove_favorite,
    handle_save_calculation,
)
from application.errors import ServiceError, domain_to_http
from application.queries.client import (
    ListFavoritesQuery,
    ListSavedCalculationsQuery,
    handle_list_favorites,
    handle_list_saved_calculations,
)
from domain.errors import DomainError
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.schemas.client import (
    BulkRemoveFavoritesResponse,
    FavoriteAddedResponse,
    FavoritesListResponse,
    SaveCalculationRequest,
    SavedCalculationOut,
    SavedCalculationsListResponse,
)

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _allowed_role(user: dict[str, Any]) -> bool:
    """Both clients and CarCraft employees may use these endpoints."""
    return user.get("role") in {"client", "carcraft_employee"}


def _ensure_role(user: dict[str, Any]) -> None:
    if not _allowed_role(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав доступа")


# ---------------------------------------------------------------------------
# Phone change
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 15 H3 — /profile/send-sms and /profile/phone-change/verify deleted.
# Phone-change is canonical at POST /users/me/phone-change{,/verify}; the
# shared RequestPhoneChangeCommand / VerifyPhoneChangeCommand handlers stay
# behind the unified users router.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Saved calculations
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 15 H3 — /saved-calculations {GET,POST,DELETE /{id}} endpoints
# deleted; only the canonical /calculations surface remains.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


@router.get(
    "/favorites",
    response_model=FavoritesListResponse,
    summary="Избранные автомобили",
    description=(
        "Возвращает список автомобилей в избранном текущего пользователя "
        "с базовыми полями ТС (mark/model/complectation/price/images)."
    ),
)
async def list_favorites(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    _ensure_role(user)
    items = await handle_list_favorites(
        ListFavoritesQuery(user_id=user["id"], scope=scope), session
    )
    return JSONResponse(content=jsonable_encoder({"favorites": items}))


@router.delete(
    "/favorites",
    response_model=BulkRemoveFavoritesResponse,
    summary="Удалить автомобили из избранного (bulk / clear-all)",
    description=(
        "Коллекционный DELETE. Поведение зависит от query-параметров:\n\n"
        "* `?ids=1&ids=2` — удаляет только указанные ТС (bulk-remove). "
        "Идемпотентно: `removed` отражает число фактически удалённых строк.\n"
        "* Без `ids` — очищает всё избранное текущего юзера. Для защиты "
        "от случайного clear-all требуется `?confirm=true`, иначе 422 "
        "(REST §5).\n\n"
        "Замена RPC-эндпоинтов `POST /favorites/bulk-remove`, "
        "`POST /favorites/clear` и `DELETE /favorites/bulk`."
    ),
)
async def delete_favorites(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    ids: Annotated[list[UUID], Query(default_factory=list)],
    confirm: bool = Query(default=False),
) -> JSONResponse:
    _ensure_role(user)
    if ids:
        removed = await handle_bulk_remove_favorites(
            BulkRemoveFavoritesCommand(
                user_id=user["id"],
                vehicle_ids=tuple(ids),
                scope=scope,
            ),
            session,
        )
        await session.commit()
        return JSONResponse(content={"removed": removed})
    if not confirm:
        raise HTTPException(
            status_code=422,
            detail=(
                "Очистка всего избранного требует явного подтверждения "
                "`?confirm=true`."
            ),
        )
    cleared = await handle_clear_favorites(
        ClearFavoritesCommand(user_id=user["id"], scope=scope), session
    )
    await session.commit()
    return JSONResponse(content={"removed": cleared})


# ---------------------------------------------------------------------------
# Phase 15 H3 — /favorites/{id}/check deleted; the frontend tracks the set
# of favoured vehicle ids in the pinia store and no longer round-trips.
# ---------------------------------------------------------------------------


@router.post(
    "/favorites/{product_id}",
    response_model=FavoriteAddedResponse,
    status_code=201,
    summary="Добавить товар в избранное",
    description=(
        "Добавляет товар в избранное. 409 если товар уже в избранном; "
        "уникальность гарантирует уникальный индекс `(user_id, product_id)`."
    ),
)
async def add_favorite(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    product_id: Annotated[UUID, Path()],
) -> JSONResponse:
    _ensure_role(user)
    v_kw = "product_id" if "product_id" in getattr(AddFavoriteCommand, "__dataclass_fields__", {}) else "vehicle_id"
    try:
        added = await handle_add_favorite(
            AddFavoriteCommand(
                user_id=user["id"],
                scope=scope,
                **{v_kw: product_id},
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    if isinstance(added, dict) and "product_id" not in added and "vehicle_id" in added:
        added["product_id"] = added["vehicle_id"]
    return JSONResponse(status_code=201, content=jsonable_encoder(added))


@router.delete(
    "/favorites/{product_id}",
    status_code=204,
    summary="Убрать товар из избранного",
    description=(
        "Идемпотентное удаление: 204 даже если товар не был в избранном. "
        "Express возвращал такое же поведение (без 404)."
    ),
)
async def remove_favorite(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    product_id: Annotated[UUID, Path()],
) -> JSONResponse:
    _ensure_role(user)
    v_kw = "product_id" if "product_id" in getattr(RemoveFavoriteCommand, "__dataclass_fields__", {}) else "vehicle_id"
    await handle_remove_favorite(
        RemoveFavoriteCommand(
            user_id=user["id"],
            scope=scope,
            **{v_kw: product_id},
        ),
        session,
    )
    await session.commit()
    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# Phase 7a — G4 additions (phone-change POST aliases / calculations)
# ---------------------------------------------------------------------------


@router.get(
    "/calculations",
    response_model=SavedCalculationsListResponse,
    summary="Сохранённые расчёты (alias на /saved-calculations)",
    description="Express-совместимый alias на `GET /saved-calculations`.",
)
async def list_calculations_alias(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _ensure_role(user)
    items = await handle_list_saved_calculations(
        ListSavedCalculationsQuery(user_id=user["id"]), session
    )
    return JSONResponse(content=jsonable_encoder({"calculations": items}))


@router.post(
    "/calculations",
    response_model=SavedCalculationOut,
    status_code=201,
    summary="Сохранить расчёт (alias на POST /saved-calculations)",
    description="Express-совместимый POST-alias на `POST /saved-calculations`.",
)
async def save_calculation_alias(
    body: SaveCalculationRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _ensure_role(user)
    try:
        result = await handle_save_calculation(
            SaveCalculationCommand(
                user_id=user["id"],
                name=body.name,
                params=body.params,
                calculation=body.calculation,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        status_code=201,
        content=jsonable_encoder(result.saved),
    )


@router.delete(
    "/calculations/{calculation_id}",
    status_code=204,
    summary="Удалить расчёт (alias на DELETE /saved-calculations/{id})",
    description=(
        "Express-совместимый alias на `DELETE /saved-calculations/{id}`."
    ),
)
async def delete_calculation_alias(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    calculation_id: Annotated[UUID, Path()],
) -> JSONResponse:
    _ensure_role(user)
    try:
        await handle_delete_saved_calculation(
            DeleteSavedCalculationCommand(
                user_id=user["id"],
                calculation_id=calculation_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(status_code=204, content=None)
