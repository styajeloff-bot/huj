"""Database adapter for the special-equipment commerce bounded context."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from domain.leasing_purposes import selected_purposes
from domain.special_equipment_commerce import (
    SpecialEquipmentCartConfigurationConflictError,
    SpecialEquipmentCartPositionConflictError,
)
from domain.storefronts import CatalogScope
from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentFavorite,
    SpecialEquipmentGuestCartTransfer,
    SpecialEquipmentLeasingPaymentSchedule,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPayment,
    SpecialEquipmentPaymentCallbackInbox,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.repositories import application_repository
from infrastructure.repositories.catalog_scope import special_equipment_visible_in
from infrastructure.repositories.questionnaire_purpose_repository import (
    sync_vehicle_purchase_purpose,
)
from infrastructure.repository_timing import timed_repository


def _to_dict(obj: Any) -> dict[str, Any]:
    return {
        column.key: getattr(obj, column.key)
        for column in sa_inspect(obj).mapper.column_attrs
    }


def _product_to_dict(product: SpecialEquipmentProduct) -> dict[str, Any]:
    """Expose the price charged by commerce while retaining its components."""

    result = _to_dict(product)
    if result["price_on_request"]:
        result["base_price"] = None
        result["special_price"] = None
        result["price"] = result["price_from"]
    else:
        result["base_price"] = result["price"]
        result["price"] = (
            result["special_price"]
            if result["special_price"] is not None
            else result["price"]
        )
    return result


def _initial_requested_price_status(
    *, item_role: str, item_snapshot: dict[str, Any]
) -> str:
    if item_role != "component" and item_snapshot.get("price_on_request") is True:
        return "pending"
    return "none"


_PRODUCT_SELECT = """
        SELECT
            p.id,
            p.slug,
            p.seller_company_id,
            p.trim_id,
            trim.name AS trim_name,
            modification.id AS modification_id,
            modification.name AS modification_name,
            model.id AS model_id,
            model.name AS model_name,
            mark.id AS mark_id,
            mark.name AS mark_name,
            p.manufacture_year,
            body_color.id AS body_color_id,
            body_color.name AS body_color_name,
            p.vin,
            CASE WHEN p.price_on_request THEN NULL ELSE p.price END AS base_price,
            CASE WHEN p.price_on_request THEN NULL ELSE p.special_price END AS special_price,
            p.price_on_request,
            p.price_from,
            CASE WHEN p.price_on_request THEN p.price_from
                 ELSE COALESCE(p.special_price, p.price) END AS price,
            p.currency_code,
            p.publication_status,
            p.sale_status,
            (
                SELECT image.id
                FROM special_equipment_product_images AS image
                WHERE image.product_id = p.id
                ORDER BY image.is_primary DESC, image.sort_order, image.id
                LIMIT 1
            ) AS primary_image_id,
            p.superstructure_id,
            p.superstructure_name,
            super_type.name AS superstructure_type_name,
            p.superstructure_manufacturer
        FROM special_equipment_products AS p
        LEFT JOIN special_equipment_modifications AS modification
          ON modification.id = p.modification_id
        JOIN special_equipment_models AS model
          ON model.id = COALESCE(modification.model_id, p.model_id)
        JOIN special_equipment_marks AS mark
          ON mark.id = model.mark_id
        LEFT JOIN special_equipment_superstructures AS super_type
          ON super_type.id = p.superstructure_id
        LEFT JOIN special_equipment_trims AS trim
          ON trim.id = p.trim_id
        LEFT JOIN special_equipment_colors AS body_color
          ON body_color.id = p.body_color_id
        WHERE p.id = :product_id
