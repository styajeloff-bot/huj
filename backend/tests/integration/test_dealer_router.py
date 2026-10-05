"""Integration tests for /api/v1/dealer/* (Phase 5 E3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.users import User, VerificationCode

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession) -> User:
    u = User(
        phone="+76660000001",
        email="dealerrouter@test.local",
        name="Dealer Router",
        role="dealer",
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    return u


@pytest.fixture
def dealer_token(dealer_user: User) -> str:
    token, _ = generate_tokens(dealer_user.id, "dealer", None)
    return token


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_invite_client_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/dealer/invite-client", json={"phone": "+76660004567"}
    )
    assert response.status_code == 401


async def test_list_inventory_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dealer/inventory")
    assert response.status_code == 401


async def test_client_role_cannot_access_dealer(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/dealer/inventory", headers=_auth(client_token)
    )
    # Clients don't have VEHICLES_ADMIN scope.
    assert response.status_code == 403


async def test_client_role_cannot_invite(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/dealer/invite-client",
        json={"phone": "+76660004567"},
        headers=_auth(client_token),
    )
    # Clients hold APPLICATIONS_WRITE scope but fail role check inside router.
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# invite-client
# ---------------------------------------------------------------------------


async def test_invite_client_new_user(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_token: str,
) -> None:
    phone = "+76660003344"
    with patch(
        "application.commands.dealer.invite_client.sms_service.send_verification_sms",
        new=AsyncMock(),
    ):
        response = await client.post(
            "/api/v1/dealer/invite-client",
            json={"phone": phone, "name": "Имя"},
            headers=_auth(dealer_token),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_user"] is True

    created = (
        await db_session.execute(sa.select(User).where(User.phone == phone))
    ).scalars().first()
    assert created is not None

    code_row = (
        await db_session.execute(
            sa.select(VerificationCode).where(VerificationCode.phone == phone)
        )
    ).scalars().first()
    assert code_row is not None


async def test_invite_client_existing_phone_silent_noop(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_token: str,
) -> None:
    phone = "+76660004433"
    db_session.add(
        User(phone=phone, role="client", is_active=True, name="Existing")
    )
    await db_session.flush()

    with patch(
        "application.commands.dealer.invite_client.sms_service.send_verification_sms",
        new=AsyncMock(),
    ):
        response = await client.post(
            "/api/v1/dealer/invite-client",
            json={"phone": phone},
            headers=_auth(dealer_token),
        )
    assert response.status_code == 200
    assert response.json()["created_user"] is False


async def test_invite_client_invalid_phone_returns_400(
    client: AsyncClient, dealer_token: str
) -> None:
    response = await client.post(
        "/api/v1/dealer/invite-client",
        json={"phone": "bogus"},
        headers=_auth(dealer_token),
    )
    assert response.status_code == 400


