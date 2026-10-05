"""Integration tests for /api/v1/cart/* (full HTTP round-trip)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.auth import generate_tokens
from infrastructure.database import get_db
from infrastructure.models.applications import (
    AdditionalEquipment,
    AdditionalService,
    ShoppingCart,
)
from infrastructure.models.cart_transfers import GuestCartTransfer
from infrastructure.models.users import User
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_not_redirected(response: Response) -> None:
    assert response.status_code != 307


def _assert_no_location(response: Response) -> None:
    assert "location" not in response.headers


async def _seed_vehicle(
    db: AsyncSession,
    *,
    base_price: Decimal | None = Decimal("2000000.00"),
    complectation_id: str | None = None,
    color: str | None = None,
    color_inter: str | None = None,
    status: str = "available",
    is_available: bool = True,
) -> Vehicle:
    v = Vehicle(
        status=status,
        is_available=is_available,
        base_price=base_price,
        complectation_id=complectation_id,
        color=color,
        color_inter=color_inter,
    )
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


async def _seed_committed_guest_transfer_context(
    engine: AsyncEngine,
) -> tuple[UUID, UUID]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique = uuid4()
    user = User(
        phone=f"+7{unique.int % 10**17:017d}",
        email=f"guest-transfer-{unique.hex}@test.local",
        name="Guest Transfer User",
        role="client",
        is_active=True,
    )
    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("2000000.00"),
    )
    async with session_factory() as session:
        session.add_all([user, vehicle])
        await session.commit()
    return user.id, vehicle.id


async def _cleanup_committed_guest_transfer_context(
    engine: AsyncEngine,
    *,
    user_id: UUID,
    vehicle_id: UUID,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            sa.delete(GuestCartTransfer).where(GuestCartTransfer.user_id == user_id)
        )
        await session.execute(
            sa.delete(ShoppingCart).where(ShoppingCart.user_id == user_id)
        )
        await session.execute(sa.delete(User).where(User.id == user_id))
        await session.execute(sa.delete(Vehicle).where(Vehicle.id == vehicle_id))
        await session.commit()


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000010",
        email="dealer@test.local",
        name="Dealer User",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def dealer_token(dealer_user: User) -> str:
    token, _ = generate_tokens(dealer_user.id, "dealer", None)
    return token


# ---------------------------------------------------------------------------
# Auth / roles
# ---------------------------------------------------------------------------


async def test_get_cart_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/cart/")
    assert response.status_code == 401


async def test_get_cart_without_trailing_slash_requires_auth_without_redirect(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/cart")
    assert response.status_code == 401
    _assert_not_redirected(response)
    _assert_no_location(response)


async def test_get_cart_empty_for_new_user(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get("/api/v1/cart/", headers=_auth(client_token))
    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_additional_option_catalogs_are_public(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(
        AdditionalEquipment(
            equipment_code="alarm",
            equipment_display_name="Сигнализация",
            sort_order=1,
        )
    )
    db_session.add(
        AdditionalService(
            service_code="kasko",
            service_display_name="Страхование КАСКО",
            sort_order=1,
        )
    )
    await db_session.flush()

    equipments = await client.get("/api/v1/equipments")
    services = await client.get("/api/v1/services")

    assert equipments.status_code == 200, equipments.text
    assert services.status_code == 200, services.text
    assert {
        "equipment_code": "alarm",
        "equipment_display_name": "Сигнализация",
    } in equipments.json()["items"]
    assert {
        "service_code": "kasko",
        "service_display_name": "Страхование КАСКО",
    } in services.json()["items"]


# ---------------------------------------------------------------------------
# Create (POST /cart)
# ---------------------------------------------------------------------------


async def test_create_cart_item_201(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    response = await client.post(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": v.id, "quantity": 2, "allow_overstock": True},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["cart_item"]["vehicle_id"] == str(v.id)
    assert body["cart_item"]["quantity"] == 2
    assert response.headers.get("location") == f"/api/v1/cart/{v.id}"


async def test_create_cart_item_without_trailing_slash_201_without_redirect(
    client: AsyncClient,
    dealer_token: str,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    response = await client.post(
        "/api/v1/cart",
        headers=_auth(dealer_token),
        json={"vehicle_id": v.id, "quantity": 1},
    )
    assert response.status_code == 201, response.text
    _assert_not_redirected(response)
    assert response.json()["cart_item"]["vehicle_id"] == str(v.id)


async def test_create_cart_item_upsert_returns_201(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    await client.post(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": v.id, "quantity": 1},
    )
    second = await client.post(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": v.id, "quantity": 3, "allow_overstock": True},
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["created"] is False
    assert body["cart_item"]["quantity"] == 4


FAKE_UUID = "00000000-0000-0000-0000-000000000000"


async def test_create_cart_item_missing_vehicle_404(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": FAKE_UUID, "quantity": 1},
    )
    assert response.status_code == 404


async def test_create_cart_item_invalid_quantity_422(
    client: AsyncClient, client_token: str, db_session: AsyncSession
) -> None:
    v = await _seed_vehicle(db_session)
    response = await client.post(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": v.id, "quantity": 0},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Idempotent guest transfer (PUT /cart/guest-transfers/{transfer_id})
# ---------------------------------------------------------------------------


async def test_guest_transfer_is_idempotent_and_applies_options_atomically(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    transfer_id = uuid4()
    payload = {
        "vehicle_id": str(vehicle.id),
        "quantity": 2, "allow_overstock": True,
        "equipments": [{"equipment_code": "alarm", "price": "1000"}],
        "services": [{"service_code": "kasko", "price": "2000"}],
    }

    first = await client.put(
        f"/api/v1/cart/guest-transfers/{transfer_id}",
        headers=_auth(client_token),
        json=payload,
    )
    replay = await client.put(
        f"/api/v1/cart/guest-transfers/{transfer_id}",
        headers=_auth(client_token),
        json=payload,
    )

    assert first.status_code == 201, first.text
    assert first.json()["applied"] is True
    assert replay.status_code == 200, replay.text
    assert replay.json()["applied"] is False
    assert replay.json()["cart_item"]["quantity"] == 2

    listing = await client.get("/api/v1/cart/", headers=_auth(client_token))
    item = listing.json()["items"][0]
    assert item["quantity"] == 2
    assert item["equipments"] == payload["equipments"]
    assert item["services"] == payload["services"]

    receipt = await db_session.get(
        GuestCartTransfer,
        {
            "user_id": client_user.id,
            "storefront_id": DEFAULT_STOREFRONT_ID,
            "transfer_id": transfer_id,
        },
    )
    assert receipt is not None
    assert receipt.vehicle_id == vehicle.id


async def test_concurrent_identical_guest_transfer_puts_apply_once(
    _engine: AsyncEngine,
) -> None:
    from main import app

    user_id, vehicle_id = await _seed_committed_guest_transfer_context(_engine)
    session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async def _independent_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _independent_session
    try:
        transfer_id = uuid4()
        token, _ = generate_tokens(user_id, "client", None)
        path = f"/api/v1/cart/guest-transfers/{transfer_id}"
        payload = {
            "vehicle_id": str(vehicle_id),
            "quantity": 2, "allow_overstock": True,
            "equipments": [{"equipment_code": "alarm"}],
            "services": [{"service_code": "kasko", "price": 2000}],
        }
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as concurrent_client:
            concurrent_client.cookies.set("accessToken", token)
            responses = await asyncio.gather(
                concurrent_client.put(
                    path,
                    json=payload,
                ),
                concurrent_client.put(
                    path,
                    json=payload,
                ),
            )

        assert sorted(response.status_code for response in responses) == [200, 201]
        assert sorted(response.json()["applied"] for response in responses) == [
            False,
            True,
        ]

        async with session_factory() as session:
            receipt_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(GuestCartTransfer)
                .where(
                    GuestCartTransfer.user_id == user_id,
                    GuestCartTransfer.transfer_id == transfer_id,
                )
            )
            cart_item = await session.scalar(
                sa.select(ShoppingCart).where(
                    ShoppingCart.user_id == user_id,
                    ShoppingCart.vehicle_id == vehicle_id,
                )
            )

        assert receipt_count == 1
        assert cart_item is not None
        assert cart_item.quantity == 2
        assert cart_item.equipments == [{"equipment_code": "alarm", "price": "0"}]
        assert cart_item.services == [{"service_code": "kasko", "price": "2000"}]
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        await _cleanup_committed_guest_transfer_context(
            _engine,
            user_id=user_id,
            vehicle_id=vehicle_id,
        )


async def test_guest_transfer_transaction_error_rolls_back_receipt_and_cart(
    _engine: AsyncEngine,
) -> None:
    from main import app

    user_id, vehicle_id = await _seed_committed_guest_transfer_context(_engine)
    session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    commit_attempted = asyncio.Event()

    async def _failing_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:

            async def _fail_commit() -> None:
                await session.flush()
                commit_attempted.set()
                raise RuntimeError("simulated guest transfer commit failure")

            session.commit = _fail_commit  # type: ignore[method-assign]
            yield session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _failing_session
    try:
        transfer_id = uuid4()
        token, _ = generate_tokens(user_id, "client", None)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as failing_client:
            failing_client.cookies.set("accessToken", token)
            with pytest.raises(
                RuntimeError,
                match="simulated guest transfer commit failure",
            ):
                await failing_client.put(
                    f"/api/v1/cart/guest-transfers/{transfer_id}",
                    json={"vehicle_id": str(vehicle_id), "quantity": 3, "allow_overstock": True},
                )

        assert commit_attempted.is_set()
        async with session_factory() as session:
            receipt_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(GuestCartTransfer)
                .where(
                    GuestCartTransfer.user_id == user_id,
                    GuestCartTransfer.transfer_id == transfer_id,
                )
            )
            cart_count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ShoppingCart)
                .where(
                    ShoppingCart.user_id == user_id,
                    ShoppingCart.vehicle_id == vehicle_id,
                )
            )

        assert receipt_count == 0
        assert cart_count == 0
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        await _cleanup_committed_guest_transfer_context(
            _engine,
            user_id=user_id,
            vehicle_id=vehicle_id,
        )


async def test_guest_transfer_conflict_returns_409_without_mutation(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    transfer_id = uuid4()
    path = f"/api/v1/cart/guest-transfers/{transfer_id}"
    original = {
        "vehicle_id": str(vehicle.id),
        "quantity": 1,
        "equipments": [],
        "services": [],
    }
    created = await client.put(path, headers=_auth(client_token), json=original)
    conflict = await client.put(
        path,
        headers=_auth(client_token),
        json={**original, "quantity": 4, "allow_overstock": True},
    )

    assert created.status_code == 201, created.text
    assert conflict.status_code == 409, conflict.text
    listing = await client.get("/api/v1/cart/", headers=_auth(client_token))
    assert listing.json()["items"][0]["quantity"] == 1


async def test_guest_transfer_id_is_scoped_to_authenticated_user(
    client: AsyncClient,
    client_token: str,
    other_token: str,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    transfer_id = uuid4()
    payload = {"vehicle_id": str(vehicle.id), "quantity": 1}

    first = await client.put(
        f"/api/v1/cart/guest-transfers/{transfer_id}",
        headers=_auth(client_token),
        json=payload,
    )
    second = await client.put(
        f"/api/v1/cart/guest-transfers/{transfer_id}",
        headers=_auth(other_token),
        json=payload,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text


async def test_guest_transfer_validates_auth_and_uuids(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    transfer_id = uuid4()
    path = f"/api/v1/cart/guest-transfers/{transfer_id}"

    unauthenticated = await client.put(
        path,
        json={"vehicle_id": str(vehicle.id), "quantity": 1},
    )
    invalid_path = await client.put(
        "/api/v1/cart/guest-transfers/not-a-uuid",
        headers=_auth(client_token),
        json={"vehicle_id": str(vehicle.id), "quantity": 1},
    )
    invalid_vehicle = await client.put(
        path,
        headers=_auth(client_token),
        json={"vehicle_id": "not-a-uuid", "quantity": 1},
    )

    assert unauthenticated.status_code == 401
    assert invalid_path.status_code == 422
    assert invalid_vehicle.status_code == 422


# ---------------------------------------------------------------------------
# Unified PATCH /cart/{vehicle_id}
# ---------------------------------------------------------------------------


async def test_patch_updates_selection(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"is_selected": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cart_item"]["is_selected"] is False


async def test_patch_updates_quantity(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"quantity": 5, "allow_overstock": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cart_item"]["quantity"] == 5


async def test_patch_quantity_zero_is_422(
    client: AsyncClient, client_token: str, db_session: AsyncSession
) -> None:
    v = await _seed_vehicle(db_session)
    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"quantity": 0},
    )
    assert response.status_code == 422


async def test_patch_all_fields_in_one_call(
    client: AsyncClient,
    dealer_token: str,
    dealer_user: User,
    db_session: AsyncSession,
) -> None:
    """One PATCH mutates is_selected + quantity + price + comment atomically."""
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=dealer_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(dealer_token),
        json={
            "is_selected": False,
            "quantity": 4, "allow_overstock": True,
            "custom_price": "1500000.00",
            "comment": "Нужен чёрный",
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()["cart_item"]
    assert item["is_selected"] is False
    assert item["quantity"] == 4
    assert Decimal(str(item["custom_price"])) == Decimal("1500000.00")
    assert item["comment"] == "Нужен чёрный"


async def test_patch_additional_options(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={
            "equipments": [{"equipment_code": "alarm", "price": 0}],
            "services": [{"service_code": "kasko", "price": 0}],
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()["cart_item"]
    assert item["equipments"] == [{"equipment_code": "alarm", "price": "0"}]
    assert item["services"] == [{"service_code": "kasko", "price": "0"}]

    listing = await client.get("/api/v1/cart/", headers=_auth(client_token))
    assert listing.status_code == 200
    listed = listing.json()["items"][0]
    assert listed["equipments"] == [{"equipment_code": "alarm", "price": "0"}]
    assert listed["services"] == [{"service_code": "kasko", "price": "0"}]


async def test_patch_empty_body_is_noop_200(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=2)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cart_item"]["quantity"] == 2


async def test_patch_404_when_item_missing(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.patch(
        f"/api/v1/cart/{FAKE_UUID}",
        headers=_auth(client_token),
        json={"is_selected": True},
    )
    assert response.status_code == 404


async def test_patch_custom_price_client_denied_403(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"custom_price": "1500000.00"},
    )
    assert response.status_code == 403


async def test_patch_custom_price_client_allowed_when_base_price_zero(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session, base_price=Decimal("0"))
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"custom_price": "1500000.00"},
    )
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["cart_item"]["custom_price"])) == Decimal(
        "1500000.00"
    )


async def test_patch_custom_price_client_allowed_when_base_price_missing(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session, base_price=None)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"custom_price": "1500000.00"},
    )
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["cart_item"]["custom_price"])) == Decimal(
        "1500000.00"
    )


async def test_patch_custom_price_null_clears(
    client: AsyncClient,
    dealer_token: str,
    dealer_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(
            user_id=dealer_user.id,
            vehicle_id=v.id,
            quantity=1,
            custom_price=Decimal("1800000"),
        )
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(dealer_token),
        json={"custom_price": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cart_item"]["custom_price"] is None


async def test_patch_comment_empty_clears(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(
            user_id=client_user.id,
            vehicle_id=v.id,
            quantity=1,
            comment="old",
        )
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
        json={"comment": ""},
    )
    assert response.status_code == 200
    assert response.json()["cart_item"]["comment"] is None


# ---------------------------------------------------------------------------
# Bulk selection — PATCH /cart
# ---------------------------------------------------------------------------


async def test_bulk_patch_selection(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v1.id, quantity=1)
    )
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v2.id, quantity=1)
    )
    await db_session.flush()

    response = await client.patch(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={
            "items": [
                {"vehicle_id": v1.id, "is_selected": False},
                {"vehicle_id": v2.id, "is_selected": False},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["updated_items"]) == 2


async def test_bulk_patch_without_trailing_slash_empty_cart_200_without_redirect(
    client: AsyncClient,
    dealer_token: str,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    response = await client.patch(
        "/api/v1/cart",
        headers=_auth(dealer_token),
        json={"items": [{"vehicle_id": v.id, "is_selected": False}]},
    )
    assert response.status_code == 200, response.text
    _assert_not_redirected(response)
    assert response.json()["updated_items"] == []


# ---------------------------------------------------------------------------
# Delete / clear
# ---------------------------------------------------------------------------


async def test_remove_from_cart_idempotent(
    client: AsyncClient, client_token: str, db_session: AsyncSession
) -> None:
    v = await _seed_vehicle(db_session)
    response = await client.delete(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    assert response.json()["removed"] is False


async def test_remove_from_cart_actual(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.delete(
        f"/api/v1/cart/{v.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    assert response.json()["removed"] is True


async def test_clear_cart(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v1.id, quantity=1)
    )
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v2.id, quantity=1)
    )
    await db_session.flush()

    response = await client.delete(
        "/api/v1/cart/",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    assert response.json() == {
        "message": "Корзина очищена",
        "deleted_count": 2,
    }


async def test_clear_cart_without_trailing_slash_200_without_redirect(
    client: AsyncClient,
    dealer_token: str,
) -> None:
    response = await client.delete(
        "/api/v1/cart",
        headers=_auth(dealer_token),
    )
    assert response.status_code == 200
    _assert_not_redirected(response)
    assert response.json()["deleted_count"] == 0


# ---------------------------------------------------------------------------
# Count projection — GET /cart?fields=count
# ---------------------------------------------------------------------------


async def test_get_cart_count_projection(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(
        ShoppingCart(user_id=client_user.id, vehicle_id=v.id, quantity=1)
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/cart/?fields=count", headers=_auth(client_token)
    )
    assert response.status_code == 200
    assert response.json() == {"count": 1}


async def test_get_cart_count_no_auth_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/cart/?fields=count")
    assert response.status_code == 401


async def test_get_cart_count_without_trailing_slash_no_auth_401_no_redirect(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/cart?fields=count")
    assert response.status_code == 401
    _assert_not_redirected(response)
    _assert_no_location(response)


async def test_public_openapi_has_public_paths_and_no_protected_cart(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/openapi.json/")
    assert response.status_code == 200
    _assert_not_redirected(response)
    _assert_no_location(response)

    paths = response.json()["paths"]
    assert {
        "/api/v1/health",
        "/api/v1/company/search",
        "/api/v1/auth/login",
    }.issubset(paths)
    assert "/api/v1/cart/" not in paths


async def test_client_openapi_has_protected_cart_path(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.get(
        "/api/v1/openapi.json",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    _assert_not_redirected(response)
    _assert_no_location(response)

    paths = response.json()["paths"]
    assert paths
    assert "get" in paths["/api/v1/cart/"]


async def test_stock_limit_requires_opt_in_and_mode_roundtrips(
    client: AsyncClient, client_token: str, db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    headers = _auth(client_token)
    rejected = await client.post('/api/v1/cart/', headers=headers,
                                 json={'vehicle_id': str(vehicle.id), 'quantity': 2})
    assert rejected.status_code == 409, rejected.text
    created = await client.post('/api/v1/cart/', headers=headers,
                                json={'vehicle_id': str(vehicle.id), 'quantity': 2, 'allow_overstock': True})
    assert created.status_code == 201, created.text
    assert created.json()['cart_item']['allow_overstock'] is True
    rejected = await client.patch(f'/api/v1/cart/{vehicle.id}', headers=headers,
                                  json={'allow_overstock': False, 'comment': 'should not save'})
    assert rejected.status_code == 409, rejected.text
    listed = await client.get('/api/v1/cart/', headers=headers)
    item = listed.json()['items'][0]
    assert item['quantity'] == 2 and item['allow_overstock'] is True and item['comment'] is None
    changed = await client.patch(f'/api/v1/cart/{vehicle.id}', headers=headers,
                                 json={'quantity': 1, 'allow_overstock': False})
    assert changed.status_code == 200, changed.text
    assert changed.json()['cart_item']['allow_overstock'] is False
