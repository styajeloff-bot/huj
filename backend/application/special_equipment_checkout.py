"""Atomic server-cart allocation for special-equipment checkout."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.special_equipment_offerings import _aggregate_candidates
from domain.special_equipment_commerce import SpecialEquipmentPriceRequiredError
from infrastructure.repositories import (
    special_equipment_commerce_repository as commerce_repository,
)
from infrastructure.repositories import (
    special_equipment_repository as catalog_repository,
)


class CheckoutAllocationError(ValueError):
    """Stable checkout conflict carrying actual availability."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        requested: int | None = None,
        available: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.requested = requested
        self.available = available


SaleStatus = Literal["available", "on_order"]


@dataclass(frozen=True, slots=True)
class AllocatedCartLine:
    cart_item_id: UUID
    representative_id: UUID
    parent_cart_item_id: UUID | None
    quantity: int
    products: tuple[dict[str, Any], ...]
    overstock_quantity: int = 0
    custom_price: Decimal | None = None
    equipments: tuple[dict[str, Any], ...] = ()
    services: tuple[dict[str, Any], ...] = ()

    def agreed_unit_price(self, product: dict[str, Any]) -> Decimal | None:
        """Return the cart agreement or ``None`` when leasing price is unknown."""

        raw_price = self.custom_price
        if raw_price is None:
            raw_price = product["price"]
        if raw_price is None:
            return None
        return Decimal(str(raw_price))

    def require_agreed_unit_price(self, product: dict[str, Any]) -> Decimal:
        """Return a positive checkout price for purchase/reservation flows."""

        price = self.agreed_unit_price(product)
        if price is None or price <= 0:
            raise SpecialEquipmentPriceRequiredError()
        return price

    @property
    def has_paid_options(self) -> bool:
        """Return whether the legacy cart carries an additional paid option."""

        for option in (*self.equipments, *self.services):
            try:
                price = Decimal(str(option.get("price") or "0"))
            except (ArithmeticError, TypeError, ValueError):
                continue
            if price > 0:
                return True
        return False


@dataclass(frozen=True, slots=True)
class AllocatedComponent:
    source_cart_item_id: UUID
    composite_product_id: UUID
    component_product_id: UUID
    position: int
    is_base: bool


@dataclass(frozen=True, slots=True)
class CheckoutAllocation:
    cart_lines: tuple[AllocatedCartLine, ...]
    components: tuple[AllocatedComponent, ...]

    @property
    def concrete_product_ids(self) -> tuple[UUID, ...]:
        values = {
            product["id"]
            for line in self.cart_lines
            for product in line.products
        }
        values.update(item.component_product_id for item in self.components)
        return tuple(sorted(values, key=str))

    @property
    def total(self) -> Decimal | None:
        prices = tuple(
            line.agreed_unit_price(product)
            for line in self.cart_lines
            for product in line.products
        )
        if any(price is None for price in prices):
            return None
        return sum(
            (price for price in prices if price is not None),
            Decimal("0.00"),
        )

    @property
    def supports_unpriced_leasing(self) -> bool:
        """Whether a missing price can be resolved by one later proposal.

        A proposal has one principal and therefore cannot safely distribute an
        unknown amount across several physical units or billable cart lines.
        The principal may keep directly attached, explicitly free equipment in
        the same bundle. Composite components are intentionally absent from
        ``cart_lines`` and keep their explicit zero price.
        """

        if self.total is not None:
            return True
        if any(line.has_paid_options for line in self.cart_lines):
            return False
        roots = tuple(
            line for line in self.cart_lines if line.parent_cart_item_id is None
        )
        if len(roots) != 1:
            return False
        root = roots[0]
        if not (
            root.quantity == 1
            and len(root.products) == 1
            and root.agreed_unit_price(root.products[0]) is None
        ):
            return False
        return all(
            line is root
            or (
                line.parent_cart_item_id == root.cart_item_id
                and line.quantity > 0
                and len(line.products) == line.quantity
                and all(
                    line.agreed_unit_price(product) == Decimal("0.00")
                    for product in line.products
                )
            )
            for line in self.cart_lines
        )


