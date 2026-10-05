"""Unit tests for email-preferences admin handlers (no HTTP layer)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.email_preferences import (
    SendTestEmailCommand,
    handle_send_test_email,
)
from application.errors import ServiceError
from application.queries.email_preferences import (
    GetEmailStatsQuery,
    handle_get_email_stats,
)
from infrastructure.models.email_preferences import EmailPreferences
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# send_test_email handler
# ---------------------------------------------------------------------------


async def test_send_test_email_uses_user_email_by_default(
    db_session: AsyncSession,
    employee_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    result = await handle_send_test_email(
        SendTestEmailCommand(user_id=employee_user.id, override_to=None),
        db_session,
    )

    assert result.sent_to == employee_user.email
    fake_send.assert_awaited_once()
    args = fake_send.call_args.args
    # send_email(to, subject, body) — positional.
    assert args[0] == employee_user.email
    assert args[1].startswith("CarCraft")


async def test_send_test_email_uses_override_when_present(
    db_session: AsyncSession,
    employee_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    result = await handle_send_test_email(
        SendTestEmailCommand(
            user_id=employee_user.id,
            override_to="override@example.com",
        ),
        db_session,
    )

    assert result.sent_to == "override@example.com"
    fake_send.assert_awaited_once()
    assert fake_send.call_args[0][0] == "override@example.com"


async def test_send_test_email_400_when_user_has_no_email(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # send_email must NOT be called when validation fails.
    fake_send = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", fake_send
    )

    user = User(
        phone="+76660000001",
        email=None,
        name="Employee No Email",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    with pytest.raises(ServiceError) as exc:
        await handle_send_test_email(
            SendTestEmailCommand(user_id=user.id, override_to=None),
            db_session,
        )

    assert exc.value.status_code == 400
    fake_send.assert_not_awaited()


async def test_send_test_email_502_on_smtp_failure(
    db_session: AsyncSession,
    employee_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(*_a: object, **_kw: object) -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "application.commands.email_preferences.send_email", _boom
    )

    with pytest.raises(ServiceError) as exc:
        await handle_send_test_email(
            SendTestEmailCommand(
                user_id=employee_user.id, override_to=None
            ),
            db_session,
        )

    assert exc.value.status_code == 502


# ---------------------------------------------------------------------------
# get_email_stats handler
# ---------------------------------------------------------------------------


async def test_get_email_stats_zero_when_no_subscribers(
    db_session: AsyncSession,
) -> None:
    stats = await handle_get_email_stats(GetEmailStatsQuery(), db_session)

    assert stats["subscribers"] == 0
    assert stats["frequency_breakdown"] == {
        "immediate": 0,
        "daily": 0,
        "weekly": 0,
    }
    # Log-derived metrics are zero until the table is migrated.
    assert stats["total_emails"] == 0
    assert stats["delivery_rate"] == 0.0


async def test_get_email_stats_aggregates_subscribers_by_frequency(
    db_session: AsyncSession,
    client_user: User,
    other_user: User,
    employee_user: User,
) -> None:
    db_session.add_all(
        [
            EmailPreferences(user_id=client_user.id, email_frequency="immediate"),
            EmailPreferences(user_id=other_user.id, email_frequency="weekly"),
            EmailPreferences(
                user_id=employee_user.id, email_frequency="weekly"
            ),
        ]
    )
    await db_session.flush()

    stats = await handle_get_email_stats(GetEmailStatsQuery(), db_session)

    assert stats["subscribers"] == 3
    assert stats["frequency_breakdown"]["immediate"] == 1
    assert stats["frequency_breakdown"]["weekly"] == 2
    assert stats["frequency_breakdown"]["daily"] == 0


# ---------------------------------------------------------------------------
# Phase 15 H3 — list_email_logs handler deleted alongside the /logs endpoint.
# ---------------------------------------------------------------------------