"""


@timed_repository
async def lock_order_idempotency(
    session: AsyncSession,
    user_id: UUID,
    idempotency_key: str,
) -> None:
    """Serialize checkout attempts for one user-scoped idempotency key.

    The order row does not exist on the first request, so a row lock cannot
    protect the initial read-before-insert window.  A transaction-scoped
    PostgreSQL advisory lock closes that race without serializing unrelated
    checkouts from the same user.
    """

    lock_key = f"special-equipment-order:{user_id}:{idempotency_key}"
    await session.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(CAST(:lock_key AS text), 0)"
            ")"
        ),
        {"lock_key": lock_key},
    )


@timed_repository
async def lock_refund_reference(
    session: AsyncSession,
    external_reference: str,
) -> None:
    """Serialize confirmations that attest the same external refund."""

    lock_key = f"special-equipment-refund:{external_reference}"
    await session.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(CAST(:lock_key AS text), 0)"
            ")"
        ),
        {"lock_key": lock_key},
    )


def _product_select(*, lock: bool = False) -> sa.TextClause:
    if lock:
        return sa.text(_PRODUCT_SELECT + " FOR UPDATE OF p")
    return sa.text(_PRODUCT_SELECT)


@timed_repository
async def get_product(
    session: AsyncSession,
    product_id: UUID,
    *,
    lock: bool = False,
) -> dict[str, Any] | None:
    result = await session.execute(
        _product_select(lock=lock), {"product_id": product_id}
    )
    row = result.mappings().first()
    return dict(row) if row else None


@timed_repository
async def product_visible_in_scope(
    session: AsyncSession,
    product_id: UUID,
    scope: CatalogScope,
) -> bool:
    """Check the current active storefront warehouse membership."""

    if scope.is_default:
        return True
    return bool(
        await session.scalar(
            sa.select(SpecialEquipmentProduct.id).where(
                SpecialEquipmentProduct.id == product_id,
                special_equipment_visible_in(scope),
            )
        )
    )


@timed_repository
async def product_ids_visible_in_scope(
    session: AsyncSession,
    product_ids: tuple[UUID, ...],
    scope: CatalogScope,
) -> frozenset[UUID]:
    """Resolve storefront visibility for a bounded product projection batch."""

    if not product_ids:
        return frozenset()
    if scope.is_default:
        return frozenset(product_ids)
    return frozenset(
        (
            await session.scalars(
                sa.select(SpecialEquipmentProduct.id).where(
                    SpecialEquipmentProduct.id.in_(product_ids),
                    special_equipment_visible_in(scope),
                )
            )
        ).all()
    )


@timed_repository
async def lock_offering_allocation(
    session: AsyncSession,
    representative_id: UUID,
) -> None:
    """Serialize quantity allocation for one public representative."""

    await session.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(CAST(:key AS text), 0))"
        ),
        {"key": f"special-equipment-offering:{representative_id}"},
    )


@timed_repository
async def lock_products(
    session: AsyncSession,
    product_ids: tuple[UUID, ...],
) -> list[dict[str, Any]]:
    """Lock concrete units in UUID order and expose their commercial state."""

    if not product_ids:
        return []
    rows = (
        await session.execute(
            sa.select(SpecialEquipmentProduct)
            .where(SpecialEquipmentProduct.id.in_(product_ids))
            .order_by(SpecialEquipmentProduct.id)
            .with_for_update()
        )
    ).scalars()
    return [_product_to_dict(row) for row in rows]


@timed_repository
async def list_compatible_attachment_ids(
    session: AsyncSession,
    product_id: UUID,
) -> tuple[UUID, ...]:
    return tuple(
        (
            await session.execute(
                sa.select(SpecialEquipmentProductAttachment.attachment_product_id)
                .where(SpecialEquipmentProductAttachment.product_id == product_id)
                .order_by(
                    SpecialEquipmentProductAttachment.position,
                    SpecialEquipmentProductAttachment.attachment_product_id,
                )
            )
        ).scalars()
    )


@timed_repository
async def list_product_components_for_checkout(
    _session: AsyncSession,
    _composite_product_id: UUID,
) -> list[dict[str, Any]]:
    return []


@timed_repository
async def list_favorites(
    session: AsyncSession, user_id: UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.text(
            """
            SELECT
                favorite.user_id,
                favorite.product_id,
                favorite.added_at,
                p.slug,
                p.trim_id,
                trim.name AS trim_name,
                modification.id AS modification_id,
                modification.name AS modification_name,
                model.id AS model_id,
                model.name AS model_name,
                mark.id AS mark_id,
                mark.name AS mark_name,
                p.manufacture_year,
                body_color.id AS body_color_id,
                body_color.name AS body_color_name,
                CASE WHEN p.price_on_request THEN NULL ELSE p.price END AS base_price,
                CASE WHEN p.price_on_request THEN NULL ELSE p.special_price END AS special_price,
                p.price_on_request,
                p.price_from,
                CASE WHEN p.price_on_request THEN p.price_from
                     ELSE COALESCE(p.special_price, p.price) END AS price,
                p.currency_code,
                p.publication_status,
                p.sale_status,
                (
                    SELECT image.id
                    FROM special_equipment_product_images AS image
                    WHERE image.product_id = p.id
                    ORDER BY image.is_primary DESC, image.sort_order, image.id
                    LIMIT 1
                ) AS primary_image_id,
                p.superstructure_id,
                p.superstructure_name,
                super_type.name AS superstructure_type_name,
                p.superstructure_manufacturer
            FROM special_equipment_favorites AS favorite
            JOIN special_equipment_products AS p ON p.id = favorite.product_id
            LEFT JOIN special_equipment_modifications AS modification
              ON modification.id = p.modification_id
            JOIN special_equipment_models AS model
              ON model.id = COALESCE(modification.model_id, p.model_id)
            JOIN special_equipment_marks AS mark
              ON mark.id = model.mark_id
            LEFT JOIN special_equipment_superstructures AS super_type
              ON super_type.id = p.superstructure_id
            LEFT JOIN special_equipment_trims AS trim
              ON trim.id = p.trim_id
            LEFT JOIN special_equipment_colors AS body_color
              ON body_color.id = p.body_color_id
            WHERE favorite.user_id = :user_id
            ORDER BY favorite.added_at DESC, favorite.product_id
            """
        ),
        {"user_id": user_id},
    )
    return [dict(row) for row in result.mappings().all()]


@timed_repository
async def put_favorite(
    session: AsyncSession, user_id: UUID, product_id: UUID
) -> bool:
    stmt = (
        pg_insert(SpecialEquipmentFavorite)
        .values(user_id=user_id, product_id=product_id)
        .on_conflict_do_nothing(
            index_elements=[
                SpecialEquipmentFavorite.user_id,
                SpecialEquipmentFavorite.product_id,
            ]
        )
        .returning(SpecialEquipmentFavorite.product_id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.scalar_one_or_none() is not None


@timed_repository
async def delete_favorite(
    session: AsyncSession, user_id: UUID, product_id: UUID
) -> bool:
    result = await session.execute(
        sa.delete(SpecialEquipmentFavorite)
        .where(
            SpecialEquipmentFavorite.user_id == user_id,
            SpecialEquipmentFavorite.product_id == product_id,
        )
        .returning(SpecialEquipmentFavorite.product_id)
    )
    return result.scalar_one_or_none() is not None


@timed_repository
async def clear_favorites(session: AsyncSession, user_id: UUID) -> int:
    result = await session.execute(
        sa.delete(SpecialEquipmentFavorite).where(
            SpecialEquipmentFavorite.user_id == user_id
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


@timed_repository
async def list_cart_items(
    session: AsyncSession, user_id: UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.text(
            """
            SELECT
                cart.id,
                cart.user_id,
                cart.product_id,
                cart.quantity,
                cart.allow_overstock,
                cart.parent_item_id,
                cart.transfer_id,
                cart.is_selected,
                cart.custom_price,
                cart.comment,
                cart.equipments,
                cart.services,
                cart.added_at,
                cart.updated_at,
                p.slug,
                p.trim_id,
                trim.name AS trim_name,
                modification.id AS modification_id,
                modification.name AS modification_name,
                model.id AS model_id,
                model.name AS model_name,
                mark.id AS mark_id,
                mark.name AS mark_name,
                p.manufacture_year,
                body_color.id AS body_color_id,
                body_color.name AS body_color_name,
                CASE WHEN p.price_on_request THEN NULL ELSE p.price END AS base_price,
                CASE WHEN p.price_on_request THEN NULL ELSE p.special_price END AS special_price,
                p.price_on_request,
                p.price_from,
                CASE WHEN p.price_on_request THEN p.price_from
                     ELSE COALESCE(p.special_price, p.price) END AS price,
                p.currency_code,
                p.publication_status,
                p.sale_status,
                (
                    SELECT image.id
                    FROM special_equipment_product_images AS image
                    WHERE image.product_id = p.id
                    ORDER BY image.is_primary DESC, image.sort_order, image.id
                    LIMIT 1
                ) AS primary_image_id,
                p.superstructure_id,
                p.superstructure_name,
                super_type.name AS superstructure_type_name,
                p.superstructure_manufacturer
            FROM special_equipment_cart_items AS cart
            JOIN special_equipment_products AS p ON p.id = cart.product_id
            LEFT JOIN special_equipment_modifications AS modification
              ON modification.id = p.modification_id
            JOIN special_equipment_models AS model
              ON model.id = COALESCE(modification.model_id, p.model_id)
            JOIN special_equipment_marks AS mark
              ON mark.id = model.mark_id
            LEFT JOIN special_equipment_superstructures AS super_type
              ON super_type.id = p.superstructure_id
            LEFT JOIN special_equipment_trims AS trim
              ON trim.id = p.trim_id
            LEFT JOIN special_equipment_colors AS body_color
              ON body_color.id = p.body_color_id
            WHERE cart.user_id = :user_id
            ORDER BY cart.added_at DESC, cart.id DESC
            """
        ),
        {"user_id": user_id},
    )
    return [dict(row) for row in result.mappings().all()]


@timed_repository
async def get_cart_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    cart_item_id: UUID,
) -> dict[str, Any] | None:
    row = await session.scalar(
        sa.select(SpecialEquipmentCartItem).where(
            SpecialEquipmentCartItem.user_id == user_id,
            SpecialEquipmentCartItem.id == cart_item_id,
        )
    )
    return _to_dict(row) if row is not None else None


_CART_COMMERCIAL_FIELDS = ("custom_price", "comment", "equipments", "services")


def _cart_configuration(
    row: SpecialEquipmentCartItem,
) -> tuple[Decimal | None, str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    return row.custom_price, row.comment, row.equipments, row.services


def _ensure_uniform_cart_configuration(
    rows: list[SpecialEquipmentCartItem],
    *,
    expected: tuple[
        Decimal | None,
        str | None,
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]
    | None = None,
) -> None:
    if not rows:
        return
    baseline = expected if expected is not None else _cart_configuration(rows[0])
    if any(_cart_configuration(row) != baseline for row in rows):
        raise SpecialEquipmentCartConfigurationConflictError()


async def _lock_cart_product_scope(
    session: AsyncSession,
    *,
    user_id: UUID,
    product_id: UUID,
) -> None:
    lock_key = f"special-equipment-cart-config:{user_id}:{product_id}"
    await session.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(CAST(:lock_key AS text), 0))"
        ),
        {"lock_key": lock_key},
    )


@timed_repository
async def put_cart_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    product_id: UUID,
    quantity: int,
    parent_item_id: UUID | None,
    transfer_id: UUID | None,
    is_selected: bool,
    comment: str | None,
    equipments: list[dict[str, Any]],
    services: list[dict[str, Any]],
    allow_overstock: bool = False,
) -> tuple[dict[str, Any], bool]:
    await _lock_cart_product_scope(
        session,
        user_id=user_id,
        product_id=product_id,
    )
    if parent_item_id is not None:
        parent = await session.scalar(
            sa.select(SpecialEquipmentCartItem).where(
                SpecialEquipmentCartItem.id == parent_item_id,
                SpecialEquipmentCartItem.user_id == user_id,
                SpecialEquipmentCartItem.parent_item_id.is_(None),
            )
        )
        if parent is None:
            raise ValueError("Родительская позиция корзины не найдена")
    product_rows = list(
        (
            await session.execute(
                sa.select(SpecialEquipmentCartItem)
                .where(
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.product_id == product_id,
                )
                .order_by(SpecialEquipmentCartItem.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    _ensure_uniform_cart_configuration(
        product_rows,
        expected=(None, comment, equipments, services),
    )
    existing = next(
        (row for row in product_rows if row.parent_item_id == parent_item_id),
        None,
    )
    created = existing is None
    if existing is None:
        row = SpecialEquipmentCartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            parent_item_id=parent_item_id,
            transfer_id=transfer_id,
            is_selected=is_selected,
            comment=comment,
            equipments=equipments,
            services=services,
            allow_overstock=allow_overstock,
        )
        session.add(row)
    else:
        row = existing
        row.quantity = quantity
        row.transfer_id = transfer_id
        row.is_selected = is_selected
        row.comment = comment
        row.equipments = equipments
        row.services = services
        row.allow_overstock = bool(existing.allow_overstock or allow_overstock)
        row.updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(row), created


@timed_repository
async def patch_cart_item(  # noqa: PLR0912 -- explicit grouped-cart transitions
    session: AsyncSession,
    *,
    user_id: UUID,
    cart_item_id: UUID,
    changes: dict[str, Any],
) -> dict[str, Any] | None:
    identity = await session.execute(
        sa.select(SpecialEquipmentCartItem.product_id).where(
            SpecialEquipmentCartItem.user_id == user_id,
            SpecialEquipmentCartItem.id == cart_item_id,
        )
    )
    product_id = identity.scalar_one_or_none()
    if product_id is None:
        return None
    await _lock_cart_product_scope(
        session,
        user_id=user_id,
        product_id=product_id,
    )
    product_rows = list(
        (
            await session.execute(
                sa.select(SpecialEquipmentCartItem)
                .where(
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.product_id == product_id,
                )
                .order_by(SpecialEquipmentCartItem.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    row = next((item for item in product_rows if item.id == cart_item_id), None)
    if row is None:
        return None
    _ensure_uniform_cart_configuration(product_rows)
    for field in _CART_COMMERCIAL_FIELDS:
        if field not in changes:
            continue
        for item in product_rows:
            setattr(item, field, changes[field])
            item.updated_at = datetime.now(UTC)
    if not changes:
        return _to_dict(row)
    if "parent_item_id" in changes:
        parent_item_id = changes["parent_item_id"]
        if parent_item_id is not None:
            if parent_item_id == cart_item_id:
                raise ValueError("Позиция не может быть собственным родителем")
            has_children = await session.scalar(
                sa.select(sa.exists().where(
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.parent_item_id == cart_item_id,
                ))
            )
            if has_children:
                raise ValueError(
                    "Родительскую позицию с надстройками нельзя вложить в другую группу"
                )
            parent = await session.scalar(
                sa.select(SpecialEquipmentCartItem)
                .where(
                    SpecialEquipmentCartItem.id == parent_item_id,
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.parent_item_id.is_(None),
                )
                .with_for_update()
            )
            if parent is None:
                raise ValueError("Родительская позиция корзины не найдена")
            duplicate = await session.scalar(
                sa.select(SpecialEquipmentCartItem)
                .where(
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.product_id == row.product_id,
                    SpecialEquipmentCartItem.parent_item_id == parent_item_id,
                    SpecialEquipmentCartItem.id != cart_item_id,
                )
                .with_for_update()
            )
            if duplicate is not None:
                raise SpecialEquipmentCartPositionConflictError()
        elif row.parent_item_id is not None:
            standalone_rows = (
                (
                    await session.execute(
                        sa.select(SpecialEquipmentCartItem)
                        .where(
                            SpecialEquipmentCartItem.user_id == user_id,
                            SpecialEquipmentCartItem.product_id == row.product_id,
                            SpecialEquipmentCartItem.parent_item_id.is_(None),
                            SpecialEquipmentCartItem.id != cart_item_id,
                        )
                        .order_by(SpecialEquipmentCartItem.id)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            _ensure_uniform_cart_configuration([row, *standalone_rows])
            duplicate = standalone_rows[0] if standalone_rows else None
            if duplicate is not None:
                duplicate.quantity += int(changes.get("quantity", row.quantity))
                duplicate.is_selected = duplicate.is_selected or bool(
                    changes.get("is_selected", row.is_selected)
                )
                duplicate.transfer_id = duplicate.transfer_id or row.transfer_id
                duplicate.allow_overstock = bool(
                    duplicate.allow_overstock
                    or changes.get("allow_overstock", row.allow_overstock)
                )
                duplicate.updated_at = datetime.now(UTC)
                await session.delete(row)
                await session.flush()
                return _to_dict(duplicate)
    for key, value in changes.items():
        if key in _CART_COMMERCIAL_FIELDS:
            continue
        setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(row)


@timed_repository
async def delete_cart_item(
    session: AsyncSession, user_id: UUID, cart_item_id: UUID
) -> bool:
    target_product_id = await session.scalar(
        sa.select(SpecialEquipmentCartItem.product_id).where(
            SpecialEquipmentCartItem.user_id == user_id,
            SpecialEquipmentCartItem.id == cart_item_id,
        )
    )
    if target_product_id is None:
        return False
    discovered_child_product_ids = tuple(
        (
            await session.execute(
                sa.select(SpecialEquipmentCartItem.product_id)
                .where(
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.parent_item_id == cart_item_id,
                )
                .distinct()
            )
        ).scalars()
    )
    locked_product_ids = tuple(
        sorted(
            {target_product_id, *discovered_child_product_ids},
            key=str,
        )
    )
    for product_id in locked_product_ids:
        await _lock_cart_product_scope(
            session,
            user_id=user_id,
            product_id=product_id,
        )

    target = await session.scalar(
        sa.select(SpecialEquipmentCartItem)
        .where(
            SpecialEquipmentCartItem.user_id == user_id,
            SpecialEquipmentCartItem.id == cart_item_id,
        )
        .with_for_update()
    )
    if target is None:
        return False

    children = list(
        (
            await session.execute(
                sa.select(SpecialEquipmentCartItem)
                .where(
                    SpecialEquipmentCartItem.user_id == user_id,
                    SpecialEquipmentCartItem.parent_item_id == cart_item_id,
                )
                .order_by(
                    SpecialEquipmentCartItem.product_id,
                    SpecialEquipmentCartItem.id,
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    child_product_ids = tuple(
        sorted({child.product_id for child in children}, key=str)
    )
    if not set(child_product_ids).issubset(locked_product_ids):
        raise SpecialEquipmentCartPositionConflictError()

    related_rows: list[SpecialEquipmentCartItem] = []
    if child_product_ids:
        related_rows = list(
            (
                await session.execute(
                    sa.select(SpecialEquipmentCartItem)
                    .where(
                        SpecialEquipmentCartItem.user_id == user_id,
                        SpecialEquipmentCartItem.product_id.in_(child_product_ids),
                    )
                    .order_by(
                        SpecialEquipmentCartItem.product_id,
                        SpecialEquipmentCartItem.id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
    for product_id in child_product_ids:
        _ensure_uniform_cart_configuration(
            [row for row in related_rows if row.product_id == product_id]
        )
    standalone_rows = [
        row
        for row in related_rows
        if row.parent_item_id is None and row.id != cart_item_id
    ]

    now = datetime.now(UTC)
    for child in children:
        standalone = next(
            (
                row
                for row in standalone_rows
                if row.product_id == child.product_id
            ),
            None,
        )
        if standalone is None:
            child.parent_item_id = None
            child.updated_at = now
            standalone_rows.append(child)
            continue
        standalone.quantity += child.quantity
        standalone.is_selected = standalone.is_selected or child.is_selected
        standalone.transfer_id = standalone.transfer_id or child.transfer_id
        standalone.updated_at = now
        await session.delete(child)

    await session.flush()
    await session.delete(target)
    await session.flush()
    return True


@timed_repository
async def lock_guest_cart_transfer(
    session: AsyncSession,
    user_id: UUID,
    transfer_id: UUID,
) -> None:
    lock_key = f"special-equipment-cart-transfer:{user_id}:{transfer_id}"
    await session.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock("
            "hashtextextended(CAST(:lock_key AS text), 0))"
        ),
        {"lock_key": lock_key},
    )


@timed_repository
async def get_guest_cart_transfer(
    session: AsyncSession,
    user_id: UUID,
    transfer_id: UUID,
) -> dict[str, Any] | None:
    row = await session.scalar(
        sa.select(SpecialEquipmentGuestCartTransfer).where(
            SpecialEquipmentGuestCartTransfer.user_id == user_id,
            SpecialEquipmentGuestCartTransfer.transfer_id == transfer_id,
        )
    )
    return _to_dict(row) if row is not None else None


@timed_repository
async def create_guest_cart_transfer(
    session: AsyncSession,
    *,
    user_id: UUID,
    transfer_id: UUID,
    request_hash: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    row = SpecialEquipmentGuestCartTransfer(
        user_id=user_id,
        transfer_id=transfer_id,
        request_hash=request_hash,
        result=result,
    )
    session.add(row)
    await session.flush()
    return _to_dict(row)


@timed_repository
async def clear_cart(session: AsyncSession, user_id: UUID) -> int:
    result = await session.execute(
        sa.delete(SpecialEquipmentCartItem).where(
            SpecialEquipmentCartItem.user_id == user_id
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


@timed_repository
async def get_cart_items_for_checkout(
    session: AsyncSession,
    *,
    user_id: UUID,
    cart_item_ids: tuple[UUID, ...],
) -> list[dict[str, Any]]:
    """Lock an explicit server-cart selection in deterministic order."""

    rows = (
        await session.execute(
            sa.select(SpecialEquipmentCartItem)
            .where(
                SpecialEquipmentCartItem.user_id == user_id,
                SpecialEquipmentCartItem.id.in_(cart_item_ids),
            )
            .order_by(SpecialEquipmentCartItem.id)
            .with_for_update()
        )
    ).scalars()
    return [_to_dict(row) for row in rows]


@timed_repository
async def delete_cart_items_by_ids(
    session: AsyncSession,
    *,
    user_id: UUID,
    cart_item_ids: tuple[UUID, ...],
) -> int:
    """Delete checkout rows without bypassing grouped-cart detach semantics."""

    rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentCartItem.id,
                SpecialEquipmentCartItem.parent_item_id,
            ).where(
                SpecialEquipmentCartItem.user_id == user_id,
                SpecialEquipmentCartItem.id.in_(cart_item_ids),
            )
        )
    ).all()
    ordered_ids = [
        row.id
        for row in sorted(
            rows,
            key=lambda row: (row.parent_item_id is None, str(row.id)),
        )
    ]
    deleted = 0
    for cart_item_id in ordered_ids:
        deleted += int(await delete_cart_item(session, user_id, cart_item_id))
    return deleted


@timed_repository
async def find_order_by_idempotency(
    session: AsyncSession, user_id: UUID, idempotency_key: str
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SpecialEquipmentPurchaseOrder).where(
            SpecialEquipmentPurchaseOrder.user_id == user_id,
            SpecialEquipmentPurchaseOrder.idempotency_key == idempotency_key,
        )
    )
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def find_order_by_refund_reference(
    session: AsyncSession,
    external_reference: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SpecialEquipmentPurchaseOrder).where(
            SpecialEquipmentPurchaseOrder.refund_external_reference
            == external_reference
        )
    )
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def create_order(
    session: AsyncSession, values: dict[str, Any]
) -> dict[str, Any]:
    row = SpecialEquipmentPurchaseOrder(**values)
    session.add(row)
    await session.flush()
    return _to_dict(row)


@timed_repository
async def create_order_items(
    session: AsyncSession,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [SpecialEquipmentOrderItem(**entry) for entry in entries]
    session.add_all(rows)
    await session.flush()
    return [_to_dict(row) for row in rows]


@timed_repository
async def list_order_items(
    session: AsyncSession,
    order_id: UUID,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            sa.select(SpecialEquipmentOrderItem)
            .where(SpecialEquipmentOrderItem.purchase_order_id == order_id)
            .order_by(
                SpecialEquipmentOrderItem.position,
                SpecialEquipmentOrderItem.id,
            )
        )
    ).scalars()
    return [_to_dict(row) for row in rows]


@timed_repository
async def list_order_items_batch(
    session: AsyncSession,
    order_ids: tuple[UUID, ...],
) -> dict[UUID, list[dict[str, Any]]]:
    if not order_ids:
        return {}
    rows = (
        await session.execute(
            sa.select(SpecialEquipmentOrderItem)
            .where(SpecialEquipmentOrderItem.purchase_order_id.in_(order_ids))
            .order_by(
                SpecialEquipmentOrderItem.purchase_order_id,
                SpecialEquipmentOrderItem.position,
                SpecialEquipmentOrderItem.id,
            )
        )
    ).scalars()
    result: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row.purchase_order_id, []).append(_to_dict(row))
    return result


@timed_repository
async def update_order_allocations_sale_status(
    session: AsyncSession,
    order_id: UUID,
    status: str,
) -> None:
    """Move every concrete physical unit allocated to an order."""

    await session.execute(
        sa.update(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.id.in_(
                sa.select(SpecialEquipmentOrderItem.product_id).where(
                    SpecialEquipmentOrderItem.purchase_order_id == order_id
                )
            )
        )
        .values(
            sale_status=status,
            lock_version=SpecialEquipmentProduct.lock_version + 1,
            updated_at=datetime.now(UTC),
        )
    )


@timed_repository
async def reserve_available_order_allocations(
    session: AsyncSession,
    order_id: UUID,
) -> None:
    """Reserve only available units of a mixed preorder cart group."""

    await session.execute(
        sa.update(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.id.in_(
                sa.select(SpecialEquipmentOrderItem.product_id).where(
                    SpecialEquipmentOrderItem.purchase_order_id == order_id
                )
            ),
            SpecialEquipmentProduct.sale_status == "available",
        )
        .values(
            sale_status="reserved",
            lock_version=SpecialEquipmentProduct.lock_version + 1,
            updated_at=datetime.now(UTC),
        )
    )


@timed_repository
async def release_order_allocations_if_unclaimed(
    session: AsyncSession,
    order_id: UUID,
) -> int:
    product_ids = tuple(
        (
            await session.execute(
                sa.select(SpecialEquipmentOrderItem.product_id)
                .where(SpecialEquipmentOrderItem.purchase_order_id == order_id)
                .order_by(SpecialEquipmentOrderItem.product_id)
            )
        ).scalars()
    )
    released = 0
    for product_id in product_ids:
        released += int(
            await release_product_if_unclaimed(
                session,
                product_id,
                excluding_order_id=order_id,
            )
        )
    return released


@timed_repository
async def order_allocations_have_conflicts(
    session: AsyncSession,
    order_id: UUID,
    *,
    excluding_application_id: UUID | None = None,
) -> bool:
    product_ids = tuple(
        (
            await session.execute(
                sa.select(SpecialEquipmentOrderItem.product_id)
                .where(SpecialEquipmentOrderItem.purchase_order_id == order_id)
                .order_by(SpecialEquipmentOrderItem.product_id)
            )
        ).scalars()
    )
    for product_id in product_ids:
        if await has_conflicting_product_claim(
            session,
            product_id=product_id,
            excluding_order_id=order_id,
            excluding_application_id=excluding_application_id,
        ):
            return True
    return False


@timed_repository
async def list_orders(
    session: AsyncSession,
    user_id: UUID,
    *,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    total = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(SpecialEquipmentPurchaseOrder)
            .where(SpecialEquipmentPurchaseOrder.user_id == user_id)
        )
        or 0
    )
    result = await session.execute(
        sa.select(SpecialEquipmentPurchaseOrder)
        .where(SpecialEquipmentPurchaseOrder.user_id == user_id)
        .order_by(
            SpecialEquipmentPurchaseOrder.created_at.desc(),
            SpecialEquipmentPurchaseOrder.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return [_to_dict(row) for row in result.scalars().all()], total


@timed_repository
async def get_order(
    session: AsyncSession, order_id: UUID, *, lock: bool = False
) -> dict[str, Any] | None:
    stmt = sa.select(SpecialEquipmentPurchaseOrder).where(
        SpecialEquipmentPurchaseOrder.id == order_id
    )
    if lock:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def update_order(
    session: AsyncSession, order_id: UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    changes["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(SpecialEquipmentPurchaseOrder)
        .where(SpecialEquipmentPurchaseOrder.id == order_id)
        .values(**changes)
        .returning(SpecialEquipmentPurchaseOrder)
    )
    row = result.scalar_one()
    await session.flush()
    return _to_dict(row)


@timed_repository
async def update_product_sale_status(
    session: AsyncSession, product_id: UUID, status: str
) -> None:
    await session.execute(
        sa.text(
            """
            UPDATE special_equipment_products
            SET sale_status = :status,
                lock_version = lock_version + 1,
                updated_at = current_timestamp
            WHERE id = :product_id
            """
        ),
        {"product_id": product_id, "status": status},
    )


@timed_repository
async def release_product_if_unclaimed(
    session: AsyncSession,
    product_id: UUID,
    *,
    excluding_order_id: UUID,
) -> bool:
    """Release a unit only when no exclusive commerce claim still owns it.

    Active leasing applications are non-exclusive until their item becomes
    ``reserved``. The conditional UPDATE keeps the claim check and status
    transition in one PostgreSQL statement.
    """

    result = await session.execute(
        sa.text(
            """
            UPDATE special_equipment_products AS product
            SET sale_status = 'available',
                lock_version = product.lock_version + 1,
                updated_at = current_timestamp
            WHERE product.id = :product_id
              AND product.sale_status IN ('reserved', 'sold')
              AND NOT EXISTS (
                  SELECT 1
                  FROM special_equipment_order_items AS claimed_item
                  JOIN special_equipment_purchase_orders AS claimed_order
                    ON claimed_order.id = claimed_item.purchase_order_id
                  WHERE claimed_item.product_id = product.id
                    AND claimed_order.id <> :excluding_order_id
                    AND claimed_order.purchase_type <> 'preorder'
                    AND claimed_order.status IN (
                        'payment_pending', 'reserved', 'purchased',
                        'leasing_pending', 'leasing_active',
                        'cancellation_requested'
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM special_equipment_application_items AS claimed_item
                  WHERE claimed_item.product_id = product.id
                    AND claimed_item.item_status = 'reserved'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM application_vehicle_allocations AS claimed_allocation
                  WHERE claimed_allocation.product_id = product.id
                    AND claimed_allocation.released_at IS NULL
              )
            RETURNING product.id
            """
        ),
        {
            "product_id": product_id,
            "excluding_order_id": excluding_order_id,
        },
    )
    return result.scalar_one_or_none() is not None


@timed_repository
async def release_order_application_claim(
    session: AsyncSession,
    application_id: UUID,
    product_id: UUID,
) -> bool:
    """Terminalize the leasing item represented by a cancelled order."""

    result = await session.execute(
        sa.update(SpecialEquipmentApplicationItem)
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            SpecialEquipmentApplicationItem.product_id == product_id,
            SpecialEquipmentApplicationItem.item_status == "reserved",
        )
        .values(item_status="removed", updated_at=datetime.now(UTC))
    )
    await session.flush()
    return bool(getattr(result, "rowcount", 0))


@timed_repository
async def release_order_application_claims(
    session: AsyncSession,
    application_id: UUID,
    order_id: UUID,
) -> int:
    """Terminalize every application item materialized in one leasing order."""

    result = await session.execute(
        sa.update(SpecialEquipmentApplicationItem)
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            SpecialEquipmentApplicationItem.product_id.in_(
                sa.select(SpecialEquipmentOrderItem.product_id).where(
                    SpecialEquipmentOrderItem.purchase_order_id == order_id
                )
            ),
            SpecialEquipmentApplicationItem.item_status == "reserved",
        )
        .values(item_status="removed", updated_at=datetime.now(UTC))
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


@timed_repository
async def create_payment(
    session: AsyncSession, values: dict[str, Any]
) -> dict[str, Any]:
    row = SpecialEquipmentPayment(**values)
    session.add(row)
    await session.flush()
    return _to_dict(row)


@timed_repository
async def find_payment_by_idempotency(
    session: AsyncSession, order_id: UUID, idempotency_key: str
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SpecialEquipmentPayment).where(
            SpecialEquipmentPayment.purchase_order_id == order_id,
            SpecialEquipmentPayment.idempotency_key == idempotency_key,
        )
    )
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def find_active_order_payment(
    session: AsyncSession,
    order_id: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SpecialEquipmentPayment)
        .where(
            SpecialEquipmentPayment.purchase_order_id == order_id,
            SpecialEquipmentPayment.status.in_(("pending", "processing")),
        )
        .order_by(
            SpecialEquipmentPayment.created_at.desc(),
            SpecialEquipmentPayment.id.desc(),
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def get_payment(
    session: AsyncSession,
    payment_id: UUID,
    *,
    lock: bool = False,
) -> dict[str, Any] | None:
    stmt = sa.select(SpecialEquipmentPayment).where(
        SpecialEquipmentPayment.id == payment_id
    )
    if lock:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def get_payment_by_gateway_transaction(
    session: AsyncSession,
    gateway_transaction_id: str,
    *,
    lock: bool = False,
) -> dict[str, Any] | None:
    stmt = sa.select(SpecialEquipmentPayment).where(
        SpecialEquipmentPayment.gateway_transaction_id == gateway_transaction_id
    )
    if lock:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def get_payment_by_fiscal_receipt_id(
    session: AsyncSession,
    fiscal_receipt_id: str | None,
) -> dict[str, Any] | None:
    if not fiscal_receipt_id:
        return None
    result = await session.execute(
        sa.select(SpecialEquipmentPayment).where(
            SpecialEquipmentPayment.fiscal_receipt_id == fiscal_receipt_id
        )
    )
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def put_payment_callback_inbox(
    session: AsyncSession,
    *,
    event_key: str,
    gateway_transaction_id: str,
    payment_id: UUID | None,
    signature_digest: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Insert one verified callback, returning the existing row on replay."""

    statement = (
        pg_insert(SpecialEquipmentPaymentCallbackInbox)
        .values(
            event_key=event_key,
            gateway_transaction_id=gateway_transaction_id,
            payment_id=payment_id,
            signature_digest=signature_digest,
            payload=payload,
        )
        .on_conflict_do_nothing(
            constraint="uq_special_equipment_callback_inbox_event_key"
        )
        .returning(SpecialEquipmentPaymentCallbackInbox)
    )
    inserted = (await session.execute(statement)).scalar_one_or_none()
    if inserted is not None:
        await session.flush()
        return _to_dict(inserted), True

    existing = (
        await session.execute(
            sa.select(SpecialEquipmentPaymentCallbackInbox).where(
                SpecialEquipmentPaymentCallbackInbox.event_key == event_key
            )
        )
    ).scalar_one()
    return _to_dict(existing), False


@timed_repository
async def claim_payment_callback_inboxes(
    session: AsyncSession,
    *,
    now: datetime,
    lease_for: timedelta,
    limit: int = 25,
    inbox_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Lease due inbox rows with ``SKIP LOCKED`` for request/task workers."""

    due = sa.and_(
        SpecialEquipmentPaymentCallbackInbox.status.in_(("pending", "retry")),
        sa.or_(
            SpecialEquipmentPaymentCallbackInbox.next_retry_at.is_(None),
            SpecialEquipmentPaymentCallbackInbox.next_retry_at <= now,
        ),
        sa.or_(
            SpecialEquipmentPaymentCallbackInbox.lease_until.is_(None),
            SpecialEquipmentPaymentCallbackInbox.lease_until <= now,
        ),
    )
    statement = sa.select(SpecialEquipmentPaymentCallbackInbox).where(due)
    if inbox_id is not None:
        statement = statement.where(
            SpecialEquipmentPaymentCallbackInbox.id == inbox_id
        )
    rows = list(
        (
            await session.execute(
                statement.order_by(
                    SpecialEquipmentPaymentCallbackInbox.next_retry_at
                    .asc()
                    .nullsfirst(),
                    SpecialEquipmentPaymentCallbackInbox.received_at,
                    SpecialEquipmentPaymentCallbackInbox.id,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    claimed: list[dict[str, Any]] = []
    for row in rows:
        row.lease_token = uuid4()
        row.lease_until = now + lease_for
        row.next_retry_at = None
        row.attempt_count += 1
        row.updated_at = now
        claimed.append(_to_dict(row))
    await session.flush()
    return claimed


@timed_repository
async def get_payment_callback_inbox_for_processing(
    session: AsyncSession,
    inbox_id: UUID,
    lease_token: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SpecialEquipmentPaymentCallbackInbox)
        .where(
            SpecialEquipmentPaymentCallbackInbox.id == inbox_id,
            SpecialEquipmentPaymentCallbackInbox.lease_token == lease_token,
            SpecialEquipmentPaymentCallbackInbox.status.in_(("pending", "retry")),
        )
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def update_payment_callback_inbox(
    session: AsyncSession,
    inbox_id: UUID,
    changes: dict[str, Any],
) -> dict[str, Any]:
    values = {**changes, "updated_at": datetime.now(UTC)}
    result = await session.execute(
        sa.update(SpecialEquipmentPaymentCallbackInbox)
        .where(SpecialEquipmentPaymentCallbackInbox.id == inbox_id)
        .values(**values)
        .returning(SpecialEquipmentPaymentCallbackInbox)
    )
    row = result.scalar_one()
    await session.flush()
    return _to_dict(row)


@timed_repository
async def list_manual_review_payment_callbacks(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(
            SpecialEquipmentPaymentCallbackInbox,
            SpecialEquipmentPayment.purchase_order_id,
        )
        .outerjoin(
            SpecialEquipmentPayment,
            SpecialEquipmentPayment.id
            == SpecialEquipmentPaymentCallbackInbox.payment_id,
        )
        .where(SpecialEquipmentPaymentCallbackInbox.status == "manual_review")
        .order_by(
            SpecialEquipmentPaymentCallbackInbox.received_at.desc(),
            SpecialEquipmentPaymentCallbackInbox.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return [
        {**_to_dict(inbox), "purchase_order_id": purchase_order_id}
        for inbox, purchase_order_id in result.all()
    ]


@timed_repository
async def get_payment_callback_inbox(
    session: AsyncSession,
    inbox_id: UUID,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.select(
                SpecialEquipmentPaymentCallbackInbox,
                SpecialEquipmentPayment.purchase_order_id,
            )
            .outerjoin(
                SpecialEquipmentPayment,
                SpecialEquipmentPayment.id
                == SpecialEquipmentPaymentCallbackInbox.payment_id,
            )
            .where(SpecialEquipmentPaymentCallbackInbox.id == inbox_id)
        )
    ).one_or_none()
    if row is None:
        return None
    inbox, purchase_order_id = row
    return {**_to_dict(inbox), "purchase_order_id": purchase_order_id}


@timed_repository
async def has_conflicting_product_claim(
    session: AsyncSession,
    *,
    product_id: UUID,
    excluding_order_id: UUID,
    excluding_application_id: UUID | None = None,
) -> bool:
    """Lock the sellable unit and detect a newer exclusive claim."""

    product = await get_product(session, product_id, lock=True)
    if product is None:
        return True
    conflicting_order = sa.exists().where(
        SpecialEquipmentOrderItem.product_id == product_id,
        SpecialEquipmentOrderItem.purchase_order_id
        == SpecialEquipmentPurchaseOrder.id,
        SpecialEquipmentPurchaseOrder.id != excluding_order_id,
        SpecialEquipmentPurchaseOrder.purchase_type != "preorder",
        SpecialEquipmentPurchaseOrder.status.in_(
            (
                "payment_pending",
                "reserved",
                "purchased",
                "leasing_pending",
                "leasing_active",
                "cancellation_requested",
            )
        ),
    )
    reserved_application_conditions = [
        SpecialEquipmentApplicationItem.product_id == product_id,
        SpecialEquipmentApplicationItem.item_status == "reserved",
    ]
    if excluding_application_id is not None:
        reserved_application_conditions.append(
            SpecialEquipmentApplicationItem.application_id
            != excluding_application_id
        )
    reserved_application = sa.exists().where(
        *reserved_application_conditions
    )
    return bool(
        await session.scalar(sa.select(conflicting_order | reserved_application))
    )


@timed_repository
async def claim_fiscalization_payments(
    session: AsyncSession,
    *,
    now: datetime,
    sent_stale_after: timedelta,
    failed_retry_after: timedelta,
    limit: int = 25,
    payment_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Claim durable fiscal work; provider I/O starts after this commits."""

    due = sa.or_(
        SpecialEquipmentPayment.fiscal_status == "pending",
        sa.and_(
            SpecialEquipmentPayment.fiscal_status == "failed",
            SpecialEquipmentPayment.updated_at <= now - failed_retry_after,
        ),
        sa.and_(
            SpecialEquipmentPayment.fiscal_status == "sent",
            SpecialEquipmentPayment.updated_at <= now - sent_stale_after,
        ),
    )
    statement = sa.select(SpecialEquipmentPayment).where(
        SpecialEquipmentPayment.status == "completed",
        SpecialEquipmentPayment.payment_method != "bank_transfer",
        due,
    )
    if payment_id is not None:
        statement = statement.where(SpecialEquipmentPayment.id == payment_id)
    rows = list(
        (
            await session.execute(
                statement.order_by(
                    SpecialEquipmentPayment.updated_at,
                    SpecialEquipmentPayment.id,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.fiscal_status = "sent"
        row.fiscal_retry_count += 1
        row.fiscal_error_message = None
        row.updated_at = now
        if row.fiscal_receipt_id is None:
            row.fiscal_receipt_id = f"{row.id}-special-equipment"
    await session.flush()
    return [_to_dict(row) for row in rows]


@timed_repository
async def claim_receipt_ingestions(
    session: AsyncSession,
    *,
    now: datetime,
    processing_stale_after: timedelta,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Claim due receipt downloads without duplicate work across workers."""

    retry_due = sa.and_(
        SpecialEquipmentPayment.receipt_ingestion_status.in_(
            ("pending", "failed")
        ),
        sa.or_(
            SpecialEquipmentPayment.receipt_ingestion_next_retry_at.is_(None),
            SpecialEquipmentPayment.receipt_ingestion_next_retry_at <= now,
        ),
    )
    stale_processing = sa.and_(
        SpecialEquipmentPayment.receipt_ingestion_status == "processing",
        SpecialEquipmentPayment.updated_at <= now - processing_stale_after,
    )
    result = await session.execute(
        sa.select(SpecialEquipmentPayment)
        .where(
            SpecialEquipmentPayment.fiscal_status == "completed",
            SpecialEquipmentPayment.fiscal_receipt_id.is_not(None),
            SpecialEquipmentPayment.receipt_storage_key.is_(None),
            sa.or_(retry_due, stale_processing),
        )
        .order_by(
            SpecialEquipmentPayment.receipt_ingestion_next_retry_at.asc().nullsfirst(),
            SpecialEquipmentPayment.updated_at,
            SpecialEquipmentPayment.id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list(result.scalars().all())
    if not rows:
        return []
    payment_ids = [row.id for row in rows]
    await session.execute(
        sa.update(SpecialEquipmentPayment)
        .where(SpecialEquipmentPayment.id.in_(payment_ids))
        .values(receipt_ingestion_status="processing", updated_at=now)
    )
    await session.flush()
    return [
        {
            "id": row.id,
            "receipt_ingestion_retry_count": row.receipt_ingestion_retry_count,
        }
        for row in rows
    ]


@timed_repository
async def update_payment(
    session: AsyncSession, payment_id: UUID, changes: dict[str, Any]
) -> dict[str, Any]:
    changes["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(SpecialEquipmentPayment)
        .where(SpecialEquipmentPayment.id == payment_id)
        .values(**changes)
        .returning(SpecialEquipmentPayment)
    )
    row = result.scalar_one()
    await session.flush()
    return _to_dict(row)


@timed_repository
async def list_order_payments(
    session: AsyncSession, order_id: UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(SpecialEquipmentPayment)
        .where(SpecialEquipmentPayment.purchase_order_id == order_id)
        .order_by(SpecialEquipmentPayment.created_at, SpecialEquipmentPayment.id)
    )
    return [_to_dict(row) for row in result.scalars().all()]


@timed_repository
async def list_application_items(
    session: AsyncSession,
    application_id: UUID,
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(SpecialEquipmentApplicationItem)
        .where(
            SpecialEquipmentApplicationItem.application_id == application_id,
            SpecialEquipmentApplicationItem.item_status.in_(("active", "reserved")),
        )
        .order_by(SpecialEquipmentApplicationItem.id)
    )
    return [_to_dict(row) for row in result.scalars().all()]


@timed_repository
async def application_has_vehicle_items(
    session: AsyncSession,
    application_id: UUID,
) -> bool:
    return bool(
        await session.scalar(
            sa.select(
                sa.exists().where(
                    ApplicationVehicle.application_id == application_id
                )
            )
        )
    )


@timed_repository
async def update_application_item_status(
    session: AsyncSession,
    item_id: UUID,
    *,
    status: str,
) -> None:
    await session.execute(
        sa.update(SpecialEquipmentApplicationItem)
        .where(SpecialEquipmentApplicationItem.id == item_id)
        .values(
            item_status=status,
            reserve_expires_at=None,
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()


@timed_repository
async def create_schedule_entries(
    session: AsyncSession,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [SpecialEquipmentLeasingPaymentSchedule(**entry) for entry in entries]
    session.add_all(rows)
    await session.flush()
    return [_to_dict(row) for row in rows]


@timed_repository
async def list_schedule_by_order(
    session: AsyncSession,
    order_id: UUID,
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(
            SpecialEquipmentLeasingPaymentSchedule,
            SpecialEquipmentPayment.status.label("payment_status"),
            SpecialEquipmentPayment.paid_at.label("payment_paid_at"),
            SpecialEquipmentPayment.receipt_storage_key.is_not(None).label(
                "has_receipt"
            ),
        )
        .outerjoin(
            SpecialEquipmentPayment,
            SpecialEquipmentPayment.id
            == SpecialEquipmentLeasingPaymentSchedule.payment_id,
        )
        .where(
            SpecialEquipmentLeasingPaymentSchedule.purchase_order_id == order_id
        )
        .order_by(
            SpecialEquipmentLeasingPaymentSchedule.payment_number,
            SpecialEquipmentLeasingPaymentSchedule.id,
        )
    )
    return [
        {
            **_to_dict(schedule),
            "payment_status": payment_status,
            "payment_paid_at": payment_paid_at,
            "has_receipt": has_receipt,
        }
        for schedule, payment_status, payment_paid_at, has_receipt in result.all()
    ]


@timed_repository
async def get_schedule_item(
    session: AsyncSession,
    schedule_id: UUID,
    *,
    lock: bool = False,
) -> dict[str, Any] | None:
    stmt = sa.select(SpecialEquipmentLeasingPaymentSchedule).where(
        SpecialEquipmentLeasingPaymentSchedule.id == schedule_id
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    return _to_dict(row) if row else None


@timed_repository
async def attach_schedule_payment(
    session: AsyncSession,
    schedule_id: UUID,
    payment_id: UUID,
) -> dict[str, Any]:
    result = await session.execute(
        sa.update(SpecialEquipmentLeasingPaymentSchedule)
        .where(
            SpecialEquipmentLeasingPaymentSchedule.id == schedule_id,
            SpecialEquipmentLeasingPaymentSchedule.is_paid.is_(False),
            SpecialEquipmentLeasingPaymentSchedule.payment_id.is_(None),
        )
        .values(payment_id=payment_id, updated_at=datetime.now(UTC))
        .returning(SpecialEquipmentLeasingPaymentSchedule)
    )
    row = result.scalar_one()
    await session.flush()
    return _to_dict(row)


@timed_repository
async def mark_schedule_paid(
    session: AsyncSession,
    schedule_id: UUID,
    payment_id: UUID,
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.update(SpecialEquipmentLeasingPaymentSchedule)
        .where(
            SpecialEquipmentLeasingPaymentSchedule.id == schedule_id,
            SpecialEquipmentLeasingPaymentSchedule.payment_id == payment_id,
            SpecialEquipmentLeasingPaymentSchedule.is_paid.is_(False),
        )
        .values(is_paid=True, updated_at=datetime.now(UTC))
        .returning(SpecialEquipmentLeasingPaymentSchedule)
    )
    row = result.scalar_one_or_none()
    await session.flush()
    return _to_dict(row) if row else None


@timed_repository
async def clear_schedule_payment(
    session: AsyncSession,
    schedule_id: UUID,
    payment_id: UUID,
) -> None:
    await session.execute(
        sa.update(SpecialEquipmentLeasingPaymentSchedule)
        .where(
            SpecialEquipmentLeasingPaymentSchedule.id == schedule_id,
            SpecialEquipmentLeasingPaymentSchedule.payment_id == payment_id,
            SpecialEquipmentLeasingPaymentSchedule.is_paid.is_(False),
        )
        .values(payment_id=None, updated_at=datetime.now(UTC))
    )
    await session.flush()


@timed_repository
async def find_expired_gateway_payments(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return expiry candidates; caller re-locks order then payment."""

    result = await session.execute(
        sa.select(SpecialEquipmentPayment)
        .where(
            SpecialEquipmentPayment.status == "pending",
            SpecialEquipmentPayment.expires_at.is_not(None),
            SpecialEquipmentPayment.expires_at <= now,
        )
        .order_by(
            SpecialEquipmentPayment.expires_at,
            SpecialEquipmentPayment.id,
        )
        .limit(limit)
    )
    return [_to_dict(row) for row in result.scalars().all()]


@timed_repository
async def find_expired_initial_orders(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Lock unpaid initial holds, excluding offline reconciliation."""

    bank_transfer_reconciliation = sa.exists().where(
        SpecialEquipmentPayment.purchase_order_id
        == SpecialEquipmentPurchaseOrder.id,
        SpecialEquipmentPayment.payment_method == "bank_transfer",
        SpecialEquipmentPayment.status == "processing",
    )

    result = await session.execute(
        sa.select(SpecialEquipmentPurchaseOrder)
        .where(
            SpecialEquipmentPurchaseOrder.status == "payment_pending",
            SpecialEquipmentPurchaseOrder.hold_expires_at.is_not(None),
            SpecialEquipmentPurchaseOrder.hold_expires_at <= now,
            SpecialEquipmentPurchaseOrder.paid_amount == Decimal("0.00"),
            ~bank_transfer_reconciliation,
        )
        .order_by(
            SpecialEquipmentPurchaseOrder.hold_expires_at,
            SpecialEquipmentPurchaseOrder.id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return [_to_dict(row) for row in result.scalars().all()]


@timed_repository
async def create_leasing_application(
    session: AsyncSession,
    *,
    actor_id: UUID,
    company_id: UUID,
    storefront_id: UUID,
    dealer_company_id: UUID | None,
    source_type: str | None = None,
    product: dict[str, Any],
    snapshot: dict[str, Any],
    comment: str | None,
    leasing_purpose: str | None,
    leasing_purposes: list[str] | None = None,
    regions: list[str],
    down_payment_percent: Decimal | None,
    lease_term_months: int | None,
    financials: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company_exists = await session.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM companies WHERE id = :company_id)"
        ),
        {"company_id": company_id},
    )
    if not company_exists:
        return {}
    price = product.get("price")
    fin = financials or {}
    application = LeasingApplication(
        company_id=company_id,
        storefront_id=storefront_id,
        source_type=source_type,
        dealer_company_id=dealer_company_id,
        created_by=actor_id,
        status="active",
        total_amount=fin.get("total_amount") if fin.get("total_amount") is not None else price,
        down_payment=fin.get("down_payment"),
        down_payment_percent=fin.get("down_payment_percent") if fin.get("down_payment_percent") is not None else down_payment_percent,
        lease_term_months=int(fin["lease_term_months"]) if fin.get("lease_term_months") is not None else lease_term_months,
        monthly_payment=fin.get("monthly_payment"),
        total_cost=fin.get("total_cost"),
        markup=fin.get("markup"),
        rate=fin.get("rate"),
        total_interest=fin.get("total_interest"),
        buyout_amount=fin.get("buyout_amount"),
        vat_refund=fin.get("vat_refund"),
        profit_tax_savings=fin.get("profit_tax_savings"),
        total_savings=fin.get("total_savings"),
        current_stage="leasing_companies",
    )
    session.add(application)
    await session.flush()
    if financials:
        await application_repository.upsert_calculation(
            session, application_id=application.id, payload=financials
        )
    item_id = uuid4()
    item = SpecialEquipmentApplicationItem(
        id=item_id,
        application_id=application.id,
        product_id=product["id"],
        seller_company_id=dealer_company_id,
        unit_price=price,
        total_price=price,
        currency_code=product.get("currency_code") or "RUB",
        item_snapshot=snapshot,
        comment=comment,
        leasing_purpose=next(iter(selected_purposes(leasing_purposes, leasing_purpose)), None),
        leasing_purposes=selected_purposes(leasing_purposes, leasing_purpose),
        regions=regions,
        item_status="active",
        price_status=_initial_requested_price_status(
            item_role="offer",
            item_snapshot=snapshot,
        ),
    )
    vehicle = ApplicationVehicle(
        id=item_id,
        application_id=application.id,
        product_id=product["id"],
        dealer_company_id=dealer_company_id,
        quantity=1,
        requested_quantity=1,
        unit_price=price,
        total_price=price,
        comment=comment,
        equipments=[],
        services=[],
        leasing_purpose=next(iter(selected_purposes(leasing_purposes, leasing_purpose)), None),
        leasing_purposes=selected_purposes(leasing_purposes, leasing_purpose),
        regions=regions or [],
        car_status="active",
    )
    session.add(item)
    session.add(vehicle)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, application.id)
    return {
        "application_id": application.id,
        "source_type": application.source_type,
        "item_id": item.id,
        "product_id": item.product_id,
        "status": application.status,
        "item_status": item.item_status,
    }


@timed_repository
async def create_leasing_application_from_items(
    session: AsyncSession,
    *,
    actor_id: UUID,
    company_id: UUID,
    storefront_id: UUID,
    dealer_company_id: UUID | None,
    source_type: str | None = None,
    total_amount: Decimal | None,
    down_payment_percent: Decimal | None,
    lease_term_months: int | None,
    item_entries: list[dict[str, Any]],
    financials: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company_exists = await session.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM companies WHERE id = :company_id)"
        ),
        {"company_id": company_id},
    )
    if not company_exists:
        return {}
    fin = financials or {}
    application = LeasingApplication(
        company_id=company_id,
        storefront_id=storefront_id,
        source_type=source_type,
        dealer_company_id=dealer_company_id,
        created_by=actor_id,
        status="active",
        total_amount=fin.get("total_amount") if fin.get("total_amount") is not None else total_amount,
        down_payment=fin.get("down_payment"),
        down_payment_percent=fin.get("down_payment_percent") if fin.get("down_payment_percent") is not None else down_payment_percent,
        lease_term_months=int(fin["lease_term_months"]) if fin.get("lease_term_months") is not None else lease_term_months,
        monthly_payment=fin.get("monthly_payment"),
        total_cost=fin.get("total_cost"),
        markup=fin.get("markup"),
        rate=fin.get("rate"),
        total_interest=fin.get("total_interest"),
        buyout_amount=fin.get("buyout_amount"),
        vat_refund=fin.get("vat_refund"),
        profit_tax_savings=fin.get("profit_tax_savings"),
        total_savings=fin.get("total_savings"),
        current_stage="leasing_companies",
    )
    session.add(application)
    await session.flush()
    if financials:
        await application_repository.upsert_calculation(
            session, application_id=application.id, payload=financials
        )
    items = []
    vehicles = []
    for entry in item_entries:
        item_values = dict(entry)
        item_values.setdefault(
            "price_status",
            _initial_requested_price_status(
                item_role=str(item_values.get("item_role") or "offer"),
                item_snapshot=item_values.get("item_snapshot") or {},
            ),
        )
        item_id = item_values.pop("id", None) or uuid4()
        se_item = SpecialEquipmentApplicationItem(
            id=item_id,
            application_id=application.id,
            **item_values,
        )
        items.append(se_item)
        if str(item_values.get("item_role") or "offer") == "offer":
            vehicles.append(
                ApplicationVehicle(
                    id=item_id,
                    application_id=application.id,
                    product_id=item_values["product_id"],
                    dealer_company_id=item_values.get("seller_company_id") or dealer_company_id,
                    quantity=1,
                    requested_quantity=1,
                    unit_price=item_values.get("unit_price"),
                    total_price=item_values.get("total_price"),
                    comment=item_values.get("comment"),
                    equipments=item_values.get("equipments") or [],
                    services=item_values.get("services") or [],
                    leasing_purpose=item_values.get("leasing_purpose"),
                    leasing_purposes=selected_purposes(item_values.get("leasing_purposes"), item_values.get("leasing_purpose")),
                    regions=item_values.get("regions") or [],
                    car_status="active",
                )
            )
    session.add_all(items)
    if vehicles:
        session.add_all(vehicles)
    await session.flush()
    await sync_vehicle_purchase_purpose(session, application.id)
    return {
        "application_id": application.id,
        "source_type": application.source_type,
        "item_id": items[0].id,
        "product_id": items[0].product_id,
        "item_ids": [item.id for item in items],
        "product_ids": [item.product_id for item in items],
        "status": application.status,
        "item_status": items[0].item_status,
    }
