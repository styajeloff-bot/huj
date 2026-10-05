"""HTTP scenarios of internal monetization against a real disposable PostgreSQL DB."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.commands.monetization.deals import capture
from domain.services.object_storage import ObjectStorage, StoredObject
from infrastructure.auth import generate_tokens
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.users import User

PROGRAMS = "/api/v1/admin/monetization/programs"
DEALS = "/api/v1/monetization/deals"


@pytest_asyncio.fixture
async def db_session(_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Keep earlier HTTP commits after a later 4xx rollback, isolated per test."""
    async with _engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session
        await transaction.rollback()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def api_seed(db_session: AsyncSession, employee_user: User) -> dict[str, Any]:
    seed: dict[str, Any] = {"employee_id": employee_user.id}
    for key, role in (
        ("dealer", "dealer"),
        ("leasing", "leasing_company"),
        ("outsider", "dealer"),
        ("other_leasing", "leasing_company"),
        ("distributor", "distributor"),
    ):
        company = Company(id=uuid4(), name=f"Monetization {key}", company_type=role)
        db_session.add(company)
        await db_session.flush()
        user = User(
            id=uuid4(),
            phone=str(uuid4())[:20],
            name=key,
            role=role,
            company_id=company.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        token, _ = generate_tokens(user.id, role, company.id)
        seed[key] = {"company_id": company.id, "user_id": user.id, "token": token}
        if role == "leasing_company":
            leasing = LeasingCompany(id=uuid4(), company_id=company.id, is_active=True)
            db_session.add(leasing)
            await db_session.flush()
            seed[key]["leasing_company_id"] = leasing.id
    client_company = Company(id=uuid4(), name="Customer", company_type="other")
    db_session.add(client_company)
    await db_session.flush()
    seed["client_company_id"] = client_company.id
    from infrastructure.models.support import DealerGroup, DealerGroupMember

    group = DealerGroup(id=uuid4(), name="Monetization dealer group", created_by=employee_user.id,
                        distributor_company_id=seed["distributor"]["company_id"])
    db_session.add(group)
    await db_session.flush()
    db_session.add(DealerGroupMember(dealer_group_id=group.id, created_by=employee_user.id,
                                    dealer_company_id=seed["dealer"]["company_id"]))
    seed["dealer_group_id"] = group.id
    await db_session.commit()
    return seed


def _program(seed: dict[str, Any], **changes: Any) -> dict[str, Any]:
    result = {
        "name": "Внутренние условия",
        "leasing_company_id": str(seed["leasing"]["leasing_company_id"]),
        "dealer_company_id": str(seed["dealer"]["company_id"]),
        "period_start": "2026-01-01",
        "period_end": None,
        "status": "active",
        "sources": [
            {
                "source_type": "exchange",
                "expenses": [
                    {
                        "local_id": "e1",
                        "participant_type": "leasing",
                        "calc_type": "amount",
                        "base_type": "none",
                        "value": "1000",
                        "vat_excluded": True,
                    }
                ],
                "incomes": [
                    {
                        "participant_type": "dealer",
                        "calc_type": "percent",
                        "base_type": "expense_amount",
                        "expense_ref": "e1",
                        "value": "50",
                        "vat_excluded": False,
                    }
                ],
            }
        ],
    }
    result.update(changes)
    return result


async def _create_program(
    client: AsyncClient, employee_token: str, payload: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(PROGRAMS, json=payload, headers=_auth(employee_token))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _captured_deal(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    seed: dict[str, Any],
    **program_changes: Any,
) -> dict[str, Any]:
    conditions = await _create_program(
        client, employee_token, _program(seed, **program_changes)
    )
    result = await capture(
        db_session,
        {
            "exchange_request_id": uuid4(),
            "source_type": "exchange",
            "application_number": "EX-22268",
            "leasing_company_id": seed["leasing"]["leasing_company_id"],
            "dealer_company_id": seed["dealer"]["company_id"],
            "distributor_company_id": seed["distributor"]["company_id"],
            "base_amount": Decimal("1000000.05"),
            "occurred_at": datetime(2026, 9, 16, tzinfo=UTC),
            "vehicles": [{"vehicle_id": uuid4(), "brand": "Sollers", "model": "SF5"}],
            "supports": [],
        },
    )
    assert result["deal"] is not None, result["reason"]
    assert str(result["deal"]["program_id"]) == conditions["id"]
    await db_session.commit()
    response = await client.get(
        f"{DEALS}/{result['deal']['id']}", headers=_auth(employee_token)
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.parametrize(
    "path", [PROGRAMS, DEALS, "/api/v1/monetization/lookups/companies?kind=leasing"]
)
async def test_client_cannot_access_internal_monetization(
    client: AsyncClient, client_token: str, path: str
) -> None:
    response = await client.get(path, headers=_auth(client_token))
    assert response.status_code == 403


async def test_create_list_detail_and_company_projection(
    client: AsyncClient, employee_token: str, api_seed: dict[str, Any]
) -> None:
    response = await client.post(
        PROGRAMS, json=_program(api_seed), headers=_auth(employee_token)
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["can_manage"] is True
    assert response.headers["location"] == f"{PROGRAMS}/{created['id']}"
    assert len(created["sources"][0]["expenses"]) == 1
    assert len(created["sources"][0]["incomes"]) == 1
    listed = await client.get(
        PROGRAMS,
        params={"source_type": "exchange", "page_size": 1},
        headers=_auth(employee_token),
    )
    assert listed.status_code == 200
    assert listed.json()["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 1,
        "total_pages": 1,
    }
    assert listed.json()["can_manage"] is True
    assert listed.json()["items"][0]["id"] == created["id"]
    assert "sources" not in listed.json()["items"][0]
    dealer = await client.get(
        f"{PROGRAMS}/{created['id']}", headers=_auth(api_seed["dealer"]["token"])
    )
    assert dealer.status_code == 200, dealer.text
    assert dealer.json()["can_manage"] is False
    assert dealer.json()["sources"][0]["expenses"] == []
    assert [
        row["participant_type"] for row in dealer.json()["sources"][0]["incomes"]
    ] == ["dealer"]
    outsider = await client.get(
        f"{PROGRAMS}/{created['id']}", headers=_auth(api_seed["outsider"]["token"])
    )
    assert outsider.status_code == 404
    other_lc = await client.get(
        PROGRAMS,
        params={"leasing_company_id": created["leasing_company_id"]},
        headers=_auth(api_seed["other_leasing"]["token"]),
    )
    assert other_lc.json()["items"] == []


@pytest.mark.parametrize("invalid", ["disabled_source", "agent", "foreign_reference"])
async def test_invalid_program_is_400_and_does_not_leave_partial_rows(
    client: AsyncClient, employee_token: str, api_seed: dict[str, Any], invalid: str
) -> None:
    payload = _program(api_seed)
    if invalid == "disabled_source":
        payload["sources"][0]["source_type"] = "dealer_site"
    elif invalid == "agent":
        payload["sources"][0]["expenses"][0]["participant_type"] = "agent"
    else:
        payload["sources"][0]["incomes"][0]["expense_ref"] = "other-source-expense"
    response = await client.post(PROGRAMS, json=payload, headers=_auth(employee_token))
    assert response.status_code == 400, response.text
    listed = await client.get(PROGRAMS, headers=_auth(employee_token))
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []


async def test_overlapping_duplicate_is_409_and_existing_program_survives(
    client: AsyncClient, employee_token: str, api_seed: dict[str, Any]
) -> None:
    first = await _create_program(
        client, employee_token, _program(api_seed, period_end="2026-09-30")
    )
    response = await client.post(
        PROGRAMS,
        json=_program(api_seed, name="Overlap", period_start="2026-09-30"),
        headers=_auth(employee_token),
    )
    assert response.status_code == 409, response.text
    later = await _create_program(
        client,
        employee_token,
        _program(api_seed, name="Next period", period_start="2026-10-01"),
    )
    listed = await client.get(PROGRAMS, headers=_auth(employee_token))
    assert {item["id"] for item in listed.json()["items"]} == {first["id"], later["id"]}


async def test_internal_capture_has_company_scoped_financial_rows_and_no_public_create(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    api_seed: dict[str, Any],
) -> None:
    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    assert Decimal(deal["base_amount"]) == Decimal("1000000.05")
    assert Decimal(deal["expenses"][0]["amount"]) == Decimal("1000")
    assert Decimal(deal["incomes"][0]["amount"]) == Decimal("500")
    dealer = await client.get(
        f"{DEALS}/{deal['id']}", headers=_auth(api_seed["dealer"]["token"])
    )
    assert dealer.status_code == 200, dealer.text
    assert dealer.json()["expenses"] == []
    assert len(dealer.json()["incomes"]) == 1
    leasing = await client.get(
        f"{DEALS}/{deal['id']}", headers=_auth(api_seed["leasing"]["token"])
    )
    assert leasing.status_code == 200, leasing.text
    assert leasing.json()["incomes"] == []
    assert len(leasing.json()["expenses"]) == 1
    for role in ("outsider", "other_leasing"):
        direct = await client.get(
            f"{DEALS}/{deal['id']}", headers=_auth(api_seed[role]["token"])
        )
        assert direct.status_code == 404
        listing = await client.get(
            DEALS,
            params={"dealer_company_id": str(api_seed["dealer"]["company_id"])},
            headers=_auth(api_seed[role]["token"]),
        )
        assert listing.json()["items"] == []
    matching = await client.get(DEALS, params={"brand": "Sollers"}, headers=_auth(employee_token))
    assert matching.status_code == 200
    assert matching.json()["pagination"]["total"] == 1
    absent = await client.get(DEALS, params={"brand": "UAZ"}, headers=_auth(employee_token))
    assert absent.status_code == 200
    assert absent.json()["pagination"]["total"] == 0
    assert absent.json()["items"] == []
    create = await client.post(DEALS, json={}, headers=_auth(employee_token))
    assert create.status_code == 405


async def test_confirm_adjust_noop_stale_revision_and_final_paid_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    api_seed: dict[str, Any],
) -> None:
    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    confirm_url = f"{DEALS}/{deal['id']}/confirm"
    final_url = f"/api/v1/admin/monetization/deals/{deal['id']}/confirm"
    adjust_url = f"/api/v1/admin/monetization/deals/{deal['id']}/adjust-conditions"
    premature = await client.post(
        final_url, json={"revision": 1}, headers=_auth(employee_token)
    )
    assert premature.status_code == 409, premature.text
    assert "ЛК" in premature.json()["detail"] and "дилер" in premature.json()["detail"]
    confirmed = await client.post(
        confirm_url, json={"revision": 1}, headers=_auth(api_seed["dealer"]["token"])
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["confirmations"]["dealer"]["confirmed_by_name"] == "dealer"
    assert confirmed.json()["confirmations"]["dealer"]["confirmed_by"] == str(
        api_seed["dealer"]["user_id"]
    )
    repeated = await client.post(
        confirm_url, json={"revision": 1}, headers=_auth(api_seed["dealer"]["token"])
    )
    assert repeated.status_code == 409, repeated.text
    unchanged = await client.post(
        adjust_url,
        json={
            "revision": 1,
            "items": [
                {
                    "deal_participant_amount_id": deal["expenses"][0]["id"],
                    "new_value": "1000",
                }
            ],
        },
        headers=_auth(employee_token),
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["revision"] == 1
    assert unchanged.json()["confirmations_reset"] is False
    assert unchanged.json()["confirmations"]["dealer"]["confirmed_at"] is not None
    adjusted = await client.post(
        adjust_url,
        json={
            "revision": 1,
            "items": [
                {
                    "deal_participant_amount_id": deal["expenses"][0]["id"],
                    "new_value": "1100",
                }
            ],
        },
        headers=_auth(employee_token),
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["revision"] == 2
    assert adjusted.json()["confirmations_reset"] is True
    assert adjusted.json()["confirmations"]["dealer"]["confirmed_at"] is None
    assert Decimal(adjusted.json()["platform_auto_amount"]) == Decimal("600")
    stale = await client.post(
        confirm_url, json={"revision": 1}, headers=_auth(api_seed["leasing"]["token"])
    )
    assert stale.status_code == 409, stale.text
    for role in ("leasing", "dealer"):
        current = await client.post(
            confirm_url, json={"revision": 2}, headers=_auth(api_seed[role]["token"])
        )
        assert current.status_code == 200, current.text
    paid = await client.post(
        final_url, json={"revision": 2}, headers=_auth(employee_token)
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    immutable = await client.post(
        adjust_url, json={"revision": 2, "items": []}, headers=_auth(employee_token)
    )
    assert immutable.status_code == 409, immutable.text
    paid_again = await client.post(
        final_url, json={"revision": 2}, headers=_auth(employee_token)
    )
    assert paid_again.status_code == 409, paid_again.text


async def test_failed_adjustment_leaves_sums_revision_and_confirmations_intact(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    api_seed: dict[str, Any],
) -> None:
    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    confirmed = await client.post(
        f"{DEALS}/{deal['id']}/confirm",
        json={"revision": 1},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["confirmations"]["dealer"]["confirmed_by_name"] == "dealer"
    adjust_url = f"/api/v1/admin/monetization/deals/{deal['id']}/adjust-conditions"
    overdrawn = await client.post(
        adjust_url,
        json={
            "revision": 1,
            "items": [
                {
                    "deal_participant_amount_id": deal["expenses"][0]["id"],
                    "new_value": "100",
                }
            ],
        },
        headers=_auth(employee_token),
    )
    assert overdrawn.status_code == 409, overdrawn.text
    outsider = await client.post(
        adjust_url,
        json={"revision": 1, "items": []},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert outsider.status_code == 403
    unchanged = await client.get(f"{DEALS}/{deal['id']}", headers=_auth(employee_token))
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["revision"] == 1
    assert Decimal(unchanged.json()["expenses"][0]["amount"]) == Decimal("1000")
    assert unchanged.json()["confirmations"]["dealer"]["confirmed_at"] is not None


@pytest.mark.parametrize("duplicate", ["expense_income", "income_income"])
async def test_duplicate_supplied_row_ids_are_400(
    client: AsyncClient, employee_token: str, api_seed: dict[str, Any], duplicate: str
) -> None:
    payload = _program(api_seed)
    incomes = payload["sources"][0]["incomes"]
    incomes[0]["local_id"] = "e1" if duplicate == "expense_income" else "i1"
    if duplicate == "income_income":
        incomes.append(dict(incomes[0], participant_type="platform"))
    result = await client.post(PROGRAMS, json=payload, headers=_auth(employee_token))
    assert result.status_code == 400, result.text


@pytest.fixture
async def memory_storage(client: AsyncClient) -> AsyncGenerator[ObjectStorage, None]:
    from infrastructure.services.object_storage import get_object_storage
    from main import app

    class MemoryStorage:
        def __init__(self) -> None:
            self.objects: dict[str, StoredObject] = {}

        async def put(self, key: str, data: bytes, content_type: str) -> str:
            self.objects[key] = StoredObject(key, content_type, len(data), None, data)
            return self.public_url(key)

        async def get(self, key: str) -> StoredObject | None:
            return self.objects.get(key)

        async def delete(self, key: str) -> bool:
            return self.objects.pop(key, None) is not None

        async def exists(self, key: str) -> bool:
            return key in self.objects

        def public_url(self, key: str) -> str:
            return f"https://test-storage.invalid/{key}"

    storage = MemoryStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_object_storage, None)


async def test_documents_require_parent_access_and_preserve_old_revision_files(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    client_token: str,
    api_seed: dict[str, Any],
    memory_storage: ObjectStorage,
) -> None:
    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    documents_url = f"{DEALS}/{deal['id']}/documents"
    uploaded = await client.post(
        documents_url,
        data={"revision": "1"},
        files={"files": ("approval.txt", b"Original approval", "text/plain")},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert uploaded.status_code == 200, uploaded.text
    document = uploaded.json()["documents"][0]
    assert document["revision"] == 1 and document["outdated"] is False
    download = await client.get(
        document["download_url"], headers=_auth(api_seed["leasing"]["token"])
    )
    assert download.status_code == 200 and download.content == b"Original approval"
    assert download.headers["cache-control"] == "private, no-store"
    outsider = await client.get(
        document["download_url"], headers=_auth(api_seed["outsider"]["token"])
    )
    assert outsider.status_code == 404
    customer = await client.get(document["download_url"], headers=_auth(client_token))
    assert customer.status_code == 403
    changed = await client.post(
        f"/api/v1/admin/monetization/deals/{deal['id']}/adjust-conditions",
        json={
            "revision": 1,
            "items": [
                {
                    "deal_participant_amount_id": deal["expenses"][0]["id"],
                    "new_value": "1200",
                }
            ],
        },
        headers=_auth(employee_token),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["documents"][0]["outdated"] is True
    assert changed.json()["documents"][0]["id"] == document["id"]
    stale = await client.post(
        documents_url,
        data={"revision": "1"},
        files={"files": ("stale.txt", b"Stale revision", "text/plain")},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert stale.status_code == 409, stale.text
    old_file = await client.get(
        document["download_url"], headers=_auth(api_seed["dealer"]["token"])
    )
    assert old_file.status_code == 200 and old_file.content == b"Original approval"
    latest = await client.get(f"{DEALS}/{deal['id']}", headers=_auth(employee_token))
    assert len(latest.json()["documents"]) == 1


async def test_contracts_are_downloadable_only_with_program_access(
    client: AsyncClient,
    employee_token: str,
    api_seed: dict[str, Any],
    memory_storage: ObjectStorage,
) -> None:
    conditions = await _create_program(client, employee_token, _program(api_seed))
    uploaded = await client.post(
        f"{PROGRAMS}/{conditions['id']}/contracts",
        files={"files": ("conditions.pdf", b"%PDF-1.4\nAgreement", "application/pdf")},
        headers=_auth(employee_token),
    )
    assert uploaded.status_code == 200, uploaded.text
    url = uploaded.json()["documents"][0]["download_url"]
    own = await client.get(url, headers=_auth(api_seed["dealer"]["token"]))
    assert own.status_code == 200 and own.content == b"%PDF-1.4\nAgreement"
    foreign = await client.get(url, headers=_auth(api_seed["outsider"]["token"]))
    assert foreign.status_code == 404
    dealer_upload = await client.post(
        f"{PROGRAMS}/{conditions['id']}/contracts",
        files={"files": ("unauthorized.txt", b"Should not upload", "text/plain")},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert dealer_upload.status_code == 403


async def _application(db_session: AsyncSession, seed: dict[str, Any]) -> UUID:
    from infrastructure.models.applications import LeasingApplication

    application = LeasingApplication(
        id=uuid4(),
        company_id=seed["client_company_id"],
        dealer_company_id=seed["dealer"]["company_id"],
        created_by=seed["dealer"]["user_id"],
        total_amount=Decimal("2400000.50"),
        down_payment=Decimal("480000.10"),
    )
    db_session.add(application)
    await db_session.commit()
    return UUID(str(application.id))


async def test_commission_requests_are_recipient_scoped_and_counteroffer_needs_dealer_decision(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any]
) -> None:
    from infrastructure.models.applications import LeasingApplication

    application_id = await _application(db_session, api_seed)
    create_url = (
        f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests"
    )
    list_url = f"/api/v1/monetization/applications/{application_id}/condition-requests"
    payload = {
        "leasing_company_ids": [
            str(api_seed[key]["leasing_company_id"])
            for key in ("leasing", "other_leasing")
        ],
        "calc_type": "percent",
        "value": "1",
    }
    created = await client.post(
        create_url, json=payload, headers=_auth(api_seed["dealer"]["token"])
    )
    assert created.status_code == 201, created.text
    requests = created.json()["requests"]
    assert len(requests) == 2
    request = next(
        row
        for row in requests
        if row["leasing_company_id"] == str(api_seed["leasing"]["leasing_company_id"])
    )
    visible = await client.get(list_url, headers=_auth(api_seed["leasing"]["token"]))
    assert [row["id"] for row in visible.json()["items"]] == [request["id"]]
    response_url = f"/api/v1/leasing-company/monetization/condition-requests/{request['id']}/respond"
    wrong_lc = await client.post(
        response_url,
        json={"decision": "accepted"},
        headers=_auth(api_seed["other_leasing"]["token"]),
    )
    assert wrong_lc.status_code == 404
    countered = await client.post(
        response_url,
        json={
            "decision": "countered",
            "counter_calc_type": "percent",
            "counter_value": "2",
        },
        headers=_auth(api_seed["leasing"]["token"]),
    )
    assert countered.status_code == 200, countered.text
    assert countered.json()["status"] == "countered"
    assert Decimal(countered.json()["requested_value"]) == Decimal("1")
    assert Decimal(countered.json()["counter_value"]) == Decimal("2")
    decision_url = (
        f"/api/v1/dealer/monetization/condition-requests/{request['id']}/decision"
    )
    foreign_dealer = await client.post(
        decision_url,
        json={"decision": "accept_counter"},
        headers=_auth(api_seed["outsider"]["token"]),
    )
    assert foreign_dealer.status_code == 404
    accepted = await client.post(
        decision_url,
        json={"decision": "accept_counter"},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    repeated = await client.post(
        decision_url,
        json={"decision": "reject"},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert repeated.status_code == 409
    application = await db_session.get(
        LeasingApplication, application_id, populate_existing=True
    )
    assert application is not None
    assert application.total_amount == Decimal("2400000.50")
    assert application.down_payment == Decimal("480000.10")


async def test_commission_request_is_forbidden_after_first_lca(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any]
) -> None:
    from infrastructure.models.applications import LeasingCompanyApplication

    application_id = await _application(db_session, api_seed)
    db_session.add(
        LeasingCompanyApplication(
            id=uuid4(),
            application_id=application_id,
            leasing_company_id=api_seed["leasing"]["leasing_company_id"],
        )
    )
    await db_session.commit()
    response = await client.post(
        f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests",
        json={
            "leasing_company_ids": [
                str(api_seed["other_leasing"]["leasing_company_id"])
            ],
            "calc_type": "amount",
            "value": "1000",
        },
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert response.status_code == 409, response.text
    listing = await client.get(
        f"/api/v1/monetization/applications/{application_id}/condition-requests",
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert listing.json()["items"] == []


async def test_distributor_without_applied_row_cannot_confirm_or_upload(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    api_seed: dict[str, Any],
    memory_storage: ObjectStorage,
) -> None:
    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    detail = await client.get(
        f"{DEALS}/{deal['id']}", headers=_auth(api_seed["distributor"]["token"])
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["expenses"] == [] and detail.json()["incomes"] == []
    assert detail.json()["can_confirm"] is False
    assert detail.json()["can_upload_documents"] is False
    confirmed = await client.post(
        f"{DEALS}/{deal['id']}/confirm",
        json={"revision": 1},
        headers=_auth(api_seed["distributor"]["token"]),
    )
    assert confirmed.status_code == 403, confirmed.text
    uploaded = await client.post(
        f"{DEALS}/{deal['id']}/documents",
        data={"revision": "1"},
        files={"files": ("invalid.txt", b"Unrelated party", "text/plain")},
        headers=_auth(api_seed["distributor"]["token"]),
    )
    assert uploaded.status_code == 403, uploaded.text


async def test_actual_distributor_confirmation_is_required_and_paid_documents_are_closed(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    api_seed: dict[str, Any],
    memory_storage: ObjectStorage,
) -> None:
    sources = _program(api_seed)["sources"]
    sources[0]["incomes"][0]["participant_type"] = "distributor"
    deal = await _captured_deal(
        client, db_session, employee_token, api_seed, sources=sources
    )
    detail = await client.get(
        f"{DEALS}/{deal['id']}", headers=_auth(api_seed["distributor"]["token"])
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_confirm"] is True
    assert [item["participant_type"] for item in detail.json()["incomes"]] == [
        "distributor"
    ]
    for role in ("leasing", "dealer"):
        confirmed = await client.post(
            f"{DEALS}/{deal['id']}/confirm",
            json={"revision": 1},
            headers=_auth(api_seed[role]["token"]),
        )
        assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["confirmations"]["dealer"]["confirmed_by_name"] == "dealer"
    final_url = f"/api/v1/admin/monetization/deals/{deal['id']}/confirm"
    pending = await client.post(
        final_url, json={"revision": 1}, headers=_auth(employee_token)
    )
    assert pending.status_code == 409 and "дистрибьютор" in pending.json()["detail"]
    distributor = await client.post(
        f"{DEALS}/{deal['id']}/confirm",
        json={"revision": 1},
        headers=_auth(api_seed["distributor"]["token"]),
    )
    assert distributor.status_code == 200, distributor.text
    paid = await client.post(
        final_url, json={"revision": 1}, headers=_auth(employee_token)
    )
    assert paid.status_code == 200 and paid.json()["status"] == "paid"
    uploaded = await client.post(
        f"{DEALS}/{deal['id']}/documents",
        data={"revision": "1"},
        files={"files": ("late.txt", b"After completion", "text/plain")},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert uploaded.status_code == 409, uploaded.text

async def test_commission_inbox_before_lca_and_server_creation_capability(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any],
    client_token: str,
) -> None:
    from infrastructure.models.applications import LeasingCompanyApplication

    application_id = await _application(db_session, api_seed)
    url = f"/api/v1/monetization/applications/{application_id}/condition-requests"
    dealer_headers = _auth(api_seed["dealer"]["token"])
    empty = await client.get(url, headers=dealer_headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["can_request"] is True
    sent = await client.post(
        f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests",
        json={"leasing_company_ids": [str(api_seed["leasing"]["leasing_company_id"])],
              "calc_type": "percent", "value": "3"}, headers=dealer_headers,
    )
    assert sent.status_code == 201, sent.text
    inbox_url = "/api/v1/monetization/condition-requests"
    inbox = await client.get(inbox_url, headers=_auth(api_seed["leasing"]["token"]))
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["pagination"]["total"] == 1
    assert inbox.json()["items"][0]["application_id"] == str(application_id)
    assert "application_number" in inbox.json()["items"][0]
    foreign = await client.get(inbox_url, headers=_auth(api_seed["other_leasing"]["token"]))
    assert foreign.status_code == 200 and foreign.json()["items"] == []
    denied = await client.get(inbox_url, headers=_auth(client_token))
    assert denied.status_code == 403
    outsider = await client.get(url, headers=_auth(api_seed["outsider"]["token"]))
    assert outsider.json() == {"items": [], "can_request": False, "can_negotiate": False}
    db_session.add(LeasingCompanyApplication(
        id=uuid4(), application_id=application_id,
        leasing_company_id=api_seed["leasing"]["leasing_company_id"],
    ))
    await db_session.commit()
    distributed = await client.get(url, headers=dealer_headers)
    assert distributed.json()["can_request"] is False
    assert len(distributed.json()["items"]) == 1


async def test_notification_company_selector_revalidates_membership_without_switching(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any],
) -> None:
    from infrastructure.models.users import UserCompany

    application_id = await _application(db_session, api_seed)
    dealer_headers = _auth(api_seed["dealer"]["token"])
    created = await client.post(
        f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests",
        json={"leasing_company_ids": [str(api_seed["leasing"]["leasing_company_id"])],
              "calc_type": "amount", "value": "1000"}, headers=dealer_headers,
    )
    assert created.status_code == 201, created.text
    user_id = api_seed["outsider"]["user_id"]
    company_id = api_seed["dealer"]["company_id"]
    headers = _auth(api_seed["outsider"]["token"])
    url = f"/api/v1/monetization/condition-requests?notification_company_id={company_id}"
    rejected = await client.get(url, headers=headers)
    assert rejected.status_code == 403, rejected.text
    membership = UserCompany(user_id=user_id, company_id=company_id,
                             can_view_applications=True, can_create_applications=True)
    db_session.add(membership)
    await db_session.commit()
    allowed = await client.get(url, headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["items"][0]["application_id"] == str(application_id)
    ordinary = await client.get("/api/v1/monetization/condition-requests", headers=headers)
    assert ordinary.json()["items"] == []
    membership.can_view_applications = False
    await db_session.commit()
    revoked = await client.get(url, headers=headers)
    assert revoked.status_code == 403, revoked.text
async def test_lc_card_selector_uses_canonical_lc_and_rejects_conflicting_company(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any],
) -> None:
    from infrastructure.models.companies import LeasingCompanyUser

    application_id = await _application(db_session, api_seed)
    target = api_seed["leasing"]
    response = await client.post(
        f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests",
        json={"leasing_company_ids": [str(target["leasing_company_id"])],
              "calc_type": "percent", "value": "1"},
        headers=_auth(api_seed["dealer"]["token"]),
    )
    assert response.status_code == 201, response.text
    actor = api_seed["other_leasing"]
    headers = _auth(actor["token"])
    url = (f"/api/v1/monetization/applications/{application_id}/condition-requests"
           f"?leasing_company_id={target['leasing_company_id']}")
    denied = await client.get(url, headers=headers)
    assert denied.status_code == 403, denied.text
    db_session.add(LeasingCompanyUser(user_id=actor["user_id"],
                                     leasing_company_id=target["leasing_company_id"]))
    await db_session.commit()
    allowed = await client.get(url, headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert len(allowed.json()["items"]) == 1
    assert allowed.json()["can_request"] is False
    conflicting = await client.get(
        url + f"&notification_company_id={actor['company_id']}", headers=headers)
    assert conflicting.status_code == 403, conflicting.text


async def _set_read_only(session: AsyncSession, member: dict[str, Any]) -> None:
    from infrastructure.models.users import UserCompany

    session.add(UserCompany(user_id=member["user_id"], company_id=member["company_id"],
                            can_view_applications=True, can_create_applications=False))
    await session.commit()


@pytest.mark.parametrize("role", ["dealer", "leasing", "distributor"])
async def test_read_only_member_reads_but_cannot_confirm_or_upload(
    client: AsyncClient, db_session: AsyncSession, employee_token: str,
    api_seed: dict[str, Any], memory_storage: ObjectStorage, role: str,
) -> None:
    sources = _program(api_seed)["sources"]
    sources[0]["incomes"][0]["participant_type"] = "distributor"
    deal = await _captured_deal(client, db_session, employee_token, api_seed, sources=sources)
    member = api_seed[role]
    await _set_read_only(db_session, member)
    headers = _auth(member["token"])
    detail = await client.get(f"{DEALS}/{deal['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_confirm"] is False
    assert detail.json()["can_upload_documents"] is False
    confirmed = await client.post(f"{DEALS}/{deal['id']}/confirm",
                                  json={"revision": 1}, headers=headers)
    assert confirmed.status_code == 403, confirmed.text
    uploaded = await client.post(f"{DEALS}/{deal['id']}/documents",
        data={"revision": "1"}, files={"files": ("denied.txt", b"No permission", "text/plain")},
        headers=headers)
    assert uploaded.status_code == 403, uploaded.text


async def test_distributor_loses_all_deal_access_after_dealer_leaves_group(
    client: AsyncClient, db_session: AsyncSession, employee_token: str,
    api_seed: dict[str, Any], memory_storage: ObjectStorage,
) -> None:
    import sqlalchemy as sa

    from infrastructure.models.support import DealerGroupMember

    sources = _program(api_seed)["sources"]
    sources[0]["incomes"][0]["participant_type"] = "distributor"
    deal = await _captured_deal(client, db_session, employee_token, api_seed, sources=sources)
    uploaded = await client.post(f"{DEALS}/{deal['id']}/documents",
        data={"revision": "1"}, files={"files": ("approval.txt", b"Approval", "text/plain")},
        headers=_auth(api_seed["dealer"]["token"]))
    assert uploaded.status_code == 200, uploaded.text
    headers = _auth(api_seed["distributor"]["token"])
    before = await client.get(f"{DEALS}/{deal['id']}", headers=headers)
    assert before.status_code == 200
    await db_session.execute(sa.delete(DealerGroupMember).where(
        DealerGroupMember.dealer_group_id == api_seed["dealer_group_id"]))
    await db_session.commit()
    listing = await client.get(DEALS, headers=headers)
    assert listing.status_code == 200 and listing.json()["items"] == []
    detail = await client.get(f"{DEALS}/{deal['id']}", headers=headers)
    assert detail.status_code == 404, detail.text
    downloaded = await client.get(uploaded.json()["documents"][0]["download_url"], headers=headers)
    assert downloaded.status_code == 404, downloaded.text
    confirmation = await client.post(f"{DEALS}/{deal['id']}/confirm",
                                     json={"revision": 1}, headers=headers)
    assert confirmation.status_code == 404, confirmation.text
    new_file = await client.post(f"{DEALS}/{deal['id']}/documents",
        data={"revision": "1"}, files={"files": ("denied.txt", b"No access", "text/plain")},
        headers=headers)
    assert new_file.status_code == 404, new_file.text


async def test_read_only_dealer_cannot_create_or_decide_commission(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any],
) -> None:
    application_id = await _application(db_session, api_seed)
    payload = {"leasing_company_ids": [str(api_seed["leasing"]["leasing_company_id"])],
               "calc_type": "amount", "value": "1000"}
    create_url = f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests"
    created = await client.post(create_url, json=payload, headers=_auth(api_seed["dealer"]["token"]))
    assert created.status_code == 201, created.text
    request = created.json()["requests"][0]
    responded = await client.post(
        f"/api/v1/leasing-company/monetization/condition-requests/{request['id']}/respond",
        json={"decision": "countered", "counter_calc_type": "amount", "counter_value": "900"},
        headers=_auth(api_seed["leasing"]["token"]))
    assert responded.status_code == 200, responded.text
    await _set_read_only(db_session, api_seed["dealer"])
    headers = _auth(api_seed["dealer"]["token"])
    listing = await client.get(
        f"/api/v1/monetization/applications/{application_id}/condition-requests", headers=headers)
    assert listing.status_code == 200 and len(listing.json()["items"]) == 1
    assert listing.json()["can_request"] is False
    assert listing.json()["can_negotiate"] is False
    denied = await client.post(create_url, json=payload, headers=headers)
    assert denied.status_code == 403, denied.text
    for decision in ("accept_counter", "reject"):
        denied = await client.post(
            f"/api/v1/dealer/monetization/condition-requests/{request['id']}/decision",
            json={"decision": decision}, headers=headers)
        assert denied.status_code == 403, denied.text


async def test_read_only_leasing_cannot_respond_to_commission(
    client: AsyncClient, db_session: AsyncSession, api_seed: dict[str, Any],
) -> None:
    application_id = await _application(db_session, api_seed)
    created = await client.post(
        f"/api/v1/dealer/monetization/applications/{application_id}/condition-requests",
        json={"leasing_company_ids": [str(api_seed["leasing"]["leasing_company_id"])],
              "calc_type": "amount", "value": "1000"}, headers=_auth(api_seed["dealer"]["token"]))
    assert created.status_code == 201, created.text
    request = created.json()["requests"][0]
    await _set_read_only(db_session, api_seed["leasing"])
    headers = _auth(api_seed["leasing"]["token"])
    listing = await client.get(
        f"/api/v1/monetization/applications/{application_id}/condition-requests", headers=headers)
    assert listing.status_code == 200 and len(listing.json()["items"]) == 1
    assert listing.json()["can_negotiate"] is False
    for decision in ("accepted", "rejected", "countered"):
        denied = await client.post(
            f"/api/v1/leasing-company/monetization/condition-requests/{request['id']}/respond",
            json={"decision": decision, **({"counter_calc_type": "amount", "counter_value": "900"}
                 if decision == "countered" else {})}, headers=headers)
        assert denied.status_code == 403, denied.text


async def test_read_only_carcraft_employee_cannot_mutate_conditions_or_deals(
    client: AsyncClient, db_session: AsyncSession, employee_token: str,
    employee_user: User, api_seed: dict[str, Any], memory_storage: ObjectStorage,
) -> None:
    from infrastructure.models.users import UserCompany

    deal = await _captured_deal(client, db_session, employee_token, api_seed)
    assert deal["can_adjust"] is True
    company = Company(id=uuid4(), name="Internal read-only", company_type="other")
    db_session.add(company)
    await db_session.flush()
    employee_user.company_id = company.id
    db_session.add(UserCompany(user_id=employee_user.id, company_id=company.id,
                              can_view_applications=True, can_create_applications=False))
    await db_session.commit()
    token, _ = generate_tokens(employee_user.id, "carcraft_employee", company.id)
    headers = _auth(token)
    detail = await client.get(f"{DEALS}/{deal['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_confirm"] is False
    assert detail.json()["can_upload_documents"] is False
    assert detail.json()["can_adjust"] is False
    programs = await client.get(PROGRAMS, headers=headers)
    assert programs.status_code == 200 and programs.json()["can_manage"] is False
    program = await client.get(f"{PROGRAMS}/{deal['program_id']}", headers=headers)
    assert program.status_code == 200 and program.json()["can_manage"] is False
    created = await client.post(PROGRAMS, json=_program(api_seed, status="inactive"), headers=headers)
    assert created.status_code == 403, created.text
    status = await client.patch(f"{PROGRAMS}/{deal['program_id']}",
                               json={"status": "inactive"}, headers=headers)
    assert status.status_code == 403, status.text
    adjusted = await client.post(
        f"/api/v1/admin/monetization/deals/{deal['id']}/adjust-conditions",
        json={"revision": 1, "items": [{"deal_participant_amount_id": deal["expenses"][0]["id"],
                                       "new_value": "2000"}]}, headers=headers)
    assert adjusted.status_code == 403, adjusted.text
    confirmed = await client.post(f"/api/v1/admin/monetization/deals/{deal['id']}/confirm",
                                  json={"revision": 1}, headers=headers)
    assert confirmed.status_code == 403, confirmed.text
    uploaded = await client.post(f"{PROGRAMS}/{deal['program_id']}/contracts",
        files={"files": ("denied.txt", b"No permission", "text/plain")}, headers=headers)
    assert uploaded.status_code == 403, uploaded.text

    old_session = await client.get(PROGRAMS, headers=_auth(employee_token))
    assert old_session.status_code == 200 and old_session.json()["can_manage"] is False
    old_session_create = await client.post(PROGRAMS, json=_program(api_seed, status="inactive"),
                                          headers=_auth(employee_token))
    assert old_session_create.status_code == 403, old_session_create.text
