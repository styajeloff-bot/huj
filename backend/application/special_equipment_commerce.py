"""Use cases for favorites, cart, leasing and purchase of special equipment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications.display_number import (
    assign_display_number_if_missing,
)
from application.commands.calculator.calculate import (
    compute_canonical_application_calculation,
)
from application.errors import ServiceError
from application.services.application_source import resolve_application_source
from application.services.questionnaire import refresh_questionnaire
from application.special_equipment_checkout import (
    CheckoutAllocationError,
    allocate_cart_items,
    available_count_for_representative,
)
from application.special_equipment_urls import public_special_equipment_detail_url
from domain.application_sources import SOURCE_VIEW_ROLES
from domain.leasing_purposes import selected_purposes
from domain.questionnaire import initial_values
from domain.services.object_storage import ObjectStorage, StoredObject
from domain.special_equipment_commerce import (
    SPECIAL_EQUIPMENT_MAX_CART_QUANTITY,
    ProductCommerceState,
    SpecialEquipmentCartConfigurationConflictError,
    SpecialEquipmentIdempotencyConflictError,
    SpecialEquipmentOrderNotFoundError,
    SpecialEquipmentOrderStateError,
    SpecialEquipmentOrderStatus,
    SpecialEquipmentProductNotFoundError,
    SpecialEquipmentPurchaseType,
    SpecialEquipmentRefundReferenceConflictError,
    compute_order_amounts,
    ensure_order_can_cancel,
    ensure_order_owned,
)
from domain.special_equipment_kits import kit_title
from domain.special_equipment_leasing import build_leasing_schedule
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import (
    application_repository as app_repo,
)
from infrastructure.repositories import (
    company_repository as company_repo,
)
from infrastructure.repositories import (
    special_equipment_commerce_repository as repo,
)
from infrastructure.services import payment_gateway

PAYMENT_HOLD_MINUTES = 30
_COMPANY_ACCESS_OVERRIDE_ROLES = frozenset({"carcraft_employee", "admin"})
_MONEY = Decimal("0.01")


def _request_hash(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _gateway_response_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return cast(
            "dict[str, Any]",
            value.model_dump(mode="json", by_alias=True),
        )
    return dict(value)


async def _payment_checkout_data(
    payment: dict[str, Any],
    session: AsyncSession,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return response additions plus the refreshed payment row."""

    if payment.get("status") != "pending":
        return {}, payment
    stored = (payment.get("gateway_response") or {}).get("checkout")
    if isinstance(stored, dict):
        return dict(stored), payment

    method = payment.get("payment_method")
    checkout: dict[str, Any]
    if method == "sbp":
        sbp_response = await payment_gateway.request_special_equipment_sbp_link(
            payment["id"],
            session,
        )
        checkout = {"sbpData": _gateway_response_payload(sbp_response)}
    elif method == "card":
        card_response = await payment_gateway.prepare_special_equipment_payment(
            payment["id"],
            session,
        )
        checkout = {"widgetData": _gateway_response_payload(card_response)}
    else:
        return {}, payment

    refreshed = await repo.update_payment(
        session,
        payment["id"],
        {
            "gateway_response": {
                **(payment.get("gateway_response") or {}),
                "checkout": checkout,
            }
        },
    )
    return checkout, refreshed


def _capabilities(row: dict[str, Any]) -> dict[str, bool]:
    is_published = row.get("publication_status") == "published"
    is_available = is_published and row.get("sale_status") == "available"
    is_on_order = is_published and row.get("sale_status") == "on_order"
    has_price = (
        not bool(row.get("price_on_request"))
        and row.get("price") is not None
        and Decimal(str(row["price"])) > 0
    )
    return {
        "can_favorite": is_published,
        "can_add_to_cart": is_available or is_on_order,
        "can_lease": is_available or is_on_order,
        "can_buy": is_available and has_price,
        "can_preorder": (is_available or is_on_order) and has_price,
    }


def _product_card(
    row: dict[str, Any],
    *,
    detail_url_allowed: bool = True,
) -> dict[str, Any]:
    image_id = row.get("primary_image_id")
    product_id = row["product_id"] if "product_id" in row else row["id"]
    return {
        "id": product_id,
        "slug": row.get("slug"),
        "title": (
            kit_title(
                chassis_mark_name=str(row.get("chassis_mark_name") or row.get("mark_name") or ""),
                chassis_model_name=str(row.get("chassis_model_name") or row.get("model_name") or ""),
                superstructure_name=str(row.get("superstructure_name") or ""),
            )
            if row.get("superstructure_id")
            else f"{row.get('mark_name', '')} {row.get('model_name', '')}".strip()
        ),
        "detail_url": (
            public_special_equipment_detail_url(
                product_id,
                row.get("slug"),
                publication_status=row.get("publication_status"),
                sale_status=row.get("sale_status"),
            )
            if detail_url_allowed
            else None
        ),
        "mark": {
            "id": row.get("mark_id"),
            "name": row.get("mark_name"),
        },
        "model": {
            "id": row.get("model_id"),
            "name": row.get("model_name"),
        },
        "modification": (
            {
                "id": row.get("modification_id"),
                "name": row.get("modification_name"),
            }
            if row.get("modification_id")
            else None
        ),
        "superstructure": (
            {
                "id": row.get("superstructure_id"),
                "name": row.get("superstructure_name"),
                "type_name": row.get("superstructure_type_name"),
                "manufacturer": row.get("superstructure_manufacturer"),
            }
            if row.get("superstructure_id")
            else None
        ),
        "trim": (
            {
                "id": row.get("trim_id"),
                "name": row.get("trim_name"),
            }
            if row.get("trim_id") and row.get("trim_name")
            else None
        ),
        "manufacture_year": row.get("manufacture_year"),
        "body_color": (
            {
                "id": row.get("body_color_id"),
                "name": row.get("body_color_name"),
            }
            if row.get("body_color_id") and row.get("body_color_name")
            else None
        ),
        "price": row.get("price"),
        "base_price": row.get("base_price"),
        "special_price": row.get("special_price"),
        "price_on_request": bool(row.get("price_on_request")),
        "price_from": row.get("price_from"),
        "currency_code": row.get("currency_code") or "RUB",
        "publication_status": row.get("publication_status"),
        "sale_status": row.get("sale_status"),
        "primary_image": (
            {
                "id": image_id,
                "content_url": f"/api/v1/special-equipment/images/{image_id}/content",
            }
            if image_id
            else None
        ),
        "capabilities": _capabilities(row),
    }


async def _load_product(
    session: AsyncSession, product_id: UUID, *, lock: bool = False
) -> tuple[dict[str, Any], ProductCommerceState]:
    row = await repo.get_product(session, product_id, lock=lock)
    if row is None:
        raise SpecialEquipmentProductNotFoundError()
    return row, ProductCommerceState.from_dict(row)


@dataclass(frozen=True, slots=True)
class UserProductCommand:
    user_id: UUID
    product_id: UUID


