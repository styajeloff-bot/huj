"""Cart repository — user-scoped shopping_cart rows + product lookups.

All public functions return plain ``dict`` / ``list[dict]`` — never ORM
objects. ORM models exist only to build queries here.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.models.applications import ShoppingCart
from infrastructure.models.cart_transfers import GuestCartTransfer
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.repositories.catalog_scope import special_equipment_visible_in
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Read — cart
# ---------------------------------------------------------------------------

@timed_repository
async def list_cart_items(
    session: AsyncSession, user_id: UUID, scope: CatalogScope
) -> list[dict[str, Any]]:
    """Return all cart rows for ``user_id`` joined with product fields suitable
    for the storefront cart view.

    The row order mirrors the Express behavior — newest-first by ``added_at``.
    """
    stmt = (
        sa.select(
            ShoppingCart.id.label("cart_id"),
            ShoppingCart.user_id,
            ShoppingCart.storefront_id,
            ShoppingCart.product_id.label("product_id"),
            ShoppingCart.product_id.label("vehicle_id"),
            ShoppingCart.quantity,
            ShoppingCart.allow_overstock,
            ShoppingCart.is_selected,
            ShoppingCart.custom_price,
            ShoppingCart.comment,
            ShoppingCart.equipments,
            ShoppingCart.services,
            ShoppingCart.added_at,
            SpecialEquipmentProduct.price.label("base_price"),
            SpecialEquipmentProduct.special_price.label("discount_price"),
            SpecialEquipmentModel.mark_id,
            sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ).label("model_id"),
            SpecialEquipmentProduct.modification_id,
            SpecialEquipmentProduct.manufacture_year.label("year"),
            SpecialEquipmentProduct.vin,
            SpecialEquipmentProduct.sale_status.label("status"),
            sa.true().label("is_available"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.name.label("model_name"),
            sa.func.coalesce(
                SpecialEquipmentModification.name,
                SpecialEquipmentProduct.superstructure_name,
            ).label("configuration_name"),
            sa.func.coalesce(
                SpecialEquipmentModification.name,
                SpecialEquipmentProduct.superstructure_name,
            ).label("group_name"),
            SpecialEquipmentProduct.superstructure_name,
            SpecialEquipmentProduct.superstructure_manufacturer,
        )
        .select_from(ShoppingCart)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ShoppingCart.product_id,
            isouter=True,
        )
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
            special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
        )
        .order_by(ShoppingCart.added_at.desc().nullslast())
    )
    result = await session.execute(stmt)
    return [dict(row) for row in result.mappings().all()]


@timed_repository
async def get_cart_item(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    conditions: list[sa.ColumnElement[bool]] = [
        ShoppingCart.user_id == user_id,
        ShoppingCart.storefront_id == scope.id,
        ShoppingCart.product_id == target_id,
    ]
    if not scope.is_default:
        conditions.extend(
            [
                SpecialEquipmentProduct.publication_status == "published",
                SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
                special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
            ]
        )
    stmt = (
        sa.select(
            ShoppingCart.id.label("cart_id"),
            ShoppingCart.user_id,
            ShoppingCart.storefront_id,
            ShoppingCart.product_id.label("product_id"),
            ShoppingCart.product_id.label("vehicle_id"),
            ShoppingCart.quantity,
            ShoppingCart.allow_overstock,
            ShoppingCart.is_selected,
            ShoppingCart.custom_price,
            ShoppingCart.comment,
            ShoppingCart.equipments,
            ShoppingCart.services,
            ShoppingCart.added_at,
            SpecialEquipmentProduct.id.label("vehicle_row_id"),
            SpecialEquipmentProduct.id.label("product_row_id"),
            SpecialEquipmentProduct.price.label("base_price"),
        )
        .select_from(ShoppingCart)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ShoppingCart.product_id,
            isouter=True,
        )
        .where(*conditions)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    return dict(row) if row else None


@timed_repository
async def count_cart_items(
    session: AsyncSession, user_id: UUID, scope: CatalogScope
) -> int:
    """Count cart items for the user whose underlying product is still available."""
    count_stmt = (
        sa.select(sa.func.count(ShoppingCart.id))
        .select_from(ShoppingCart)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ShoppingCart.product_id,
        )
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
            special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
        )
    )
    result = await session.execute(count_stmt)
    return int(result.scalar() or 0)


# ---------------------------------------------------------------------------
# Product lookups & availability
# ---------------------------------------------------------------------------

@timed_repository
async def product_exists(
    session: AsyncSession,
    product_id: UUID | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
) -> bool:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return False
    stmt = sa.select(
        sa.exists(
            sa.select(SpecialEquipmentProduct.id).where(
                SpecialEquipmentProduct.id == target_id,
                SpecialEquipmentProduct.publication_status == "published",
                SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
                special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
            )
        )
    )
    result = await session.execute(stmt)
    return bool(result.scalar())


vehicle_exists = product_exists


@timed_repository
async def get_available_counts(
    session: AsyncSession,
    product_ids: list[UUID],
    *,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
) -> list[dict[str, Any]]:
    """Per-product available stock count grouped by modification_id."""
    if not product_ids:
        return []
    inner_modifications = select(SpecialEquipmentProduct.modification_id).where(
        SpecialEquipmentProduct.id.in_(product_ids),
        special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
    )
    counts_subq = (
        select(
            SpecialEquipmentProduct.modification_id,
            sa.func.count().label("available_count"),
        )
        .where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status.in_(("available", "on_order")),
            special_equipment_visible_in(scope, product=SpecialEquipmentProduct),
            SpecialEquipmentProduct.modification_id.in_(inner_modifications),
        )
        .group_by(SpecialEquipmentProduct.modification_id)
        .subquery()
    )
    stmt = (
        select(
            SpecialEquipmentProduct.id.label("product_id"),
            SpecialEquipmentProduct.id.label("vehicle_id"),
            SpecialEquipmentProduct.modification_id,
            sa.func.coalesce(counts_subq.c.available_count, 0).label("available_count"),
        )
        .outerjoin(
            counts_subq,
            counts_subq.c.modification_id == SpecialEquipmentProduct.modification_id,
        )
        .where(SpecialEquipmentProduct.id.in_(product_ids))
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

@timed_repository
async def apply_guest_cart_transfer(
    session: AsyncSession,
    *,
    user_id: UUID,
    scope: CatalogScope,
    transfer_id: UUID,
    product_id: UUID | None = None,
    vehicle_id: UUID | None = None,
    quantity: int,
    equipments: list[dict[str, Any]],
    services: list[dict[str, Any]],
    allow_overstock: bool = False,
) -> dict[str, Any]:
    """Apply a transfer once and return the durable receipt payload."""
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        raise ValueError("Either product_id or vehicle_id must be provided")

    transfer_prod_col = "product_id" if hasattr(GuestCartTransfer, "product_id") else "vehicle_id"
    cart_prod_col = "product_id" if hasattr(ShoppingCart, "product_id") else "vehicle_id"

    receipt_values = {
        "user_id": user_id,
        "storefront_id": scope.id,
        "transfer_id": transfer_id,
        transfer_prod_col: target_id,
        "quantity": quantity,
        "allow_overstock": allow_overstock,
        "equipments": equipments,
        "services": services,
    }
    receipt_insert = (
        pg_insert(GuestCartTransfer)
        .values(**receipt_values)
        .on_conflict_do_nothing(
            index_elements=[
                GuestCartTransfer.user_id,
                GuestCartTransfer.storefront_id,
                GuestCartTransfer.transfer_id,
            ]
        )
        .returning(GuestCartTransfer.transfer_id)
    )
    receipt_result = await session.execute(receipt_insert)
    receipt_created = receipt_result.scalar_one_or_none() is not None

    if not receipt_created:
        transfer_col_attr = getattr(GuestCartTransfer, transfer_prod_col)
        existing_result = await session.execute(
            sa.select(
                transfer_col_attr.label("product_id"),
                transfer_col_attr.label("vehicle_id"),
                GuestCartTransfer.quantity,
                GuestCartTransfer.allow_overstock,
                GuestCartTransfer.equipments,
                GuestCartTransfer.services,
            ).where(
                GuestCartTransfer.user_id == user_id,
                GuestCartTransfer.storefront_id == scope.id,
                GuestCartTransfer.transfer_id == transfer_id,
            )
        )
        existing = existing_result.mappings().one()
        return {
            "applied": False,
            "receipt": dict(existing),
            "cart_item": await get_cart_item(
                session, user_id, target_id, scope
            ),
        }

    cart_values = {
        "user_id": user_id,
        "storefront_id": scope.id,
        cart_prod_col: target_id,
        "quantity": quantity,
        "allow_overstock": allow_overstock,
        "is_selected": True,
        "equipments": equipments,
        "services": services,
    }
    cart_prod_attr = getattr(ShoppingCart, cart_prod_col)
    cart_insert = (
        pg_insert(ShoppingCart)
        .values(**cart_values)
        .on_conflict_do_update(
            index_elements=[ShoppingCart.user_id, ShoppingCart.storefront_id, cart_prod_attr],
            set_={
                "quantity": ShoppingCart.quantity + quantity,
                "allow_overstock": ShoppingCart.allow_overstock | allow_overstock,
                "equipments": equipments,
                "services": services,
            },
        )
        .returning(
            ShoppingCart.id.label("cart_id"),
            ShoppingCart.user_id,
            ShoppingCart.storefront_id,
            cart_prod_attr.label("product_id"),
            cart_prod_attr.label("vehicle_id"),
            ShoppingCart.quantity,
            ShoppingCart.allow_overstock,
            ShoppingCart.is_selected,
            ShoppingCart.equipments,
            ShoppingCart.services,
            ShoppingCart.added_at,
        )
    )
    cart_result = await session.execute(cart_insert)
    cart_item = dict(cart_result.mappings().one())
    await session.flush()
    return {
        "applied": True,
        "receipt": {
            "product_id": target_id,
            "vehicle_id": target_id,
            "quantity": quantity,
            "allow_overstock": allow_overstock,
            "equipments": equipments,
            "services": services,
        },
        "cart_item": cart_item,
    }


@timed_repository
async def add_item(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    quantity: int = 1,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
    allow_overstock: bool = False,
) -> dict[str, Any]:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        raise ValueError("Either product_id or vehicle_id must be provided")

    cart_prod_col = "product_id" if hasattr(ShoppingCart, "product_id") else "vehicle_id"
    init_kwargs = {
        "user_id": user_id,
        "storefront_id": scope.id,
        cart_prod_col: target_id,
        "quantity": quantity,
        "allow_overstock": allow_overstock,
        "is_selected": True,
    }
    row = ShoppingCart(**init_kwargs)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    stored_id = getattr(row, cart_prod_col)
    return {
        "cart_id": row.id,
        "user_id": row.user_id if row.user_id is not None else user_id,
        "storefront_id": row.storefront_id,
        "product_id": stored_id,
        "vehicle_id": stored_id,
        "quantity": int(row.quantity),
        "allow_overstock": bool(row.allow_overstock),
        "is_selected": bool(row.is_selected) if row.is_selected is not None else True,
        "custom_price": row.custom_price,
        "comment": row.comment,
        "equipments": row.equipments or [],
        "services": row.services or [],
        "added_at": row.added_at,
    }


@timed_repository
async def increment_quantity(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    delta: int = 1,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
    allow_overstock: bool | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    values_map: dict[str, Any] = {"quantity": ShoppingCart.quantity + delta}
    if allow_overstock is not None:
        values_map["allow_overstock"] = allow_overstock

    stmt = (
        sa.update(ShoppingCart)
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
        .values(**values_map)
        .returning(
            ShoppingCart.id,
            ShoppingCart.quantity,
            ShoppingCart.allow_overstock,
            ShoppingCart.is_selected,
            ShoppingCart.added_at,
        )
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    await session.flush()
    if row is None:
        return None
    return {
        "cart_id": row["id"],
        "quantity": int(row["quantity"]),
        "allow_overstock": bool(row.get("allow_overstock", False)),
        "is_selected": bool(row["is_selected"]) if row["is_selected"] is not None else True,
        "added_at": row["added_at"],
    }


@timed_repository
async def update_selection(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    is_selected: bool = True,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    sel_stmt = (
        sa.update(ShoppingCart)
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
        .values(is_selected=is_selected)
        .returning(
            ShoppingCart.id,
            ShoppingCart.product_id.label("product_id"),
            ShoppingCart.product_id.label("vehicle_id"),
            ShoppingCart.is_selected,
        )
    )
    result = await session.execute(sel_stmt)
    row = result.mappings().first()
    await session.flush()
    if row is None:
        return None
    return {
        "cart_id": row["id"],
        "product_id": row["product_id"],
        "vehicle_id": row["vehicle_id"],
        "is_selected": bool(row["is_selected"]) if row["is_selected"] is not None else True,
    }


@timed_repository
async def bulk_update_selection(
    session: AsyncSession,
    user_id: UUID,
    items: Sequence[tuple[UUID, bool]],
    scope: CatalogScope,
) -> list[dict[str, Any]]:
    """Set ``is_selected`` atomically for many ``(product_id, flag)`` pairs."""
    updated: list[dict[str, Any]] = []
    for pid, is_selected in items:
        result = await update_selection(
            session, user_id, pid, is_selected, scope
        )
        if result is not None:
            updated.append(result)
    return updated


@timed_repository
async def update_quantity(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    quantity: int = 1,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
    allow_overstock: bool | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    values_map: dict[str, Any] = {"quantity": quantity}
    if allow_overstock is not None:
        values_map["allow_overstock"] = allow_overstock

    stmt = (
        sa.update(ShoppingCart)
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
        .values(**values_map)
        .returning(ShoppingCart.id, ShoppingCart.quantity, ShoppingCart.allow_overstock)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    await session.flush()
    if row is None:
        return None
    return {
        "cart_id": row["id"],
        "quantity": int(row["quantity"]),
        "allow_overstock": bool(row.get("allow_overstock", False)),
    }


@timed_repository
async def update_custom_price(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    custom_price: Decimal | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    stmt = (
        sa.update(ShoppingCart)
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
        .values(custom_price=custom_price)
        .returning(ShoppingCart.id, ShoppingCart.custom_price)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    await session.flush()
    if row is None:
        return None
    return {
        "cart_id": row["id"],
        "custom_price": row["custom_price"],
    }


@timed_repository
async def update_comment(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    comment: str | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    stmt = (
        sa.update(ShoppingCart)
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
        .values(comment=comment)
        .returning(ShoppingCart.id, ShoppingCart.comment)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    await session.flush()
    if row is None:
        return None
    return {
        "cart_id": row["id"],
        "comment": row["comment"],
    }


@timed_repository
async def update_additional_options(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
    equipments: list[dict[str, Any]] | None = None,
    services: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    values: dict[str, Any] = {}
    if equipments is not None:
        values["equipments"] = equipments
    if services is not None:
        values["services"] = services
    if not values:
        return None
    stmt = (
        sa.update(ShoppingCart)
        .where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
        .values(**values)
        .returning(ShoppingCart.id, ShoppingCart.equipments, ShoppingCart.services)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    await session.flush()
    if row is None:
        return None
    return {
        "cart_id": row["id"],
        "equipments": row["equipments"] or [],
        "services": row["services"] or [],
    }


@timed_repository
async def remove_item(
    session: AsyncSession,
    user_id: UUID,
    product_id: UUID | None = None,
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE,
    *,
    vehicle_id: UUID | None = None,
) -> bool:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return False
    await lock_cart(session, user_id, scope)
    result = await session.execute(
        sa.delete(ShoppingCart).where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
            ShoppingCart.product_id == target_id,
        )
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0


@timed_repository
async def clear_cart(
    session: AsyncSession, user_id: UUID, scope: CatalogScope
) -> int:
    await lock_cart(session, user_id, scope)
    result = await session.execute(
        sa.delete(ShoppingCart).where(
            ShoppingCart.user_id == user_id,
            ShoppingCart.storefront_id == scope.id,
        )
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0)


async def lock_cart(session: AsyncSession, user_id: UUID, scope: CatalogScope) -> None:
    """Serialize mutations including initial INSERTs without an existing row.

    Transaction-scoped; callers must commit/rollback normally. The storefront
    participates in the key so independent storefront carts remain independent.
    """
    key = int.from_bytes(
        sha256(f"cart/{user_id}/{scope.id}".encode()).digest()[:8], "big", signed=True
    )
    await session.execute(sa.select(sa.func.pg_advisory_xact_lock(key)))


async def get_transfer_receipt(
    session: AsyncSession,
    user_id: UUID,
    scope: CatalogScope,
    transfer_id: UUID,
) -> dict[str, Any] | None:
    transfer_prod_col = "product_id" if hasattr(GuestCartTransfer, "product_id") else "vehicle_id"
    transfer_prod_attr = getattr(GuestCartTransfer, transfer_prod_col)
    result = await session.execute(
        sa.select(
            transfer_prod_attr.label("product_id"),
            transfer_prod_attr.label("vehicle_id"),
            GuestCartTransfer.quantity,
            GuestCartTransfer.allow_overstock,
            GuestCartTransfer.equipments,
            GuestCartTransfer.services,
        ).where(
            GuestCartTransfer.user_id == user_id,
            GuestCartTransfer.storefront_id == scope.id,
            GuestCartTransfer.transfer_id == transfer_id,
        )
    )
    row = result.mappings().first()
    return dict(row) if row else None
