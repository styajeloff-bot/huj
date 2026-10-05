"""/api/v1/cart/* — per-user shopping cart (dealer / client / employee).

All endpoints are auth-gated and strictly user-scoped: every mutation
targets rows where ``shopping_cart.user_id == current_user.id``.

Phase 10 R5 consolidation:
    * ``POST /add`` replaced with ``POST /`` (resource create, 201).
    * Three sub-field PATCH endpoints (``/{id}/quantity``, ``/price``,
      ``/comment``) and the is_selected ``PUT /{id}`` collapsed into a
      single ``PATCH /{product_id}`` with an optional-fields body.
    * ``GET /count``, ``GET /check/{vid}``, ``GET /summary``,
      ``GET /available-count/{vid}`` removed — count projection lives on
      ``GET /?fields=count``; in-cart checks move client-side; the
      summary / available-count endpoints were backend orphans.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.cart import (
    AddToCartCommand,
    BulkUpdateCartSelectionCommand,
    ClearCartCommand,
    RemoveFromCartCommand,
    TransferGuestCartCommand,
    UpdateCartItemCommand,
    handle_add_to_cart,
    handle_bulk_update_cart_selection,
    handle_clear_cart,
    handle_remove_from_cart,
    handle_transfer_guest_cart,
    handle_update_cart_item,
)
from application.errors import ServiceError, domain_to_http
from application.queries.cart import (
    GetCartCountQuery,
    GetCartQuery,
    handle_get_cart,
    handle_get_cart_count,
)
from domain.errors import DomainError
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user
from presentation.dependencies.storefront import resolve_catalog_scope
from presentation.schemas.cart import (
    AddToCartRequest,
    AddToCartResponse,
    BulkUpdateCartRequest,
    BulkUpdateCartResponse,
    CartListResponse,
    ClearCartResponse,
    GuestCartTransferRequest,
    GuestCartTransferResponse,
    PatchCartItemRequest,
    RemoveFromCartResponse,
    UpdateCartItemResponse,
)

router = APIRouter()

# Roles authorized to use the cart. Mirrors Express ``requireRole``.
_ALLOWED_ROLES: frozenset[str] = frozenset(
    {"dealer", "client", "carcraft_employee"}
)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _ensure_role(user: dict[str, Any]) -> None:
    if user.get("role") not in _ALLOWED_ROLES:
        raise HTTPException(
            status_code=403, detail="Недостаточно прав доступа"
        )


def _cart_path(scope: CatalogScope, suffix: str = "") -> str:
    prefix = (
        "/api/v1/cart"
        if scope.is_default
        else f"/api/v1/storefronts/{scope.slug}/cart"
    )
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=CartListResponse,
    summary="Содержимое корзины",
    description=(
        "Возвращает все позиции корзины текущего пользователя с базовыми "
        "полями автомобиля (цена, марка, модель, комплектация, цвет, VIN, "
        "изображения). Сортировка — по дате добавления убыванием. "
        "Поддерживает лёгкую проекцию ``?fields=count`` — в этом режиме "
        "отдаётся только `{count: N}` (число активных позиций, т.е. "
        "автомобилей с ``is_available = TRUE``)."
    ),
)
async def get_cart(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    fields: Annotated[
        Literal["count"] | None,
        Query(description="Лёгкая проекция: ``count`` → `{count: N}`."),
    ] = None,
) -> JSONResponse:
    _ensure_role(user)
    if fields == "count":
        count = await handle_get_cart_count(
            GetCartCountQuery(user_id=user["id"], scope=scope), session
        )
        return JSONResponse(content={"count": count})
    items = await handle_get_cart(
        GetCartQuery(user_id=user["id"], scope=scope), session
    )
    return JSONResponse(content=jsonable_encoder({"items": items}))


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@router.put(
    "/guest-transfers/{transfer_id}",
    response_model=GuestCartTransferResponse,
    summary="Перенести позицию гостевой корзины",
    description=(
        "Идемпотентно применяет количество и дополнительные опции. "
        "Первое применение возвращает 201, идентичный повтор — 200 без "
        "изменения корзины, другой payload для того же transfer_id — 409."
    ),
)
async def transfer_guest_cart_item(
    body: GuestCartTransferRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    transfer_id: Annotated[UUID, Path()],
) -> JSONResponse:
    _ensure_role(user)
    payload = body.model_dump(mode="json")
    pid = getattr(body, "product_id", getattr(body, "vehicle_id", None))
    v_kw = "product_id" if "product_id" in getattr(TransferGuestCartCommand, "__dataclass_fields__", {}) else "vehicle_id"
    transfer_cmd_args: dict[str, Any] = {
        "user_id": user["id"],
        "transfer_id": transfer_id,
        "quantity": body.quantity,
        "allow_overstock": body.allow_overstock,
        "equipments": payload["equipments"],
        "services": payload["services"],
        "scope": scope,
        v_kw: pid,
    }
    try:
        result = await handle_transfer_guest_cart(
            TransferGuestCartCommand(**transfer_cmd_args),  # type: ignore[arg-type]
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        status_code=201 if result.applied else 200,
        headers={"Location": _cart_path(scope, f"/guest-transfers/{transfer_id}")},
        content=jsonable_encoder(
            {
                "transfer_id": result.transfer_id,
                "applied": result.applied,
                "cart_item": result.cart_item,
            }
        ),
    )


@router.post(
    "/",
    response_model=AddToCartResponse,
    status_code=201,
    summary="Добавить товар в корзину",
    description=(
        "Создаёт позицию `(user_id, product_id)`. Если позиция уже "
        "существует — количество увеличивается на `quantity` (upsert). "
        "Возвращает `201` с телом созданной/обновлённой позиции и "
        "заголовком `Location: /api/v1/cart/{product_id}`. `404` если "
        "товар не существует, `422` при `quantity < 1`."
    ),
)
async def create_cart_item(
    body: AddToCartRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    _ensure_role(user)
    pid = getattr(body, "product_id", getattr(body, "vehicle_id", None))
    v_kw = "product_id" if "product_id" in getattr(AddToCartCommand, "__dataclass_fields__", {}) else "vehicle_id"
    add_cmd_args: dict[str, Any] = {
        "user_id": user["id"],
        "quantity": body.quantity,
        "allow_overstock": body.allow_overstock,
        "scope": scope,
        v_kw: pid,
    }
    try:
        result = await handle_add_to_cart(
            AddToCartCommand(**add_cmd_args),  # type: ignore[arg-type]
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()

    message = (
        "Товар добавлен в корзину"
        if result.created
        else "Количество товара в корзине обновлено"
    )
    headers = {"Location": _cart_path(scope, f"/{pid}")}
    return JSONResponse(
        status_code=201,
        headers=headers,
        content=jsonable_encoder(
            {
                "message": message,
                "cart_item": result.cart_item,
                "created": result.created,
            }
        ),
    )


@router.patch(
    "/",
    response_model=BulkUpdateCartResponse,
    summary="Массовое обновление выбранности позиций",
    description=(
        "Атомарно выставляет `is_selected` для множества позиций. "
        "Позиции, не принадлежащие текущему пользователю, молча "
        "пропускаются — ответ содержит только реально обновлённые строки."
    ),
)
async def bulk_update_cart(
    body: BulkUpdateCartRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    _ensure_role(user)
    items: list[tuple[UUID, bool]] = [
        (item.product_id, item.is_selected)
        for item in body.items
    ]
    updated = await handle_bulk_update_cart_selection(
        BulkUpdateCartSelectionCommand(
            user_id=user["id"], items=items, scope=scope
        ),
        session,
    )
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(
            {"message": "Корзина обновлена", "updated_items": updated}
        )
    )


@router.patch(
    "/{product_id}",
    response_model=UpdateCartItemResponse,
    summary="Частичное обновление позиции корзины",
    description=(
        "Изменяет любое подмножество полей позиции в одном запросе: "
        "`is_selected`, `quantity`, `custom_price` (для ролей `dealer` / "
        "`carcraft_employee`, а также для `client`, если у товара "
        "`base_price` равен `0` или `NULL`), `comment` (`null` или пустая "
        "строка очищает). Отсутствующие в теле поля сохраняют своё "
        "значение. `404` — позиция не найдена, `403` — клиенту запрещено "
        "менять `custom_price` у платного товара, `422` — некорректные "
        "значения."
    ),
)
async def update_cart_item(
    body: PatchCartItemRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    product_id: Annotated[UUID, Path()],
) -> JSONResponse:
    _ensure_role(user)
    v_kw = "product_id" if "product_id" in getattr(UpdateCartItemCommand, "__dataclass_fields__", {}) else "vehicle_id"
    cmd_kwargs: dict[str, Any] = {
        "user_id": user["id"],
        v_kw: product_id,
        "role": user.get("role"),
        "is_selected": body.is_selected,
        "quantity": body.quantity,
        "allow_overstock": body.allow_overstock,
        "scope": scope,
    }
    data = body.model_dump(exclude_unset=True)
    if "comment" in data:
        cmd_kwargs["comment"] = body.comment
    if "custom_price" in data:
        cmd_kwargs["custom_price"] = body.custom_price
    if "equipments" in data:
        cmd_kwargs["equipments"] = jsonable_encoder(body.equipments or [])
    if "services" in data:
        cmd_kwargs["services"] = jsonable_encoder(body.services or [])
    try:
        updated = await handle_update_cart_item(
            UpdateCartItemCommand(**cmd_kwargs), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(
        content=jsonable_encoder(
            {"message": "Позиция корзины обновлена", "cart_item": updated}
        )
    )


@router.delete(
    "/{product_id}",
    response_model=RemoveFromCartResponse,
    summary="Удалить позицию из корзины",
    description=(
        "Идемпотентное удаление: 200 и `removed = false`, если позиции "
        "не было в корзине; 200 и `removed = true`, если строка удалена."
    ),
)
async def remove_from_cart(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
    product_id: Annotated[UUID, Path()],
) -> JSONResponse:
    _ensure_role(user)
    v_kw = "product_id" if "product_id" in getattr(RemoveFromCartCommand, "__dataclass_fields__", {}) else "vehicle_id"
    removed = await handle_remove_from_cart(
        RemoveFromCartCommand(
            user_id=user["id"], scope=scope, **{v_kw: product_id}
        ),
        session,
    )
    await session.commit()
    return JSONResponse(
        content={
            "message": (
                "Товар удален из корзины"
                if removed
                else "Товар не найден в корзине"
            ),
            "removed": removed,
        }
    )


@router.delete(
    "/",
    response_model=ClearCartResponse,
    summary="Очистить корзину",
    description=(
        "Удаляет все позиции корзины текущего пользователя. "
        "`deleted_count` отражает фактическое число удалённых строк."
    ),
)
async def clear_cart(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    scope: Annotated[CatalogScope, Depends(resolve_catalog_scope)],
) -> JSONResponse:
    _ensure_role(user)
    deleted = await handle_clear_cart(
        ClearCartCommand(user_id=user["id"], scope=scope), session
    )
    await session.commit()
    return JSONResponse(
        content={"message": "Корзина очищена", "deleted_count": deleted}
    )
