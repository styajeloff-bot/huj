"""Integration tests for /api/v1/exchange/requests (LC + dealer view)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def exc_lc_user(db_session: AsyncSession) -> User:
    company = Company(name="Exchange LC", company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    user = User(
        company_id=company.id,
        phone="+76660000001",
        email="exclc@test.local",
        name="Exc LC Router",
        role="leasing_company",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def exc_lc_token(exc_lc_user: User) -> str:
    token, _ = generate_tokens(exc_lc_user.id, "leasing_company", None)
    return token


@pytest_asyncio.fixture
async def exc_dealer_user(db_session: AsyncSession, exc_dealer_company: Company) -> User:
    user = User(
        phone="+76660000002",
        email="excdealer@test.local",
        name="Exc Dealer Router",
        role="dealer",
        company_id=exc_dealer_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def exc_dealer_token(exc_dealer_user: User) -> str:
    token, _ = generate_tokens(
        exc_dealer_user.id, "dealer", exc_dealer_user.company_id
    )
    return token


@pytest_asyncio.fixture
async def exc_dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="ExcDealerCo",
        inn="1122334455",
        ogrn="1122334455667",
        legal_address="ExcLegalAddr",
        actual_address="ExcActualAddr",
        company_type="dealer",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def exc_city(db_session: AsyncSession) -> City:
    city = City(name="IntCity")
    db_session.add(city)
    await db_session.flush()
    return city


@pytest_asyncio.fixture
async def exc_warehouse(
    db_session: AsyncSession, exc_city: City, exc_dealer_company: Company
) -> Warehouse:
    wh = Warehouse(
        address="IntWh",
        brand="IntBrand",
        city_id=exc_city.id,
        dealer_id=exc_dealer_company.id,
    )
    db_session.add(wh)
    await db_session.flush()
    return wh


@pytest_asyncio.fixture
async def exc_vehicle(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("3500000"),
    )
    db_session.add(v)
    await db_session.flush()
    return v


# ---------------------------------------------------------------------------
# Happy path — LC creates a request, dealer sees it
# ---------------------------------------------------------------------------


async def test_create_request_happy_path(
    client: AsyncClient,
    exc_lc_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    response = await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "quantity": 1,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                    "dealer_comment": "подготовьте",
                }
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["request"]["status"] == "open"
    assert body["batch_number"] >= 1


async def test_create_request_anon_unauthorized(
    client: AsyncClient, exc_vehicle: Vehicle
) -> None:
    response = await client.post(
        "/api/v1/exchange/requests/",
        json={"vehicle_id": exc_vehicle.id, "warehouses": []},
    )
    assert response.status_code == 401


async def test_create_request_dealer_forbidden(
    client: AsyncClient,
    exc_dealer_token: str,
    exc_vehicle: Vehicle,
) -> None:
    response = await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_dealer_token),
        json={"vehicle_id": exc_vehicle.id, "warehouses": []},
    )
    assert response.status_code == 403


async def test_list_own_requests_returns_only_lc_owned(
    client: AsyncClient,
    exc_lc_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                }
            ],
        },
    )
    listing = await client.get(
        "/api/v1/exchange/requests/", headers=_auth(exc_lc_token)
    )
    assert listing.status_code == 200
    assert len(listing.json()["requests"]) >= 1


async def test_lc_counts_endpoint(
    client: AsyncClient,
    exc_lc_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                }
            ],
        },
    )
    response = await client.get(
        "/api/v1/exchange/requests/counts",
        headers=_auth(exc_lc_token),
    )
    assert response.status_code == 200
    assert response.json()["counts"]["open"] >= 1


async def test_dealer_sees_own_requests(
    client: AsyncClient,
    exc_lc_token: str,
    exc_dealer_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                }
            ],
        },
    )
    dealer_list = await client.get(
        "/api/v1/exchange/requests/dealer",
        headers=_auth(exc_dealer_token),
    )
    assert dealer_list.status_code == 200
    assert len(dealer_list.json()["requests"]) >= 1


async def test_dealer_list_lc_forbidden(
    client: AsyncClient, exc_lc_token: str
) -> None:
    response = await client.get(
        "/api/v1/exchange/requests/dealer",
        headers=_auth(exc_lc_token),
    )
    assert response.status_code == 403


async def test_get_request_detail_as_lc(
    client: AsyncClient,
    exc_lc_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    created = await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                }
            ],
        },
    )
    rid = created.json()["request"]["id"]
    detail = await client.get(
        f"/api/v1/exchange/requests/{rid}",
        headers=_auth(exc_lc_token),
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["request"]["id"] == rid
    assert len(body["warehouses"]) == 1


async def test_get_request_denied_for_other_lc(
    client: AsyncClient,
    db_session: AsyncSession,
    exc_lc_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    other_lc = User(
        phone="+76660000099",
        email="otherlc@test.local",
        name="Other LC",
        role="leasing_company",
        is_active=True,
    )
    db_session.add(other_lc)
    await db_session.flush()
    other_token, _ = generate_tokens(other_lc.id, "leasing_company", None)

    created = await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                }
            ],
        },
    )
    rid = created.json()["request"]["id"]
    detail = await client.get(
        f"/api/v1/exchange/requests/{rid}",
        headers=_auth(other_token),
    )
    assert detail.status_code == 403


async def test_update_request_happy(
    client: AsyncClient,
    exc_lc_token: str,
    exc_vehicle: Vehicle,
    exc_warehouse: Warehouse,
    exc_dealer_user: User,
) -> None:
    created = await client.post(
        "/api/v1/exchange/requests/",
        headers=_auth(exc_lc_token),
        json={
            "vehicle_id": exc_vehicle.id,
            "warehouses": [
                {
                    "warehouse_id": exc_warehouse.id,
                    "dealer_id": exc_dealer_user.company_id,
                }
            ],
        },
    )
    rid = created.json()["request"]["id"]
    updated = await client.put(
        f"/api/v1/exchange/requests/{rid}",
        headers=_auth(exc_lc_token),
        json={"quantity": 5, "discount_value": "10000.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["request"]["quantity"] == 5


FAKE_UUID = "00000000-0000-0000-0000-000000000000"


async def test_update_request_404(
    client: AsyncClient, exc_lc_token: str
) -> None:
    response = await client.put(
        f"/api/v1/exchange/requests/{FAKE_UUID}",
        headers=_auth(exc_lc_token),
        json={"quantity": 2},
    )
    assert response.status_code == 404