async def _group_for_representative(
    session: AsyncSession,
    representative_id: UUID,
    *,
    eligible_ids: tuple[UUID, ...] | None = None,
    allowed_statuses: tuple[SaleStatus, ...] = ("available", "on_order"),
) -> dict[str, Any] | None:
    representative_rows = await catalog_repository.list_products_by_ids(
        session, (representative_id,)
    )
    if not representative_rows:
        stale_rows = await catalog_repository.list_products_by_ids_unrestricted(
            session, (representative_id,)
        )
        if not stale_rows:
            return None
        stale = stale_rows[0]
        for sale_status in allowed_statuses:
            if eligible_ids is None:
                candidates = await catalog_repository.list_product_candidates(
                    session,
                    filters=catalog_repository.SpecialEquipmentFilters(
                        modification_ids=(stale["modification_id"],),
                        availability=(sale_status,),
                    ),
                )
            else:
                candidates = [
                    row
                    for row in await catalog_repository.list_products_by_ids(
                        session, eligible_ids
                    )
                    if row["sale_status"] == sale_status
                ]
            synthetic = {**stale, "sale_status": sale_status}
            for group in await _aggregate_candidates(
                session, [synthetic, *candidates]
            ):
                if representative_id not in group["_physical_ids"]:
                    continue
                physical_ids = tuple(
                    product_id
                    for product_id in sorted(group["_physical_ids"], key=str)
                    if product_id != representative_id
                )
                if physical_ids:
                    available_count = await _bundle_safe_available_count(
                        session,
                        physical_ids,
                        allowed_statuses=allowed_statuses,
                    )
                    return {
                        **synthetic,
                        "available_count": available_count,
                        "_physical_ids": physical_ids,
                    }
        return None
    representative = representative_rows[0]
    physical_ids, available_count = (
        await catalog_repository.get_grouped_product_inventory_for_member(
            session,
            representative_id,
            candidate_ids=eligible_ids,
            availability=allowed_statuses,
        )
    )
    if not physical_ids:
        return None
    return {
        **representative,
        "available_count": available_count,
        "_physical_ids": physical_ids,
    }


async def _bundle_safe_available_count(
    session: AsyncSession,
    physical_ids: tuple[UUID, ...],
    *,
    allowed_statuses: tuple[SaleStatus, ...],
) -> int:
    """Mirror deterministic bundle allocation for a stale representative."""

    claimed_ids: set[UUID] = set()
    available_count = 0
    for product_id in sorted(physical_ids, key=str):
        components = (
            await commerce_repository.list_product_components_for_checkout(
                session,
                product_id,
            )
        )
        bundle_ids = {
            product_id,
            *(item["component_product_id"] for item in components),
        }
        bundle_products = await catalog_repository.list_products_by_ids(
            session,
            tuple(sorted(bundle_ids, key=str)),
        )
        if (
            bundle_ids & claimed_ids
            or {item["id"] for item in bundle_products} != bundle_ids
            or any(
                item["sale_status"] not in allowed_statuses
                for item in bundle_products
            )
        ):
            continue
        claimed_ids.update(bundle_ids)
        available_count += 1
    return available_count


async def available_count_for_representative(
    session: AsyncSession,
    representative_id: UUID,
    *,
    eligible_ids: tuple[UUID, ...] | None = None,
    allowed_statuses: tuple[SaleStatus, ...] = ("available", "on_order"),
) -> int:
    group = await _group_for_representative(
        session,
        representative_id,
        eligible_ids=eligible_ids,
        allowed_statuses=allowed_statuses,
    )
    return int(group["available_count"]) if group is not None else 0


def _availability_error(*, requested: int, available: int) -> CheckoutAllocationError:
    return CheckoutAllocationError(
        "Недостаточно доступных эквивалентных единиц",
        code="INSUFFICIENT_EQUIVALENT_PRODUCTS",
        requested=requested,
        available=available,
    )


