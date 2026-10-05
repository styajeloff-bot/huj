"""Tests for the security-notification consumer handler.

Drives ``handle_security_notification`` directly with fake event dicts,
stubbing out the email + SMS side-effect functions so the real SMTP/SMS
gateway never runs. The Redis throttle is exercised via the
``fakeredis`` fixture installed by ``conftest.py``.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.messaging.consumers import auth_notifications
from infrastructure.messaging.consumers.auth_notifications import (
    handle_security_notification,
)
from infrastructure.models.users import User, UserSession
from infrastructure.settings import settings


class _Spy:
    """Minimal async spy — records each call for later assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))

    @property
    def call_count(self) -> int:
        return len(self.calls)


@pytest.fixture
def _patch_session_factory(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route the handler's ``AsyncSessionLocal()`` calls to the test session.

    The production handler opens fresh sessions via ``AsyncSessionLocal``;
    tests use a rolled-back transaction, so we yield the shared test
    session from an async context manager instead.
    """

    @asynccontextmanager
    async def _factory() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    monkeypatch.setattr(auth_notifications, "AsyncSessionLocal", _factory)


@pytest_asyncio.fixture
async def notif_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000001",
        email="secnotify@test.local",
        name="Sec Notify",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture(autouse=True)
def _install_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, _Spy]:
    spies = {
        "new_device": _Spy(),
        "mfa_disabled": _Spy(),
        "sessions_revoked_all": _Spy(),
        "refresh_reuse": _Spy(),
    }
    monkeypatch.setattr(
        auth_notifications,
        "send_new_device_notification",
        spies["new_device"],
    )
    monkeypatch.setattr(
        auth_notifications,
        "send_mfa_disabled_notification",
        spies["mfa_disabled"],
    )
    monkeypatch.setattr(
        auth_notifications,
        "send_sessions_revoked_all_notification",
        spies["sessions_revoked_all"],
    )
    monkeypatch.setattr(
        auth_notifications,
        "send_refresh_reuse_notification",
        spies["refresh_reuse"],
    )
    return spies


# ---------------------------------------------------------------------------
# LOGIN_SUCCEEDED → new-device detection + throttle
# ---------------------------------------------------------------------------


async def test_login_succeeded_brand_new_ip_triggers_new_device_alert(
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    event = {
        "event": "login.succeeded",
        "user_id": notif_user.id,
        "ip": "198.51.100.7",
        "user_agent": "pytest/1.0",
    }
    await handle_security_notification(event)

    spy = _install_spies["new_device"]
    assert spy.call_count == 1
    user_arg, session_arg = spy.calls[0][0]
    assert user_arg["id"] == notif_user.id
    assert session_arg["ip_address"] == "198.51.100.7"


async def test_login_succeeded_replay_throttled(
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    event = {
        "event": "login.succeeded",
        "user_id": notif_user.id,
        "ip": "198.51.100.8",
        "user_agent": "pytest/1.0",
    }
    await handle_security_notification(event)
    await handle_security_notification(event)  # replay — must be throttled

    assert _install_spies["new_device"].call_count == 1


async def test_login_succeeded_known_ip_skips_new_device_alert(
    db_session: AsyncSession,
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    # Seed a prior session at the same IP within the lookback window.
    prior = UserSession(
        user_id=notif_user.id,
        refresh_token_hash="hash-prior",
        ip_address="203.0.113.5",
        user_agent="pytest/0.9",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    db_session.add(prior)
    await db_session.flush()

    event = {
        "event": "login.succeeded",
        "user_id": notif_user.id,
        "ip": "203.0.113.5",
        "user_agent": "pytest/1.0",
    }
    await handle_security_notification(event)

    assert _install_spies["new_device"].call_count == 0


# ---------------------------------------------------------------------------
# MFA_DISABLED, SESSIONS_REVOKED_ALL, REFRESH_REUSE_DETECTED
# ---------------------------------------------------------------------------


async def test_mfa_disabled_dispatches_notification(
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    event = {"event": "mfa.disabled", "user_id": notif_user.id}
    await handle_security_notification(event)

    assert _install_spies["mfa_disabled"].call_count == 1
    (user_arg,), _ = _install_spies["mfa_disabled"].calls[0]
    assert user_arg["id"] == notif_user.id


async def test_sessions_revoked_all_dispatches_notification(
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    event = {"event": "sessions.revoked_all", "user_id": notif_user.id}
    await handle_security_notification(event)

    assert _install_spies["sessions_revoked_all"].call_count == 1


async def test_refresh_reuse_dispatches_notification_with_kill_count(
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    event = {
        "event": "refresh.reuse_detected",
        "user_id": notif_user.id,
        "sessions_killed": 3,
    }
    await handle_security_notification(event)

    spy = _install_spies["refresh_reuse"]
    assert spy.call_count == 1
    (user_arg, sessions_killed), _ = spy.calls[0]
    assert user_arg["id"] == notif_user.id
    assert sessions_killed == 3


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


async def test_disabled_flag_suppresses_all_dispatch(
    notif_user: User,
    monkeypatch: pytest.MonkeyPatch,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    monkeypatch.setattr(settings, "security_notifications_enabled", False)

    events = [
        {"event": "login.succeeded", "user_id": notif_user.id, "ip": "10.0.0.1"},
        {"event": "mfa.disabled", "user_id": notif_user.id},
        {"event": "sessions.revoked_all", "user_id": notif_user.id},
        {"event": "refresh.reuse_detected", "user_id": notif_user.id},
    ]
    for event in events:
        await handle_security_notification(event)

    for spy in _install_spies.values():
        assert spy.call_count == 0


# ---------------------------------------------------------------------------
# Malformed + unknown events — must not raise
# ---------------------------------------------------------------------------


async def test_unknown_event_silently_ignored(
    notif_user: User,
    _patch_session_factory: None,
    _install_spies: dict[str, _Spy],
) -> None:
    await handle_security_notification(
        {"event": "login.failed", "user_id": notif_user.id}
    )
    for spy in _install_spies.values():
        assert spy.call_count == 0


async def test_bad_payload_does_not_raise(
    _install_spies: dict[str, _Spy],
) -> None:
    await handle_security_notification("not a dict")  # type: ignore[arg-type]
    await handle_security_notification({"event": ""})
    await handle_security_notification({"event": "login.succeeded"})  # no user_id
    for spy in _install_spies.values():
        assert spy.call_count == 0
