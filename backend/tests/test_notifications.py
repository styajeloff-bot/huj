"""Functional + integration tests for /api/v1/notifications."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.notifications import (
    DeleteNotificationCommand,
    MarkNotificationReadCommand,
    handle_delete_notification,
    handle_mark_read,
)
from domain.entities.notification import (
    Notification as NotificationEntity,
)
from domain.entities.notification import (
    can_create_notifications,
)
from domain.errors import AccessDeniedError, NotificationNotFoundError
from infrastructure.models.misc import Notification
from infrastructure.models.users import User
from infrastructure.repositories import notification_repository as repo


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unit tests — domain entity
# ---------------------------------------------------------------------------


def test_ensure_owned_by_raises_for_stranger() -> None:
    notif = NotificationEntity(
        id=uuid4(),
        user_id=uuid4(),
        type="system",
        title="t",
        message="m",
        is_read=False,
        application_id=None,
        action_url=None,
        created_at=None,
        read_at=None,
    )
    with pytest.raises(AccessDeniedError):
        notif.ensure_owned_by(UUID("00000000-0000-0000-0000-000000000063"))


def test_can_create_notifications_only_for_carcraft_employee() -> None:
    assert can_create_notifications("carcraft_employee") is True
    assert can_create_notifications("client") is False
    assert can_create_notifications(None) is False


# ---------------------------------------------------------------------------
# Functional — command/query handlers
# ---------------------------------------------------------------------------


async def test_handle_mark_read_rejects_non_owner(
    db_session: AsyncSession, client_user: User, other_user: User
) -> None:
    notif_id = await repo.create_notification(
        db_session,
        user_id=client_user.id,
        notification_type="system",
        title="t",
        message="m",
    )
    with pytest.raises(AccessDeniedError):
        await handle_mark_read(
            MarkNotificationReadCommand(
                user_id=other_user.id, notification_id=notif_id
            ),
            db_session,
        )


async def test_handle_delete_missing_raises(
    db_session: AsyncSession, client_user: User
) -> None:
    with pytest.raises(NotificationNotFoundError):
        await handle_delete_notification(
            DeleteNotificationCommand(
                user_id=client_user.id, notification_id=uuid4()
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Integration — HTTP
# ---------------------------------------------------------------------------


async def _seed(
    db_session: AsyncSession, user_id: UUID, *, count: int = 3
) -> list[UUID]:
    ids: list[UUID] = []
    for i in range(count):
        nid = await repo.create_notification(
            db_session,
            user_id=user_id,
            notification_type="system",
            title=f"t{i}",
            message=f"m{i}",
        )
        ids.append(nid)
    return ids


async def test_list_endpoint_returns_user_notifications(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, client_user.id, count=3)
    response = await client.get(
        "/api/v1/notifications", headers=_auth(client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["notifications"]) == 3
    assert body["pagination"]["total"] == 3


async def test_list_endpoint_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401


async def test_list_endpoint_isolates_users(
    client: AsyncClient,
    other_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, client_user.id, count=2)
    response = await client.get(
        "/api/v1/notifications", headers=_auth(other_token)
    )
    assert response.status_code == 200
    assert response.json()["notifications"] == []


async def test_count_projection_returns_unread_count(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, client_user.id, count=4)
    response = await client.get(
        "/api/v1/notifications?fields=count", headers=_auth(client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 4
    assert body["unread_count"] == 4


async def test_create_endpoint_forbidden_for_client(
    client: AsyncClient, client_token: str, client_user: User
) -> None:
    response = await client.post(
        "/api/v1/notifications",
        headers=_auth(client_token),
        json={
            "user_id": client_user.id,
            "type": "system",
            "title": "hi",
            "message": "hello",
        },
    )
    assert response.status_code == 403


async def test_create_endpoint_allowed_for_employee(
    client: AsyncClient, employee_token: str, client_user: User
) -> None:
    response = await client.post(
        "/api/v1/notifications",
        headers=_auth(employee_token),
        json={
            "user_id": client_user.id,
            "type": "system",
            "title": "hi",
            "message": "hello",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str)
    assert len(body["id"]) == 36
    assert body["title"] == "hi"
    assert response.headers["location"] == f"/api/v1/notifications/{body['id']}"


async def test_create_endpoint_validates_type(
    client: AsyncClient, employee_token: str, client_user: User
) -> None:
    response = await client.post(
        "/api/v1/notifications",
        headers=_auth(employee_token),
        json={
            "user_id": client_user.id,
            "type": "bogus",
            "title": "hi",
            "message": "hello",
        },
    )
    assert response.status_code == 422


async def test_mark_read_endpoint_updates_is_read(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    [nid] = await _seed(db_session, client_user.id, count=1)
    response = await client.patch(
        f"/api/v1/notifications/{nid}",
        headers=_auth(client_token),
        json={"is_read": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(nid)
    assert body["is_read"] is True
    row = await db_session.get(Notification, nid)
    assert row is not None
    assert row.is_read is True


async def test_mark_read_endpoint_forbidden_for_other_user(
    client: AsyncClient,
    other_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    [nid] = await _seed(db_session, client_user.id, count=1)
    response = await client.patch(
        f"/api/v1/notifications/{nid}",
        headers=_auth(other_token),
        json={"is_read": True},
    )
    assert response.status_code == 403


async def test_mark_all_read_endpoint(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, client_user.id, count=3)
    response = await client.patch(
        "/api/v1/notifications",
        headers=_auth(client_token),
        json={"is_read": True},
    )
    assert response.status_code == 204
    result = await db_session.execute(
        select(Notification).where(Notification.user_id == client_user.id)
    )
    assert all(n.is_read for n in result.scalars().all())


async def test_delete_endpoint_removes_row(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    [nid] = await _seed(db_session, client_user.id, count=1)
    response = await client.delete(
        f"/api/v1/notifications/{nid}", headers=_auth(client_token)
    )
    assert response.status_code == 204
    listed = await client.get("/api/v1/notifications", headers=_auth(client_token))
    assert listed.status_code == 200
    assert listed.json()["notifications"] == []
    counts = await client.get("/api/v1/notifications?fields=count", headers=_auth(client_token))
    assert counts.json() == {"total_count": 0, "unread_count": 0}


async def test_delete_endpoint_forbidden_for_other_user(
    client: AsyncClient,
    other_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    [nid] = await _seed(db_session, client_user.id, count=1)
    response = await client.delete(
        f"/api/v1/notifications/{nid}", headers=_auth(other_token)
    )
    assert response.status_code == 403
    assert await db_session.get(Notification, nid) is not None


async def test_delete_endpoint_404_for_missing(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.delete(
        "/api/v1/notifications/00000000-0000-0000-0000-000000000000", headers=_auth(client_token)
    )
    assert response.status_code == 404
