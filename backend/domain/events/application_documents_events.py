"""Application-documents domain events (Phase 4 — D2 is the author).

Published events
----------------

- :class:`DocumentRequestedEvent` — emitted when an LC creates a
  document request for an application. Consumer: notifications service,
  D3 (status-management) may record in audit.

- :class:`DocumentReviewedEvent` — emitted when an LC reviews an uploaded
  document (approved / rejected / revision_requested). Consumer: D3 —
  may trigger ``LeasingCompanyApplication`` status updates / aggregate
  checks ("all LCs approved → application approved").

These are plain dataclasses — no transport concerns. They are published
via the faststream broker from the application layer; consumers live in
``application/tasks/*`` and run in the event-worker process.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(kw_only=True)
class ApplicationDocumentsDomainEvent:
    """Base for events emitted from the application-documents context."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(kw_only=True)
class DocumentRequestedEvent(ApplicationDocumentsDomainEvent):
    """An LC requested an additional document from the applicant."""

    application_id: uuid.UUID
    leasing_company_id: uuid.UUID
    document_type: str
    is_required: bool = True
    deadline: datetime | None = None
    request_message: str | None = None
    requested_by_user_id: uuid.UUID | None = None


@dataclass(kw_only=True)
class DocumentReviewedEvent(ApplicationDocumentsDomainEvent):
    """An LC reviewed one of the application's uploaded documents."""

    application_id: uuid.UUID
    document_id: uuid.UUID
    leasing_company_id: uuid.UUID
    new_status: str
    reviewer_user_id: uuid.UUID | None = None
    reviewer_comments: str | None = None


__all__ = [
    "ApplicationDocumentsDomainEvent",
    "DocumentRequestedEvent",
    "DocumentReviewedEvent",
]
