"""Integration tests for /api/v1/admin/support-programs and /api/v1/admin/dealer-groups."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.companies import (
    Company,
    Distributor,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.users import User
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage
from tests.legacy_compat import Mark

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    csrf = "test-csrf-token"
    return {
        "Authorization": f"Bearer {token}",
        "Cookie": f"accessToken={token}; csrfToken={csrf}",
        "X-CSRF-Token": csrf,
    }


@pytest.fixture(autouse=True)
def _fake_storage() -> Iterator[FakeObjectStorage]:
    fake = FakeObjectStorage()
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


@pytest_asyncio.fixture
async def mark_bmw(db_session: AsyncSession) -> Mark:
    mark = Mark(id="bmw", name="BMW", cyrillic_name="БМВ")
    db_session.add(mark)
    await db_session.flush()
    return mark


@pytest_asyncio.fixture
async def leasing_company(db_session: AsyncSession) -> LeasingCompany:
    lc = LeasingCompany()
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def distributor(db_session: AsyncSession) -> Distributor:
    company = Company(
        name="Admin Support Distributor",
        inn="7700000200",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    d = Distributor(company_id=company.id, is_active=True)
    db_session.add(d)
    await db_session.flush()
    return d


def _company_id(distributor: Distributor) -> str:
    assert distributor.company_id is not None
    return str(distributor.company_id)


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660002222",
        email="dealer-it@test.local",
        name="Dealer IT",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def dealer_company(
    db_session: AsyncSession,
    distributor: Distributor,
) -> Company:
    company = Company(
        name="Admin Support Dealer Company",
        inn="7700000202",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    db_session.add(
        DistributorDealerLink(
            distributor_company_id=distributor.company_id,
            dealer_company_id=company.id,
        )
    )
    await db_session.flush()
    return company


# ---------------------------------------------------------------------------
# Support programs — golden path & auth
# ---------------------------------------------------------------------------


async def test_create_program_happy_path(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    leasing_company: LeasingCompany,
    distributor: Distributor,
) -> None:
    payload = {
        "name": "Support 1",
        "mark_id": mark_bmw.id,
        "distributor_id": _company_id(distributor),
        "leasing_company_ids": [leasing_company.id],
        "support_type": "down_payment_compensation",
        "support_params": {"value_type": "amount", "value": 10000},
        "production_date_from": "2026-01-10",
        "production_date_to": "2026-02-20",
        "delivery_date_from": "2026-03-01",
        "delivery_date_to": "2026-04-15",
        "compensation_templates": [
            {
                "payer": "distributor",
                "recipient": "leasing_company",
                "calculation_base": "down_payment",
                "value_type": "percent",
                "value": 5,
                "payment_schedule_type": "reporting_period",
                "payment_schedule_period": "half_year",
                "payment_schedule_value": "90",
            }
        ],
    }
    response = await client.post(
        "/api/v1/admin/support-programs",
        json=payload,
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["support_program"]["name"] == "Support 1"
    assert body["support_program"]["mark_name"] == "BMW"
    assert body["support_program"]["is_active"] is False
    assert body["support_program"]["production_date_from"] == "2026-01-10"
    assert body["support_program"]["production_date_to"] == "2026-02-20"
    assert body["support_program"]["delivery_date_from"] == "2026-03-01"
    assert body["support_program"]["delivery_date_to"] == "2026-04-15"
    assert body["support_program"]["leasing_company_ids"] == [str(leasing_company.id)]
    assert body["support_program"]["leasing_companies"][0]["id"] == str(
        leasing_company.id
    )
    assert body["support_program"]["distributor_ids"] == [_company_id(distributor)]
    assert (
        body["support_program"]["compensation_templates"][0]["payment_schedule_period"]
        == "half_year"
    )
    location = response.headers["location"]
    assert location.endswith(str(body["support_program"]["id"]))


async def test_admin_api_returns_symmetric_compatibility(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    common_payload = {
        "mark_id": mark_bmw.id,
        "distributor_id": _company_id(distributor),
        "support_type": "down_payment_compensation",
        "support_params": {"value_type": "amount", "value": 10000},
        "is_compatible": True,
    }
    second_response = await client.post(
        "/api/v1/admin/support-programs",
        json={"name": "second compatible", **common_payload},
        headers=_auth(employee_token),
    )
    assert second_response.status_code == 201, second_response.text
    second_id = second_response.json()["support_program"]["id"]

    first_response = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "first compatible",
            **common_payload,
            "compatible_support_ids": [second_id],
        },
        headers=_auth(employee_token),
    )
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()["support_program"]
    assert first["is_compatible"] is True
    assert first["compatible_support_ids"] == [second_id]

    second_get = await client.get(
        f"/api/v1/admin/support-programs/{second_id}",
        headers=_auth(employee_token),
    )
    assert second_get.status_code == 200
    assert second_get.json()["support_program"]["compatible_support_ids"] == [
        first["id"]
    ]

    clear_response = await client.put(
        f"/api/v1/admin/support-programs/{first['id']}",
        json={
            "name": "first compatible",
            **common_payload,
            "is_compatible": False,
            "compatible_support_ids": [],
        },
        headers=_auth(employee_token),
    )
    assert clear_response.status_code == 200, clear_response.text
    assert clear_response.json()["support_program"]["compatible_support_ids"] == []

    second_get = await client.get(
        f"/api/v1/admin/support-programs/{second_id}",
        headers=_auth(employee_token),
    )
    assert second_get.json()["support_program"]["compatible_support_ids"] == []


async def test_admin_api_update_enables_selected_disabled_target(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    common_payload = {
        "mark_id": mark_bmw.id,
        "distributor_id": _company_id(distributor),
        "support_type": "down_payment_compensation",
        "support_params": {"value_type": "amount", "value": 10000},
    }
    target_response = await client.post(
        "/api/v1/admin/support-programs",
        json={"name": "disabled target", **common_payload},
        headers=_auth(employee_token),
    )
    assert target_response.status_code == 201, target_response.text
    target_id = target_response.json()["support_program"]["id"]

    source_response = await client.post(
        "/api/v1/admin/support-programs",
        json={"name": "source", **common_payload},
        headers=_auth(employee_token),
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["support_program"]["id"]

    update_response = await client.put(
        f"/api/v1/admin/support-programs/{source_id}",
        json={
            "name": "source",
            **common_payload,
            "is_compatible": True,
            "compatible_support_ids": [target_id],
        },
        headers=_auth(employee_token),
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["support_program"]["compatible_support_ids"] == [
        target_id
    ]

    target_get = await client.get(
        f"/api/v1/admin/support-programs/{target_id}",
        headers=_auth(employee_token),
    )
    assert target_get.status_code == 200, target_get.text
    target = target_get.json()["support_program"]
    assert target["is_compatible"] is True
    assert target["compatible_support_ids"] == [source_id]


async def test_create_program_accepts_distributor_company_without_extension(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    db_session: AsyncSession,
) -> None:
    company = Company(
        name="Admin Support Company Only Distributor",
        inn="7700000201",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    response = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "Support company only",
            "mark_id": mark_bmw.id,
            "distributor_id": str(company.id),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10000},
        },
        headers=_auth(employee_token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["support_program"]
    assert body["distributor_id"] == str(company.id)
    assert body["distributor_ids"] == [str(company.id)]
    assert body["distributors"][0]["id"] == str(company.id)


async def test_create_program_anon_unauthorised(
    client: AsyncClient, mark_bmw: Mark
) -> None:
    response = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "x",
            "mark_id": mark_bmw.id,
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10},
        },
    )
    assert response.status_code == 401


async def test_create_program_client_forbidden(
    client: AsyncClient, client_token: str, mark_bmw: Mark
) -> None:
    response = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "x",
            "mark_id": mark_bmw.id,
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10},
        },
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_create_program_requires_distributor(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
) -> None:
    response = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "x",
            "mark_id": mark_bmw.id,
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10},
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 400
    assert "Дистрибьютор" in response.json()["detail"]


async def test_create_program_rejects_inverted_delivery_dates(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    response = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "bad dates",
            "mark_id": mark_bmw.id,
            "distributor_id": _company_id(distributor),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10},
            "delivery_date_from": "2026-05-01",
            "delivery_date_to": "2026-04-01",
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 400
    assert "поставки" in response.json()["detail"]


async def test_list_programs_returns_pagination(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    for i in range(2):
        await client.post(
            "/api/v1/admin/support-programs",
            json={
                "name": f"P{i}",
                "mark_id": mark_bmw.id,
                "distributor_id": _company_id(distributor),
                "support_type": "down_payment_compensation",
                "support_params": {"value_type": "amount", "value": 10},
            },
            headers=_auth(employee_token),
        )
    response = await client.get(
        "/api/v1/admin/support-programs?page=1&limit=10",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] >= 2
    assert isinstance(body["support_programs"], list)


async def test_distributor_sees_only_own_support_programs(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    mark_bmw: Mark,
) -> None:
    first_distributor = Company(name="Support scope D1", company_type="distributor")
    second_distributor = Company(name="Support scope D2", company_type="distributor")
    db_session.add_all([first_distributor, second_distributor])
    await db_session.flush()
    actor = User(
        phone="+766****0002",
        email="support-scope-distributor@test.local",
        name="Support scope distributor",
        role="distributor",
        is_active=True,
        company_id=first_distributor.id,
    )
    db_session.add(actor)
    await db_session.flush()
    distributor_token, _ = generate_tokens(actor.id, "distributor", first_distributor.id)

    own = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "Support scope own",
            "mark_id": mark_bmw.id,
            "distributor_id": str(first_distributor.id),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10},
        },
        headers=_auth(employee_token),
    )
    foreign = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "Support scope foreign",
            "mark_id": mark_bmw.id,
            "distributor_id": str(second_distributor.id),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 10},
        },
        headers=_auth(employee_token),
    )
    assert own.status_code == foreign.status_code == 201
    own_id = own.json()["support_program"]["id"]
    foreign_id = foreign.json()["support_program"]["id"]

    listing = await client.get(
        "/api/v1/admin/support-programs", headers=_auth(distributor_token)
    )
    assert listing.status_code == 200
    assert {item["id"] for item in listing.json()["support_programs"]} == {own_id}
    assert listing.json()["pagination"]["total"] == 1
    assert (
        await client.get(
            f"/api/v1/admin/support-programs/{own_id}",
            headers=_auth(distributor_token),
        )
    ).status_code == 200
    assert (
        await client.get(
            f"/api/v1/admin/support-programs/{foreign_id}",
            headers=_auth(distributor_token),
        )
    ).status_code == 404


async def test_get_program_404(client: AsyncClient, employee_token: str) -> None:
    response = await client.get(
        f"/api/v1/admin/support-programs/{uuid4()}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_update_program_replaces_fields(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    leasing_company: LeasingCompany,
    distributor: Distributor,
) -> None:
    create = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "orig",
            "mark_id": mark_bmw.id,
            "distributor_id": _company_id(distributor),
            "support_type": "leasing_interest_compensation",
            "support_params": {"value_type": "percent", "value": 1},
            "leasing_company_ids": [leasing_company.id],
        },
        headers=_auth(employee_token),
    )
    program_id = create.json()["support_program"]["id"]

    response = await client.put(
        f"/api/v1/admin/support-programs/{program_id}",
        json={
            "name": "renamed",
            "mark_id": mark_bmw.id,
            "distributor_id": _company_id(distributor),
            "support_type": "leasing_interest_compensation",
            "support_params": {"value_type": "percent", "value": 2},
            "leasing_company_ids": [],
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert response.json()["support_program"]["name"] == "renamed"
    assert response.json()["support_program"]["leasing_company_ids"] == []


async def test_delete_program_soft_deactivates(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    create = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "kill me",
            "mark_id": mark_bmw.id,
            "distributor_id": _company_id(distributor),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 1},
        },
        headers=_auth(employee_token),
    )
    program_id = create.json()["support_program"]["id"]
    response = await client.delete(
        f"/api/v1/admin/support-programs/{program_id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200

    after = await client.get(
        f"/api/v1/admin/support-programs/{program_id}",
        headers=_auth(employee_token),
    )
    assert after.status_code == 200
    assert after.json()["support_program"]["is_active"] is False


# ---------------------------------------------------------------------------
# Bill of Lading upload
# ---------------------------------------------------------------------------


async def test_upload_bill_of_lading_happy_path(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    create = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "x",
            "mark_id": mark_bmw.id,
            "distributor_id": _company_id(distributor),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 1},
        },
        headers=_auth(employee_token),
    )
    program_id = create.json()["support_program"]["id"]
    response = await client.post(
        f"/api/v1/admin/support-programs/{program_id}/bill-of-lading/upload",
        files={"file": ("bol.pdf", b"%PDF-1.4 hello", "application/pdf")},
        data={"comment": "first upload"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bill_of_lading"]["file_name"] == "bol.pdf"
    files = body["support_program"]["bill_of_lading"]["files"]
    assert len(files) == 1


async def test_upload_bill_of_lading_rejects_bad_extension(
    client: AsyncClient,
    employee_token: str,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    create = await client.post(
        "/api/v1/admin/support-programs",
        json={
            "name": "x",
            "mark_id": mark_bmw.id,
            "distributor_id": _company_id(distributor),
            "support_type": "down_payment_compensation",
            "support_params": {"value_type": "amount", "value": 1},
        },
        headers=_auth(employee_token),
    )
    program_id = create.json()["support_program"]["id"]

    response = await client.post(
        f"/api/v1/admin/support-programs/{program_id}/bill-of-lading/upload",
        files={"file": ("bad.txt", b"hi", "text/plain")},
        headers=_auth(employee_token),
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Dealer groups
# ---------------------------------------------------------------------------


async def test_create_dealer_group_happy_path(
    client: AsyncClient,
    employee_token: str,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "Group Alpha",
            "distributor_company_id": _company_id(distributor),
            "dealer_company_ids": [str(dealer_company.id)],
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["dealer_group"]["name"] == "Group Alpha"
    assert body["dealer_group"]["dealer_company_ids"] == [str(dealer_company.id)]


async def test_create_dealer_group_duplicate_name_returns_409(
    client: AsyncClient,
    employee_token: str,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "Dup",
            "distributor_company_id": _company_id(distributor),
            "dealer_company_ids": [str(dealer_company.id)],
        },
        headers=_auth(employee_token),
    )
    second = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "DUP",
            "distributor_company_id": _company_id(distributor),
            "dealer_company_ids": [str(dealer_company.id)],
        },
        headers=_auth(employee_token),
    )
    assert second.status_code == 409


async def test_create_dealer_group_duplicate_dealer_returns_400(
    client: AsyncClient,
    employee_token: str,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "Duplicate Dealer",
            "distributor_company_id": _company_id(distributor),
            "dealer_company_ids": [
                str(dealer_company.id),
                str(dealer_company.id),
            ],
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 400
    assert "Повторяющиеся дилеры" in response.text


async def test_create_dealer_group_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "no-auth",
            "distributor_company_id": str(uuid4()),
            "dealer_company_ids": [str(uuid4())],
        },
    )
    assert response.status_code == 401


async def test_create_dealer_group_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "client-attempt",
            "distributor_company_id": str(uuid4()),
            "dealer_company_ids": [str(uuid4())],
        },
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_list_dealer_groups_pagination(
    client: AsyncClient,
    employee_token: str,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    for i in range(2):
        await client.post(
            "/api/v1/admin/dealer-groups",
            json={
                "name": f"GroupList{i}",
                "distributor_company_id": _company_id(distributor),
                "dealer_company_ids": [str(dealer_company.id)],
            },
            headers=_auth(employee_token),
        )
    response = await client.get(
        "/api/v1/admin/dealer-groups?page=1&limit=10",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] >= 2
    assert isinstance(body["dealer_groups"], list)


async def test_delete_dealer_group_deactivates_and_list_keeps_it_below_active(
    client: AsyncClient,
    employee_token: str,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    active = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "Active Dealer Group",
            "distributor_company_id": _company_id(distributor),
            "dealer_company_ids": [str(dealer_company.id)],
        },
        headers=_auth(employee_token),
    )
    inactive = await client.post(
        "/api/v1/admin/dealer-groups",
        json={
            "name": "Inactive Dealer Group",
            "distributor_company_id": _company_id(distributor),
            "dealer_company_ids": [str(dealer_company.id)],
        },
        headers=_auth(employee_token),
    )
    active_id = active.json()["dealer_group"]["id"]
    inactive_id = inactive.json()["dealer_group"]["id"]

    response = await client.delete(
        f"/api/v1/admin/dealer-groups/{inactive_id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Группа дилеров деактивирована"

    after = await client.get(
        f"/api/v1/admin/dealer-groups/{inactive_id}",
        headers=_auth(employee_token),
    )
    assert after.status_code == 200
    assert after.json()["dealer_group"]["is_active"] is False
    assert after.json()["dealer_group"]["dealer_company_ids"] == [str(dealer_company.id)]

    listed = await client.get(
        "/api/v1/admin/dealer-groups?page=1&limit=10",
        headers=_auth(employee_token),
    )
    ids = [item["id"] for item in listed.json()["dealer_groups"]]
    assert ids == [active_id, inactive_id]
