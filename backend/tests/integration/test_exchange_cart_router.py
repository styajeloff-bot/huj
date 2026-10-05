"""Integration tests for /api/v1/exchange/cart (Phase 5 E2, Phase 10 R5)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from tests.legacy_compat import Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def cart_lc(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000001",
        email="cartlc@test.local",
        name="Cart LC",
        role="leasing_company",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def cart_lc_token(cart_lc: User) -> str:
    token, _ = generate_tokens(cart_lc.id, "leasing_company", None)
    return token


@pytest_asyncio.fixture
async def cart_dealer_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000002",
        email="cartdealer@test.local",
        name="Cart Dealer",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def cart_dealer_token(cart_dealer_user: User) -> str:
    token, _ = generate_tokens(cart_dealer_user.id, "dealer", None)
    return token


@pytest_asyncio.fixture
async def cart_vehicle(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        status="available", is_available=True, base_price=Decimal("3000000")
    )
    db_session.add(v)
    await db_session.flush()
    return v


# ---------------------------------------------------------------------------
# Cart CRUD
# ---------------------------------------------------------------------------


async def test_create_cart_item_201(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    response = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 2},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["item"]["quantity"] == 2
    assert response.headers.get("location", "").startswith(
        "/api/v1/exchange/cart/"
    )


async def test_create_cart_item_anon_unauthorized(
    client: AsyncClient, cart_vehicle: Vehicle
) -> None:
    response = await client.post(
        "/api/v1/exchange/cart/",
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    assert response.status_code == 401


async def test_create_cart_item_dealer_forbidden(
    client: AsyncClient, cart_dealer_token: str, cart_vehicle: Vehicle
) -> None:
    response = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_dealer_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    assert response.status_code == 403


async def test_create_cart_item_duplicate_increments(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    second = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 2},
    )
    body = second.json()
    assert body["created"] is False
    assert body["item"]["quantity"] == 3


async def test_get_cart(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    response = await client.get(
        "/api/v1/exchange/cart/", headers=_auth(cart_lc_token)
    )
    assert response.status_code == 200
    assert response.json()["summary"]["total_items"] == 1


async def test_get_cart_count_projection(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    response = await client.get(
        "/api/v1/exchange/cart/?fields=count",
        headers=_auth(cart_lc_token),
    )
    assert response.status_code == 200
    assert response.json() == {"count": 1}


async def test_patch_cart_item(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    added = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    item_id = added.json()["item"]["id"]
    updated = await client.patch(
        f"/api/v1/exchange/cart/{item_id}",
        headers=_auth(cart_lc_token),
        json={"quantity": 5, "discount_value": "50000.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["item"]["quantity"] == 5


async def test_patch_accepts_warehouse_and_option_lists(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    """PATCH writes warehouses/options/dealer_comment through to the cart.

    Empty lists are the safe no-op variant that every environment
    accepts — they clear the server-side selection while still
    exercising the full write path.
    """
    added = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    item_id = added.json()["item"]["id"]
    updated = await client.patch(
        f"/api/v1/exchange/cart/{item_id}",
        headers=_auth(cart_lc_token),
        json={
            "quantity": 2,
            "warehouses": [],
            "options": [],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["item"]["quantity"] == 2


async def test_available_warehouses_uses_warehouse_company_as_dealer(
    client: AsyncClient,
    db_session: AsyncSession,
    cart_lc_token: str,
    cart_vehicle: Vehicle,
) -> None:
    dealer_center_1 = Company(
        name="Dealer Center 1",
        company_type="dealer",
        inn="7703000001",
    )
    dealer_center_3 = Company(
        name="Dealer Center 3",
        company_type="dealer",
        inn="7703000003",
    )
    db_session.add_all([dealer_center_1, dealer_center_3])
    await db_session.flush()

    warehouse = Warehouse(
        address="Москва, тестовый склад",
        brand="TEST",
        # Reproduce Bitrix 21854: the stale dealer_id disagrees with the
        # authoritative warehouse owner.
        dealer_id=dealer_center_1.id,
        company_id=dealer_center_3.id,
    )
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(
        VehicleWarehouse(vehicle_id=cart_vehicle.id, warehouse_id=warehouse.id)
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/exchange/cart/warehouses/{cart_vehicle.id}",
        headers=_auth(cart_lc_token),
    )

    assert response.status_code == 200
    body = response.json()
    response_warehouse = next(
        row for row in body["warehouses"] if row["id"] == str(warehouse.id)
    )
    assert response_warehouse["dealer_id"] == str(dealer_center_3.id)
    assert response_warehouse["dealer_name"] == dealer_center_3.name
    assert response_warehouse["company_name"] == dealer_center_3.name


async def test_patch_accepts_uuid_warehouse_selection(
    client: AsyncClient,
    db_session: AsyncSession,
    cart_lc_token: str,
    cart_vehicle: Vehicle,
) -> None:
    warehouse = Warehouse(address="Москва, склад для выбора", brand="TEST")
    db_session.add(warehouse)
    await db_session.flush()

    added = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": str(cart_vehicle.id), "quantity": 1},
    )
    item_id = added.json()["item"]["id"]

    updated = await client.patch(
        f"/api/v1/exchange/cart/{item_id}",
        headers=_auth(cart_lc_token),
        json={"warehouses": [str(warehouse.id)]},
    )

    assert updated.status_code == 200

    cart = await client.get("/api/v1/exchange/cart/", headers=_auth(cart_lc_token))
    assert cart.status_code == 200
    assert cart.json()["cart_items"][0]["selected_warehouse_ids"] == [str(warehouse.id)]


async def test_remove_cart_item(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    added = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    item_id = added.json()["item"]["id"]
    response = await client.delete(
        f"/api/v1/exchange/cart/{item_id}",
        headers=_auth(cart_lc_token),
    )
    assert response.status_code == 200


FAKE_UUID = "00000000-0000-0000-0000-000000000000"


async def test_remove_unknown_cart_item_returns_404(
    client: AsyncClient, cart_lc_token: str
) -> None:
    response = await client.delete(
        f"/api/v1/exchange/cart/{FAKE_UUID}",
        headers=_auth(cart_lc_token),
    )
    assert response.status_code == 404


async def test_clear_cart(
    client: AsyncClient, cart_lc_token: str, cart_vehicle: Vehicle
) -> None:
    await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": cart_vehicle.id, "quantity": 1},
    )
    response = await client.delete(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
    )
    assert response.status_code == 200
    assert response.json()["deleted_count"] >= 1


async def test_create_cart_item_unknown_vehicle_404(
    client: AsyncClient, cart_lc_token: str
) -> None:
    response = await client.post(
        "/api/v1/exchange/cart/",
        headers=_auth(cart_lc_token),
        json={"vehicle_id": FAKE_UUID, "quantity": 1},
    )
    assert response.status_code == 404
