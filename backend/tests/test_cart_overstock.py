from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from domain.entities.cart_item import CartItem
from domain.errors import InsufficientVehiclesError, InvalidCartQuantityError
from infrastructure.models.users import User
from presentation.schemas.commerce import CommerceLeasingApplicationItemRequest
from tests.legacy_compat import Modification, Vehicle


def test_excess_quantity_requires_explicit_opt_in() -> None:
    with pytest.raises(InsufficientVehiclesError):
        CartItem.ensure_stock_quantity(5, available=3, allow_overstock=False)
    CartItem.ensure_stock_quantity(5, available=3, allow_overstock=True)


@pytest.mark.parametrize('quantity', [0, -1, 2147483648])
def test_overstock_does_not_bypass_integer_bounds(quantity: int) -> None:
    with pytest.raises(InvalidCartQuantityError):
        CartItem.ensure_stock_quantity(quantity, available=3, allow_overstock=True)


def test_vehicle_leasing_supports_more_than_100_with_explicit_mode() -> None:
    line = CommerceLeasingApplicationItemRequest(
        item={'type': 'vehicle', 'id': uuid4()}, quantity=101, allow_overstock=True,
    )
    assert line.quantity == 101
    assert line.allow_overstock is True


@pytest.mark.asyncio
async def test_cart_stock_mode_roundtrip_and_atomic_disable(db_session: AsyncSession, client_user: User) -> None:
    from application.commands.cart import (
        AddToCartCommand,
        UpdateCartItemCommand,
        handle_add_to_cart,
        handle_update_cart_item,
    )
    from application.queries.cart import GetCartQuery, handle_get_cart

    trim = str(uuid4())
    db_session.add(Modification(complectation_id=trim))
    await db_session.flush()
    cars = [Vehicle(complectation_id=trim, base_price=2000000, status='available', is_available=True) for _ in range(3)]
    db_session.add_all(cars)
    await db_session.flush()
    uid, vid = client_user.id, cars[0].id
    with pytest.raises(InsufficientVehiclesError):
        await handle_add_to_cart(AddToCartCommand(uid, vid, quantity=4), db_session)
    assert await handle_get_cart(GetCartQuery(uid), db_session) == []
    await handle_add_to_cart(AddToCartCommand(uid, vid, quantity=3), db_session)
    with pytest.raises(InsufficientVehiclesError):
        await handle_add_to_cart(AddToCartCommand(uid, vid), db_session)
    result = await handle_update_cart_item(UpdateCartItemCommand(uid, vid, quantity=5, allow_overstock=True,
        equipments=[{'equipment_code': 'alarm', 'price': '1000'}], comment='retain'), db_session)
    assert result['quantity'] == 5 and result['allow_overstock'] is True
    with pytest.raises(InsufficientVehiclesError):
        await handle_update_cart_item(UpdateCartItemCommand(uid, vid, allow_overstock=False,
            comment='must not apply'), db_session)
    unchanged = (await handle_get_cart(GetCartQuery(uid), db_session))[0]
    assert (unchanged['quantity'], unchanged['allow_overstock'], unchanged['comment']) == (5, True, 'retain')
    result = await handle_update_cart_item(UpdateCartItemCommand(uid, vid, quantity=2, allow_overstock=False), db_session)
    assert result['quantity'] == 2 and result['allow_overstock'] is False
    assert result['equipments'] == unchanged['equipments']
    # Existing opted-in mode survives normal increments without an explicit mode field.
    await handle_update_cart_item(UpdateCartItemCommand(uid, vid, allow_overstock=True), db_session)
    added = await handle_add_to_cart(AddToCartCommand(uid, vid, quantity=4), db_session)
    assert added.cart_item['quantity'] == 6 and added.cart_item['allow_overstock'] is True


@pytest.mark.asyncio
async def test_guest_transfer_mode_is_part_of_receipt_and_replay_survives_stock_change(db_session: AsyncSession, client_user: User) -> None:
    from dataclasses import replace

    from application.commands.cart import (
        TransferGuestCartCommand,
        handle_transfer_guest_cart,
    )
    from domain.errors import GuestCartTransferConflictError
    from domain.storefronts import DEFAULT_CATALOG_SCOPE
    from infrastructure.repositories.cart_repository import get_cart_item

    vehicle = Vehicle(status='available', is_available=True)
    db_session.add(vehicle)
    await db_session.flush()
    command = TransferGuestCartCommand(client_user.id, uuid4(), vehicle.id, 5, [], [], allow_overstock=True)
    applied = await handle_transfer_guest_cart(command, db_session)
    assert applied.applied and applied.cart_item is not None
    assert applied.cart_item['allow_overstock'] is True
    with pytest.raises(GuestCartTransferConflictError):
        await handle_transfer_guest_cart(replace(command, allow_overstock=False), db_session)
    vehicle.is_available = False
    await db_session.flush()
    replay = await handle_transfer_guest_cart(command, db_session)
    assert not replay.applied
    row = await get_cart_item(db_session, client_user.id, vehicle.id, DEFAULT_CATALOG_SCOPE)
    assert row is not None and row['quantity'] == 5



@pytest.mark.asyncio
async def test_concurrent_cart_initial_adds_cannot_exceed_stock(_engine: AsyncEngine) -> None:
    import asyncio

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import AsyncSession

    from application.commands.cart import AddToCartCommand, handle_add_to_cart
    from infrastructure.models.applications import ShoppingCart
    from infrastructure.models.users import User

    # Independent committed fixture is necessary for real separate DB connections.
    async with AsyncSession(_engine, expire_on_commit=False) as setup:
        user = User(role='client', name='21924 concurrent cart', phone=f'+7{uuid4().int % 10**10:010d}')
        vehicle = Vehicle(status='available', is_available=True)
        setup.add_all([user, vehicle])
        await setup.commit()
        uid, vid = user.id, vehicle.id
    try:
        async def add() -> int | str:
            async with AsyncSession(_engine) as session:
                try:
                    result = await handle_add_to_cart(AddToCartCommand(uid, vid), session)
                    await session.commit()
                    return int(result.cart_item['quantity'])
                except InsufficientVehiclesError:
                    await session.rollback()
                    return 'insufficient'
        results = await asyncio.gather(add(), add())
        assert sorted(results, key=str) == [1, 'insufficient']
        async with AsyncSession(_engine) as session:
            rows = (await session.execute(select(ShoppingCart.quantity).where(ShoppingCart.user_id == uid))).scalars().all()
            assert rows == [1]
    finally:
        async with AsyncSession(_engine) as cleanup:
            await cleanup.execute(delete(ShoppingCart).where(ShoppingCart.user_id == uid))
            await cleanup.execute(delete(User).where(User.id == uid))
            await cleanup.execute(delete(Vehicle).where(Vehicle.id == vid))
            await cleanup.commit()
