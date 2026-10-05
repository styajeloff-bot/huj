"""Functional + integration tests for /api/v1/email-preferences."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.email_preferences import (
    UpdateEmailPreferencesCommand,
    handle_update_email_preferences,
)
from application.errors import ServiceError
from application.queries.email_preferences import (
    GetEmailPreferencesQuery,
    handle_get_email_preferences,
)
from infrastructure.models.email_preferences import EmailPreferences
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Functional — handlers in isolation
# ---------------------------------------------------------------------------


async def test_get_creates_defaults_on_first_access(
    db_session: AsyncSession, client_user: User
) -> None:
    prefs = await handle_get_email_preferences(
        GetEmailPreferencesQuery(user_id=client_user.id), db_session
    )
    assert prefs["user_id"] == client_user.id
    assert prefs["application_status_emails"] is True
    assert prefs["marketing_emails"] is False
    assert prefs["email_frequency"] == "immediate"


async def test_update_rejects_empty_payload(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(ServiceError) as exc:
        await handle_update_email_preferences(
            UpdateEmailPreferencesCommand(user_id=client_user.id, updates={}),
            db_session,
        )
    assert exc.value.status_code == 400


async def test_update_ignores_unknown_fields(
    db_session: AsyncSession, client_user: User
) -> None:
    prefs = await handle_update_email_preferences(
        UpdateEmailPreferencesCommand(
            user_id=client_user.id,
            updates={"marketing_emails": True, "hackme": "evil"},
        ),
        db_session,
    )
    assert prefs["marketing_emails"] is True


# ---------------------------------------------------------------------------
# Integration — full HTTP roundtrip
# ---------------------------------------------------------------------------


async def test_get_endpoint_returns_defaults(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/email-preferences", headers=_auth(client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    prefs = body["preferences"]
    assert prefs["application_status_emails"] is True
    assert prefs["email_frequency"] == "immediate"


async def test_get_endpoint_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/email-preferences")
    assert response.status_code == 401


async def test_put_endpoint_updates_preferences(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.put(
        "/api/v1/email-preferences",
        headers=_auth(client_token),
        json={"marketing_emails": True, "email_frequency": "weekly"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["preferences"]["marketing_emails"] is True
    assert body["preferences"]["email_frequency"] == "weekly"


async def test_put_endpoint_persists_changes(
    client: AsyncClient, client_token: str
) -> None:
    await client.put(
        "/api/v1/email-preferences",
        headers=_auth(client_token),
        json={"weekly_digest": False},
    )
    response = await client.get(
        "/api/v1/email-preferences", headers=_auth(client_token)
    )
    assert response.json()["preferences"]["weekly_digest"] is False


async def test_put_endpoint_rejects_unknown_field(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.put(
        "/api/v1/email-preferences",
        headers=_auth(client_token),
        json={"injection": True},
    )
    assert response.status_code == 422


async def test_put_endpoint_rejects_invalid_frequency(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.put(
        "/api/v1/email-preferences",
        headers=_auth(client_token),
        json={"email_frequency": "yearly"},
    )
    assert response.status_code == 422


async def test_users_are_isolated(
    client: AsyncClient,
    client_token: str,
    other_token: str,
    db_session: AsyncSession,
) -> None:
    await client.put(
        "/api/v1/email-preferences",
        headers=_auth(client_token),
        json={"marketing_emails": True},
    )
    response = await client.get(
        "/api/v1/email-preferences", headers=_auth(other_token)
    )
    # Other user must see defaults, not the first user's overrides.
    assert response.json()["preferences"]["marketing_emails"] is False

    # GET no longer creates a row for the second user.
    from sqlalchemy import select

    result = await db_session.execute(select(EmailPreferences))
    rows = result.scalars().all()
    assert len(rows) == 1
