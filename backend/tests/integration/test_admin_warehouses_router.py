"""Integration tests for /api/v1/admin/warehouses and /api/v1/admin/cities."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from tests.legacy_compat import Mark, Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def city_moscow(db_session: AsyncSession) -> City:
    city = City(name="Москва-IT")
    db_session.add(city)
    await db_session.flush()
    return city


@pytest_asyncio.fixture
async def dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Dealer Company IT WH",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession, dealer_company: Company) -> User:
    user = User(
        phone="+76660005555",
        email="dealer-itwh@test.local",
        name="Dealer IT WH",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def mark_bmw(db_session: AsyncSession) -> Mark:
    mark = Mark(id="bmw_itwh", name="BMW")
    db_session.add(mark)
    await db_session.flush()
    return mark


@pytest_asyncio.fixture
async def vehicle_with_mark(
    db_session: AsyncSession, mark_bmw: Mark
) -> Vehicle:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        vin="ITWHVIN1234567890",
        status="available",
        is_available=True,
    )
    db_session.add(vehicle)
    await db_session.flush()
    return vehicle


# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------


async def test_create_city_happy_path(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/cities",
        json={"name": "Тверь"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["city"]["name"] == "Тверь"
    assert "Location" in {k.title() for k in response.headers}


async def test_create_city_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/admin/cities", json={"name": "x"}
    )
    assert response.status_code == 401


async def test_create_city_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/cities",
        json={"name": "x"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_create_city_duplicate_returns_409(
    client: AsyncClient, employee_token: str
) -> None:
    await client.post(
        "/api/v1/admin/cities",
        json={"name": "Дубль-Сити"},
        headers=_auth(employee_token),
    )
    second = await client.post(
        "/api/v1/admin/cities",
        json={"name": "ДУБЛЬ-СИТИ"},
        headers=_auth(employee_token),
    )
    assert second.status_code == 409


async def test_list_cities_returns_sorted(
    client: AsyncClient, employee_token: str
) -> None:
    for name in ("Я-город", "А-город"):
        await client.post(
            "/api/v1/admin/cities",
            json={"name": name},
            headers=_auth(employee_token),
        )
    response = await client.get(
        "/api/v1/admin/cities", headers=_auth(employee_token)
    )
    assert response.status_code == 200
    names = [c["name"] for c in response.json()["cities"]]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# Warehouses CRUD
# ---------------------------------------------------------------------------


async def test_create_warehouse_happy_path(
    client: AsyncClient,
    employee_token: str,
    city_moscow: City,
    dealer_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/admin/warehouses",
        json={
            "address": "Кутузовский 1",
            "brand": "BMW",
            "city_id": city_moscow.id,
            "dealer_id": dealer_company.id,
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["warehouse"]["address"] == "Кутузовский 1"
    assert body["warehouse"]["city_id"] == str(city_moscow.id)


async def test_create_warehouse_with_company(
    client: AsyncClient,
    employee_token: str,
    dealer_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/admin/warehouses",
        json={
            "address": "Кутузовский 2",
            "brand": "Audi",
            "company_id": dealer_company.id,
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["warehouse"]["address"] == "Кутузовский 2"
    assert body["warehouse"]["company_id"] == str(dealer_company.id)
    assert body["warehouse"]["company_name"] == dealer_company.name
    # dealer_id auto-resolved from company (now companies.id)
    assert body["warehouse"]["dealer_id"] == str(dealer_company.id)


async def test_create_warehouse_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "x", "brand": "y"},
    )
    assert response.status_code == 401


async def test_create_warehouse_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "x", "brand": "y"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_warehouse_validation_error_uses_problem_json(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.put(
        f"/api/v1/admin/warehouses/{uuid4()}",
        json={"status": "broken"},
        headers=_auth(employee_token),
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 422


async def test_create_warehouse_unknown_city_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "x", "brand": "y", "city_id": str(uuid4())},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404
    assert response.json()["detail"]


async def test_get_warehouse_returns_404_for_unknown(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        f"/api/v1/admin/warehouses/{uuid4()}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["detail"]


async def test_list_warehouses_pagination(
    client: AsyncClient, employee_token: str
) -> None:
    for i in range(2):
        await client.post(
            "/api/v1/admin/warehouses",
            json={"address": f"addr-{i}", "brand": "BMW"},
            headers=_auth(employee_token),
        )
    response = await client.get(
        "/api/v1/admin/warehouses?page=1&limit=10",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] >= 2
    assert isinstance(body["warehouses"], list)


async def test_distributor_sees_only_linked_dealer_warehouses(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    distributor = Company(name="Warehouse scope distributor", company_type="distributor")
    linked_dealer = Company(name="Warehouse scope linked", company_type="dealer")
    foreign_dealer = Company(name="Warehouse scope foreign", company_type="dealer")
    db_session.add_all([distributor, linked_dealer, foreign_dealer])
    await db_session.flush()
    db_session.add(
        DistributorDealerLink(
            distributor_company_id=distributor.id,
            dealer_company_id=linked_dealer.id,
        )
    )
    user = User(
        phone="+76669990001",
        email="warehouse-scope-distributor@test.local",
        name="Warehouse scope distributor",
        role="distributor",
        is_active=True,
        company_id=distributor.id,
    )
    db_session.add(user)
    await db_session.flush()
    distributor_token, _ = generate_tokens(user.id, "distributor", distributor.id)

    linked = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "linked warehouse", "brand": "BMW", "company_id": str(linked_dealer.id)},
        headers=_auth(employee_token),
    )
    foreign = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "foreign warehouse", "brand": "BMW", "company_id": str(foreign_dealer.id)},
        headers=_auth(employee_token),
    )
    assert linked.status_code == foreign.status_code == 201
    linked_id = linked.json()["warehouse"]["id"]
    foreign_id = foreign.json()["warehouse"]["id"]

    listing = await client.get("/api/v1/admin/warehouses", headers=_auth(distributor_token))
    assert listing.status_code == 200
    assert {row["id"] for row in listing.json()["warehouses"]} == {linked_id}
    assert listing.json()["pagination"]["total"] == 1

    assert (await client.get(f"/api/v1/admin/warehouses/{linked_id}", headers=_auth(distributor_token))).status_code == 200
    assert (await client.get(f"/api/v1/admin/warehouses/{foreign_id}", headers=_auth(distributor_token))).status_code == 404


async def test_update_warehouse_renames_address(
    client: AsyncClient, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "orig", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]
    response = await client.put(
        f"/api/v1/admin/warehouses/{warehouse_id}",
        json={"address": "renamed"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert response.json()["warehouse"]["address"] == "renamed"


async def test_delete_warehouse_removes(
    client: AsyncClient, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "to-del", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]

    response = await client.delete(
        f"/api/v1/admin/warehouses/{warehouse_id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 204
    assert response.content == b""

    after = await client.get(
        f"/api/v1/admin/warehouses/{warehouse_id}",
        headers=_auth(employee_token),
    )
    assert after.status_code == 404


async def test_delete_warehouse_with_vehicle_dependency_returns_problem_details(
    client: AsyncClient,
    employee_token: str,
    vehicle_with_mark: Vehicle,
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "blocked", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]
    bind = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        json={"vehicle_id": str(vehicle_with_mark.id)},
        headers=_auth(employee_token),
    )
    assert bind.status_code == 201

    response = await client.delete(
        f"/api/v1/admin/warehouses/{warehouse_id}",
        headers=_auth(employee_token),
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 409
    assert body["type"] == "warehouse-has-dependencies"
    assert body["blockingDependencies"] == {
        "special_equipment_links": 0,
        "vehicle_warehouses": 1,
        "transfer_history": 0,
            "exchange_links": 0,
            "import_jobs": 0,
            "storefronts": 0,
        }


async def test_update_warehouse_accepts_inactive_status(
    client: AsyncClient, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "inactive", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]

    response = await client.put(
        f"/api/v1/admin/warehouses/{warehouse_id}",
        json={"status": "inactive"},
        headers=_auth(employee_token),
    )

    assert response.status_code == 200
    assert response.json()["warehouse"]["status"] == "inactive"


# ---------------------------------------------------------------------------
# Vehicle ↔ warehouse bindings
# ---------------------------------------------------------------------------


async def test_add_and_list_warehouse_vehicles(
    client: AsyncClient,
    employee_token: str,
    vehicle_with_mark: Vehicle,
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-bind", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]

    bind = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        json={"vehicle_id": vehicle_with_mark.id},
        headers=_auth(employee_token),
    )
    assert bind.status_code == 201

    listing = await client.get(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        headers=_auth(employee_token),
    )
    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] == 1


async def test_bulk_add_warehouse_vehicles_binds_selected_unbound_vehicles(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    mark_bmw: Mark,
    vehicle_with_mark: Vehicle,
) -> None:
    second_vehicle = Vehicle(
        mark_id=mark_bmw.id,
        vin="ITWHVINBULK000002",
        status="available",
        is_available=True,
    )
    db_session.add(second_vehicle)
    await db_session.flush()

    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-bulk", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]

    response = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles/bulk",
        json={"vehicle_ids": [str(vehicle_with_mark.id), str(second_vehicle.id)]},
        headers=_auth(employee_token),
    )

    assert response.status_code == 201
    assert response.json() == {"bound": 2, "skipped": 0}

    listing = await client.get(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        headers=_auth(employee_token),
    )
    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] == 2


async def test_bulk_add_warehouse_vehicles_skips_vehicle_bound_concurrently(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    mark_bmw: Mark,
    vehicle_with_mark: Vehicle,
) -> None:
    unbound_vehicle = Vehicle(
        mark_id=mark_bmw.id,
        vin="ITWHVINBULK000003",
        status="available",
        is_available=True,
    )
    db_session.add(unbound_vehicle)
    await db_session.flush()

    first = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-first", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    second = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-second", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    first_id = first.json()["warehouse"]["id"]
    second_id = second.json()["warehouse"]["id"]

    bound = await client.post(
        f"/api/v1/admin/warehouses/{first_id}/vehicles",
        json={"vehicle_id": str(vehicle_with_mark.id)},
        headers=_auth(employee_token),
    )
    assert bound.status_code == 201

    response = await client.post(
        f"/api/v1/admin/warehouses/{second_id}/vehicles/bulk",
        json={"vehicle_ids": [str(vehicle_with_mark.id), str(unbound_vehicle.id)]},
        headers=_auth(employee_token),
    )

    assert response.status_code == 201
    assert response.json() == {"bound": 1, "skipped": 1}

    first_listing = await client.get(
        f"/api/v1/admin/warehouses/{first_id}/vehicles",
        headers=_auth(employee_token),
    )
    second_listing = await client.get(
        f"/api/v1/admin/warehouses/{second_id}/vehicles",
        headers=_auth(employee_token),
    )
    assert first_listing.json()["pagination"]["total"] == 1
    assert second_listing.json()["pagination"]["total"] == 1
    assert first_listing.json()["vehicles"][0]["id"] == str(vehicle_with_mark.id)
    assert second_listing.json()["vehicles"][0]["id"] == str(unbound_vehicle.id)


async def test_bulk_add_warehouse_vehicles_rejects_unknown_vehicle_without_binding(
    client: AsyncClient,
    employee_token: str,
    vehicle_with_mark: Vehicle,
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-unknown", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]

    response = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles/bulk",
        json={"vehicle_ids": [str(vehicle_with_mark.id), str(uuid4())]},
        headers=_auth(employee_token),
    )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "не найден" in response.json()["detail"]

    listing = await client.get(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        headers=_auth(employee_token),
    )
    assert listing.json()["pagination"]["total"] == 0


async def test_bulk_add_warehouse_vehicles_rejects_oversized_request(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.post(
        f"/api/v1/admin/warehouses/{uuid4()}/vehicles/bulk",
        json={"vehicle_ids": [str(uuid4()) for _ in range(501)]},
        headers=_auth(employee_token),
    )

    assert response.status_code == 422


async def test_add_vehicle_already_bound_returns_409(
    client: AsyncClient,
    employee_token: str,
    vehicle_with_mark: Vehicle,
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-dup", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]
    await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        json={"vehicle_id": vehicle_with_mark.id},
        headers=_auth(employee_token),
    )
    response = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        json={"vehicle_id": vehicle_with_mark.id},
        headers=_auth(employee_token),
    )
    assert response.status_code == 409


async def test_remove_vehicle_missing_binding_returns_404(
    client: AsyncClient,
    employee_token: str,
    vehicle_with_mark: Vehicle,
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-rem", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]
    response = await client.delete(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles/{vehicle_with_mark.id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_bind_by_mark_attaches_unbound(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    mark_bmw: Mark,
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-mark", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]

    v1 = Vehicle(mark_id=mark_bmw.id, vin="ITBINDMARK1", status="available")
    v2 = Vehicle(mark_id=mark_bmw.id, vin="ITBINDMARK2", status="available")
    db_session.add_all([v1, v2])
    await db_session.flush()

    response = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles/bind-by-mark",
        json={"mark_id": mark_bmw.id},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bound_count"] == 2

    listing = await client.get(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles",
        headers=_auth(employee_token),
    )
    assert listing.json()["pagination"]["total"] == 2


async def test_bind_by_mark_unknown_mark_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/admin/warehouses",
        json={"address": "addr-mark-bad", "brand": "BMW"},
        headers=_auth(employee_token),
    )
    warehouse_id = create.json()["warehouse"]["id"]
    response = await client.post(
        f"/api/v1/admin/warehouses/{warehouse_id}/vehicles/bind-by-mark",
        json={"mark_id": "no_such_mark_at_all"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_warehouse_vehicles_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/admin/warehouses/1/vehicles")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Dealer warehouse scope
# ---------------------------------------------------------------------------


async def test_dealer_reads_only_own_warehouses_and_vehicles(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_company: Company,
    dealer_user: User,
) -> None:
    foreign_company = Company(
        name="Warehouse scope foreign dealer",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(foreign_company)
    await db_session.flush()

    own_company_warehouse = Warehouse(
        address="Dealer own company warehouse",
        brand="BMW",
        company_id=dealer_company.id,
    )
    own_legacy_warehouse = Warehouse(
        address="Dealer own legacy warehouse",
        brand="BMW",
        dealer_id=dealer_company.id,
    )
    foreign_warehouse = Warehouse(
        address="Dealer foreign warehouse",
        brand="Audi",
        company_id=foreign_company.id,
    )
    conflicting_warehouse = Warehouse(
        address="Dealer conflicting warehouse",
        brand="Mercedes-Benz",
        company_id=foreign_company.id,
        dealer_id=dealer_company.id,
    )
    db_session.add_all(
        [
            own_company_warehouse,
            own_legacy_warehouse,
            foreign_warehouse,
            conflicting_warehouse,
        ]
    )
    await db_session.flush()

    own_vehicle = Vehicle(vin="DEALER22130OWN001", status="available")
    foreign_vehicle = Vehicle(vin="DEALER22130OTHER1", status="available")
    db_session.add_all([own_vehicle, foreign_vehicle])
    await db_session.flush()
    db_session.add_all(
        [
            VehicleWarehouse(
                warehouse_id=own_company_warehouse.id,
                vehicle_id=own_vehicle.id,
            ),
            VehicleWarehouse(
                warehouse_id=foreign_warehouse.id,
                vehicle_id=foreign_vehicle.id,
            ),
        ]
    )
    await db_session.flush()

    dealer_token, _ = generate_tokens(
        dealer_user.id, "dealer", dealer_company.id
    )
    headers = _auth(dealer_token)

    listing = await client.get("/api/v1/admin/warehouses", headers=headers)
    assert listing.status_code == 200
    assert {item["id"] for item in listing.json()["warehouses"]} == {
        str(own_company_warehouse.id),
        str(own_legacy_warehouse.id),
    }
    assert listing.json()["pagination"]["total"] == 2

    brands = await client.get(
        "/api/v1/admin/warehouses/brands", headers=headers
    )
    assert brands.status_code == 200
    assert brands.json() == {"brands": ["BMW"]}

    for warehouse in (own_company_warehouse, own_legacy_warehouse):
        detail = await client.get(
            f"/api/v1/admin/warehouses/{warehouse.id}", headers=headers
        )
        assert detail.status_code == 200

    vehicles = await client.get(
        f"/api/v1/admin/warehouses/{own_company_warehouse.id}/vehicles",
        headers=headers,
    )
    assert vehicles.status_code == 200
    assert [item["id"] for item in vehicles.json()["vehicles"]] == [
        str(own_vehicle.id)
    ]

    for warehouse in (foreign_warehouse, conflicting_warehouse):
        detail = await client.get(
            f"/api/v1/admin/warehouses/{warehouse.id}", headers=headers
        )
        warehouse_vehicles = await client.get(
            f"/api/v1/admin/warehouses/{warehouse.id}/vehicles",
            headers=headers,
        )
        assert detail.status_code == 404
        assert warehouse_vehicles.status_code == 404

    missing_id = uuid4()
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{missing_id}", headers=headers
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{missing_id}/vehicles", headers=headers
        )
    ).status_code == 404


async def test_dealer_can_read_warehouse_filter_references(
    client: AsyncClient,
    dealer_company: Company,
    dealer_user: User,
) -> None:
    dealer_token, _ = generate_tokens(
        dealer_user.id, "dealer", dealer_company.id
    )
    headers = _auth(dealer_token)

    assert (
        await client.get("/api/v1/admin/warehouses/brands", headers=headers)
    ).status_code == 200
    assert (
        await client.get("/api/v1/admin/cities", headers=headers)
    ).status_code == 200


async def test_dealer_without_company_has_empty_warehouse_scope(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    dealer_user = User(
        phone="+766600022130",
        email="warehouse-scope-dealer-no-company@test.local",
        name="Warehouse dealer without company",
        role="dealer",
        is_active=True,
    )
    existing_warehouse = Warehouse(
        address="Warehouse hidden from dealer without company",
        brand="BMW",
    )
    db_session.add_all([dealer_user, existing_warehouse])
    await db_session.flush()

    dealer_token, _ = generate_tokens(dealer_user.id, "dealer", None)
    headers = _auth(dealer_token)

    listing = await client.get("/api/v1/admin/warehouses", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["warehouses"] == []
    assert listing.json()["pagination"]["total"] == 0
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{existing_warehouse.id}",
            headers=headers,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{existing_warehouse.id}/vehicles",
            headers=headers,
        )
    ).status_code == 404


@pytest.mark.parametrize(
    ("method", "request_path", "payload"),
    [
        (
            "post",
            "/api/v1/admin/warehouses",
            {"address": "Forbidden", "brand": "BMW"},
        ),
        ("post", "/api/v1/admin/cities", {"name": "Forbidden"}),
        ("put", f"/api/v1/admin/warehouses/{uuid4()}", {"address": "x"}),
        ("delete", f"/api/v1/admin/warehouses/{uuid4()}", None),
        (
            "post",
            f"/api/v1/admin/warehouses/{uuid4()}/vehicles",
            {"vehicle_id": str(uuid4())},
        ),
        (
            "post",
            f"/api/v1/admin/warehouses/{uuid4()}/vehicles/bulk",
            {"vehicle_ids": [str(uuid4())]},
        ),
        (
            "post",
            f"/api/v1/admin/warehouses/{uuid4()}/vehicles/bind-by-mark",
            {"mark_id": "bmw"},
        ),
        (
            "delete",
            f"/api/v1/admin/warehouses/{uuid4()}/vehicles/{uuid4()}",
            None,
        ),
    ],
)
async def test_dealer_cannot_mutate_warehouses(
    client: AsyncClient,
    dealer_company: Company,
    dealer_user: User,
    method: str,
    request_path: str,
    payload: dict[str, object] | None,
) -> None:
    dealer_token, _ = generate_tokens(
        dealer_user.id, "dealer", dealer_company.id
    )
    response = await client.request(
        method,
        request_path,
        json=payload,
        headers=_auth(dealer_token),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Distributor warehouse scope
# ---------------------------------------------------------------------------


async def test_distributor_sees_only_linked_warehouses_by_effective_owner(  # noqa: PLR0915
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    distributor_one = Company(
        name="Warehouse scope distributor one",
        company_type="distributor",
        is_active=True,
    )
    distributor_two = Company(
        name="Warehouse scope distributor two",
        company_type="distributor",
        is_active=True,
    )
    dealer_one = Company(
        name="Warehouse scope dealer one",
        company_type="dealer",
        is_active=True,
    )
    dealer_two = Company(
        name="Warehouse scope dealer two",
        company_type="dealer",
        is_active=True,
    )
    db_session.add_all(
        [distributor_one, distributor_two, dealer_one, dealer_two]
    )
    await db_session.flush()

    distributor_user = User(
        phone="+766600022054",
        email="warehouse-scope-distributor@test.local",
        name="Warehouse scope distributor",
        role="distributor",
        company_id=distributor_one.id,
        is_active=True,
    )
    db_session.add_all(
        [
            distributor_user,
            DistributorDealerLink(
                distributor_company_id=distributor_one.id,
                dealer_company_id=dealer_one.id,
            ),
            DistributorDealerLink(
                distributor_company_id=distributor_two.id,
                dealer_company_id=dealer_two.id,
            ),
        ]
    )
    await db_session.flush()

    linked_company_warehouse = Warehouse(
        address="Scope linked company",
        brand="BMW",
        company_id=dealer_one.id,
    )
    linked_legacy_warehouse = Warehouse(
        address="Scope linked legacy",
        brand="BMW",
        dealer_id=dealer_one.id,
    )
    foreign_warehouse = Warehouse(
        address="Scope foreign",
        brand="BMW",
        company_id=dealer_two.id,
    )
    ownerless_warehouse = Warehouse(address="Scope ownerless", brand="BMW")
    conflicting_warehouse = Warehouse(
        address="Scope conflict",
        brand="BMW",
        company_id=dealer_two.id,
        dealer_id=dealer_one.id,
    )
    db_session.add_all(
        [
            linked_company_warehouse,
            linked_legacy_warehouse,
            foreign_warehouse,
            ownerless_warehouse,
            conflicting_warehouse,
        ]
    )
    await db_session.flush()

    linked_vehicle = Vehicle(vin="SCOPE22054LINKED", status="available")
    foreign_vehicle = Vehicle(vin="SCOPE22054FOREIGN", status="available")
    db_session.add_all([linked_vehicle, foreign_vehicle])
    await db_session.flush()
    db_session.add_all(
        [
            VehicleWarehouse(
                warehouse_id=linked_company_warehouse.id,
                vehicle_id=linked_vehicle.id,
            ),
            VehicleWarehouse(
                warehouse_id=foreign_warehouse.id,
                vehicle_id=foreign_vehicle.id,
            ),
        ]
    )
    await db_session.flush()

    distributor_token, _ = generate_tokens(
        distributor_user.id, "distributor", distributor_one.id
    )
    headers = _auth(distributor_token)

    listing = await client.get("/api/v1/admin/warehouses", headers=headers)
    assert listing.status_code == 200
    listing_body = listing.json()
    assert {item["id"] for item in listing_body["warehouses"]} == {
        str(linked_company_warehouse.id),
        str(linked_legacy_warehouse.id),
    }
    assert listing_body["pagination"]["total"] == 2

    for warehouse in (linked_company_warehouse, linked_legacy_warehouse):
        detail = await client.get(
            f"/api/v1/admin/warehouses/{warehouse.id}", headers=headers
        )
        assert detail.status_code == 200

    own_vehicles = await client.get(
        f"/api/v1/admin/warehouses/{linked_company_warehouse.id}/vehicles",
        headers=headers,
    )
    assert own_vehicles.status_code == 200
    assert [vehicle["id"] for vehicle in own_vehicles.json()["vehicles"]] == [
        str(linked_vehicle.id)
    ]

    for warehouse in (
        foreign_warehouse,
        ownerless_warehouse,
        conflicting_warehouse,
    ):
        detail = await client.get(
            f"/api/v1/admin/warehouses/{warehouse.id}", headers=headers
        )
        vehicles = await client.get(
            f"/api/v1/admin/warehouses/{warehouse.id}/vehicles", headers=headers
        )
        assert detail.status_code == 404
        assert vehicles.status_code == 404
        assert "warehouse" not in detail.json()
        assert "vehicles" not in vehicles.json()

    missing_id = uuid4()
    missing_detail = await client.get(
        f"/api/v1/admin/warehouses/{missing_id}", headers=headers
    )
    missing_vehicles = await client.get(
        f"/api/v1/admin/warehouses/{missing_id}/vehicles", headers=headers
    )
    assert missing_detail.status_code == 404
    assert missing_vehicles.status_code == 404
    assert "warehouse" not in missing_detail.json()
    assert "vehicles" not in missing_vehicles.json()

    employee_listing = await client.get(
        "/api/v1/admin/warehouses", headers=_auth(employee_token)
    )
    employee_ids = {item["id"] for item in employee_listing.json()["warehouses"]}
    assert {
        str(linked_company_warehouse.id),
        str(linked_legacy_warehouse.id),
        str(foreign_warehouse.id),
        str(ownerless_warehouse.id),
        str(conflicting_warehouse.id),
    } <= employee_ids
    employee_vehicles = await client.get(
        f"/api/v1/admin/warehouses/{foreign_warehouse.id}/vehicles",
        headers=_auth(employee_token),
    )
    assert employee_vehicles.status_code == 200
    assert [vehicle["id"] for vehicle in employee_vehicles.json()["vehicles"]] == [
        str(foreign_vehicle.id)
    ]


async def test_distributor_without_linked_dealers_has_empty_warehouse_scope(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    distributor_company = Company(
        name="Warehouse scope unlinked distributor",
        company_type="distributor",
        is_active=True,
    )
    distributor_user = User(
        phone="+766600022055",
        email="warehouse-scope-unlinked@test.local",
        name="Warehouse scope unlinked",
        role="distributor",
        company_id=distributor_company.id,
        is_active=True,
    )
    visible_to_someone_else = Warehouse(
        address="Scope exists but unlinked",
        brand="BMW",
    )
    db_session.add_all(
        [distributor_company, distributor_user, visible_to_someone_else]
    )
    await db_session.flush()

    distributor_token, _ = generate_tokens(
        distributor_user.id, "distributor", distributor_company.id
    )
    headers = _auth(distributor_token)

    listing = await client.get("/api/v1/admin/warehouses", headers=headers)
    assert listing.status_code == 200
    assert listing.json() == {
        "warehouses": [],
        "pagination": {"page": 1, "limit": 20, "total": 0, "pages": 0},
    }
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{visible_to_someone_else.id}",
            headers=headers,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{visible_to_someone_else.id}/vehicles",
            headers=headers,
        )
    ).status_code == 404


async def test_distributor_without_company_has_empty_warehouse_scope(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    distributor_user = User(
        phone="+766600022056",
        email="warehouse-scope-no-company@test.local",
        name="Warehouse scope without company",
        role="distributor",
        is_active=True,
    )
    existing_warehouse = Warehouse(
        address="Scope exists without distributor company",
        brand="BMW",
    )
    db_session.add_all([distributor_user, existing_warehouse])
    await db_session.flush()

    distributor_token, _ = generate_tokens(
        distributor_user.id, "distributor", None
    )
    headers = _auth(distributor_token)

    listing = await client.get("/api/v1/admin/warehouses", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["warehouses"] == []
    assert listing.json()["pagination"]["total"] == 0
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{existing_warehouse.id}",
            headers=headers,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/admin/warehouses/{existing_warehouse.id}/vehicles",
            headers=headers,
        )
    ).status_code == 404


async def test_warehouses_pagination_limit_500(
    client: AsyncClient,
    employee_token: str,
) -> None:
    headers = _auth(employee_token)
    response = await client.get("/api/v1/admin/warehouses?limit=500", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "warehouses" in data
    assert data["pagination"]["limit"] == 500


async def test_warehouse_access_rules_endpoints_and_aliases(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    dealer_company: Company,
) -> None:
    headers = _auth(employee_token)

    # 1. Verify GET on both paths with limit=500
    res_canonical = await client.get(
        "/api/v1/admin/warehouses/access-rules?page=1&limit=500",
        headers=headers,
    )
    assert res_canonical.status_code == 200
    data_canonical = res_canonical.json()
    assert "rules" in data_canonical
    assert data_canonical["pagination"]["limit"] == 500

    res_alias = await client.get(
        "/api/v1/admin/warehouse-access-rules?page=1&limit=500",
        headers=headers,
    )
    assert res_alias.status_code == 200
    data_alias = res_alias.json()
    assert "rules" in data_alias
    assert data_alias["pagination"]["limit"] == 500

    # 2. Create a warehouse
    create_wh_res = await client.post(
        "/api/v1/admin/warehouses",
        json={
            "name": "Warehouse For Access Rules Test",
            "owner_company_id": str(dealer_company.id),
            "address": "Тестовый адрес 123",
        },
        headers=headers,
    )
    assert create_wh_res.status_code == 201
    wh_id = create_wh_res.json()["warehouse"]["id"]

    # 3. Create another dealer company to grant access
    grantee = Company(name="Grantee Dealer Company", company_type="dealer", is_active=True)
    db_session.add(grantee)
    await db_session.flush()

    # 4. POST via alias /api/v1/admin/warehouse-access-rules
    post_res = await client.post(
        "/api/v1/admin/warehouse-access-rules",
        json={
            "warehouse_id": wh_id,
            "mode": "dealers",
            "dealers": [{"dealer_id": str(grantee.id), "access_type": "B"}],
        },
        headers=headers,
    )
    assert post_res.status_code == 201
    rules = post_res.json()["rules"]
    assert len(rules) >= 1
    grantee_rule = next(r for r in rules if r["target_id"] == str(grantee.id))
    rule_id = grantee_rule["id"]

    # 5. PUT update via alias /api/v1/admin/warehouse-access-rules/{rule_id}
    put_res = await client.put(
        f"/api/v1/admin/warehouse-access-rules/{rule_id}",
        json={"warehouse_access_type": "C", "is_active": True},
        headers=headers,
    )
    assert put_res.status_code == 200
    assert put_res.json()["rule"]["warehouse_access_type"] == "C"

    # 6. PATCH update via canonical /api/v1/admin/warehouses/access-rules/{rule_id}
    patch_res = await client.patch(
        f"/api/v1/admin/warehouses/access-rules/{rule_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["rule"]["is_active"] is False

    # 7. DELETE via alias /api/v1/admin/warehouse-access-rules/{rule_id}
    del_res = await client.delete(
        f"/api/v1/admin/warehouse-access-rules/{rule_id}",
        headers=headers,
    )
    assert del_res.status_code == 204


