"""HTTP schemas for notifications."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

NotificationType = Literal[
    "application_status",
    "document_request",
    "document_status",
    "leasing_approval",
    "system",
    "approval", "general",
    "exchange_new_request", "exchange_new_bid", "exchange_bid_updated",
    "exchange_bid_accepted", "exchange_request_changed", "exchange_bid_withdrawn",
    "exchange_deadline", "exchange_request_finalized", "exchange_bid_not_selected",
]


class CreateNotificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID = Field(...)
    type: NotificationType
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1, max_length=500)
    application_id: uuid.UUID | None = None
    action_url: HttpUrl | None = None


class MarkReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_read: Literal[True]


class NotificationResource(BaseModel):
    id: str
    user_id: str | None = None
    type: str
    title: str
    message: str
    is_read: bool
    application_id: uuid.UUID | None = None
    application_display_number: str | None = None
    action_url: str | None = None
    created_at: datetime | None = None
    read_at: datetime | None = None
    event_id: UUID | None = None
    data: dict | None = None


class PaginationBody(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class NotificationsListResponse(BaseModel):
    notifications: list[NotificationResource]
    pagination: PaginationBody


class NotificationCountsResponse(BaseModel):
    total_count: int
    unread_count: int
