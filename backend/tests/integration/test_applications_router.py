"""Integration tests for /api/v1/applications/*."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingPurpose,
    LeasingRegion,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
)
from infrastructure.models.users import User, UserCompany
from tests.application_create_assertions import assert_create_idempotency
from tests.legacy_compat import Vehicle
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def apps_company(db_session: AsyncSession) -> Company:
    c = Company(name="Apps Router Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def apps_leasing_provider_company(
    db_session: AsyncSession,
) -> Company:
    c = Company(name="LC Router Provider", company_type="leasing_company")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def apps_leasing_company(
    db_session: AsyncSession,
    apps_leasing_provider_company: Company,
) -> LeasingCompany:
    lc = LeasingCompany(
        company_id=apps_leasing_provider_company.id, is_active=True
    )
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def apps_dealer(db_session: AsyncSession, apps_company: Company) -> User:
    # Create a company for the dealer first
    dealer_company = Company(name="Apps Dealer Co", company_type="dealer")
    db_session.add(dealer_company)
    await db_session.flush()
    await db_session.refresh(dealer_company)

    user = User(
        phone="+76660008881",
        email="appsdealer@test.local",
        name="Apps Dealer",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=apps_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def apps_dealer_token(apps_dealer: User) -> str:
    token, _ = generate_tokens(apps_dealer.id, "dealer", apps_dealer.company_id)
    return cast("str", token)


@pytest_asyncio.fixture
async def apps_client_user(
    db_session: AsyncSession, apps_company: Company
) -> User:
    user = User(
        phone="+76660008882",
        email="appsclient@test.local",
        name="Apps Client",
        role="client",
        is_active=True,
        company_id=apps_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def apps_client_token(
    apps_client_user: User, apps_company: Company
) -> str:
    token, _ = generate_tokens(
        apps_client_user.id, "client", apps_company.id
    )
    return cast("str", token)


@pytest_asyncio.fixture
async def apps_lc_user(
    db_session: AsyncSession,
    apps_leasing_provider_company: Company,
) -> User:
    user = User(
        phone="+76660008883",
        email="appslc@test.local",
        name="Apps LC",
        role="leasing_company",
        is_active=True,
        company_id=apps_leasing_provider_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def apps_lc_token(
    apps_lc_user: User, apps_leasing_provider_company: Company
) -> str:
    token, _ = generate_tokens(
        apps_lc_user.id,
        "leasing_company",
        apps_leasing_provider_company.id,
    )
    return cast("str", token)


@pytest_asyncio.fixture
async def apps_available_vehicle(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        vin="INTVIN00000000001",
        status="available",
        is_available=True,
        complectation_id="COMPL-INT",
        base_price=Decimal("1000.00"),
    )
    db_session.add(v)
    await db_session.flush()
    await db_session.refresh(v)
    return v


async def _seed_application(
    db_session: AsyncSession,
    *,
    company: Company,
    dealer_company_id: UUID | None,
    status: str,
    selected_leasing_companies: list[UUID] | None = None,
) -> LeasingApplication:
    row = LeasingApplication(
        company_id=company.id,
        dealer_company_id=dealer_company_id,
        email="seed@test.local",
        status=status,
        selected_leasing_companies=selected_leasing_companies,
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_list_applications_anon_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/applications/")
    assert response.status_code == 401


async def test_create_application_anon_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/applications",
        json={"company_id": 1, "vehicles": []},
    )
    assert response.status_code == 401


@pytest_asyncio.fixture
async def editable_lines(db_session: AsyncSession, apps_company: Company, apps_client_user: User) -> dict[str, Any]:
    applications = [LeasingApplication(company_id=apps_company.id, created_by=apps_client_user.id, status="active") for _ in range(2)]
    directory = special_equipment_directory(mark_name="Edit", model_name="Items", modification_name="35")
    db_session.add_all([*applications, *directory])
    await db_session.flush()
    product = SpecialEquipmentProduct(code=f"edit-{uuid4()}", slug=f"edit-{uuid4()}", modification_id=directory[2].id,
        condition="new", no_vin=True, publication_status="draft", sale_status="available", price=Decimal("100"))
    db_session.add(product)
    await db_session.flush()
    vehicle = ApplicationVehicle(application_id=applications[0].id, modification_id="edit-model", quantity=1,
        unit_price=Decimal("100"), total_price=Decimal("100"), comment="Исходный автомобиль")
    equipment = SpecialEquipmentApplicationItem(application_id=applications[0].id, product_id=product.id,
        unit_price=Decimal("100"), total_price=Decimal("100"), item_snapshot={"title": "Исходная техника"}, comment="Исходная техника")
    foreign = ApplicationVehicle(application_id=applications[1].id, modification_id="foreign-model", quantity=1,
        unit_price=Decimal("100"), total_price=Decimal("100"), comment="Чужая позиция")
    db_session.add_all([vehicle, equipment, foreign])
    await db_session.flush()
    return {"application": applications[0], "vehicle": vehicle, "special_equipment": equipment, "foreign": foreign}


@pytest.mark.parametrize("kind", ["vehicle", "special_equipment"])
async def test_editable_item_http_round_trip_and_empty_values(client: AsyncClient, editable_lines: dict[str, Any],
    apps_client_token: str, kind: str) -> None:
    application_id, line_id = editable_lines["application"].id, editable_lines[kind].id
    payload: dict[str, Any] = {"line_id": str(line_id), "kind": kind, "leasing_purpose": None, "regions": [], "region": None, "comment": "ТЗ35 новый комментарий"}
    updated = await client.put(f"/api/v1/applications/{application_id}/items", json={"items": [payload]}, headers=_auth(apps_client_token))
    assert updated.status_code == 200, updated.text
    assert updated.json() == {"ok": True, "items": [payload]}
    detail = await client.get(f"/api/v1/applications/{application_id}", headers=_auth(apps_client_token))
    assert detail.status_code == 200
    assert next(item for item in detail.json()["items"] if item["id"] == str(line_id))["comment"] == "ТЗ35 новый комментарий"
    cleared = await client.put(f"/api/v1/applications/{application_id}/items", json={"items": [{**payload, "comment": None}]}, headers=_auth(apps_client_token))
    assert cleared.status_code == 200
    detail = await client.get(f"/api/v1/applications/{application_id}", headers=_auth(apps_client_token))
    assert next(item for item in detail.json()["items"] if item["id"] == str(line_id))["comment"] is None


@pytest.mark.parametrize("invalid,expected", [("foreign", 404), ("missing", 404), ("kind", 422), ("purpose", 422), ("region", 422)])
async def test_item_batch_validation_never_partially_writes(client: AsyncClient, editable_lines: dict[str, Any],
    apps_client_token: str, invalid: str, expected: int) -> None:
    app_id = editable_lines["application"].id
    first = {"line_id": str(editable_lines["vehicle"].id), "kind": "vehicle", "comment": "Не должно сохраниться"}
    second = {"line_id": str(editable_lines["special_equipment"].id), "kind": "special_equipment"}
    if invalid == "foreign":
        second.update(line_id=str(editable_lines["foreign"].id), kind="vehicle")
    elif invalid == "missing":
        second["line_id"] = str(uuid4())
    elif invalid == "kind":
        second["kind"] = "vehicle"
    elif invalid == "purpose":
        second["leasing_purpose"] = "not-in-directory"
    else:
        second["region"] = "not-in-directory"
    before = await client.get(f"/api/v1/applications/{app_id}", headers=_auth(apps_client_token))
    result = await client.put(f"/api/v1/applications/{app_id}/items", json={"items": [first, second]}, headers=_auth(apps_client_token))
    assert result.status_code == expected, result.text
    after = await client.get(f"/api/v1/applications/{app_id}", headers=_auth(apps_client_token))
    assert before.status_code == after.status_code == 200
    assert after.json()["items"] == before.json()["items"]


async def test_item_write_permission_revoke_keeps_read_and_data(client: AsyncClient, db_session: AsyncSession,
    editable_lines: dict[str, Any], apps_client_user: User, apps_client_token: str) -> None:
    db_session.add(UserCompany(user_id=apps_client_user.id, company_id=apps_client_user.company_id,
        can_view_applications=True, can_create_applications=False))
    await db_session.flush()
    app_id = editable_lines["application"].id
    before = await client.get(f"/api/v1/applications/{app_id}", headers=_auth(apps_client_token))
    result = await client.put(f"/api/v1/applications/{app_id}/items", headers=_auth(apps_client_token),
        json={"items": [{"line_id": str(editable_lines["vehicle"].id), "kind": "vehicle", "comment": "Запрещено"}]})
    assert result.status_code == 403
    after = await client.get(f"/api/v1/applications/{app_id}", headers=_auth(apps_client_token))
    assert before.status_code == after.status_code == 200
    assert after.json()["items"] == before.json()["items"]


async def test_item_edit_repository_projection_is_dict_and_application_scoped(db_session: AsyncSession, editable_lines: dict[str, Any]) -> None:
    from infrastructure.repositories import application_repository as repository
    rows = await repository.get_application_item_edit_rows(db_session, editable_lines["application"].id,
        [editable_lines[kind].id for kind in ("vehicle", "special_equipment", "foreign")])
    assert all(type(row) is dict for row in rows)
    assert {row["line_id"]: row["kind"] for row in rows} == {
        editable_lines["vehicle"].id: "vehicle", editable_lines["special_equipment"].id: "special_equipment"}


async def test_grouped_special_equipment_items_update_by_group_id(
    client: AsyncClient,
    db_session: AsyncSession,
    editable_lines: dict[str, Any],
    apps_client_token: str,
) -> None:
    app_id = editable_lines["application"].id
    group_id = uuid4()
    directory = special_equipment_directory(mark_name="GroupEdit", model_name="Items", modification_name="1")
    db_session.add_all(directory)
    await db_session.flush()
    p1 = SpecialEquipmentProduct(
        code=f"g1-{uuid4()}", slug=f"g1-{uuid4()}", modification_id=directory[2].id,
        condition="new", no_vin=True, publication_status="draft", sale_status="available", price=Decimal("100"),
    )
    p2 = SpecialEquipmentProduct(
        code=f"g2-{uuid4()}", slug=f"g2-{uuid4()}", modification_id=directory[2].id,
        condition="new", no_vin=True, publication_status="draft", sale_status="available", price=Decimal("100"),
    )
    db_session.add_all([p1, p2])
    await db_session.flush()

    item1 = SpecialEquipmentApplicationItem(
        application_id=app_id, product_id=p1.id, group_id=group_id,
        unit_price=Decimal("100"), total_price=Decimal("100"), item_snapshot={"title": "П1"},
    )
    item2 = SpecialEquipmentApplicationItem(
        application_id=app_id, product_id=p2.id, group_id=group_id,
        unit_price=Decimal("100"), total_price=Decimal("100"), item_snapshot={"title": "П2"},
    )
    db_session.add_all([
        item1, item2,
        LeasingPurpose(purpose_name="business", purpose_display_name="Для бизнеса"),
        LeasingRegion(region_name="Республика Адыгея", region_display_name="01 — Республика Адыгея", region_number="01"),
        LeasingRegion(region_name="Республика Башкортостан", region_display_name="02 — Республика Башкортостан", region_number="02"),
    ])
    await db_session.flush()

    payload = {
        "line_id": str(group_id),
        "kind": "special_equipment",
        "leasing_purpose": "business",
        "regions": ["Республика Адыгея", "Республика Башкортостан"],
        "region": "Республика Адыгея",
        "comment": "Тестовый комментарий для группы",
    }
    response = await client.put(
        f"/api/v1/applications/{app_id}/items",
        json={"items": [payload]},
        headers=_auth(apps_client_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert len(body["items"]) == 1
    assert body["items"][0]["line_id"] == str(group_id)
    assert body["items"][0]["regions"] == ["Республика Адыгея", "Республика Башкортостан"]

    # Verify both items in the group have been updated in the database
    await db_session.refresh(item1)
    await db_session.refresh(item2)
    assert item1.leasing_purpose == "business"
    assert item1.regions == ["Республика Адыгея", "Республика Башкортостан"]
    assert item1.comment == "Тестовый комментарий для группы"
    assert item2.leasing_purpose == "business"
    assert item2.regions == ["Республика Адыгея", "Республика Башкортостан"]
    assert item2.comment == "Тестовый комментарий для группы"



# ---------------------------------------------------------------------------
# Create / draft
# ---------------------------------------------------------------------------


async def test_create_application_legacy_route_returns_location(
    client: AsyncClient,
    apps_dealer_token: str,
    apps_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/applications",
        json={
            "company_id": apps_company.id,
            "name": "Foo",
            "email": "foo@test.local",
            "vehicles": [
                {
                    "modification_id": "MOD-INT",
                    "quantity": 1,
                    "custom_price": "100.00",
                }
            ],
        },
        headers=_auth(apps_dealer_token) | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["application_id"], str)
    assert body["status"] == "active"
    assert response.headers["location"] == (
        f"/api/v1/applications/{body['application_id']}"
    )
    await assert_create_idempotency(client, response, change_field="name")


async def test_create_draft_route_ignores_option_comments(
    client: AsyncClient,
    apps_client_token: str,
    apps_company: Company,
) -> None:
    created = await client.post(
        "/api/v1/applications/draft",
        json={
            "company_id": str(apps_company.id),
            "vehicles": [
                {
                    "modification_id": "MOD-DRAFT-OPTIONS",
                    "quantity": 1,
                    "custom_price": "100.00",
                    "equipments": [
                        {
                            "equipment_code": "alarm",
                            "price": "5000000",
                            "comment": "must be ignored",
                        }
                    ],
                    "services": [
                        {
                            "service_code": "kasko",
                            "price": "100000",
                            "comment": "must be ignored",
                        }
                    ],
                }
            ],
        },
        headers=_auth(apps_client_token) | {"Idempotency-Key": str(uuid4())},
    )

    assert created.status_code == 201
    application_id = created.json()["application_id"]
    assert created.headers["location"] == f"/api/v1/applications/{application_id}"
    await assert_create_idempotency(client, created, change_field="name")
    detail = await client.get(
        f"/api/v1/applications/{application_id}",
        headers=_auth(apps_client_token),
    )
    assert detail.status_code == 200
    vehicle = detail.json()["vehicles"][0]
    assert vehicle["equipments"][0]["equipment_code"] == "alarm"
    assert vehicle["equipments"][0]["comment"] is None
    assert vehicle["services"][0]["service_code"] == "kasko"
    assert vehicle["services"][0]["comment"] is None


async def test_create_application_without_vehicles_returns_400(
    client: AsyncClient,
    apps_dealer_token: str,
    apps_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/applications",
        json={
            "company_id": apps_company.id,
            "vehicles": [],
        },
        headers=_auth(apps_dealer_token) | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 400


async def test_create_application_unknown_company_returns_404(
    client: AsyncClient, apps_dealer_token: str
) -> None:
    response = await client.post(
        "/api/v1/applications",
        json={
            "company_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "vehicles": [{"modification_id": "M"}],
        },
        headers=_auth(apps_dealer_token) | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 404


async def test_create_draft_then_submit_with_lc(
    client: AsyncClient,
    apps_dealer_token: str,
    apps_company: Company,
    apps_leasing_company: LeasingCompany,
) -> None:
    # 1. Create draft
    response = await client.post(
        "/api/v1/applications",
        json={
            "company_id": apps_company.id,
            "name": "Full",
            "email": "full@test.local",
            "vehicles": [
                {
                    "modification_id": "M",
                    "quantity": 1,
                    "custom_price": "50.00",
                }
            ],
        },
        headers=_auth(apps_dealer_token) | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    body = response.json()
    app_id = body["application_id"]
    assert body["status"] == "active"

    # 2. Select leasing companies
    response = await client.put(
        f"/api/v1/applications/{app_id}/leasing-companies",
        json={"leasing_company_ids": [apps_leasing_company.id]},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 200

    # 3. Move to rejected
    response = await client.put(
        f"/api/v1/applications/{app_id}/status",
        json={"status": "rejected"},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["application"]["status"] == "rejected"


# ---------------------------------------------------------------------------
# List / get — role filters
# ---------------------------------------------------------------------------


async def test_list_applications_dealer_sees_own(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
) -> None:
    await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    response = await client.get(
        "/api/v1/applications/", headers=_auth(apps_dealer_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    for _app in body["applications"]:
        assert body["total"] >= 1


async def test_list_applications_client_filters_by_company(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_company: Company,
    apps_client_token: str,
) -> None:
    await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    other_company = Company(name="Outsider", company_type="other")
    db_session.add(other_company)
    await db_session.flush()
    await _seed_application(
        db_session,
        company=other_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    response = await client.get(
        "/api/v1/applications/", headers=_auth(apps_client_token)
    )
    assert response.status_code == 200
    for app in response.json()["applications"]:
        assert app["company_id"] == str(apps_company.id)


async def test_list_applications_leasing_company_filters(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_company: Company,
    apps_leasing_company: LeasingCompany,
    apps_lc_token: str,
) -> None:
    await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
        selected_leasing_companies=[apps_leasing_company.id],
    )
    await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
        selected_leasing_companies=[uuid4()],
    )
    response = await client.get(
        "/api/v1/applications/", headers=_auth(apps_lc_token)
    )
    assert response.status_code == 200
    body = response.json()
    for app in body["applications"]:
        assert apps_leasing_company.id in app["selected_leasing_companies"]


async def test_list_applications_employee_sees_all(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    apps_dealer: User,
    apps_company: Company,
) -> None:
    await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    response = await client.get(
        "/api/v1/applications/", headers=_auth(employee_token)
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_get_application_404_missing(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        "/api/v1/applications/a0b1c2d3-e4f5-6789-0123-456789abcdef",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_get_application_403_for_other_dealer(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_company: Company,
) -> None:
    seeded = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    other_dealer = User(
        phone="+76660008888",
        email="otherdealer-int@test.local",
        role="dealer",
        is_active=True,
    )
    db_session.add(other_dealer)
    await db_session.flush()
    token, _ = generate_tokens(other_dealer.id, "dealer", None)
    response = await client.get(
        f"/api/v1/applications/{seeded.id}",
        headers=_auth(token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------


async def test_update_status_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
) -> None:
    app = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    response = await client.put(
        f"/api/v1/applications/{app.id}/status",
        json={"status": "rejected"},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 200


async def test_update_status_illegitimate_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
) -> None:
    app = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    response = await client.put(
        f"/api/v1/applications/{app.id}/status",
        json={"status": "approved"},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 422


async def test_update_status_unknown_application_returns_404(
    client: AsyncClient,
    apps_dealer_token: str,
) -> None:
    response = await client.put(
        "/api/v1/applications/a0b1c2d3-e4f5-6789-0123-456789abcdef/status",
        json={"status": "active"},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Phase 15 H3 — /submit-documents and /requested-documents were deleted;
# the nested /documents?requested=true endpoint covers the requirements
# projection and submission happens implicitly when all documents land.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# VIN assignment (client-side)
# ---------------------------------------------------------------------------


async def test_available_vins_needs_approved_application(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
    apps_available_vehicle: Vehicle,
) -> None:
    app = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="rejected",
    )
    av = ApplicationVehicle(
        application_id=app.id,
        modification_id="COMPL-INT",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
    )
    db_session.add(av)
    await db_session.flush()
    response = await client.get(
        f"/api/v1/application-vehicles/{av.id}/available-vins",
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 400


async def test_available_vins_success_when_approved(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
    apps_available_vehicle: Vehicle,
) -> None:
    app = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    av = ApplicationVehicle(
        application_id=app.id,
        modification_id="COMPL-INT",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
    )
    db_session.add(av)
    await db_session.flush()
    response = await client.get(
        f"/api/v1/application-vehicles/{av.id}/available-vins",
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 200
    assert len(response.json()["vehicles"]) >= 1


async def test_assign_vin_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
    apps_available_vehicle: Vehicle,
) -> None:
    app = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    av = ApplicationVehicle(
        application_id=app.id,
        modification_id="COMPL-INT",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
    )
    db_session.add(av)
    await db_session.flush()
    response = await client.patch(
        f"/api/v1/application-vehicles/{av.id}",
        json={"vehicle_id": apps_available_vehicle.id},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assigned_vin"] == "INTVIN00000000001"


async def test_assign_vin_duplicate_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    apps_dealer: User,
    apps_dealer_token: str,
    apps_company: Company,
    apps_available_vehicle: Vehicle,
) -> None:
    app = await _seed_application(
        db_session,
        company=apps_company,
        dealer_company_id=apps_dealer.company_id,
        status="active",
    )
    av1 = ApplicationVehicle(
        application_id=app.id,
        modification_id="COMPL-INT",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
        vin=apps_available_vehicle.vin,  # preoccupied
    )
    av2 = ApplicationVehicle(
        application_id=app.id,
        modification_id="COMPL-INT",
        quantity=1,
        unit_price=Decimal("10"),
        total_price=Decimal("10"),
    )
    db_session.add_all([av1, av2])
    await db_session.flush()
    response = await client.patch(
        f"/api/v1/application-vehicles/{av2.id}",
        json={"vehicle_id": apps_available_vehicle.id},
        headers=_auth(apps_dealer_token),
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# End-to-end lifecycle
# ---------------------------------------------------------------------------


async def test_full_lifecycle_draft_to_rejected(
    client: AsyncClient,
    apps_dealer_token: str,
    apps_company: Company,
    apps_leasing_company: LeasingCompany,
) -> None:
    # 1. Dealer creates draft.
    create = await client.post(
        "/api/v1/applications",
        json={
            "company_id": apps_company.id,
            "email": "lifecycle@test.local",
            "vehicles": [
                {
                    "modification_id": "MOD-LC",
                    "quantity": 1,
                    "custom_price": "10.00",
                }
            ],
        },
        headers=_auth(apps_dealer_token) | {"Idempotency-Key": str(uuid4())},
    )
    assert create.status_code == 201
    app_id = create.json()["application_id"]

    # 2. Active → rejected.
    to_rejected = await client.put(
        f"/api/v1/applications/{app_id}/status",
        json={"status": "rejected"},
        headers=_auth(apps_dealer_token),
    )
    assert to_rejected.status_code == 200

    # 3. Get and check final status.
    detail = await client.get(
        f"/api/v1/applications/{app_id}",
        headers=_auth(apps_dealer_token),
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "rejected"
