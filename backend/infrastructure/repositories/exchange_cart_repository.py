"""Exchange-cart repository — async, dict-only API (Phase 5 E2)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.companies import Company
from infrastructure.models.exchange import (
    ExchangeCartItem,
    ExchangeCartItemDealerComment,
    ExchangeCartItemOption,
    ExchangeCartItemWarehouse,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from infrastructure.repository_timing import timed_repository
from infrastructure.services.file_proxy import exchange_cart_item_file_url


def _item_to_dict(row: ExchangeCartItem) -> dict[str, Any]:
    prod_id = getattr(row, "product_id", getattr(row, "vehicle_id", None))
    return {
        "id": row.id,
        "user_id": row.user_id,
        "product_id": prod_id,
        "vehicle_id": prod_id,
        "quantity": row.quantity,
        "expiration_at": row.expiration_at,
        "discount_type": row.discount_type,
        "discount_value": row.discount_value,
        # Swap the raw S3 URL for a backend-proxied link — the bucket is
        # private and direct ``storage.yandexcloud.net`` URLs would 403.
        "file_url": (
            exchange_cart_item_file_url(row.id) if row.file_url else None
        ),
        "file_name": row.file_name,
        "selected_support_ids": list(row.selected_support_ids or []),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

def _wh_to_dict(row: ExchangeCartItemWarehouse) -> dict[str, Any]:
    return {
        "id": row.id,
        "cart_item_id": row.cart_item_id,
        "warehouse_id": row.warehouse_id,
    }

def _opt_to_dict(row: ExchangeCartItemOption) -> dict[str, Any]:
    return {
        "id": row.id,
        "cart_item_id": row.cart_item_id,
        "dealer_option_id": row.dealer_option_id,
    }

def _comment_to_dict(row: ExchangeCartItemDealerComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "cart_item_id": row.cart_item_id,
        "dealer_id": row.dealer_id,
        "comment": row.comment,
    }

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@timed_repository
async def list_for_user(
    session: AsyncSession, user_id: UUID
) -> list[dict[str, Any]]:
    """Cart rows joined with product display fields expected by the UI."""
    stmt = (
        sa.select(
            ExchangeCartItem.id,
            ExchangeCartItem.user_id,
            ExchangeCartItem.product_id.label("product_id"),
            ExchangeCartItem.product_id.label("vehicle_id"),
            ExchangeCartItem.quantity,
            ExchangeCartItem.expiration_at,
            ExchangeCartItem.discount_type,
            ExchangeCartItem.discount_value,
            ExchangeCartItem.file_url,
            ExchangeCartItem.file_name,
            ExchangeCartItem.selected_support_ids,
            ExchangeCartItem.created_at,
            ExchangeCartItem.updated_at,
            SpecialEquipmentProduct.price.label("base_price"),
            SpecialEquipmentProduct.special_price.label("discount_price"),
            sa.cast(None, sa.String).label("color"),
            SpecialEquipmentProduct.manufacture_year.label("vehicle_year"),
            sa.cast(None, sa.dialects.postgresql.JSONB).label("images"),
            SpecialEquipmentProduct.modification_id.label("modification_id"),
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModel.name.label("model_name"),
            sa.cast(None, sa.String).label("generation_name"),
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
        .select_from(ExchangeCartItem)
        .outerjoin(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == ExchangeCartItem.product_id,
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
        .where(ExchangeCartItem.user_id == user_id)
        .order_by(ExchangeCartItem.created_at.desc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [_normalize_enriched(dict(row)) for row in rows]

def _normalize_enriched(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("file_url"):
        item_id = row.get("id")
        if item_id is not None:
            row["file_url"] = exchange_cart_item_file_url(item_id)
    else:
        row["file_url"] = None
    base = row.get("base_price")
    discount = row.get("discount_price")
    row["base_price"] = float(base) if isinstance(base, Decimal) else base
    row["discount_price"] = (
        float(discount) if isinstance(discount, Decimal) else discount
    )
    raw_images = row.get("images")
    if isinstance(raw_images, dict):
        for key in ("urls", "list", "items"):
            value = raw_images.get(key)
            if isinstance(value, list):
                row["images"] = [str(v) for v in value if v]
                break
        else:
            row["images"] = []
    elif isinstance(raw_images, list):
        row["images"] = [str(v) for v in raw_images if v]
    else:
        row["images"] = []
    return row

@timed_repository
async def count_for_user(
    session: AsyncSession, user_id: UUID
) -> int:
    stmt = select(ExchangeCartItem.id).where(
        ExchangeCartItem.user_id == user_id
    )
    rows = (await session.execute(stmt)).all()
    return len(rows)

@timed_repository
async def get_by_id(
    session: AsyncSession, item_id: UUID
) -> dict[str, Any] | None:
    row = (await session.execute(
        select(ExchangeCartItem).where(ExchangeCartItem.id == item_id)
    )).scalar_one_or_none()
    if row is None:
        return None
    return _item_to_dict(row)

@timed_repository
async def find_by_user_and_product(
    session: AsyncSession,
    *,
    user_id: UUID,
    product_id: UUID | None = None,
    vehicle_id: UUID | None = None,
) -> dict[str, Any] | None:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return None
    stmt = select(ExchangeCartItem).where(
        ExchangeCartItem.user_id == user_id,
        ExchangeCartItem.product_id == target_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _item_to_dict(row)


find_by_user_and_vehicle = find_by_user_and_product

@timed_repository
async def list_warehouses(
    session: AsyncSession, cart_item_id: UUID
) -> list[dict[str, Any]]:
    stmt = select(ExchangeCartItemWarehouse).where(
        ExchangeCartItemWarehouse.cart_item_id == cart_item_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_wh_to_dict(r) for r in rows]

@timed_repository
async def warehouse_dealer_map(
    session: AsyncSession, warehouse_ids: list[UUID]
) -> dict[UUID, UUID | None]:
    if not warehouse_ids:
        return {}

    dealer_company = aliased(Company)
    dealer_user_company = aliased(Company)
    warehouse_company = aliased(Company)
    dealer_user = aliased(User)
    stmt = (
        select(
            Warehouse.id.label("warehouse_id"),
            warehouse_company.id.label("warehouse_company_id"),
            dealer_company.id.label("dealer_company_id"),
            dealer_user_company.id.label("dealer_user_company_id"),
        )
        .select_from(Warehouse)
        .outerjoin(
            warehouse_company,
            warehouse_company.id == Warehouse.company_id,
        )
        .outerjoin(dealer_company, dealer_company.id == Warehouse.dealer_id)
        .outerjoin(dealer_user, dealer_user.id == Warehouse.dealer_id)
        .outerjoin(
            dealer_user_company,
            dealer_user_company.id == dealer_user.company_id,
        )
        .where(Warehouse.id.in_(warehouse_ids))
    )

    out: dict[UUID, UUID | None] = {}
    for row in (await session.execute(stmt)).mappings().all():
        target_company_id = (
            row["warehouse_company_id"]
            or row["dealer_company_id"]
            or row["dealer_user_company_id"]
        )
        if target_company_id is None:
            continue
        out[row["warehouse_id"]] = target_company_id
    return out

@timed_repository
async def list_options(
    session: AsyncSession, cart_item_id: UUID
) -> list[dict[str, Any]]:
    stmt = select(ExchangeCartItemOption).where(
        ExchangeCartItemOption.cart_item_id == cart_item_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_opt_to_dict(r) for r in rows]

@timed_repository
async def list_dealer_comments(
    session: AsyncSession, cart_item_id: UUID
) -> list[dict[str, Any]]:
    stmt = select(ExchangeCartItemDealerComment).where(
        ExchangeCartItemDealerComment.cart_item_id == cart_item_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_comment_to_dict(r) for r in rows]

@timed_repository
async def get_item_file_meta(
    session: AsyncSession, item_id: UUID, *, user_id: UUID
) -> tuple[str | None, str | None] | None:
    row = await session.get(ExchangeCartItem, item_id)
    if row is None or row.user_id != user_id:
        return None
    return row.file_url, row.file_name

@timed_repository
async def product_exists(
    session: AsyncSession,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> bool:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return False
    row = await session.get(SpecialEquipmentProduct, target_id)
    return row is not None


vehicle_exists = product_exists

@timed_repository
async def list_available_warehouses_for_product(
    session: AsyncSession,
    product_id: UUID | None = None,
    *,
    vehicle_id: UUID | None = None,
) -> list[dict[str, Any]]:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        return []
    ref = await session.get(SpecialEquipmentProduct, target_id)
    if ref is None:
        return []

    if ref.modification_id is not None:
        match_clause = SpecialEquipmentProduct.modification_id == ref.modification_id
    elif ref.model_id is not None:
        match_clause = sa.and_(
            SpecialEquipmentProduct.model_id == ref.model_id,
            SpecialEquipmentProduct.superstructure_id == ref.superstructure_id,
        )
    else:
        match_clause = SpecialEquipmentProduct.id == ref.id
    effective_price = sa.func.coalesce(
        SpecialEquipmentProduct.special_price, SpecialEquipmentProduct.price
    )

    warehouse_company = aliased(Company)
    dealer_company = aliased(Company)
    dealer_user = aliased(User)
    dealer_user_company = aliased(Company)
    resolved_dealer_id = sa.func.coalesce(
        warehouse_company.id,
        dealer_company.id,
        dealer_user_company.id,
    )
    resolved_dealer_name = sa.func.coalesce(
        warehouse_company.name,
        dealer_company.name,
        dealer_user_company.name,
    )

    stmt = (
        sa.select(
            Warehouse.id,
            Warehouse.address,
            Warehouse.brand,
            Warehouse.city_id,
            resolved_dealer_id.label("dealer_id"),
            City.name.label("city_name"),
            resolved_dealer_name.label("dealer_name"),
            resolved_dealer_name.label("company_name"),
            sa.func.count(SpecialEquipmentProduct.id).label("vehicle_count"),
            sa.func.min(effective_price).label("min_price"),
            sa.func.max(effective_price).label("max_price"),
        )
        .select_from(Warehouse)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.warehouse_id == Warehouse.id,
        )
        .outerjoin(City, City.id == Warehouse.city_id)
        .outerjoin(
            warehouse_company,
            warehouse_company.id == Warehouse.company_id,
        )
        .outerjoin(dealer_company, dealer_company.id == Warehouse.dealer_id)
        .outerjoin(dealer_user, dealer_user.id == Warehouse.dealer_id)
        .outerjoin(
            dealer_user_company,
            dealer_user_company.id == dealer_user.company_id,
        )
        .where(
            match_clause,
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status == "available",
        )
        .group_by(
            Warehouse.id,
            Warehouse.address,
            Warehouse.brand,
            Warehouse.city_id,
            City.name,
            resolved_dealer_id,
            resolved_dealer_name,
        )
        .order_by(Warehouse.brand.asc(), Warehouse.address.asc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": str(row["id"]),
            "address": row["address"],
            "brand": row["brand"],
            "city_id": str(row["city_id"]) if row["city_id"] else None,
            "city_name": row["city_name"],
            "dealer_id": str(row["dealer_id"]) if row["dealer_id"] else None,
            "dealer_name": row["dealer_name"],
            "company_name": row["company_name"],
            "vehicle_count": int(row["vehicle_count"] or 0),
            "min_price": (
                float(row["min_price"])
                if isinstance(row["min_price"], Decimal)
                else row["min_price"]
            ),
            "max_price": (
                float(row["max_price"])
                if isinstance(row["max_price"], Decimal)
                else row["max_price"]
            ),
        }
        for row in rows
    ]


list_available_warehouses_for_vehicle = list_available_warehouses_for_product

# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

@timed_repository
async def add_item(
    session: AsyncSession,
    *,
    user_id: UUID,
    product_id: UUID | None = None,
    quantity: int = 1,
    vehicle_id: UUID | None = None,
) -> UUID:
    target_id = product_id if product_id is not None else vehicle_id
    if target_id is None:
        raise ValueError("Either product_id or vehicle_id must be provided")

    cart_prod_col = "product_id" if hasattr(ExchangeCartItem, "product_id") else "vehicle_id"
    init_kwargs = {
        "user_id": user_id,
        cart_prod_col: target_id,
        "quantity": quantity,
    }
    row = ExchangeCartItem(**init_kwargs)
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def set_item_file(
    session: AsyncSession,
    item_id: UUID,
    *,
    user_id: UUID,
    file_url: str | None,
    file_name: str | None,
) -> dict[str, Any] | None:
    row = await session.get(ExchangeCartItem, item_id)
    if row is None or row.user_id != user_id:
        return None
    row.file_url = file_url
    row.file_name = file_name
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return _item_to_dict(row)

@timed_repository
async def update_item(
    session: AsyncSession,
    item_id: UUID,
    *,
    user_id: UUID,
    quantity: int | None = None,
    discount_type: str | None = None,
    discount_value: Decimal | None = None,
    expiration_at: Any | None = None,
    expiration_at_set: bool = False,
    selected_support_ids: list[UUID] | None = None,
) -> bool:
    row = (await session.execute(
        select(ExchangeCartItem).where(
            ExchangeCartItem.id == item_id,
            ExchangeCartItem.user_id == user_id,
        )
    )).scalar_one_or_none()
    if row is None:
        return False
    if quantity is not None:
        row.quantity = quantity
    if discount_type is not None:
        row.discount_type = discount_type
    if discount_value is not None:
        cast("Any", row).discount_value = discount_value
    if expiration_at_set or expiration_at is not None:
        row.expiration_at = expiration_at
    if selected_support_ids is not None:
        row.selected_support_ids = list(selected_support_ids)
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def remove_item(
    session: AsyncSession, item_id: UUID, *, user_id: UUID
) -> bool:
    row = await session.get(ExchangeCartItem, item_id)
    if row is None or row.user_id != user_id:
        return False
    await session.delete(row)
    await session.flush()
    return True

@timed_repository
async def clear_cart(session: AsyncSession, user_id: UUID) -> int:
    stmt = select(ExchangeCartItem).where(
        ExchangeCartItem.user_id == user_id
    )
    rows = (await session.execute(stmt)).scalars().all()
    count = 0
    for row in rows:
        await session.delete(row)
        count += 1
    await session.flush()
    return count

@timed_repository
async def set_warehouses(
    session: AsyncSession,
    *,
    cart_item_id: UUID,
    warehouse_ids: list[UUID],
) -> None:
    await session.execute(
        delete(ExchangeCartItemWarehouse).where(
            ExchangeCartItemWarehouse.cart_item_id == cart_item_id
        )
    )
    for wid in warehouse_ids:
        session.add(
            ExchangeCartItemWarehouse(
                cart_item_id=cart_item_id, warehouse_id=wid
            )
        )
    await session.flush()

@timed_repository
async def add_warehouse_if_missing(
    session: AsyncSession,
    *,
    cart_item_id: UUID,
    warehouse_id: UUID,
) -> None:
    existing = await session.execute(
        select(ExchangeCartItemWarehouse.id).where(
            ExchangeCartItemWarehouse.cart_item_id == cart_item_id,
            ExchangeCartItemWarehouse.warehouse_id == warehouse_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(
        ExchangeCartItemWarehouse(
            cart_item_id=cart_item_id, warehouse_id=warehouse_id
        )
    )
    await session.flush()

@timed_repository
async def set_options(
    session: AsyncSession,
    *,
    cart_item_id: UUID,
    dealer_option_ids: list[UUID],
) -> None:
    await session.execute(
        delete(ExchangeCartItemOption).where(
            ExchangeCartItemOption.cart_item_id == cart_item_id
        )
    )
    for opt_id in dealer_option_ids:
        session.add(
            ExchangeCartItemOption(
                cart_item_id=cart_item_id, dealer_option_id=opt_id
            )
        )
    await session.flush()

@timed_repository
async def upsert_dealer_comment(
    session: AsyncSession,
    *,
    cart_item_id: UUID,
    dealer_id: UUID,
    comment: str | None,
) -> None:
    stmt = select(ExchangeCartItemDealerComment).where(
        ExchangeCartItemDealerComment.cart_item_id == cart_item_id,
        ExchangeCartItemDealerComment.dealer_id == dealer_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        session.add(
            ExchangeCartItemDealerComment(
                cart_item_id=cart_item_id,
                dealer_id=dealer_id,
                comment=comment,
            )
        )
    else:
        row.comment = comment
    await session.flush()