async def list_favorites(
    user_id: UUID,
    session: AsyncSession,
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> list[dict[str, Any]]:
    rows = await repo.list_favorites(session, user_id)
    visible_ids = await repo.product_ids_visible_in_scope(
        session,
        tuple(row["product_id"] for row in rows),
        scope,
    )
    return [
        {
            "product_id": row["product_id"],
            "product": _product_card(
                row,
                detail_url_allowed=row["product_id"] in visible_ids,
            ),
            "added_at": row["added_at"],
        }
        for row in rows
    ]


async def put_favorite(
    cmd: UserProductCommand,
    session: AsyncSession,
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> dict[str, Any]:
    row, state = await _load_product(session, cmd.product_id)
    state.ensure_catalog_action_allowed()
    created = await repo.put_favorite(session, cmd.user_id, cmd.product_id)
    visible = await repo.product_visible_in_scope(session, cmd.product_id, scope)
    return {
        "created": created,
        "product": _product_card(
            {**row, "product_id": row["id"]},
            detail_url_allowed=visible,
        ),
    }


async def delete_favorite(cmd: UserProductCommand, session: AsyncSession) -> bool:
    return bool(await repo.delete_favorite(session, cmd.user_id, cmd.product_id))


async def clear_favorites(
    user_id: UUID,
    session: AsyncSession,
) -> int:
    return int(await repo.clear_favorites(session, user_id))


@dataclass(frozen=True, slots=True)
class PutCartItemCommand:
    user_id: UUID
    product_id: UUID
    quantity: int = 1
    allow_overstock: bool = False
    parent_item_id: UUID | None = None
    transfer_id: UUID | None = None
    is_selected: bool = True
    comment: str | None = None
    equipments: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PatchCartItemCommand:
    user_id: UUID
    cart_item_id: UUID
    actor_role: str
    changes: dict[str, Any]


async def list_cart(
    user_id: UUID,
    session: AsyncSession,
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> list[dict[str, Any]]:
    rows = await repo.list_cart_items(session, user_id)
    visible_ids = await repo.product_ids_visible_in_scope(
        session,
        tuple(row["product_id"] for row in rows),
        scope,
    )
    return [
        {
            "id": row["id"],
            "product_id": row["product_id"],
            "quantity": row["quantity"],
            "allow_overstock": bool(row.get("allow_overstock", False)),
            "parent_item_id": row.get("parent_item_id"),
            "transfer_id": row.get("transfer_id"),
            "is_selected": row["is_selected"],
            "custom_price": row.get("custom_price"),
            "comment": row.get("comment"),
            "equipments": row.get("equipments") or [],
            "services": row.get("services") or [],
            "added_at": row["added_at"],
            "updated_at": row["updated_at"],
            "product": _product_card(
                row,
                detail_url_allowed=row["product_id"] in visible_ids,
            ),
        }
        for row in rows
    ]


async def put_cart_item(
    cmd: PutCartItemCommand,
    session: AsyncSession,
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> dict[str, Any]:
    if cmd.quantity < 1 or cmd.quantity > SPECIAL_EQUIPMENT_MAX_CART_QUANTITY:
        raise ServiceError(
            f"Количество должно быть от 1 до {SPECIAL_EQUIPMENT_MAX_CART_QUANTITY}",
            422,
            code="CART_QUANTITY_OUT_OF_RANGE",
        )
    if cmd.allow_overstock and cmd.parent_item_id is not None:
        raise ServiceError(
            "Для надстроек нельзя указать количество сверх наличия",
            422,
            code="OVERSTOCK_NOT_ALLOWED_FOR_ATTACHMENT",
        )
    row, state = await _load_product(session, cmd.product_id)
    state.ensure_cart_action_allowed()
    eligible_ids: tuple[UUID, ...] | None = None
    if cmd.parent_item_id is not None:
        parent = await repo.get_cart_item(
            session,
            user_id=cmd.user_id,
            cart_item_id=cmd.parent_item_id,
        )
        if parent is None or parent.get("parent_item_id") is not None:
            raise ServiceError("Родительская техника в корзине не найдена", 422)
        eligible_ids = await repo.list_compatible_attachment_ids(
            session,
            UUID(str(parent["product_id"])),
        )
        if cmd.product_id not in eligible_ids:
            raise ServiceError(
                "Надстройка несовместима с выбранной техникой",
                422,
            )
    available = await available_count_for_representative(
        session,
        cmd.product_id,
        eligible_ids=eligible_ids,
    )
    if cmd.allow_overstock:
        if available == 0:
            raise CheckoutAllocationError(
                "Недостаточно доступных эквивалентных единиц",
                code="INSUFFICIENT_EQUIVALENT_PRODUCTS",
                requested=cmd.quantity,
                available=available,
            )
    elif cmd.quantity > available:
        raise CheckoutAllocationError(
            "Недостаточно доступных эквивалентных единиц",
            code="INSUFFICIENT_EQUIVALENT_PRODUCTS",
            requested=cmd.quantity,
            available=available,
        )
    try:
        cart, created = await repo.put_cart_item(
            session,
            user_id=cmd.user_id,
            product_id=cmd.product_id,
            quantity=cmd.quantity,
            parent_item_id=cmd.parent_item_id,
            transfer_id=cmd.transfer_id,
            is_selected=cmd.is_selected,
            comment=cmd.comment,
            equipments=cmd.equipments,
            services=cmd.services,
            allow_overstock=cmd.allow_overstock,
        )
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    visible = await repo.product_visible_in_scope(session, cmd.product_id, scope)
    return {
        "created": created,
        "cart_item": {
            **cart,
            "product": _product_card(
                {**row, "product_id": row["id"]},
                detail_url_allowed=visible,
            ),
        },
    }


async def patch_cart_item(  # noqa: PLR0912 -- explicit cart updates
    cmd: PatchCartItemCommand, session: AsyncSession
) -> dict[str, Any]:
    allowed = {
        "quantity",
        "allow_overstock",
        "parent_item_id",
        "is_selected",
        "comment",
        "equipments",
        "services",
    }
    changes = {key: value for key, value in cmd.changes.items() if key in allowed}
    if "custom_price" in cmd.changes:
        if cmd.actor_role not in {"dealer", "carcraft_employee"}:
            raise ServiceError("Изменять цену может только дилер или сотрудник", 403)
        changes["custom_price"] = cmd.changes["custom_price"]
    current = await repo.get_cart_item(
        session,
        user_id=cmd.user_id,
        cart_item_id=cmd.cart_item_id,
    )
    if current is None:
        raise ServiceError("Позиция спецтехники не найдена в корзине", 404)
    if "quantity" in changes or "parent_item_id" in changes or "allow_overstock" in changes:
        parent_item_id = (
            changes["parent_item_id"]
            if "parent_item_id" in changes
            else current.get("parent_item_id")
        )
        effective_allow_overstock = (
            bool(changes["allow_overstock"])
            if "allow_overstock" in changes
            else bool(current.get("allow_overstock", False))
        )
        if effective_allow_overstock and parent_item_id is not None:
            raise ServiceError(
                "Для надстроек нельзя указать количество сверх наличия",
                422,
                code="OVERSTOCK_NOT_ALLOWED_FOR_ATTACHMENT",
            )
        quantity = int(changes.get("quantity", current["quantity"]))
        if quantity < 1 or quantity > SPECIAL_EQUIPMENT_MAX_CART_QUANTITY:
            raise ServiceError(
                f"Количество должно быть от 1 до {SPECIAL_EQUIPMENT_MAX_CART_QUANTITY}",
                422,
                code="CART_QUANTITY_OUT_OF_RANGE",
            )
        eligible_ids: tuple[UUID, ...] | None = None
        if parent_item_id is not None:
            parent = await repo.get_cart_item(
                session,
                user_id=cmd.user_id,
                cart_item_id=UUID(str(parent_item_id)),
            )
            if parent is None or parent.get("parent_item_id") is not None:
                raise ServiceError("Родительская техника в корзине не найдена", 422)
            eligible_ids = await repo.list_compatible_attachment_ids(
                session,
                UUID(str(parent["product_id"])),
            )
            if UUID(str(current["product_id"])) not in eligible_ids:
                raise ServiceError(
                    "Надстройка несовместима с выбранной техникой",
                    422,
                )
        available = await available_count_for_representative(
            session,
            UUID(str(current["product_id"])),
            eligible_ids=eligible_ids,
        )
        if (
            "allow_overstock" in changes
            and not changes["allow_overstock"]
            and current.get("allow_overstock")
            and quantity > available
        ):
            quantity = max(1, available)
            changes["quantity"] = quantity
            effective_allow_overstock = False
        if effective_allow_overstock:
            if available == 0:
                raise CheckoutAllocationError(
                    "Недостаточно доступных эквивалентных единиц",
                    code="INSUFFICIENT_EQUIVALENT_PRODUCTS",
                    requested=quantity,
                    available=available,
                )
        elif quantity > available:
            raise CheckoutAllocationError(
                "Недостаточно доступных эквивалентных единиц",
                code="INSUFFICIENT_EQUIVALENT_PRODUCTS",
                requested=quantity,
                available=available,
            )
    try:
        updated = await repo.patch_cart_item(
            session,
            user_id=cmd.user_id,
            cart_item_id=cmd.cart_item_id,
            changes=changes,
        )
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    if updated is None:
        raise ServiceError("Позиция спецтехники не найдена в корзине", 404)
    return dict(updated)


@dataclass(frozen=True, slots=True)
class DeleteCartItemCommand:
    user_id: UUID
    cart_item_id: UUID


async def delete_cart_item(cmd: DeleteCartItemCommand, session: AsyncSession) -> bool:
    return bool(await repo.delete_cart_item(session, cmd.user_id, cmd.cart_item_id))


@dataclass(frozen=True, slots=True)
class TransferGuestCartCommand:
    user_id: UUID
    transfer_id: UUID
    version: int
    items: tuple[dict[str, Any], ...]
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


def _transfer_payload(cmd: TransferGuestCartCommand) -> dict[str, Any]:
    return {
        "version": cmd.version,
        "items": [
            {
                **item,
                "local_id": str(item["local_id"]),
                "product_id": str(item["product_id"]),
                "parent_local_id": (
                    str(item["parent_local_id"])
                    if item.get("parent_local_id") is not None
                    else None
                ),
            }
            for item in cmd.items
        ],
    }


async def transfer_guest_cart(
    cmd: TransferGuestCartCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Idempotently materialize a versioned local cart after authentication."""

    if cmd.version != 2:
        raise ServiceError("Поддерживается только гостевая корзина версии 2", 422)
    local_ids = [UUID(str(item["local_id"])) for item in cmd.items]
    if len(local_ids) != len(set(local_ids)):
        raise ServiceError("Локальную позицию нельзя передать дважды", 422)
    by_local_id = {
        UUID(str(item["local_id"])): item
        for item in cmd.items
    }
    for local_id, item in by_local_id.items():
        parent_value = item.get("parent_local_id")
        if parent_value is None:
            continue
        parent_id = UUID(str(parent_value))
        parent = by_local_id.get(parent_id)
        if parent_id == local_id or parent is None:
            raise ServiceError("Некорректная родительская позиция корзины", 422)
        if parent.get("parent_local_id") is not None:
            raise ServiceError("Вложенные группы корзины не поддерживаются", 422)
    logical_positions = [
        (
            UUID(str(item["product_id"])),
            UUID(str(item["parent_local_id"]))
            if item.get("parent_local_id") is not None
            else None,
        )
        for item in cmd.items
    ]
    if len(logical_positions) != len(set(logical_positions)):
        raise ServiceError(
            "Одинаковый товар нельзя передать дважды в одной группе корзины",
            422,
        )

    configuration_by_product: dict[UUID, tuple[Any, ...]] = {}
    for item in cmd.items:
        product_id = UUID(str(item["product_id"]))
        configuration = (
            None,
            item.get("comment"),
            item.get("equipments") or [],
            item.get("services") or [],
        )
        existing_configuration = configuration_by_product.setdefault(
            product_id, configuration
        )
        if existing_configuration != configuration:
            raise SpecialEquipmentCartConfigurationConflictError()

    request_hash = _request_hash(_transfer_payload(cmd))
    await repo.lock_guest_cart_transfer(session, cmd.user_id, cmd.transfer_id)
    receipt = await repo.get_guest_cart_transfer(
        session,
        cmd.user_id,
        cmd.transfer_id,
    )
    if receipt is not None:
        if receipt["request_hash"] != request_hash:
            raise ServiceError(
                "transfer_id уже использован для другой гостевой корзины",
                409,
            )
        stored = dict(receipt["result"])
        return {
            "transfer_id": cmd.transfer_id,
            "replayed": True,
            "item_ids": stored["item_ids"],
            "items": await list_cart(cmd.user_id, session, scope=cmd.scope),
        }

    ordered = sorted(
        cmd.items,
        key=lambda item: (item.get("parent_local_id") is not None, str(item["local_id"])),
    )
    server_ids: dict[UUID, UUID] = {}
    for item in ordered:
        local_id = UUID(str(item["local_id"]))
        parent_local_id = item.get("parent_local_id")
        parent_item_id = (
            server_ids[UUID(str(parent_local_id))]
            if parent_local_id is not None
            else None
        )
        result = await put_cart_item(
            PutCartItemCommand(
                user_id=cmd.user_id,
                product_id=UUID(str(item["product_id"])),
                quantity=int(item["quantity"]),
                allow_overstock=bool(item.get("allow_overstock", False)),
                parent_item_id=parent_item_id,
                transfer_id=cmd.transfer_id,
                is_selected=bool(item.get("is_selected", True)),
                comment=item.get("comment"),
                equipments=list(item.get("equipments") or []),
                services=list(item.get("services") or []),
            ),
            session,
            scope=cmd.scope,
        )
        server_ids[local_id] = UUID(str(result["cart_item"]["id"]))

    stored_result = {
        "item_ids": {
            str(local_id): str(server_id)
            for local_id, server_id in server_ids.items()
        }
    }
    await repo.create_guest_cart_transfer(
        session,
        user_id=cmd.user_id,
        transfer_id=cmd.transfer_id,
        request_hash=request_hash,
        result=stored_result,
    )
    return {
        "transfer_id": cmd.transfer_id,
        "replayed": False,
        "item_ids": stored_result["item_ids"],
        "items": await list_cart(cmd.user_id, session, scope=cmd.scope),
    }


async def clear_cart(
    user_id: UUID,
    session: AsyncSession,
) -> int:
    return int(await repo.clear_cart(session, user_id))


@dataclass(frozen=True, slots=True)
class CreateLeasingApplicationCommand:
    user_id: UUID
    source_type: str
    company_id: UUID
    actor_role: str | None = None
    allow_dealer_client_company: bool = False
    comment: str | None = None
    leasing_purpose: str | None = None
    leasing_purposes: list[str] | None = None
    regions: list[str] = field(default_factory=list)
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    cart_item_ids: tuple[UUID, ...] = ()
    product_id: UUID | None = None
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def _normalize_leasing_purpose(
    purpose: str | None,
    session: AsyncSession,
) -> str | None:
    if not purpose:
        return None
    valid_purposes = {
        row["purpose_name"]
        for row in await app_repo.list_leasing_purposes(session)
    }
    return purpose if purpose in valid_purposes else None


async def _initialize_leasing_questionnaire(
    session: AsyncSession, application_id: UUID,
) -> None:
    await app_repo.upsert_questionnaire(
        session, application_id=application_id, payload=initial_values(), source="system",
    )
    await refresh_questionnaire(session, application_id)


async def create_leasing_application(
    cmd: CreateLeasingApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    if (
        cmd.actor_role not in _COMPANY_ACCESS_OVERRIDE_ROLES
        and not (
            cmd.actor_role == "dealer" and cmd.allow_dealer_client_company
        )
        and not await company_repo.is_user_linked_to_company(
            session,
            cmd.user_id,
            cmd.company_id,
        )
    ):
        raise ServiceError("Нет доступа к выбранной компании", 403)
    if cmd.cart_item_ids:
        return await _create_cart_leasing_application(cmd, session)
    if cmd.product_id is None:
        raise ServiceError("Нужно выбрать позиции серверной корзины", 422)
    # Serialize application creation with admin/import archive. Re-read the
    # commercial state after any in-flight catalog mutation commits, so an
    # active application can never be attached to an archived product.
    row, state = await _load_product(session, cmd.product_id, lock=True)
    state.ensure_leasing_application_allowed()
    financials = await compute_canonical_application_calculation(
        session,
        total_amount=row.get("price"),
        down_payment_percent=cmd.down_payment_percent,
        lease_term_months=cmd.lease_term_months,
    )
    leasing_purposes = selected_purposes(cmd.leasing_purposes, cmd.leasing_purpose)
    leasing_purpose = next(iter(leasing_purposes), None)
    result = await repo.create_leasing_application(
        session,
        actor_id=cmd.user_id,
        company_id=cmd.company_id,
        storefront_id=cmd.scope.id,
        source_type=await resolve_application_source(
            session, requested=cmd.source_type, first_product_id=cmd.product_id,
        ),
        dealer_company_id=state.seller_company_id,
        product=row,
        snapshot=state.snapshot(),
        comment=cmd.comment,
        leasing_purpose=leasing_purpose,
        leasing_purposes=leasing_purposes,
        regions=cmd.regions,
        down_payment_percent=cmd.down_payment_percent,
        lease_term_months=cmd.lease_term_months,
        financials=financials,
    )
    if not result:
        raise ServiceError("Компания для лизинговой заявки не найдена", 404)
    await _initialize_leasing_questionnaire(session, result["application_id"])
    display_number = await assign_display_number_if_missing(
        session,
        application={"id": result["application_id"], "company_id": cmd.company_id},
    )
    result["display_number"] = display_number
    if cmd.actor_role not in SOURCE_VIEW_ROLES:
        result.pop("source_type", None)
    return dict(result)


async def _create_cart_leasing_application(
    cmd: CreateLeasingApplicationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    allocation = await allocate_cart_items(
        session,
        user_id=cmd.user_id,
        cart_item_ids=cmd.cart_item_ids,
        allow_on_order=True,
        allow_overstock=True,
    )
    if not allocation.supports_unpriced_leasing:
        raise ServiceError(
            "Технику без цены можно оформить в лизинг только одной единицей "
            "без автомобилей и других платных позиций",
            422,
        )
    state_by_id: dict[UUID, ProductCommerceState] = {}
    component_ids = {
        component.component_product_id for component in allocation.components
    }
    for product_id in allocation.concrete_product_ids:
        _row, state = await _load_product(session, product_id)
        if product_id not in component_ids:
            state.ensure_leasing_application_allowed()
        state_by_id[product_id] = state
    sellers = {
        state.seller_company_id
        for state in state_by_id.values()
        if state.seller_company_id is not None
    }
    currencies = {state.currency_code for state in state_by_id.values()}
    if len(currencies) > 1:
        raise ServiceError(
            "Одна лизинговая заявка не может объединять товары в разных валютах",
            422,
        )
    header_dealer_company_id = next(iter(sellers)) if len(sellers) == 1 else None
    total = allocation.total
    leasing_purposes = selected_purposes(cmd.leasing_purposes, cmd.leasing_purpose)
    leasing_purpose = next(iter(leasing_purposes), None)
    entries: list[dict[str, Any]] = []
    for line in allocation.cart_lines:
        first_offer = True
        for product in line.products:
            product_id = product["id"]
            state = state_by_id[product_id]
            price = line.agreed_unit_price(product)
            item_role = (
                "attachment"
                if line.parent_cart_item_id is not None
                else "offer"
            )
            overstock_qty = 0
            if item_role == "offer" and first_offer:
                overstock_qty = line.overstock_quantity
                first_offer = False
            entries.append(
                {
                    "product_id": product_id,
                    "source_cart_item_id": line.cart_item_id,
                    "group_id": line.cart_item_id,
                    "parent_group_id": line.parent_cart_item_id,
                    "item_role": item_role,
                    "seller_company_id": state.seller_company_id,
                    "unit_price": price,
                    "total_price": price,
                    "currency_code": state.currency_code,
                    "item_snapshot": state.snapshot(),
                    "comment": cmd.comment,
                    "leasing_purpose": leasing_purpose,
                "leasing_purposes": leasing_purposes,
                    "regions": cmd.regions,
                    "item_status": "active",
                    "overstock_requested_quantity": overstock_qty,
                }
            )
    for component in allocation.components:
        state = state_by_id[component.component_product_id]
        entries.append(
            {
                "product_id": component.component_product_id,
                "source_cart_item_id": component.source_cart_item_id,
                "group_id": component.source_cart_item_id,
                "parent_group_id": component.source_cart_item_id,
                "item_role": "component",
                "seller_company_id": state.seller_company_id,
                "unit_price": Decimal("0.00"),
                "total_price": Decimal("0.00"),
                "currency_code": state.currency_code,
                "item_snapshot": {
                    **state.snapshot(),
                    "composite_product_id": str(component.composite_product_id),
                    "is_base": component.is_base,
                },
                "comment": cmd.comment,
                "leasing_purpose": leasing_purpose,
                "leasing_purposes": leasing_purposes,
                "regions": cmd.regions,
                "item_status": "active",
            }
        )
    financials = await compute_canonical_application_calculation(
        session,
        total_amount=total,
        down_payment_percent=cmd.down_payment_percent,
        lease_term_months=cmd.lease_term_months,
    )
    result = await repo.create_leasing_application_from_items(
        session,
        actor_id=cmd.user_id,
        company_id=cmd.company_id,
        storefront_id=cmd.scope.id,
        source_type=await resolve_application_source(
            session, requested=cmd.source_type,
            first_product_id=next(
                (entry["product_id"] for entry in entries
                 if entry["source_cart_item_id"] == cmd.cart_item_ids[0]
                 and entry["item_role"] == "offer"),
                None,
            ),
        ),
        dealer_company_id=header_dealer_company_id,
        total_amount=total,
        down_payment_percent=cmd.down_payment_percent,
        lease_term_months=cmd.lease_term_months,
        item_entries=entries,
        financials=financials,
    )
    if not result:
        raise ServiceError("Компания для лизинговой заявки не найдена", 404)
    await _initialize_leasing_questionnaire(session, result["application_id"])
    display_number = await assign_display_number_if_missing(
        session,
        application={"id": result["application_id"], "company_id": cmd.company_id},
    )
    result["display_number"] = display_number
    await repo.delete_cart_items_by_ids(
        session,
        user_id=cmd.user_id,
        cart_item_ids=cmd.cart_item_ids,
    )
    if cmd.actor_role not in SOURCE_VIEW_ROLES:
        result.pop("source_type", None)
    return dict(result)


def _required_leasing_money(
    proposal: dict[str, Any], key: str, *, allow_zero: bool = False
) -> Decimal:
    value = proposal.get(key)
    if value is None:
        raise ServiceError(
            f"В принятом итоговом КП не заполнено поле {key}",
            422,
        )
    amount = _money(value)
    if amount < 0 or (not allow_zero and amount == 0):
        raise ServiceError(
            f"В принятом итоговом КП некорректно поле {key}",
            422,
        )
    return amount


@dataclass(frozen=True, slots=True)
class _AcceptedLeasingTerms:
    proposal_id: UUID
    principal: Decimal
    total_cost: Decimal
    down_payment: Decimal
    monthly_payment: Decimal
    buyout_amount: Decimal
    term_months: int
    down_payment_percent: Decimal | None


def _accepted_leasing_terms(proposal: dict[str, Any]) -> _AcceptedLeasingTerms:
    principal = _required_leasing_money(proposal, "total_amount")
    total_cost = _required_leasing_money(proposal, "total_cost")
    raw_term = proposal.get("lease_term_months")
    if not isinstance(raw_term, int) or raw_term < 1:
        raise ServiceError("В принятом итоговом КП некорректный срок лизинга", 422)
    if total_cost < principal:
        raise ServiceError(
            "Полная стоимость лизинга меньше стоимости предмета лизинга", 422
        )
    return _AcceptedLeasingTerms(
        proposal_id=UUID(str(proposal["id"])),
        principal=principal,
        total_cost=total_cost,
        down_payment=_required_leasing_money(
            proposal, "down_payment", allow_zero=True
        ),
        monthly_payment=_required_leasing_money(proposal, "monthly_payment"),
        buyout_amount=_money(proposal.get("buyout_amount") or 0),
        term_months=raw_term,
        down_payment_percent=(
            _money(proposal["down_payment_percent"])
            if proposal.get("down_payment_percent") is not None
            else None
        ),
    )


def _application_owner_id(application: dict[str, Any]) -> UUID:
    raw_user_id = application.get("created_by")
    if not raw_user_id:
        raise ServiceError(
            "У заявки со спецтехникой не указан пользователь-владелец", 422
        )
    try:
        return UUID(str(raw_user_id))
    except ValueError as exc:
        raise ServiceError(
            "У заявки со спецтехникой некорректный пользователь-владелец", 422
        ) from exc


def _item_principals(
    items: list[dict[str, Any]],
    proposal_principal: Decimal,
    *,
    allow_single_item_fallback: bool,
) -> list[Decimal]:
    values: list[Decimal] = []
    for item in items:
        raw_amount = item.get("total_price") or item.get("unit_price")
        if raw_amount is None and len(items) == 1 and allow_single_item_fallback:
            raw_amount = proposal_principal
        if raw_amount is None or _money(raw_amount) <= 0:
            raise ServiceError(
                "Для каждой единицы спецтехники должна быть зафиксирована цена",
                422,
            )
        values.append(_money(raw_amount))
    if sum(values, Decimal("0.00")) > proposal_principal:
        raise ServiceError(
            "Стоимость спецтехники превышает сумму принятого итогового КП", 422
        )
    return values


def _ensure_leasing_product_available(
    *, item: dict[str, Any], product_state: ProductCommerceState
) -> None:
    if product_state.publication_status != "published":
        raise ServiceError(
            "Выдача невозможна: единица спецтехники снята с публикации", 409
        )
    allowed_statuses = (
        {"available", "reserved"}
        if item.get("item_status") == "reserved"
        else {"available"}
    )
    if product_state.sale_status not in allowed_statuses:
        raise ServiceError(
            "Выдача невозможна: единица спецтехники уже занята", 409
        )
    if product_state.currency_code != "RUB" or item.get("currency_code") != "RUB":
        raise ServiceError("Лизинговые платежи поддерживаются только в RUB", 422)


def _allocated_leasing_terms(
    principal: Decimal, terms: _AcceptedLeasingTerms
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    ratio = principal / terms.principal
    return (
        _money(terms.total_cost * ratio),
        _money(terms.down_payment * ratio),
        _money(terms.monthly_payment * ratio),
        _money(terms.buyout_amount * ratio),
    )


async def _create_leasing_order_for_item(
    *,
    application_id: UUID,
    user_id: UUID,
    item: dict[str, Any],
    principal: Decimal,
    terms: _AcceptedLeasingTerms,
    component_items: tuple[dict[str, Any], ...] = (),
    session: AsyncSession,
) -> dict[str, Any]:
    product_id = UUID(str(item["product_id"]))
    component_product_ids = tuple(
        UUID(str(component_item["product_id"]))
        for component_item in component_items
    )
    await repo.lock_products(
        session,
        tuple(sorted((product_id, *component_product_ids), key=str)),
    )
    product_row, product_state = await _load_product(session, product_id)
    idempotency_key = f"leasing-issue:{application_id}:{item['id']}"
    request_hash = _request_hash(
        {
            "application_id": application_id,
            "application_item_id": item["id"],
            "component_item_ids": [str(value["id"]) for value in component_items],
            "proposal_id": terms.proposal_id,
            "principal": principal,
            "terms": terms,
        }
    )
    existing = await repo.find_order_by_idempotency(
        session, user_id, idempotency_key
    )
    if existing:
        if (
            existing["request_hash"] != request_hash
            or existing.get("leasing_application_id") != application_id
            or existing.get("product_id") != product_id
        ):
            raise SpecialEquipmentIdempotencyConflictError()
        return cast("dict[str, Any]", existing)

    _ensure_leasing_product_available(item=item, product_state=product_state)
    component_states: list[tuple[dict[str, Any], ProductCommerceState]] = []
    for component_item in component_items:
        _component_row, component_state = await _load_product(
            session,
            UUID(str(component_item["product_id"])),
        )
        _ensure_leasing_product_available(
            item=component_item,
            product_state=component_state,
        )
        component_states.append((component_item, component_state))
    total, down, monthly, buyout = _allocated_leasing_terms(principal, terms)
    try:
        schedule = build_leasing_schedule(
            issued_on=datetime.now(UTC).date(),
            principal_total=principal,
            total_cost=total,
            down_payment=down,
            monthly_payment=monthly,
            lease_term_months=terms.term_months,
            buyout_amount=buyout,
        )
    except ValueError as exc:
        raise ServiceError(
            f"Принятое итоговое КП не образует корректный график: {exc}", 422
        ) from exc
    snapshot = {
        **(item.get("item_snapshot") or product_state.snapshot()),
        "leasing_terms": {
            "proposal_id": str(terms.proposal_id),
            "total_amount": str(principal),
            "total_cost": str(total),
            "down_payment": str(down),
            "monthly_payment": str(monthly),
            "buyout_amount": str(buyout),
            "lease_term_months": terms.term_months,
        },
    }
    order = await repo.create_order(
        session,
        {
            "user_id": user_id,
            "product_id": product_id,
            "seller_company_id": (
                item.get("seller_company_id") or product_row.get("seller_company_id")
            ),
            "leasing_application_id": application_id,
            "purchase_type": SpecialEquipmentPurchaseType.LEASING.value,
            "status": SpecialEquipmentOrderStatus.LEASING_ACTIVE.value,
            "unit_price": principal,
            "total_price": total,
            "paid_amount": Decimal("0.00"),
            "remaining_amount": total,
            "currency_code": "RUB",
            "down_payment_percent": terms.down_payment_percent,
            "item_snapshot": snapshot,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "hold_expires_at": None,
        },
    )
    await repo.create_schedule_entries(
        session,
        [
            {
                "purchase_order_id": order["id"],
                "payment_number": row.payment_number,
                "due_date": row.due_date,
                "amount": row.amount,
                "principal": row.principal,
                "interest": row.interest,
                "is_paid": False,
            }
            for row in schedule
        ],
    )
    order_item_entries = [
        {
            "purchase_order_id": order["id"],
            "product_id": product_id,
            "source_cart_item_id": item.get("source_cart_item_id"),
            "group_id": item.get("group_id") or UUID(str(item["id"])),
            "parent_group_id": item.get("parent_group_id"),
            "item_role": item.get("item_role") or "offer",
            "position": 0,
            "unit_price": principal,
            "item_snapshot": snapshot,
        }
    ]
    for position, (component_item, component_state) in enumerate(
        component_states, start=1
    ):
        order_item_entries.append(
            {
                "purchase_order_id": order["id"],
                "product_id": UUID(str(component_item["product_id"])),
                "source_cart_item_id": component_item.get("source_cart_item_id"),
                "group_id": component_item.get("group_id") or UUID(
                    str(item["id"])
                ),
                "parent_group_id": component_item.get("parent_group_id"),
                "item_role": "component",
                "position": position,
                "unit_price": Decimal("0.00"),
                "item_snapshot": component_item.get("item_snapshot")
                or component_state.snapshot(),
            }
        )
    await repo.create_order_items(
        session,
        order_item_entries,
    )
    await repo.update_order_allocations_sale_status(session, order["id"], "sold")
    await repo.update_application_item_status(
        session, UUID(str(item["id"])), status="reserved"
    )
    for component_item in component_items:
        await repo.update_application_item_status(
            session,
            UUID(str(component_item["id"])),
            status="reserved",
        )
    return cast("dict[str, Any]", order)


async def create_leasing_orders_for_issued_application(
    *,
    application: dict[str, Any],
    final_proposal: dict[str, Any],
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Idempotently convert issued equipment without touching vehicle items."""

    application_id = UUID(str(application["id"]))
    items = await repo.list_application_items(session, application_id)
    if not items:
        return []
    if any(
        item.get("price_status") == "pending"
        and item.get("item_role") != "component"
        and item.get("item_status") in {"active", "reserved"}
        for item in items
    ):
        raise ServiceError(
            "Сначала дилер должен выставить цену для всех позиций",
            409,
            code="PRICE_ON_REQUEST_PENDING",
        )
    user_id = _application_owner_id(application)
    terms = _accepted_leasing_terms(final_proposal)
    has_vehicle_items = await repo.application_has_vehicle_items(
        session, application_id
    )
    billable_items = [item for item in items if item.get("item_role") != "component"]
    component_items = [item for item in items if item.get("item_role") == "component"]
    components_by_composite: dict[UUID, list[dict[str, Any]]] = {}
    for component in component_items:
        snapshot = component.get("item_snapshot") or {}
        composite_product_id = snapshot.get("composite_product_id")
        if composite_product_id is None:
            raise ServiceError(
                "Компонент лизинговой заявки потерял конкретный состав",
                409,
            )
        components_by_composite.setdefault(
            UUID(str(composite_product_id)), []
        ).append(component)
    billable_product_ids = {
        UUID(str(item["product_id"])) for item in billable_items
    }
    if set(components_by_composite) - billable_product_ids:
        raise ServiceError("Компонент лизинговой заявки потерял родительский комплект", 409)
    principals = _item_principals(
        billable_items,
        terms.principal,
        allow_single_item_fallback=not has_vehicle_items,
    )
    return [
        await _create_leasing_order_for_item(
            application_id=application_id,
            user_id=user_id,
            item=item,
            principal=principal,
            terms=terms,
            component_items=tuple(
                components_by_composite.get(
                    UUID(str(item["product_id"])),
                    (),
                )
            ),
            session=session,
        )
        for item, principal in zip(billable_items, principals, strict=True)
    ]


@dataclass(frozen=True, slots=True)
class CreateOrderCommand:
    user_id: UUID
    purchase_type: SpecialEquipmentPurchaseType
    idempotency_key: str
    payment_method: str | None = None
    down_payment_percent: Decimal | None = None
    cart_item_ids: tuple[UUID, ...] = ()
    product_id: UUID | None = None
    quantity: int | None = None


async def create_order(
    cmd: CreateOrderCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.cart_item_ids:
        return await _create_cart_order(cmd, session)
    if cmd.product_id is None:
        raise ServiceError("Нужно выбрать позиции серверной корзины", 422)
    return await _create_legacy_order(cmd, session)


async def _create_legacy_order(
    cmd: CreateOrderCommand, session: AsyncSession
) -> dict[str, Any]:
    assert cmd.product_id is not None
    hash_payload = {
        "product_id": str(cmd.product_id),
        "purchase_type": cmd.purchase_type.value,
        "payment_method": cmd.payment_method,
        "down_payment_percent": cmd.down_payment_percent,
    }
    request_hash = _request_hash(hash_payload)
    await repo.lock_order_idempotency(
        session,
        cmd.user_id,
        cmd.idempotency_key,
    )
    existing = await repo.find_order_by_idempotency(
        session, cmd.user_id, cmd.idempotency_key
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise SpecialEquipmentIdempotencyConflictError()
        payments = await repo.list_order_payments(session, existing["id"])
        replay_payment = payments[0] if payments else None
        replay_checkout, replay_payment = (
            await _payment_checkout_data(replay_payment, session)
            if replay_payment
            else ({}, None)
        )
        return {
            "order": existing,
            "payment": replay_payment,
            "replayed": True,
            **replay_checkout,
        }

    _row, state = await _load_product(session, cmd.product_id, lock=True)
    state.ensure_purchase_type_allowed(cmd.purchase_type)
    price = state.require_positive_price()
    amounts = compute_order_amounts(
        cmd.purchase_type, price, cmd.down_payment_percent
    )
    now = datetime.now(UTC)
    # Offline reconciliation is asynchronous and may take longer than a
    # browser checkout. It remains processing until employee confirmation or
    # explicit cancellation instead of silently releasing after 30 minutes.
    hold_expires_at = (
        None
        if cmd.payment_method == "bank_transfer"
        else now + timedelta(minutes=PAYMENT_HOLD_MINUTES)
    )
    order = await repo.create_order(
        session,
        {
            "user_id": cmd.user_id,
            "product_id": cmd.product_id,
            "seller_company_id": state.seller_company_id,
            "purchase_type": cmd.purchase_type.value,
            "status": (
                SpecialEquipmentOrderStatus.PREORDERED.value
                if cmd.purchase_type == SpecialEquipmentPurchaseType.PREORDER
                else SpecialEquipmentOrderStatus.PAYMENT_PENDING.value
            ),
            "unit_price": amounts.total,
            "total_price": amounts.total,
            "paid_amount": Decimal("0.00"),
            "remaining_amount": amounts.total,
            "currency_code": state.currency_code,
            "down_payment_percent": amounts.down_payment_percent,
            "item_snapshot": state.snapshot(),
            "idempotency_key": cmd.idempotency_key,
            "request_hash": request_hash,
            "hold_expires_at": hold_expires_at,
        },
    )
    payment: dict[str, Any] | None = None
    if cmd.payment_method:
        payment_hash = _request_hash(
            {
                "order_id": str(order["id"]),
                "amount": amounts.initial_payment,
                "payment_method": cmd.payment_method,
            }
        )
        payment = await repo.create_payment(
            session,
            {
                "purchase_order_id": order["id"],
                "user_id": cmd.user_id,
                "payment_type": cmd.purchase_type.value,
                "amount": amounts.initial_payment,
                "status": "pending" if cmd.payment_method in {"card", "sbp"} else "processing",
                "payment_method": cmd.payment_method,
                "gateway_transaction_id": None,
                "idempotency_key": cmd.idempotency_key,
                "request_hash": payment_hash,
                "expires_at": (
                    hold_expires_at if cmd.payment_method in {"card", "sbp"} else None
                ),
            },
        )
        if cmd.payment_method in {"card", "sbp"}:
            payment = await repo.update_payment(
                session,
                payment["id"],
                {"gateway_transaction_id": f"CARCRAFT-SE-{payment['id']}"},
            )
    if cmd.purchase_type != SpecialEquipmentPurchaseType.PREORDER:
        await repo.update_product_sale_status(session, cmd.product_id, "reserved")
    # Compatibility-only path; the public API always checks out cart-item UUIDs.
    await repo.delete_cart_item(session, cmd.user_id, cmd.product_id)
    checkout_data: dict[str, Any] = {}
    if payment:
        checkout_data, payment = await _payment_checkout_data(payment, session)
    return {
        "order": order,
        "payment": payment,
        "replayed": False,
        **checkout_data,
    }


async def _create_cart_order(  # noqa: PLR0912, PLR0915 -- atomic checkout
    cmd: CreateOrderCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    hash_payload = {
        "cart_item_ids": [str(value) for value in cmd.cart_item_ids],
        "product_id": str(cmd.product_id) if cmd.product_id is not None else None,
        "quantity": cmd.quantity,
        "purchase_type": cmd.purchase_type.value,
        "payment_method": cmd.payment_method,
        "down_payment_percent": cmd.down_payment_percent,
    }
    request_hash = _request_hash(hash_payload)
    await repo.lock_order_idempotency(
        session,
        cmd.user_id,
        cmd.idempotency_key,
    )
    existing = await repo.find_order_by_idempotency(
        session, cmd.user_id, cmd.idempotency_key
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise SpecialEquipmentIdempotencyConflictError()
        existing["items"] = await repo.list_order_items(session, existing["id"])
        payments = await repo.list_order_payments(session, existing["id"])
        replay_payment = payments[0] if payments else None
        replay_checkout, replay_payment = (
            await _payment_checkout_data(replay_payment, session)
            if replay_payment
            else ({}, None)
        )
        return {
            "order": existing,
            "payment": replay_payment,
            "replayed": True,
            **replay_checkout,
        }

    allocation = await allocate_cart_items(
        session,
        user_id=cmd.user_id,
        cart_item_ids=cmd.cart_item_ids,
        allow_on_order=cmd.purchase_type == SpecialEquipmentPurchaseType.PREORDER,
    )
    if cmd.product_id is not None or cmd.quantity is not None:
        root_lines = tuple(
            line
            for line in allocation.cart_lines
            if line.parent_cart_item_id is None
        )
        if (
            len(root_lines) != 1
            or cmd.product_id is None
            or root_lines[0].representative_id != cmd.product_id
        ):
            raise ServiceError(
                "Позиция серверной корзины не соответствует выбранному товару",
                409,
            )
        if cmd.quantity is None or root_lines[0].quantity != cmd.quantity:
            raise ServiceError(
                "Количество позиции серверной корзины изменилось",
                409,
            )
    state_by_id: dict[UUID, ProductCommerceState] = {}
    component_ids = {
        item.component_product_id for item in allocation.components
    }
    for product_id in allocation.concrete_product_ids:
        _row, state = await _load_product(session, product_id)
        state_by_id[product_id] = state
    group_has_on_order: dict[UUID, bool] = {}
    for line in allocation.cart_lines:
        root_cart_item_id = line.parent_cart_item_id or line.cart_item_id
        group_has_on_order[root_cart_item_id] = (
            group_has_on_order.get(root_cart_item_id, False)
            or any(
                state_by_id[product["id"]].sale_status == "on_order"
                for product in line.products
            )
        )
    for line in allocation.cart_lines:
        root_cart_item_id = line.parent_cart_item_id or line.cart_item_id
        for product in line.products:
            state_by_id[product["id"]].ensure_group_purchase_type_allowed(
                cmd.purchase_type,
                group_has_on_order=group_has_on_order[root_cart_item_id],
            )
    sellers = {state.seller_company_id for state in state_by_id.values()}
    currencies = {state.currency_code for state in state_by_id.values()}
    if len(sellers) != 1:
        raise ServiceError(
            "Один заказ не может объединять товары разных продавцов",
            422,
        )
    if len(currencies) != 1:
        raise ServiceError(
            "Один заказ не может объединять товары в разных валютах",
            422,
        )
    total = sum(
        (
            line.require_agreed_unit_price(product)
            for line in allocation.cart_lines
            for product in line.products
        ),
        Decimal("0.00"),
    )
    amounts = compute_order_amounts(
        cmd.purchase_type,
        total,
        cmd.down_payment_percent,
    )
    first_line = allocation.cart_lines[0]
    primary_product_id = first_line.products[0]["id"]
    now = datetime.now(UTC)
    hold_expires_at = (
        None
        if cmd.payment_method == "bank_transfer"
        else now + timedelta(minutes=PAYMENT_HOLD_MINUTES)
    )
    order = await repo.create_order(
        session,
        {
            "user_id": cmd.user_id,
            "product_id": primary_product_id,
            "seller_company_id": next(iter(sellers)),
            "purchase_type": cmd.purchase_type.value,
            "status": (
                SpecialEquipmentOrderStatus.PREORDERED.value
                if cmd.purchase_type == SpecialEquipmentPurchaseType.PREORDER
                else SpecialEquipmentOrderStatus.PAYMENT_PENDING.value
            ),
            "unit_price": amounts.total,
            "total_price": amounts.total,
            "paid_amount": Decimal("0.00"),
            "remaining_amount": amounts.total,
            "currency_code": next(iter(currencies)),
            "down_payment_percent": amounts.down_payment_percent,
            "item_snapshot": {
                "cart_item_ids": [str(value) for value in cmd.cart_item_ids],
                "products": [
                    state_by_id[product_id].snapshot()
                    for product_id in allocation.concrete_product_ids
                ],
            },
            "idempotency_key": cmd.idempotency_key,
            "request_hash": request_hash,
            "hold_expires_at": hold_expires_at,
        },
    )
    item_entries: list[dict[str, Any]] = []
    position = 0
    for line in allocation.cart_lines:
        for product in line.products:
            product_id = product["id"]
            item_entries.append(
                {
                    "purchase_order_id": order["id"],
                    "product_id": product_id,
                    "source_cart_item_id": line.cart_item_id,
                    "group_id": line.cart_item_id,
                    "parent_group_id": line.parent_cart_item_id,
                    "item_role": (
                        "attachment"
                        if line.parent_cart_item_id is not None
                        else "offer"
                    ),
                    "position": position,
                    "unit_price": line.require_agreed_unit_price(product),
                    "item_snapshot": state_by_id[product_id].snapshot(),
                }
            )
            position += 1
    for component in allocation.components:
        state = state_by_id[component.component_product_id]
        item_entries.append(
            {
                "purchase_order_id": order["id"],
                "product_id": component.component_product_id,
                "source_cart_item_id": component.source_cart_item_id,
                "group_id": component.source_cart_item_id,
                "parent_group_id": component.source_cart_item_id,
                "item_role": "component",
                "position": position + component.position,
                "unit_price": Decimal("0.00"),
                "item_snapshot": {
                    **state.snapshot(),
                    "composite_product_id": str(component.composite_product_id),
                    "is_base": component.is_base,
                },
            }
        )
    order_items = await repo.create_order_items(session, item_entries)
    order["items"] = order_items

    payment: dict[str, Any] | None = None
    if cmd.payment_method:
        payment_hash = _request_hash(
            {
                "order_id": str(order["id"]),
                "amount": amounts.initial_payment,
                "payment_method": cmd.payment_method,
            }
        )
        payment = await repo.create_payment(
            session,
            {
                "purchase_order_id": order["id"],
                "user_id": cmd.user_id,
                "payment_type": cmd.purchase_type.value,
                "amount": amounts.initial_payment,
                "status": (
                    "pending"
                    if cmd.payment_method in {"card", "sbp"}
                    else "processing"
                ),
                "payment_method": cmd.payment_method,
                "gateway_transaction_id": None,
                "idempotency_key": cmd.idempotency_key,
                "request_hash": payment_hash,
                "expires_at": (
                    hold_expires_at
                    if cmd.payment_method in {"card", "sbp"}
                    else None
                ),
            },
        )
        if cmd.payment_method in {"card", "sbp"}:
            payment = await repo.update_payment(
                session,
                payment["id"],
                {"gateway_transaction_id": f"CARCRAFT-SE-{payment['id']}"},
            )
    if cmd.purchase_type != SpecialEquipmentPurchaseType.PREORDER:
        await repo.update_order_allocations_sale_status(
            session, order["id"], "reserved"
        )
    elif any(
        state.sale_status == "available"
        for product_id, state in state_by_id.items()
        if product_id not in component_ids
    ):
        await repo.reserve_available_order_allocations(session, order["id"])
    await repo.delete_cart_items_by_ids(
        session,
        user_id=cmd.user_id,
        cart_item_ids=cmd.cart_item_ids,
    )
    checkout_data: dict[str, Any] = {}
    if payment:
        checkout_data, payment = await _payment_checkout_data(payment, session)
    return {
        "order": order,
        "payment": payment,
        "replayed": False,
        **checkout_data,
    }


async def list_orders(
    user_id: UUID,
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    rows, total = await repo.list_orders(
        session,
        user_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    items_by_order = await repo.list_order_items_batch(
        session, tuple(row["id"] for row in rows)
    )
    for row in rows:
        row["items"] = items_by_order.get(row["id"], [])
    return {
        "items": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        },
    }


@dataclass(frozen=True, slots=True)
class CreateRemainingPaymentCommand:
    user_id: UUID
    order_id: UUID
    idempotency_key: str
    payment_method: str


async def create_remaining_payment(
    cmd: CreateRemainingPaymentCommand, session: AsyncSession
) -> dict[str, Any]:
    request_hash = _request_hash(
        {
            "order_id": str(cmd.order_id),
            "scope": "remaining",
            "payment_method": cmd.payment_method,
        }
    )
    order = await repo.get_order(session, cmd.order_id, lock=True)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], cmd.user_id)
    existing = await repo.find_payment_by_idempotency(
        session, cmd.order_id, cmd.idempotency_key
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise SpecialEquipmentIdempotencyConflictError()
        checkout, existing = await _payment_checkout_data(existing, session)
        return {
            "order": order,
            "payment": existing,
            "replayed": True,
            **checkout,
        }
    if order["status"] != SpecialEquipmentOrderStatus.RESERVED.value:
        raise SpecialEquipmentOrderStateError(
            "Доплата доступна только для зарезервированного товара"
        )
    active_payment = await repo.find_active_order_payment(session, cmd.order_id)
    if active_payment:
        raise SpecialEquipmentOrderStateError(
            "По заказу уже существует незавершённый платёж"
        )
    amount = Decimal(str(order["remaining_amount"]))
    if amount <= 0:
        raise SpecialEquipmentOrderStateError("По заказу нет остатка к оплате")
    expires_at = (
        datetime.now(UTC) + timedelta(minutes=PAYMENT_HOLD_MINUTES)
        if cmd.payment_method in {"card", "sbp"}
        else None
    )
    payment = await repo.create_payment(
        session,
        {
            "purchase_order_id": cmd.order_id,
            "user_id": cmd.user_id,
            "payment_type": "remaining_balance",
            "amount": amount,
            "status": "pending" if expires_at else "processing",
            "payment_method": cmd.payment_method,
            "gateway_transaction_id": None,
            "idempotency_key": cmd.idempotency_key,
            "request_hash": request_hash,
            "expires_at": expires_at,
        },
    )
    if expires_at:
        payment = await repo.update_payment(
            session,
            payment["id"],
            {"gateway_transaction_id": f"CARCRAFT-SE-{payment['id']}"},
        )
    checkout, payment = await _payment_checkout_data(payment, session)
    return {
        "order": order,
        "payment": payment,
        "replayed": False,
        **checkout,
    }


def _schedule_item_view(
    row: dict[str, Any], *, order_status: str
) -> dict[str, Any]:
    payment_id = row.get("payment_id")
    payment_status = row.get("payment_status")
    receipt_content_url = (
        f"/api/v1/special-equipment/purchase-orders/"
        f"{row['purchase_order_id']}/payments/{payment_id}/receipt/content"
        if payment_id and row.get("has_receipt")
        else None
    )
    return {
        "id": row["id"],
        "purchase_order_id": row["purchase_order_id"],
        "payment_number": row["payment_number"],
        "due_date": row["due_date"],
        "amount": row["amount"],
        "principal": row.get("principal"),
        "interest": row.get("interest"),
        "payment_id": payment_id,
        "is_paid": bool(row["is_paid"]),
        "payment_status": payment_status,
        "payment_paid_at": row.get("payment_paid_at"),
        "receipt_content_url": receipt_content_url,
        "can_pay": (
            order_status == SpecialEquipmentOrderStatus.LEASING_ACTIVE.value
            and not row["is_paid"]
            and payment_status not in {"pending", "processing", "completed"}
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_leasing_payment_schedule(
    user_id: UUID,
    order_id: UUID,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    order = await repo.get_order(session, order_id)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], user_id)
    if order["purchase_type"] != SpecialEquipmentPurchaseType.LEASING.value:
        raise SpecialEquipmentOrderStateError(
            "График платежей доступен только для лизингового заказа"
        )
    rows = await repo.list_schedule_by_order(session, order_id)
    return [
        _schedule_item_view(row, order_status=str(order["status"]))
        for row in rows
    ]


@dataclass(frozen=True, slots=True)
class CreateScheduledPaymentCommand:
    user_id: UUID
    order_id: UUID
    schedule_id: UUID
    idempotency_key: str
    payment_method: str


async def create_scheduled_payment(
    cmd: CreateScheduledPaymentCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Create one attempt for a leasing installment without marking it paid."""

    request_hash = _request_hash(
        {
            "order_id": str(cmd.order_id),
            "schedule_id": str(cmd.schedule_id),
            "scope": "leasing_schedule",
            "payment_method": cmd.payment_method,
        }
    )
    order = await repo.get_order(session, cmd.order_id, lock=True)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], cmd.user_id)
    if (
        order["purchase_type"] != SpecialEquipmentPurchaseType.LEASING.value
        or order["status"] != SpecialEquipmentOrderStatus.LEASING_ACTIVE.value
    ):
        raise SpecialEquipmentOrderStateError(
            "Взнос можно оплатить только по действующему лизинговому заказу"
        )

    schedule_item = await repo.get_schedule_item(
        session, cmd.schedule_id, lock=True
    )
    if (
        schedule_item is None
        or schedule_item["purchase_order_id"] != cmd.order_id
    ):
        raise SpecialEquipmentOrderNotFoundError()

    existing = await repo.find_payment_by_idempotency(
        session, cmd.order_id, cmd.idempotency_key
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise SpecialEquipmentIdempotencyConflictError()
        checkout, existing = await _payment_checkout_data(existing, session)
        return {
            "order": order,
            "payment": existing,
            "schedule_item": _schedule_item_view(
                {
                    **schedule_item,
                    "payment_status": existing["status"],
                    "payment_paid_at": existing.get("paid_at"),
                    "has_receipt": bool(existing.get("receipt_storage_key")),
                },
                order_status=str(order["status"]),
            ),
            "replayed": True,
            **checkout,
        }
    if schedule_item["is_paid"]:
        raise SpecialEquipmentOrderStateError("Лизинговый взнос уже оплачен")
    linked_payment_id = schedule_item.get("payment_id")
    if linked_payment_id:
        linked_payment = await repo.get_payment(
            session, linked_payment_id, lock=True
        )
        if linked_payment and linked_payment["status"] in {"pending", "processing"}:
            raise SpecialEquipmentOrderStateError(
                "По этому взносу уже существует незавершённый платёж"
            )
        if linked_payment and linked_payment["status"] == "completed":
            raise SpecialEquipmentOrderStateError(
                "Подтверждённый платёж ожидает сверки графика"
            )

    active_payment = await repo.find_active_order_payment(session, cmd.order_id)
    if active_payment:
        raise SpecialEquipmentOrderStateError(
            "По заказу уже существует незавершённый платёж"
        )
    amount = _money(schedule_item["amount"])
    expires_at = (
        datetime.now(UTC) + timedelta(minutes=PAYMENT_HOLD_MINUTES)
        if cmd.payment_method in {"card", "sbp"}
        else None
    )
    payment = await repo.create_payment(
        session,
        {
            "purchase_order_id": cmd.order_id,
            "user_id": cmd.user_id,
            "payment_type": "leasing_monthly",
            "amount": amount,
            "status": "pending" if expires_at else "processing",
            "payment_method": cmd.payment_method,
            "gateway_transaction_id": None,
            "gateway_response": {"schedule_id": str(cmd.schedule_id)},
            "idempotency_key": cmd.idempotency_key,
            "request_hash": request_hash,
            "expires_at": expires_at,
        },
    )
    if expires_at:
        payment = await repo.update_payment(
            session,
            payment["id"],
            {"gateway_transaction_id": f"CARCRAFT-SE-{payment['id']}"},
        )
    schedule_item = await repo.attach_schedule_payment(
        session, cmd.schedule_id, payment["id"]
    )
    checkout, payment = await _payment_checkout_data(payment, session)
    return {
        "order": order,
        "payment": payment,
        "schedule_item": _schedule_item_view(
            {
                **schedule_item,
                "payment_status": payment["status"],
                "payment_paid_at": payment.get("paid_at"),
                "has_receipt": False,
            },
            order_status=str(order["status"]),
        ),
        "replayed": False,
        **checkout,
    }


async def get_order(
    user_id: UUID, order_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    order = await repo.get_order(session, order_id)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], user_id)
    return {
        **order,
        "items": await repo.list_order_items(session, order_id),
        "payments": await repo.list_order_payments(session, order_id),
    }


async def get_payment_status(
    user_id: UUID,
    order_id: UUID,
    payment_id: UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    order = await repo.get_order(session, order_id)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], user_id)
    payment = await repo.get_payment(session, payment_id)
    if payment is None or payment["purchase_order_id"] != order_id:
        raise SpecialEquipmentOrderNotFoundError()
    return {
        "id": payment["id"],
        "status": payment["status"],
        "fiscal_status": payment.get("fiscal_status"),
        "receipt_content_url": (
            f"/api/v1/special-equipment/purchase-orders/{order_id}"
            f"/payments/{payment_id}/receipt/content"
            if payment.get("receipt_storage_key")
            else None
        ),
        "error_message": payment.get("error_message"),
        "expires_at": payment.get("expires_at"),
        "paid_at": payment.get("paid_at"),
    }


async def get_payment_receipt_content(
    user_id: UUID,
    order_id: UUID,
    payment_id: UUID,
    session: AsyncSession,
    storage: ObjectStorage,
) -> StoredObject:
    order = await repo.get_order(session, order_id)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], user_id)
    payment = await repo.get_payment(session, payment_id)
    if payment is None or payment["purchase_order_id"] != order_id:
        raise SpecialEquipmentOrderNotFoundError()
    storage_key = payment.get("receipt_storage_key")
    if not storage_key:
        raise ServiceError("Фискальный чек ещё не сохранён", 404)
    obj = await storage.get(str(storage_key))
    if obj is None:
        raise ServiceError("Фискальный чек не найден в хранилище", 404)
    return obj


@dataclass(frozen=True, slots=True)
class CancelOrderCommand:
    user_id: UUID
    order_id: UUID
    reason: str | None = None


async def cancel_order(
    cmd: CancelOrderCommand, session: AsyncSession
) -> dict[str, Any]:
    order = await repo.get_order(session, cmd.order_id, lock=True)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    ensure_order_owned(order["user_id"], cmd.user_id)
    if order["status"] in {
        SpecialEquipmentOrderStatus.CANCELLED.value,
        SpecialEquipmentOrderStatus.CANCELLATION_REQUESTED.value,
    }:
        return dict(order)
    ensure_order_can_cancel(order["status"])

    # Global financial lock order is purchase order first, then its payments.
    # Webhook, offline confirmation and expiry follow the same sequence.
    payment_rows = await repo.list_order_payments(session, cmd.order_id)
    locked_payments: list[dict[str, Any]] = []
    for row in payment_rows:
        if row["status"] not in {"pending", "processing"}:
            continue
        locked = await repo.get_payment(session, row["id"], lock=True)
        if locked and locked["status"] in {"pending", "processing"}:
            locked_payments.append(locked)

    for payment in locked_payments:
        await repo.update_payment(
            session,
            payment["id"],
            {
                "status": "expired",
                "error_message": "Order cancellation requested before payment completion",
            },
        )
    now = datetime.now(UTC)
    paid_amount = Decimal(str(order["paid_amount"]))
    if paid_amount > Decimal("0.00"):
        updated = await repo.update_order(
            session,
            cmd.order_id,
            {
                "status": SpecialEquipmentOrderStatus.CANCELLATION_REQUESTED.value,
                "cancellation_reason": cmd.reason,
                "cancellation_requested_at": now,
                "hold_expires_at": None,
            },
        )
        return dict(updated)

    updated = await repo.update_order(
        session,
        cmd.order_id,
        {
            "status": SpecialEquipmentOrderStatus.CANCELLED.value,
            "cancellation_reason": cmd.reason,
            "cancellation_requested_at": now,
            "cancelled_at": now,
            "hold_expires_at": None,
        },
    )
    if order.get("leasing_application_id"):
        await repo.release_order_application_claims(
            session,
            order["leasing_application_id"],
            cmd.order_id,
        )
    await repo.release_order_allocations_if_unclaimed(session, cmd.order_id)
    return dict(updated)


@dataclass(frozen=True, slots=True)
class ConfirmOrderRefundCommand:
    actor_id: UUID
    actor_role: str
    order_id: UUID
    external_reference: str


def _refund_confirmation_is_replay(
    order: dict[str, Any],
    external_reference: str,
) -> bool:
    stored_reference = order.get("refund_external_reference")
    if order["status"] == SpecialEquipmentOrderStatus.CANCELLED.value:
        if stored_reference == external_reference:
            return True
        if stored_reference:
            raise SpecialEquipmentRefundReferenceConflictError()
        raise SpecialEquipmentOrderStateError(
            "Отмена без оплаты не требует подтверждения возврата"
        )
    if order["status"] != SpecialEquipmentOrderStatus.CANCELLATION_REQUESTED.value:
        raise SpecialEquipmentOrderStateError(
            "Сначала владелец должен запросить отмену оплаченного заказа"
        )
    return False


async def confirm_order_refund(
    cmd: ConfirmOrderRefundCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Record an already completed external refund without calling a provider."""

    if cmd.actor_role not in _COMPANY_ACCESS_OVERRIDE_ROLES:
        raise ServiceError("Подтвердить возврат может только сотрудник", 403)
    external_reference = cmd.external_reference.strip()
    if not external_reference or len(external_reference) > 255:
        raise ServiceError("Некорректная внешняя ссылка возврата", 422)

    # Keep the global financial lock order: order, idempotency reference, payments.
    order = await repo.get_order(session, cmd.order_id, lock=True)
    if order is None:
        raise SpecialEquipmentOrderNotFoundError()
    await repo.lock_refund_reference(session, external_reference)

    referenced_order = await repo.find_order_by_refund_reference(
        session,
        external_reference,
    )
    if referenced_order is not None and referenced_order["id"] != cmd.order_id:
        raise SpecialEquipmentRefundReferenceConflictError()

    if _refund_confirmation_is_replay(order, external_reference):
        payments = await repo.list_order_payments(session, cmd.order_id)
        return {
            "order": order,
            "refunded_amount": order.get("refunded_amount") or Decimal("0.00"),
            "refunded_payment_ids": [
                payment["id"]
                for payment in payments
                if payment["status"] == "refunded"
            ],
            "replayed": True,
        }
    paid_amount = Decimal(str(order["paid_amount"]))
    if paid_amount <= Decimal("0.00"):
        raise SpecialEquipmentOrderStateError(
            "В заказе нет подтверждённой суммы для возврата"
        )

    payment_rows = await repo.list_order_payments(session, cmd.order_id)
    locked_payments: list[dict[str, Any]] = []
    for row in payment_rows:
        locked = await repo.get_payment(session, row["id"], lock=True)
        if locked is not None:
            locked_payments.append(locked)
    completed_payments = [
        payment for payment in locked_payments if payment["status"] == "completed"
    ]
    completed_amount = sum(
        (Decimal(str(payment["amount"])) for payment in completed_payments),
        start=Decimal("0.00"),
    )
    if not completed_payments or completed_amount != paid_amount:
        raise SpecialEquipmentOrderStateError(
            "Сумма завершённых платежей не совпадает с оплаченной суммой заказа"
        )

    confirmed_at = datetime.now(UTC)
    refunded_payment_ids: list[UUID] = []
    for payment in completed_payments:
        await repo.update_payment(
            session,
            payment["id"],
            {
                "status": "refunded",
                "refunded_at": confirmed_at,
            },
        )
        refunded_payment_ids.append(payment["id"])

    updated = await repo.update_order(
        session,
        cmd.order_id,
        {
            "status": SpecialEquipmentOrderStatus.CANCELLED.value,
            "paid_amount": Decimal("0.00"),
            "remaining_amount": Decimal(str(order["total_price"])),
            "refund_external_reference": external_reference,
            "refunded_amount": paid_amount,
            "refund_confirmed_by": cmd.actor_id,
            "refund_confirmed_at": confirmed_at,
            "cancelled_at": confirmed_at,
            "hold_expires_at": None,
        },
    )
    if order.get("leasing_application_id"):
        await repo.release_order_application_claims(
            session,
            order["leasing_application_id"],
            cmd.order_id,
        )
    await repo.release_order_allocations_if_unclaimed(session, cmd.order_id)

    return {
        "order": updated,
        "refunded_amount": paid_amount,
        "refunded_payment_ids": refunded_payment_ids,
        "replayed": False,
    }


@dataclass(frozen=True, slots=True)
class ConfirmOfflinePaymentCommand:
    actor_role: str
    order_id: UUID
    payment_id: UUID


async def confirm_offline_payment(
    cmd: ConfirmOfflinePaymentCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.actor_role != "carcraft_employee":
        raise ServiceError("Подтвердить банковский перевод может только сотрудник", 403)
    order = await repo.get_order(session, cmd.order_id, lock=True)
    payment = await repo.get_payment(session, cmd.payment_id, lock=True)
    if order is None or payment is None or payment["purchase_order_id"] != cmd.order_id:
        raise SpecialEquipmentOrderNotFoundError()
    if payment.get("payment_method") != "bank_transfer":
        raise SpecialEquipmentOrderStateError(
            "Ручное подтверждение доступно только для банковского перевода"
        )
    if payment["status"] == "completed":
        return {"order": order, "payment": payment}
    if payment["status"] != "processing" or order["status"] not in {
        SpecialEquipmentOrderStatus.PAYMENT_PENDING.value,
        SpecialEquipmentOrderStatus.RESERVED.value,
        SpecialEquipmentOrderStatus.LEASING_ACTIVE.value,
        SpecialEquipmentOrderStatus.PREORDERED.value,
    }:
        raise SpecialEquipmentOrderStateError(
            "Банковский перевод уже завершён или срок резерва истёк"
        )

    is_leasing_installment = payment["payment_type"] == "leasing_monthly"
    schedule_item: dict[str, Any] | None = None
    if is_leasing_installment:
        raw_schedule_id = (payment.get("gateway_response") or {}).get(
            "schedule_id"
        )
        try:
            schedule_id = UUID(str(raw_schedule_id))
        except (TypeError, ValueError) as exc:
            raise SpecialEquipmentOrderStateError(
                "Платёж не связан с лизинговым графиком"
            ) from exc
        schedule_item = await repo.get_schedule_item(
            session, schedule_id, lock=True
        )
        if (
            schedule_item is None
            or schedule_item["purchase_order_id"] != cmd.order_id
            or schedule_item.get("payment_id") != cmd.payment_id
            or schedule_item["is_paid"]
            or _money(schedule_item["amount"]) != _money(payment["amount"])
        ):
            raise SpecialEquipmentOrderStateError(
                "Платёж не соответствует неоплаченному взносу графика"
            )

    is_remaining = payment["payment_type"] == "remaining_balance"
    is_preorder = (
        order["purchase_type"] == SpecialEquipmentPurchaseType.PREORDER.value
    )
    is_reservation = (
        order["purchase_type"] == SpecialEquipmentPurchaseType.RESERVATION.value
        and not is_remaining
    )
    target_status = (
        SpecialEquipmentOrderStatus.LEASING_ACTIVE.value
        if is_leasing_installment
        else (
            SpecialEquipmentOrderStatus.PREORDERED.value
            if is_preorder
            else (
                SpecialEquipmentOrderStatus.RESERVED.value
                if is_reservation
                else SpecialEquipmentOrderStatus.PURCHASED.value
            )
        )
    )
    completed_payment = await repo.update_payment(
        session,
        cmd.payment_id,
        {"status": "completed", "paid_at": datetime.now(UTC)},
    )
    paid_amount = Decimal(str(order["paid_amount"])) + Decimal(str(payment["amount"]))
    if paid_amount > Decimal(str(order["total_price"])):
        raise SpecialEquipmentOrderStateError(
            "Сумма платежей превышает стоимость лизингового заказа"
        )
    updated = await repo.update_order(
        session,
        cmd.order_id,
        {
            "status": target_status,
            "paid_amount": paid_amount,
            "remaining_amount": max(
                Decimal("0.00"), Decimal(str(order["total_price"])) - paid_amount
            ),
            "hold_expires_at": None,
        },
    )
    if schedule_item is not None:
        marked = await repo.mark_schedule_paid(
            session, schedule_item["id"], cmd.payment_id
        )
        if marked is None:
            raise SpecialEquipmentOrderStateError(
                "Лизинговый взнос уже обработан"
            )
    if not is_leasing_installment and not is_preorder:
        await repo.update_order_allocations_sale_status(
            session,
            order["id"],
            "reserved" if is_reservation else "sold",
        )
    return {
        "order": updated,
        "payment": completed_payment,
    }