async def allocate_cart_items(  # noqa: PLR0912, PLR0915 -- explicit invariants
    session: AsyncSession,
    *,
    user_id: UUID,
    cart_item_ids: tuple[UUID, ...],
    allow_on_order: bool,
    allow_overstock: bool = False,
) -> CheckoutAllocation:
    """Resolve representatives to concrete UUIDs and lock the full bundle."""

    if not cart_item_ids or len(set(cart_item_ids)) != len(cart_item_ids):
        raise CheckoutAllocationError(
            "Нужно выбрать уникальные позиции серверной корзины",
            code="SPECIAL_EQUIPMENT_CART_SELECTION_INVALID",
        )
    cart_rows = await commerce_repository.get_cart_items_for_checkout(
        session,
        user_id=user_id,
        cart_item_ids=cart_item_ids,
    )
    if {row["id"] for row in cart_rows} != set(cart_item_ids):
        raise CheckoutAllocationError(
            "Позиция серверной корзины не найдена",
            code="SPECIAL_EQUIPMENT_CART_ITEM_NOT_FOUND",
        )
    selected_ids = {row["id"] for row in cart_rows}
    for row in cart_rows:
        parent_id = row.get("parent_item_id")
        if parent_id is not None and parent_id not in selected_ids:
            raise CheckoutAllocationError(
                "Для дочерней надстройки нужно выбрать родительскую технику",
                code="SPECIAL_EQUIPMENT_CART_PARENT_REQUIRED",
            )

    for representative_id in sorted(
        {row["product_id"] for row in cart_rows}, key=str
    ):
        await commerce_repository.lock_offering_allocation(
            session, representative_id
        )

    rows_by_id = {row["id"]: row for row in cart_rows}
    ordered_rows = sorted(
        cart_rows,
        key=lambda row: (row.get("parent_item_id") is not None, str(row["id"])),
    )
    candidates_by_cart_item: dict[UUID, tuple[dict[str, Any], ...]] = {}
    components_by_product: dict[UUID, tuple[dict[str, Any], ...]] = {}
    lock_ids: set[UUID] = set()
    for row in ordered_rows:
        eligible_ids: tuple[UUID, ...] | None = None
        if row.get("parent_item_id") is not None:
            parent = rows_by_id[row["parent_item_id"]]
            eligible_ids = await commerce_repository.list_compatible_attachment_ids(
                session, parent["product_id"]
            )
            if row["product_id"] not in eligible_ids:
                raise CheckoutAllocationError(
                    "Надстройка более не совместима с выбранной техникой",
                    code="SPECIAL_EQUIPMENT_ATTACHMENT_INCOMPATIBLE",
                )
        group = await _group_for_representative(
            session,
            row["product_id"],
            eligible_ids=eligible_ids,
            allowed_statuses=(
                ("available", "on_order")
                if allow_on_order
                else ("available",)
            ),
        )
        available = int(group["available_count"]) if group is not None else 0
        requested = int(row["quantity"])
        if allow_overstock and row.get("allow_overstock") and row.get("parent_item_id") is None:
            if group is None or available < 1:
                raise _availability_error(requested=requested, available=available)
            billable = min(requested, available)
            overstock = requested - billable
        else:
            if not allow_overstock and row.get("allow_overstock") and requested > available:
                raise CheckoutAllocationError(
                    "Для покупки ограничьте количество наличием или оформите лизинговую заявку.",
                    code="OVERSTOCK_NOT_ALLOWED_FOR_PURCHASE",
                    requested=requested,
                    available=available,
                )
            if group is None or requested > available:
                raise _availability_error(requested=requested, available=available)
            billable, overstock = requested, 0
        physical_ids = tuple(sorted(group["_physical_ids"], key=str))
        physical_by_id = {
            product["id"]: product
            for product in (
                await catalog_repository.list_products_by_ids(session, physical_ids)
            )
        }
        candidates = tuple(physical_by_id[item_id] for item_id in physical_ids)
        candidates_by_cart_item[row["id"]] = candidates
        lock_ids.update(physical_ids)
        for product in candidates:
            component_rows = tuple(
                await commerce_repository.list_product_components_for_checkout(
                    session, product["id"]
                )
            )
            if component_rows and (
                len(component_rows) < 2
                or sum(bool(item["is_base"]) for item in component_rows) != 1
            ):
                raise CheckoutAllocationError(
                    "Составное объявление имеет некорректный состав",
                    code="SPECIAL_EQUIPMENT_COMPOSITE_INVALID",
                )
            for component in component_rows:
                component_id = component["component_product_id"]
                if await commerce_repository.list_product_components_for_checkout(
                    session, component_id
                ):
                    raise CheckoutAllocationError(
                        "Вложенные составные объявления запрещены",
                        code="SPECIAL_EQUIPMENT_NESTED_COMPOSITE",
                    )
                lock_ids.add(component_id)
            components_by_product[product["id"]] = component_rows

    locked = await commerce_repository.lock_products(
        session,
        tuple(sorted(lock_ids, key=str)),
    )
    locked_by_id = {row["id"]: row for row in locked}
    allowed_statuses = {"available", "on_order"} if allow_on_order else {"available"}
    allowed_status_values: tuple[SaleStatus, ...] = (
        ("available", "on_order") if allow_on_order else ("available",)
    )

    # Catalog relations and fingerprints may change while checkout waits for
    # the globally ordered product locks. Re-read every mutable input only
    # after those locks and retain solely candidates that are still the same
    # offering with the same concrete component set.
    for row in ordered_rows:
        current_eligible_ids: tuple[UUID, ...] | None = None
        if row.get("parent_item_id") is not None:
            parent = rows_by_id[row["parent_item_id"]]
            current_eligible_ids = (
                await commerce_repository.list_compatible_attachment_ids(
                    session, parent["product_id"]
                )
            )
            if row["product_id"] not in current_eligible_ids:
                raise CheckoutAllocationError(
                    "Надстройка более не совместима с выбранной техникой",
                    code="SPECIAL_EQUIPMENT_ATTACHMENT_INCOMPATIBLE",
                )
        current_group = await _group_for_representative(
            session,
            row["product_id"],
            eligible_ids=current_eligible_ids,
            allowed_statuses=allowed_status_values,
        )
        current_group_ids = (
            set(current_group["_physical_ids"])
            if current_group is not None
            else set()
        )
        originally_locked_ids = {
            product["id"] for product in candidates_by_cart_item[row["id"]]
        }
        usable_ids = tuple(
            sorted(current_group_ids & originally_locked_ids, key=str)
        )
        current_products = {
            product["id"]: product
            for product in await catalog_repository.list_products_by_ids(
                session, usable_ids
            )
        }
        current_candidates: list[dict[str, Any]] = []
        for product_id in usable_ids:
            current_product = current_products.get(product_id)
            if current_product is None:
                continue
            current_components = tuple(
                await commerce_repository.list_product_components_for_checkout(
                    session, product_id
                )
            )
            previous_components = components_by_product[product_id]
            component_signature = tuple(
                (
                    item["component_product_id"],
                    int(item["position"]),
                    bool(item["is_base"]),
                )
                for item in current_components
            )
            previous_signature = tuple(
                (
                    item["component_product_id"],
                    int(item["position"]),
                    bool(item["is_base"]),
                )
                for item in previous_components
            )
            bundle_ids = {
                product_id,
                *(item["component_product_id"] for item in current_components),
            }
            if (
                component_signature != previous_signature
                or not bundle_ids.issubset(locked_by_id)
            ):
                continue
            components_by_product[product_id] = current_components
            current_candidates.append(current_product)
        candidates_by_cart_item[row["id"]] = tuple(current_candidates)

    def is_available(product_id: UUID) -> bool:
        product = locked_by_id.get(product_id)
        return bool(
            product is not None
            and product["publication_status"] == "published"
            and product["sale_status"] in allowed_statuses
        )

    allocations: list[AllocatedCartLine] = []
    components: list[AllocatedComponent] = []
    claimed_ids: set[UUID] = set()
    for row in ordered_rows:
        available_candidates: list[
            tuple[dict[str, Any], tuple[dict[str, Any], ...]]
        ] = []
        tentative_claimed_ids = set(claimed_ids)
        for product in candidates_by_cart_item[row["id"]]:
            component_rows = components_by_product[product["id"]]
            bundle_ids = {
                product["id"],
                *(component["component_product_id"] for component in component_rows),
            }
            if bundle_ids & tentative_claimed_ids or not all(
                is_available(product_id) for product_id in bundle_ids
            ):
                continue
            available_candidates.append((product, component_rows))
            tentative_claimed_ids.update(bundle_ids)
        requested = int(row["quantity"])
        available_count = len(available_candidates)
        if allow_overstock and row.get("allow_overstock") and row.get("parent_item_id") is None:
            if available_count < 1:
                raise _availability_error(
                    requested=requested,
                    available=available_count,
                )
            billable = min(requested, available_count)
            overstock = requested - billable
        else:
            if not allow_overstock and row.get("allow_overstock") and requested > available_count:
                raise CheckoutAllocationError(
                    "Для покупки ограничьте количество наличием или оформите лизинговую заявку.",
                    code="OVERSTOCK_NOT_ALLOWED_FOR_PURCHASE",
                    requested=requested,
                    available=available_count,
                )
            if available_count < requested:
                raise _availability_error(
                    requested=requested,
                    available=available_count,
                )
            billable, overstock = requested, 0
        selected = available_candidates[:billable]
        allocations.append(
            AllocatedCartLine(
                cart_item_id=row["id"],
                representative_id=row["product_id"],
                parent_cart_item_id=row.get("parent_item_id"),
                quantity=billable,
                products=tuple(product for product, _items in selected),
                overstock_quantity=overstock,
                custom_price=(
                    Decimal(str(row["custom_price"]))
                    if row.get("custom_price") is not None
                    else None
                ),
                equipments=tuple(row.get("equipments") or ()),
                services=tuple(row.get("services") or ()),
            )
        )
        for product, component_rows in selected:
            claimed_ids.add(product["id"])
            for component in component_rows:
                component_id = component["component_product_id"]
                claimed_ids.add(component_id)
                components.append(
                    AllocatedComponent(
                        source_cart_item_id=row["id"],
                        composite_product_id=product["id"],
                        component_product_id=component_id,
                        position=int(component["position"]),
                        is_base=bool(component["is_base"]),
                    )
                )
    return CheckoutAllocation(tuple(allocations), tuple(components))
