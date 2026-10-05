"""Notification domain entity.

Inviariants:
  * A notification can only be read, marked-read or deleted by its owner.
  * Creation is restricted to users with the appropriate role (`carcraft_employee`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.errors import AccessDeniedError


@dataclass
class Notification:
    id: UUID
    user_id: UUID | None
    type: str
    title: str
    message: str
    is_read: bool
    application_id: uuid.UUID | None
    action_url: str | None
    created_at: datetime | None
    read_at: datetime | None
    event_id: UUID | None = None
    data: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Notification:
        return cls(
            id=data["id"],
            user_id=data.get("user_id"),
            type=data["type"],
            title=data["title"],
            message=data["message"],
            is_read=bool(data.get("is_read")),
            application_id=data.get("application_id"),
            action_url=data.get("action_url"),
            created_at=data.get("created_at"),
            read_at=data.get("read_at"),
            event_id=data.get("event_id"),
            data=data.get("data"),
        )

    def ensure_owned_by(self, user_id: UUID) -> None:
        """Raise AccessDeniedError if caller is not the owner."""
        if self.user_id != user_id:
            raise AccessDeniedError("Уведомление не найдено")


_ALLOWED_ROLES_FOR_CREATE: frozenset[str] = frozenset({"carcraft_employee"})


def can_create_notifications(role: str | None) -> bool:
    """Business rule: only carcraft employees can create arbitrary notifications."""
    return role in _ALLOWED_ROLES_FOR_CREATE
