"""Functional tests for cart handlers (real Postgres, no HTTP)."""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
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
from application.queries.cart import (
    GetCartCountQuery,
    GetCartQuery,
    handle_get_cart,
    handle_get_cart_count,
)
from domain.errors import (
    CartCustomPriceDeniedError,
    CartItemNotFoundError,
    GuestCartTransferConflictError,
    InvalidCartQuantityError,
    VehicleNotFoundError,
)
from infrastructure.models.applications import ShoppingCart
from infrastructure.models.users import User
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_vehicle(
    db: AsyncSession,
    *,
    base_price: Decimal | None = Decimal("2000000.00"),
    discount_price: Decimal | None = None,
    complectation_id: str | None = None,
    color: str | None = None,
    color_inter: str | None = None,
    status: str = "available",
    is_available: bool = True,
) -> Vehicle:
    v = Vehicle(
        base_price=base_price,
        discount_price=discount_price,
        complectation_id=complectation_id,
        color=color,
        color_inter=color_inter,
        status=status,
        is_available=is_available,
    )
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


# ---------------------------------------------------------------------------
# Add / upsert / quantity edge cases
# ---------------------------------------------------------------------------


async def test_add_to_cart_creates_new_row(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    result = await handle_add_to_cart(
        AddToCartCommand(
            user_id=client_user.id, vehicle_id=vehicle.id, quantity=1
        ),
        db_session,
    )
    assert result.created is True
    assert result.cart_item["vehicle_id"] == vehicle.id
    assert result.cart_item["quantity"] == 1


async def test_add_to_cart_increments_quantity_on_dup(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(
            user_id=client_user.id, vehicle_id=vehicle.id, quantity=2, allow_overstock=True
        ),
        db_session,
    )
    second = await handle_add_to_cart(
        AddToCartCommand(
            user_id=client_user.id, vehicle_id=vehicle.id, quantity=3, allow_overstock=True
        ),
        db_session,
    )
    assert second.created is False
    assert second.cart_item["quantity"] == 5


async def test_add_to_cart_404_when_vehicle_missing(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(VehicleNotFoundError):
        await handle_add_to_cart(
            AddToCartCommand(
                user_id=client_user.id, vehicle_id=uuid4(), quantity=1
            ),
            db_session,
        )


async def test_add_to_cart_invalid_quantity_400(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    with pytest.raises(InvalidCartQuantityError):
        await handle_add_to_cart(
            AddToCartCommand(
                user_id=client_user.id, vehicle_id=vehicle.id, quantity=0
            ),
            db_session,
        )


async def test_guest_transfer_replay_does_not_increment_quantity(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    transfer_id = uuid4()
    command = TransferGuestCartCommand(
        user_id=client_user.id,
        transfer_id=transfer_id,
        vehicle_id=vehicle.id,
        quantity=2,
        allow_overstock=True,
        equipments=[{"equipment_code": "alarm", "price": "1000"}],
        services=[{"service_code": "kasko", "price": "2000"}],
    )

    first = await handle_transfer_guest_cart(command, db_session)
    replay = await handle_transfer_guest_cart(command, db_session)

    assert first.applied is True
    assert replay.applied is False
    assert replay.cart_item is not None
    assert replay.cart_item["quantity"] == 2
    assert replay.cart_item["equipments"] == command.equipments
    assert replay.cart_item["services"] == command.services


async def test_guest_transfer_conflicting_payload_is_rejected(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    transfer_id = uuid4()
    original = TransferGuestCartCommand(
        user_id=client_user.id,
        transfer_id=transfer_id,
        vehicle_id=vehicle.id,
        quantity=1,
        equipments=[],
        services=[],
    )
    await handle_transfer_guest_cart(original, db_session)

    with pytest.raises(GuestCartTransferConflictError):
        await handle_transfer_guest_cart(
            TransferGuestCartCommand(
                user_id=client_user.id,
                transfer_id=transfer_id,
                vehicle_id=vehicle.id,
                quantity=2,
                equipments=[],
                services=[],
            ),
            db_session,
        )

    cart = await handle_get_cart(GetCartQuery(user_id=client_user.id), db_session)
    assert cart[0]["quantity"] == 1


async def test_distinct_guest_transfers_increment_and_replace_options_atomically(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    first = TransferGuestCartCommand(
        user_id=client_user.id,
        transfer_id=uuid4(),
        vehicle_id=vehicle.id,
        quantity=1,
        equipments=[{"equipment_code": "alarm", "price": "1000"}],
        services=[],
    )
    second = TransferGuestCartCommand(
        user_id=client_user.id,
        transfer_id=uuid4(),
        vehicle_id=vehicle.id,
        quantity=3,
        allow_overstock=True,
        equipments=[],
        services=[{"service_code": "kasko", "price": "2000"}],
    )

    await handle_transfer_guest_cart(first, db_session)
    result = await handle_transfer_guest_cart(second, db_session)

    assert result.applied is True
    assert result.cart_item is not None
    assert result.cart_item["quantity"] == 4
    assert result.cart_item["equipments"] == []
    assert result.cart_item["services"] == second.services


# ---------------------------------------------------------------------------
# Unified PATCH — single field subsets
# ---------------------------------------------------------------------------


async def test_update_cart_item_toggles_selection(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            is_selected=False,
        ),
        db_session,
    )
    assert updated["is_selected"] is False


async def test_update_cart_item_404_when_missing(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(CartItemNotFoundError):
        await handle_update_cart_item(
            UpdateCartItemCommand(
                user_id=client_user.id,
                vehicle_id=uuid4(),
                is_selected=True,
            ),
            db_session,
        )


async def test_update_cart_item_sets_new_quantity(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id, vehicle_id=vehicle.id, quantity=7, allow_overstock=True
        ),
        db_session,
    )
    assert updated["quantity"] == 7


async def test_update_cart_item_invalid_quantity_zero(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    with pytest.raises(InvalidCartQuantityError):
        await handle_update_cart_item(
            UpdateCartItemCommand(
                user_id=client_user.id,
                vehicle_id=vehicle.id,
                quantity=0,
            ),
            db_session,
        )


async def test_update_cart_item_custom_price_dealer_ok(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            role="dealer",
            custom_price=Decimal("1500000.00"),
        ),
        db_session,
    )
    assert updated["custom_price"] == Decimal("1500000.00")


async def test_update_cart_item_custom_price_client_denied(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    with pytest.raises(CartCustomPriceDeniedError):
        await handle_update_cart_item(
            UpdateCartItemCommand(
                user_id=client_user.id,
                vehicle_id=vehicle.id,
                role="client",
                custom_price=Decimal("1500000.00"),
            ),
            db_session,
        )


async def test_update_cart_item_custom_price_client_allowed_when_base_price_zero(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session, base_price=Decimal("0"))
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            role="client",
            custom_price=Decimal("1500000.00"),
        ),
        db_session,
    )
    assert updated["custom_price"] == Decimal("1500000.00")


async def test_update_cart_item_custom_price_client_allowed_when_base_price_missing(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session, base_price=None)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            role="client",
            custom_price=Decimal("1500000.00"),
        ),
        db_session,
    )
    assert updated["custom_price"] == Decimal("1500000.00")


async def test_update_cart_item_comment_still_works_for_stale_vehicle_row(
    db_session: AsyncSession, client_user: User
) -> None:
    stale_vehicle_id = uuid4()
    db_session.add(
        ShoppingCart(
            user_id=client_user.id,
            vehicle_id=stale_vehicle_id,
            quantity=1,
        )
    )
    await db_session.flush()

    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=stale_vehicle_id,
            role="client",
            comment="Проверить наличие",
        ),
        db_session,
    )

    assert updated["comment"] == "Проверить наличие"


