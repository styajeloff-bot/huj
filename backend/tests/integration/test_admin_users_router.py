"""Integration tests for admin-scope CRUD on ``/api/v1/users``.

Phase 13 R13b — consolidates the former ``/admin/users`` surface into the
main ``/users`` router (list / create / patch / delete). Auth scope:
``users:admin`` (employee-only). Self callers may only PATCH a base-field
subset of their own record via ``PATCH /users/{me_id}`` or
``PATCH /users/me``.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.users import User, UserCompany

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def target_dealer(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660001001",
        email="target-dealer@test.local",
        name="Target Dealer",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def sample_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Admin Users Company",
        inn="7799000001",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


# ---------------------------------------------------------------------------
# List users — GET /users
# ---------------------------------------------------------------------------


async def test_list_users_happy_path(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        "/api/v1/users",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "users" in body
    assert "pagination" in body


async def test_list_users_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users")
    assert response.status_code == 401


async def test_list_users_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get("/api/v1/users", headers=_auth(client_token))
    assert response.status_code == 403


async def test_list_users_filter_by_role(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
) -> None:
    response = await client.get(
        "/api/v1/users?role=dealer",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    users = response.json()["users"]
    assert any(str(u["id"]) == str(target_dealer.id) for u in users)
    assert all(u["role"] == "dealer" for u in users)


# ---------------------------------------------------------------------------
# Create user — POST /users
# ---------------------------------------------------------------------------


async def test_create_user_happy_path(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "New Admin-Created",
            "email": "newcreated@test.local",
            "phone": "+76660002001",
            "role": "dealer",
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["name"] == "New Admin-Created"
    assert body["user"]["role"] == "dealer"
    assert "Location" in {k.title() for k in response.headers}
    assert response.headers["location"].startswith("/api/v1/users/")


async def test_create_client_with_company_sets_primary_company_and_membership(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Client Company Owner",
            "email": "client-company-owner@test.local",
            "phone": "+76660002901",
            "role": "client",
            "company": {
                "name": "Client Company",
                "inn": "7701234567",
                "entity_type": "LEGAL",
            },
        },
        headers=_auth(employee_token),
    )

    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    user = await db_session.get(User, user_id)
    assert user is not None
    assert user.company_id is not None
    membership = await db_session.get(UserCompany, (user.id, user.company_id))
    assert membership is not None
    assert membership.sub_role == "administrator"
    assert membership.can_view_applications is True
    assert membership.can_create_applications is True


async def test_create_client_with_existing_company_grants_administrator_permissions(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    sample_company: Company,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Existing Company Client",
            "email": "existing-company-client@test.local",
            "phone": "+76660002904",
            "role": "client",
            "company": {
                "name": sample_company.name,
                "inn": sample_company.inn,
                "entity_type": "other",
            },
        },
        headers=_auth(employee_token),
    )

    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    user = await db_session.get(User, user_id)
    assert user is not None
    membership = await db_session.get(UserCompany, (user.id, sample_company.id))
    assert membership is not None
    assert membership.sub_role == "administrator"
    assert membership.can_view_applications is True
    assert membership.can_create_applications is True


async def test_create_user_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "x",
            "email": "x@test.local",
            "phone": "+76660002002",
            "role": "dealer",
        },
    )
    assert response.status_code == 401


async def test_create_user_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "x",
            "email": "x2@test.local",
            "phone": "+76660002003",
            "role": "dealer",
        },
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_create_user_duplicate_email_returns_409(
    client: AsyncClient,
    employee_token: str,
) -> None:
    phone1 = "+76660002010"
    phone2 = "+76660002011"
    email = "dup-email@test.local"

    first = await client.post(
        "/api/v1/users",
        json={
            "name": "First",
            "email": email,
            "phone": phone1,
            "role": "client",
        },
        headers=_auth(employee_token),
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/users",
        json={
            "name": "Second",
            "email": email,
            "phone": phone2,
            "role": "client",
        },
        headers=_auth(employee_token),
    )
    assert second.status_code == 409


async def test_create_user_invalid_phone_returns_422(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "Bad Phone",
            "email": "badphone@test.local",
            "phone": "not-a-phone",
            "role": "client",
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Update user — PATCH /users/{user_id}
# ---------------------------------------------------------------------------


async def test_update_user_happy_path(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{target_dealer.id}",
        json={"name": "Renamed Dealer"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert response.json()["user"]["name"] == "Renamed Dealer"


async def test_update_user_change_email_and_role(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{target_dealer.id}",
        json={"email": "renamed-dealer@test.local", "role": "client"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()["user"]
    assert body["email"] == "renamed-dealer@test.local"
    assert body["role"] == "client"


async def test_update_user_missing_returns_404(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{uuid4()}",
        json={"name": "x"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_update_user_anon_unauthorised(
    client: AsyncClient, target_dealer: User
) -> None:
    response = await client.patch(
        f"/api/v1/users/{target_dealer.id}",
        json={"name": "x"},
    )
    assert response.status_code == 401


async def test_update_user_client_patching_other_forbidden(
    client: AsyncClient,
    client_token: str,
    target_dealer: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{target_dealer.id}",
        json={"name": "Hack"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_update_user_self_base_fields_ok(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{client_user.id}",
        json={"name": "Self Renamed"},
        headers=_auth(client_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["name"] == "Self Renamed"


async def test_update_user_self_role_forbidden(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{client_user.id}",
        json={"role": "carcraft_employee"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_update_user_self_status_forbidden(
    client: AsyncClient,
    client_token: str,
    client_user: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{client_user.id}",
        json={"status": "disabled"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_admin_cannot_disable_self(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{employee_user.id}",
        json={"status": "disabled"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 403


async def test_update_user_status_disabled_flips_is_active(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
    db_session: AsyncSession,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{target_dealer.id}",
        json={"status": "disabled"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(target_dealer)
    assert target_dealer.is_active is False


async def test_update_client_company_by_id_updates_primary_and_links_membership(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    initial_company = Company(
        name="Initial Client Co",
        inn="7701234521",
        company_type="other",
        is_active=True,
    )
    new_company = Company(
        name="New Client Co",
        inn="7701234522",
        company_type="other",
        is_active=True,
    )
    db_session.add_all([initial_company, new_company])
    await db_session.flush()

    target = User(
        phone="+76660003001",
        email="update-client-by-id@test.local",
        name="Client To Update Company ID",
        role="client",
        company_id=initial_company.id,
        is_active=True,
    )
    db_session.add(target)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=target.id,
            company_id=initial_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers=_auth(employee_token),
        json={"company_id": str(new_company.id)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["company_id"] == str(new_company.id)

    await db_session.refresh(target)
    assert target.company_id == new_company.id

    membership = await db_session.get(UserCompany, (target.id, new_company.id))
    assert membership is not None
    assert membership.sub_role == "administrator"
    assert membership.can_view_applications is True
    assert membership.can_create_applications is True


async def test_update_client_company_by_object_creates_and_links_membership(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    target = User(
        phone="+76660003002",
        email="update-client-by-obj@test.local",
        name="Client To Update Company Obj",
        role="client",
        is_active=True,
    )
    db_session.add(target)
    await db_session.flush()

    company_payload = {
        "name": "Newly Created Client Company",
        "inn": "7701234523",
        "entity_type": "LEGAL",
    }

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers=_auth(employee_token),
        json={"company": company_payload},
    )
    assert response.status_code == 200, response.text
    updated_user = response.json()["user"]
    assert updated_user["company_id"] is not None
    new_company_id = UUID(updated_user["company_id"])

    await db_session.refresh(target)
    assert target.company_id == new_company_id

    created_company = await db_session.get(Company, new_company_id)
    assert created_company is not None
    assert created_company.name == "Newly Created Client Company"
    assert created_company.inn == "7701234523"

    membership = await db_session.get(UserCompany, (target.id, new_company_id))
    assert membership is not None
    assert membership.sub_role == "administrator"
    assert membership.can_view_applications is True
    assert membership.can_create_applications is True


async def test_update_client_role_to_dealer_with_company_id_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    client_co = Company(
        name="Old Client Company",
        inn="7701234524",
        company_type="other",
        is_active=True,
    )
    dealer_co = Company(
        name="New Dealer Company",
        inn="7701234525",
        company_type="dealer",
        is_active=True,
    )
    db_session.add_all([client_co, dealer_co])
    await db_session.flush()

    target = User(
        phone="+76660003003",
        email="client-to-dealer@test.local",
        name="Client Switching To Dealer",
        role="client",
        company_id=client_co.id,
        is_active=True,
    )
    db_session.add(target)
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers=_auth(employee_token),
        json={
            "role": "dealer",
            "company_id": str(dealer_co.id),
        },
    )
    assert response.status_code == 200, response.text
    user_data = response.json()["user"]
    assert user_data["role"] == "dealer"
    assert user_data["company_id"] == str(dealer_co.id)

    await db_session.refresh(target)
    assert target.role == "dealer"
    assert target.company_id == dealer_co.id


async def test_update_client_company_both_object_and_id_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    sample_company: Company,
) -> None:
    target = User(
        phone="+76660003004",
        email="both-company-fields@test.local",
        name="Both Company Fields User",
        role="client",
        is_active=True,
    )
    db_session.add(target)
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers=_auth(employee_token),
        json={
            "company_id": str(sample_company.id),
            "company": {
                "name": "Duplicate Target Co",
                "inn": "7701234526",
                "entity_type": "LEGAL",
            },
        },
    )
    assert response.status_code == 422, response.text


async def test_update_client_company_object_for_non_client_returns_400(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
) -> None:
    response = await client.patch(
        f"/api/v1/users/{target_dealer.id}",
        headers=_auth(employee_token),
        json={
            "company": {
                "name": "Dealer Cannot Link By Object",
                "inn": "7701234527",
                "entity_type": "LEGAL",
            },
        },
    )
    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == "Компанию объектом можно привязать только клиенту"
    )


# ---------------------------------------------------------------------------
# Delete user (soft-delete) — DELETE /users/{user_id}
# ---------------------------------------------------------------------------


async def test_delete_user_soft_delete(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
    db_session: AsyncSession,
) -> None:
    response = await client.delete(
        f"/api/v1/users/{target_dealer.id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    # Record still exists (soft-delete only).
    await db_session.refresh(target_dealer)
    assert target_dealer.is_active is False


async def test_delete_user_missing_returns_404(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.delete(
        f"/api/v1/users/{uuid4()}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_delete_user_client_forbidden(
    client: AsyncClient, client_token: str, target_dealer: User
) -> None:
    response = await client.delete(
        f"/api/v1/users/{target_dealer.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_admin_cannot_delete_self(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
) -> None:
    response = await client.delete(
        f"/api/v1/users/{employee_user.id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /users/:id — admin single-user read (Phase 14 G3 backport)
# ---------------------------------------------------------------------------


async def test_get_user_admin_happy_path(
    client: AsyncClient,
    employee_token: str,
    target_dealer: User,
) -> None:
    response = await client.get(
        f"/api/v1/users/{target_dealer.id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "user" in body
    assert body["user"]["id"] == str(target_dealer.id)
    assert body["user"]["role"] == "dealer"


async def test_get_user_admin_missing_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        f"/api/v1/users/{uuid4()}", headers=_auth(employee_token)
    )
    assert response.status_code == 404


async def test_get_user_admin_client_forbidden(
    client: AsyncClient, client_token: str, target_dealer: User
) -> None:
    response = await client.get(
        f"/api/v1/users/{target_dealer.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_get_user_admin_anon_unauthorised(
    client: AsyncClient, target_dealer: User
) -> None:
    response = await client.get(f"/api/v1/users/{target_dealer.id}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET/POST /users/:id/companies — admin client company links (#21822)
# ---------------------------------------------------------------------------


async def test_admin_can_list_and_add_client_company_without_replacing_primary(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    primary = Company(
        name="Primary Client Company",
        inn="7701234501",
        company_type="other",
        is_active=True,
    )
    db_session.add(primary)
    await db_session.flush()
    target = User(
        phone="+76660002122",
        email="client-companies-target@test.local",
        name="Client Companies Target",
        role="client",
        company_id=primary.id,
        is_active=True,
    )
    db_session.add(target)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=target.id,
            company_id=primary.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()

    listed = await client.get(
        f"/api/v1/users/{target.id}/companies",
        headers=_auth(employee_token),
    )

    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["companies"]] == [str(primary.id)]

    primary_change = await client.patch(
        f"/api/v1/users/{target.id}",
        headers=_auth(employee_token),
        json={"company_id": str(primary.id)},
    )
    assert primary_change.status_code == 200, primary_change.text

    added = await client.post(
        f"/api/v1/users/{target.id}/companies",
        headers=_auth(employee_token),
        json={
            "company": {
                "name": "Second Client Company",
                "inn": "7701234502",
                "entity_type": "other",
            }
        },
    )

    assert added.status_code == 201, added.text
    await db_session.refresh(target)
    assert target.company_id == primary.id
    assert len(added.json()["companies"]) == 2
    added_company_id = UUID(added.json()["company_id"])
    membership = await db_session.get(UserCompany, (target.id, added_company_id))
    assert membership is not None
    assert membership.sub_role == "administrator"
    assert membership.can_view_applications is True
    assert membership.can_create_applications is True

    target_without_primary = User(
        phone="+766****2123",
        email="client-without-primary@test.local",
        name="Client Without Primary",
        role="client",
        is_active=True,
    )
    db_session.add(target_without_primary)
    await db_session.flush()
    added_without_primary = await client.post(
        f"/api/v1/users/{target_without_primary.id}/companies",
        headers=_auth(employee_token),
        json={
            "company": {
                "name": "Only Linked Client Company",
                "inn": "7701234504",
                "entity_type": "other",
            }
        },
    )
    assert added_without_primary.status_code == 201, added_without_primary.text
    await db_session.refresh(target_without_primary)
    assert target_without_primary.company_id is None


async def test_admin_cannot_add_company_to_non_client(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    target_dealer: User,
) -> None:
    response = await client.post(
        f"/api/v1/users/{target_dealer.id}/companies",
        headers=_auth(employee_token),
        json={
            "company": {
                "name": "Should Not Link",
                "inn": "7701234503",
                "entity_type": "other",
            }
        },
    )

    assert response.status_code == 400, response.text
    assert await db_session.get(UserCompany, (target_dealer.id, uuid4())) is None


async def test_list_users_csv_format(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        "/api/v1/users?format=csv",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert response.content


async def test_import_users_csv_enqueues_async_job(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Import is now async: the route stores the CSV + enqueues a taskiq job."""
    import io
    from typing import Any

    kiq_calls: list[dict[str, Any]] = []

    async def _fake_kiq(*args: Any, **kwargs: Any) -> None:
        kiq_calls.append(kwargs)

    from application.tasks import data_import as data_import_tasks
    monkeypatch.setattr(data_import_tasks.process_upload, "kiq", _fake_kiq)

    class _FakeStorage:
        async def put(self, key: str, data: bytes, content_type: str) -> str:
            return f"http://fake/{key}"

    from infrastructure.services import object_storage as os_mod
    monkeypatch.setattr(os_mod._StorageState, "storage", _FakeStorage())

    csv_content = "phone;role;name;email;is_active\n+777****3001;client;Test User;test1@local.local;true"
    response = await client.post(
        "/api/v1/users/import",
        headers=_auth(employee_token),
        files={"file": ("users.csv", io.BytesIO(csv_content.encode("utf-8-sig")), "text/csv")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert "job_id" in body
    assert len(kiq_calls) == 1
    assert kiq_calls[0]["kind"] == "users"


async def test_import_users_csv_anon_unauthorised(client: AsyncClient) -> None:
    import io
    response = await client.post(
        "/api/v1/users/import",
        files={"file": ("users.csv", io.BytesIO(b"phone;role\n+777****3004;client"), "text/csv")},
    )
    assert response.status_code == 401
