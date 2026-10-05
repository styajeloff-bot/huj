"""Integration tests for /api/v1/exchange/dealer-options."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660006666",
        email="dealer-options@test.local",
        name="Dealer Options",
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
# CRUD happy paths + auth
# ---------------------------------------------------------------------------


async def test_create_dealer_option_happy_path(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "Зимняя резина", "sort_order": 1},
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["option"]["name"] == "Зимняя резина"
    assert body["option"]["sort_order"] == 1


async def test_create_dealer_option_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/exchange/dealer-options", json={"name": "x"}
    )
    assert response.status_code == 401


async def test_create_dealer_option_dealer_forbidden(
    client: AsyncClient, dealer_token: str
) -> None:
    response = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "x"},
        headers=_auth(dealer_token),
    )
    assert response.status_code == 403


async def test_create_dealer_option_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "x"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_create_dealer_option_duplicate_returns_409(
    client: AsyncClient, employee_token: str
) -> None:
    await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "Доставка"},
        headers=_auth(employee_token),
    )
    second = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "ДОСТАВКА"},
        headers=_auth(employee_token),
    )
    assert second.status_code == 409


async def test_list_dealer_options_returns_active_for_dealer(
    client: AsyncClient,
    employee_token: str,
    dealer_token: str,
) -> None:
    await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "Опция-1", "sort_order": 0},
        headers=_auth(employee_token),
    )
    response = await client.get(
        "/api/v1/exchange/dealer-options",
        headers=_auth(dealer_token),
    )
    assert response.status_code == 200
    names = [o["name"] for o in response.json()["options"]]
    assert "Опция-1" in names


async def test_list_dealer_options_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/exchange/dealer-options")
    assert response.status_code == 401


async def test_update_dealer_option_renames(
    client: AsyncClient, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "to-rename"},
        headers=_auth(employee_token),
    )
    option_id = create.json()["option"]["id"]
    response = await client.put(
        f"/api/v1/exchange/dealer-options/{option_id}",
        json={"name": "renamed-option"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert response.json()["option"]["name"] == "renamed-option"


async def test_update_dealer_option_unknown_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.put(
        f"/api/v1/exchange/dealer-options/{uuid4()}",
        json={"name": "x"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_delete_dealer_option_soft_deactivates(
    client: AsyncClient, employee_token: str, dealer_token: str
) -> None:
    create = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "to-erase"},
        headers=_auth(employee_token),
    )
    option_id = create.json()["option"]["id"]
    response = await client.delete(
        f"/api/v1/exchange/dealer-options/{option_id}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200

    listing = await client.get(
        "/api/v1/exchange/dealer-options", headers=_auth(dealer_token)
    )
    ids = [o["id"] for o in listing.json()["options"]]
    assert option_id not in ids


async def test_delete_dealer_option_unknown_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.delete(
        f"/api/v1/exchange/dealer-options/{uuid4()}",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_delete_dealer_option_dealer_forbidden(
    client: AsyncClient, dealer_token: str, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "dealer-cant-delete"},
        headers=_auth(employee_token),
    )
    option_id = create.json()["option"]["id"]
    response = await client.delete(
        f"/api/v1/exchange/dealer-options/{option_id}",
        headers=_auth(dealer_token),
    )
    assert response.status_code == 403


async def test_admin_can_list_all_with_include_inactive(
    client: AsyncClient, employee_token: str
) -> None:
    create = await client.post(
        "/api/v1/exchange/dealer-options",
        json={"name": "soon-inactive"},
        headers=_auth(employee_token),
    )
    option_id = create.json()["option"]["id"]
    await client.delete(
        f"/api/v1/exchange/dealer-options/{option_id}",
        headers=_auth(employee_token),
    )
    response = await client.get(
        "/api/v1/exchange/dealer-options?include_inactive=true",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    ids = [o["id"] for o in response.json()["options"]]
    assert option_id in ids