async def test_update_cart_item_custom_price_null_clears(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            role="dealer",
            custom_price=Decimal("1500000"),
        ),
        db_session,
    )
    cleared = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            role="dealer",
            custom_price=None,
        ),
        db_session,
    )
    assert cleared["custom_price"] is None


async def test_update_cart_item_comment_empty_becomes_null(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id, vehicle_id=vehicle.id, comment=""
        ),
        db_session,
    )
    assert updated["comment"] is None


async def test_update_cart_item_combined_fields(
    db_session: AsyncSession, client_user: User
) -> None:
    """All four mutable fields set in one command."""
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    updated = await handle_update_cart_item(
        UpdateCartItemCommand(
            user_id=client_user.id,
            vehicle_id=vehicle.id,
            role="dealer",
            is_selected=False,
            quantity=3,
            allow_overstock=True,
            comment="Нужен чёрный",
            custom_price=Decimal("1700000"),
        ),
        db_session,
    )
    assert updated["is_selected"] is False
    assert updated["quantity"] == 3
    assert updated["comment"] == "Нужен чёрный"
    assert updated["custom_price"] == Decimal("1700000")


# ---------------------------------------------------------------------------
# Bulk selection
# ---------------------------------------------------------------------------


async def test_bulk_update_selection_applies_to_own_items_only(
    db_session: AsyncSession, client_user: User, other_user: User
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(
            user_id=client_user.id,
            vehicle_id=v1.id,
            quantity=1,
            is_selected=True,
        )
    )
    db_session.add(
        ShoppingCart(
            user_id=client_user.id,
            vehicle_id=v2.id,
            quantity=1,
            is_selected=True,
        )
    )
    db_session.add(
        ShoppingCart(
            user_id=other_user.id,
            vehicle_id=v1.id,
            quantity=1,
            is_selected=True,
        )
    )
    await db_session.flush()

    updated = await handle_bulk_update_cart_selection(
        BulkUpdateCartSelectionCommand(
            user_id=client_user.id,
            items=[(v1.id, False), (v2.id, False)],
        ),
        db_session,
    )
    assert len(updated) == 2
    assert all(it["is_selected"] is False for it in updated)

    # The other user's row is unchanged.
    other_rows = await handle_get_cart(
        GetCartQuery(user_id=other_user.id), db_session
    )
    assert len(other_rows) == 1
    assert other_rows[0]["is_selected"] is True


