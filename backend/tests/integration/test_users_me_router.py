"""Integration tests for the unified ``/api/v1/users/me`` profile surface.

Phase 13 R13a — consolidates the former ``/client/profile``,
``/dealer/profile``, ``/distributor/profile`` endpoints into one
role-discriminated resource.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company, Distributor
from infrastructure.models.users import CompanySelectHistory, User, UserCompany
from infrastructure.repositories import (
    user_identity_verification_repository as verifications,
)

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures for the three role surfaces.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dealer_surface(
    db_session: AsyncSession,
) -> tuple[User, Company, str]:
    company = Company(name="Dealer Me Co", inn="7710999100", company_type="dealer")
    db_session.add(company)
    await db_session.flush()

    user = User(
        phone="+76660007701",
        email="me-dealer@test.local",
        name="Me Dealer",
        role="dealer",
        company_id=company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "dealer", company.id)
    return user, company, token


@pytest_asyncio.fixture
async def distributor_surface(
    db_session: AsyncSession,
) -> tuple[User, Company, str]:
    company = Company(
        name="Distr Me Co", inn="9998887770", company_type="distributor"
    )
    db_session.add(company)
    await db_session.flush()

    row = Distributor(company_id=company.id, is_active=True)
    db_session.add(row)
    await db_session.flush()

    user = User(
        phone="+76660007702",
        email="me-distr@test.local",
        name="Me Distr",
        role="distributor",
        company_id=company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "distributor", company.id)
    return user, company, token


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------


async def test_get_me_unauthenticated_is_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_get_me_as_client_returns_client_role_specific(
    client: AsyncClient, client_token: str, client_user: User
) -> None:
    response = await client.get(
        "/api/v1/users/me", headers=_auth(client_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(client_user.id)
    assert body["phone"] == client_user.phone
    assert body["role"] == "client"
    # client_profiles row not yet created → all role-specific fields None
    assert body["role_specific"] is not None
    assert body["role_specific"]["client_type"] is None
    assert body["role_specific"]["profile_id"] is None
    assert body["role_specific"]["identity_verified"] is False
    assert body["role_specific"]["identity_verified_at"] is None
    assert body["role_specific"]["identity_verification_provider"] is None


async def test_get_me_as_client_returns_mobile_id_verified_state(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    attempt = await verifications.create_attempt(
        db_session,
        user_id=client_user.id,
        provider=verifications.PROVIDER_MOBILE_ID,
        phone_number=client_user.phone,
        expires_at=datetime.now(UTC),
    )
    await verifications.mark_verified(
        db_session,
        verification_id=attempt["id"],
        mobile_id_sub="sub-users-me",
        phone_number=client_user.phone,
        birthdate_match="Y",
    )

    response = await client.get("/api/v1/users/me", headers=_auth(client_token))

    assert response.status_code == 200, response.text
    role_specific = response.json()["role_specific"]
    assert role_specific["identity_verified"] is True
    assert role_specific["identity_verified_at"] is not None
    assert role_specific["identity_verification_provider"] == "mobile_id"


async def test_patch_me_identity_fields_expire_mobile_id_verified_state(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    attempt = await verifications.create_attempt(
        db_session,
        user_id=client_user.id,
        provider=verifications.PROVIDER_MOBILE_ID,
        phone_number=client_user.phone,
        expires_at=datetime.now(UTC),
    )
    await verifications.mark_verified(
        db_session,
        verification_id=attempt["id"],
        mobile_id_sub="sub-users-me-reset",
        phone_number=client_user.phone,
        birthdate_match="Y",
    )

    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(client_token),
        json={"name": "Профиль С Новым ФИО"},
    )

    assert response.status_code == 200, response.text
    role_specific = response.json()["role_specific"]
    assert role_specific["identity_verified"] is False
    assert role_specific["identity_verified_at"] is None
    assert role_specific["identity_verification_provider"] is None

    latest = await verifications.get_latest_for_user(
        db_session,
        user_id=client_user.id,
        provider=verifications.PROVIDER_MOBILE_ID,
    )
    assert latest is not None
    assert latest["status"] == verifications.STATUS_EXPIRED
    assert latest["failure_code"] == "profile_identity_changed"


async def test_get_me_as_dealer_returns_company_and_stats(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_surface: tuple[User, Company, str],
) -> None:
    user, company, token = dealer_surface
    db_session.add(
        LeasingApplication(
            company_id=company.id,
            status="active",
            total_amount=Decimal("500"),
            email="some@x.y",
        )
    )
    await db_session.flush()

    response = await client.get("/api/v1/users/me", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["role"] == "dealer"
    rs = body["role_specific"]
    assert rs["company"]["id"] == str(company.id)
    assert rs["stats"]["total_applications"] == 1
    assert rs["stats"]["total_sales"] == 1


async def test_get_me_as_distributor_returns_company_and_distributor_block(
    client: AsyncClient,
    distributor_surface: tuple[User, Company, str],
) -> None:
    user, company, token = distributor_surface
    response = await client.get("/api/v1/users/me", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["role"] == "distributor"
    rs = body["role_specific"]
    assert rs["company"]["id"] == str(company.id)
    assert rs["distributor"]["company_id"] == str(company.id)


async def test_auth_me_uses_selected_user_company_permissions_without_primary_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    company = Company(name="Selected Join Co", inn="7711223344", company_type="other")
    db_session.add(company)
    await db_session.flush()
    user = User(
        phone="+76660007703",
        email="selected-join@test.local",
        name="Selected Join User",
        role="client",
        company_id=None,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=company.id,
            sub_role="employee",
            can_view_applications=False,
            can_create_applications=False,
        )
    )
    db_session.add(CompanySelectHistory(user_id=user.id, company_id=company.id))
    await db_session.flush()

    token, _ = generate_tokens(user.id, "client", None)
    response = await client.get("/api/v1/auth/me", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()["user"]
    assert body["company_id"] == str(company.id)
    assert body["sub_role"] == "employee"
    assert body["can_view_applications"] is False
    assert body["can_create_applications"] is False


async def test_add_my_new_company_grants_administrator_permissions(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    response = await client.post(
        "/api/v1/users/me/companies",
        headers=_auth(client_token),
        json={
            "company": {
                "name": "Brand New Self Company",
                "inn": "7711223355",
                "entity_type": "other",
            }
        },
    )

    assert response.status_code == 201, response.text
    company = (
        await db_session.execute(select(Company).where(Company.inn == "7711223355"))
    ).scalars().one()
    link = (
        await db_session.execute(
            select(UserCompany).where(
                UserCompany.user_id == client_user.id,
                UserCompany.company_id == company.id,
            )
        )
    ).scalars().one()
    assert link.sub_role == "administrator"
    assert link.can_view_applications is True
    assert link.can_create_applications is True
    await db_session.refresh(client_user)
    assert str(client_user.company_id) == str(company.id)


async def test_add_my_company_does_not_replace_existing_primary_company(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    primary = Company(
        name="Existing Primary Company",
        inn="7711223388",
        company_type="other",
        is_active=True,
    )
    db_session.add(primary)
    await db_session.flush()
    client_user.company_id = primary.id
    await db_session.flush()

    response = await client.post(
        "/api/v1/users/me/companies",
        headers=_auth(client_token),
        json={
            "company": {
                "name": "Second Client Company",
                "inn": "7711223377",
                "entity_type": "other",
            }
        },
    )

    assert response.status_code == 201, response.text
    await db_session.refresh(client_user)
    assert client_user.company_id == primary.id


async def test_add_my_existing_company_links_blocked_employee(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    company = Company(
        name="Existing Self Company",
        inn="7711223366",
        company_type="other",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    response = await client.post(
        "/api/v1/users/me/companies",
        headers=_auth(client_token),
        json={
            "company": {
                "name": company.name,
                "inn": company.inn,
                "entity_type": "other",
            }
        },
    )

    assert response.status_code == 201, response.text
    link = (
        await db_session.execute(
            select(UserCompany).where(
                UserCompany.user_id == client_user.id,
                UserCompany.company_id == company.id,
            )
        )
    ).scalars().one()
    assert link.sub_role == "employee"
    assert link.can_view_applications is False
    assert link.can_create_applications is False


# ---------------------------------------------------------------------------
# PATCH /users/me
# ---------------------------------------------------------------------------


async def test_patch_me_base_fields_client(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(client_token),
        json={"name": "Новое Имя", "email": "new@test.local"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Новое Имя"
    assert body["email"] == "new@test.local"


async def test_patch_me_client_with_role_specific_creates_client_profile(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(client_token),
        json={
            "role_specific": {
                "client_type": "individual",
                "inn": "771234567890",
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    rs = body["role_specific"]
    assert rs["client_type"] == "individual"
    assert rs["inn"] == "771234567890"
    assert rs["profile_id"] is not None


async def test_patch_me_dealer_with_role_specific_updates_company(
    client: AsyncClient,
    dealer_surface: tuple[User, Company, str],
) -> None:
    _, _, token = dealer_surface
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(token),
        json={
            "name": "Dealer New",
            "role_specific": {
                "company": {"name": "Новое ООО", "phone": "+7 495 111-22-33"}
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Dealer New"
    assert body["role_specific"]["company"]["name"] == "Новое ООО"
    assert body["role_specific"]["company"]["phone"] == "+7 495 111-22-33"


async def test_patch_me_wrong_role_specific_for_client_is_422(
    client: AsyncClient, client_token: str
) -> None:
    # Sending a dealer-shaped role_specific block (has ``company``) while
    # authenticated as a client must be rejected.
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(client_token),
        json={"role_specific": {"company": {"name": "Hack"}}},
    )
    assert response.status_code == 422, response.text


async def test_patch_me_wrong_role_specific_for_dealer_is_422(
    client: AsyncClient,
    dealer_surface: tuple[User, Company, str],
) -> None:
    _, _, token = dealer_surface
    # Sending a client-shaped role_specific block (``inn`` at top level)
    # while authenticated as a dealer must be rejected.
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(token),
        json={"role_specific": {"inn": "123456"}},
    )
    assert response.status_code == 422, response.text


async def test_patch_me_distributor_role_specific_is_422(
    client: AsyncClient,
    distributor_surface: tuple[User, Company, str],
) -> None:
    _, _, token = distributor_surface
    # Distributor self-update via /users/me is intentionally unsupported
    # (legacy /distributor/profile had no PUT either). Any role_specific
    # block → 422.
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(token),
        json={"role_specific": {"company": {"name": "x"}}},
    )
    assert response.status_code == 422, response.text


async def test_patch_me_distributor_base_fields_ok(
    client: AsyncClient,
    distributor_surface: tuple[User, Company, str],
) -> None:
    user, _, token = distributor_surface
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(token),
        json={"name": "Distr Updated"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["name"] == "Distr Updated"


async def test_patch_me_validation_422(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.patch(
        "/api/v1/users/me",
        headers=_auth(client_token),
        json={"role_specific": {"client_type": "alien"}},
    )
    assert response.status_code == 422


async def test_patch_me_unauthenticated_is_401(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/v1/users/me", json={"name": "x"}
    )
    assert response.status_code == 401
