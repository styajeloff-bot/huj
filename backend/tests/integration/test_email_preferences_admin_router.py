"""HTTP integration tests for /api/v1/email-preferences admin endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.email_preferences import EmailPreferences
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /test
# ---------------------------------------------------------------------------


async def test_test_endpoint_anon_returns_401(client: AsyncClient) -> None:
    response = await client.post("/api/v1/email-preferences/test")
    assert response.status_code == 401


async def test_test_endpoint_client_role_forbidden(
    client: AsyncClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    response = await client.post(
        "/api/v1/email-preferences/test", headers=_auth(client_token)
    )
    assert response.status_code == 403
    fake_send.assert_not_awaited()


async def test_test_endpoint_employee_golden_path(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    response = await client.post(
        "/api/v1/email-preferences/test", headers=_auth(employee_token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["sent_to"] == employee_user.email
    fake_send.assert_awaited_once()


async def test_test_endpoint_honours_override_to(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    response = await client.post(
        "/api/v1/email-preferences/test",
        headers=_auth(employee_token),
        json={"to": "elsewhere@example.com"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["sent_to"] == "elsewhere@example.com"
    fake_send.assert_awaited_once()
    assert fake_send.call_args[0][0] == "elsewhere@example.com"


async def test_test_endpoint_rejects_invalid_email(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    response = await client.post(
        "/api/v1/email-preferences/test",
        headers=_auth(employee_token),
        json={"to": "not-an-email"},
    )

    assert response.status_code == 422
    fake_send.assert_not_awaited()


async def test_test_endpoint_smtp_failure_returns_502(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(*_a: object, **_kw: object) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", _boom
    )

    response = await client.post(
        "/api/v1/email-preferences/test", headers=_auth(employee_token)
    )

    assert response.status_code == 502


async def test_test_endpoint_400_when_no_email_anywhere(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Employee without an email and no override → 400 from handler."""
    from infrastructure.auth import generate_tokens

    user = User(
        phone="+76660009999",
        email=None,
        name="Employee No Email",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token, _ = generate_tokens(user.id, "carcraft_employee", None)

    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    response = await client.post(
        "/api/v1/email-preferences/test", headers=_auth(token)
    )

    assert response.status_code == 400, response.text
    fake_send.assert_not_awaited()


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


async def test_stats_endpoint_anon_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/email-preferences/stats")
    assert response.status_code == 401


async def test_stats_endpoint_client_role_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/email-preferences/stats", headers=_auth(client_token)
    )
    assert response.status_code == 403


async def test_stats_endpoint_employee_returns_aggregates(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    client_user: User,
    other_user: User,
) -> None:
    db_session.add_all(
        [
            EmailPreferences(
                user_id=client_user.id, email_frequency="immediate"
            ),
            EmailPreferences(user_id=other_user.id, email_frequency="weekly"),
        ]
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/email-preferences/stats", headers=_auth(employee_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    stats = body["stats"]
    # Expected fields used by frontend (frontend/pages/settings/email.vue).
    for key in (
        "total_emails",
        "delivery_rate",
        "skipped_emails",
        "today_emails",
    ):
        assert key in stats
    assert not {"open_rate", "opened_emails", "clicked_emails", "delivered_emails"} & stats.keys()
    assert stats["subscribers"] == 2
    assert stats["frequency_breakdown"]["immediate"] == 1
    assert stats["frequency_breakdown"]["weekly"] == 1


# ---------------------------------------------------------------------------
# Phase 15 H3 — GET /logs was deleted; no admin UI consumed the list view.
# ---------------------------------------------------------------------------