# ---------------------------------------------------------------------------
# Remove / clear
# ---------------------------------------------------------------------------


async def test_remove_from_cart_idempotent_when_missing(
    db_session: AsyncSession, client_user: User
) -> None:
    removed = await handle_remove_from_cart(
        RemoveFromCartCommand(user_id=client_user.id, vehicle_id=uuid4()),
        db_session,
    )
    assert removed is False


async def test_remove_from_cart_removes_existing(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    removed = await handle_remove_from_cart(
        RemoveFromCartCommand(
            user_id=client_user.id, vehicle_id=vehicle.id
        ),
        db_session,
    )
    assert removed is True


async def test_clear_cart_wipes_only_current_user(
    db_session: AsyncSession, client_user: User, other_user: User
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v1.id, quantity=1)
    )
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v2.id, quantity=1)
    )
    db_session.add(
        ShoppingCart(user_id=other_user.id, vehicle_id=v1.id, quantity=1)
    )
    await db_session.flush()

    deleted = await handle_clear_cart(
        ClearCartCommand(user_id=client_user.id), db_session
    )
    assert deleted == 2

    other_items = await handle_get_cart(
        GetCartQuery(user_id=other_user.id), db_session
    )
    assert len(other_items) == 1


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def test_get_cart_joins_vehicle_fields(
    db_session: AsyncSession, client_user: User
) -> None:
    vehicle = await _seed_vehicle(
        db_session, base_price=Decimal("3000000"), color="red"
    )
    await handle_add_to_cart(
        AddToCartCommand(user_id=client_user.id, vehicle_id=vehicle.id),
        db_session,
    )
    items = await handle_get_cart(
        GetCartQuery(user_id=client_user.id), db_session
    )
    assert len(items) == 1
    assert items[0]["vehicle_id"] == vehicle.id
    assert items[0]["base_price"] == Decimal("3000000")
    assert items[0]["color"] == "red"


async def test_get_cart_count_only_available(
    db_session: AsyncSession, client_user: User
) -> None:
    v_ok = await _seed_vehicle(db_session, is_available=True)
    v_gone = await _seed_vehicle(db_session, is_available=False)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v_ok.id, quantity=1)
    )
    db_session.add(
        ShoppingCart(
            user_id=client_user.id, vehicle_id=v_gone.id, quantity=1
        )
    )
    await db_session.flush()
    count = await handle_get_cart_count(
        GetCartCountQuery(user_id=client_user.id), db_session
    )
    assert count == 1
