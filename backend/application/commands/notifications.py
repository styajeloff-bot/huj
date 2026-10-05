"""Notification commands."""
import uuid
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.entities.notification import Notification
from domain.errors import NotificationNotFoundError
from infrastructure.repositories import notification_repository as repo
from infrastructure.repositories.notification_repository import NotificationDict


@dataclass
class CreateNotificationCommand:
    user_id: UUID
    type: str
    title: str
    message: str
    application_id: uuid.UUID | None = None
    action_url: str | None = None


@dataclass
class MarkNotificationReadCommand:
    user_id: UUID
    notification_id: UUID


@dataclass
class MarkAllReadCommand:
    user_id: UUID


@dataclass
class DeleteNotificationCommand:
    user_id: UUID
    notification_id: UUID


async def handle_create_notification(
    command: CreateNotificationCommand, session: AsyncSession
) -> NotificationDict:
    notification_id = await repo.create_notification(
        session,
        user_id=command.user_id,
        notification_type=command.type,
        title=command.title,
        message=command.message,
        application_id=command.application_id,
        action_url=command.action_url,
    )
    created = await repo.get_by_id(session, notification_id)
    if created is None:
        raise ServiceError("Не удалось загрузить созданное уведомление", 500)
    return cast("NotificationDict", created)


async def _load_owned(
    session: AsyncSession, notification_id: UUID, user_id: UUID
) -> Notification:
    data = await repo.get_by_id(session, notification_id)
    if data is None:
        raise NotificationNotFoundError()
    notification = Notification.from_dict(dict(data))
    notification.ensure_owned_by(user_id)
    return notification


async def handle_mark_read(
    command: MarkNotificationReadCommand, session: AsyncSession
) -> NotificationDict:
    await _load_owned(session, command.notification_id, command.user_id)
    await repo.mark_as_read(session, command.notification_id)
    updated = await repo.get_by_id(session, command.notification_id)
    if updated is None:
        raise ServiceError("Не удалось загрузить обновлённое уведомление", 500)
    return cast("NotificationDict", updated)


async def handle_mark_all_read(
    command: MarkAllReadCommand, session: AsyncSession
) -> None:
    await repo.mark_all_as_read(session, command.user_id)


async def handle_delete_notification(
    command: DeleteNotificationCommand, session: AsyncSession
) -> None:
    await _load_owned(session, command.notification_id, command.user_id)
    await repo.delete_by_id(session, command.notification_id)
