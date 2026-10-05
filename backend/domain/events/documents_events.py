"""Document domain events (Phase 4 — D1 is the author).

Cross-domain consumers:
- ``DocumentUploadedEvent`` — D2 (application-documents) consumes it to
  attach the freshly uploaded document row to the ``application_documents``
  M2M when auto-approval fires via recognition.
- ``DocumentStatusChangedEvent`` — D3 (status-management) persists the
  transition into ``document_status_history`` (D3 owns that table's writes
  for non-D1-initiated transitions).

These are plain dataclasses — they carry no HTTP / DB / transport concerns.
The events are published via the faststream broker from the application
layer; consumers live in ``application/tasks/*`` in D2 / D3 when those
agents complete their own work.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

ZERO_UUID = uuid.UUID(int=0)


@dataclass
class DocumentDomainEvent:
    """Base for document-domain events."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DocumentUploadedEvent(DocumentDomainEvent):
    """A new document (or new version) has been uploaded to object storage.

    Consumed by D2 when the document is linked to an application so the
    ``application_documents`` row can be created / updated.
    """

    document_id: uuid.UUID = ZERO_UUID
    company_id: uuid.UUID = ZERO_UUID
    uploaded_by_user_id: uuid.UUID = ZERO_UUID
    document_type: str = ""
    application_id: uuid.UUID | None = None
    parent_document_id: uuid.UUID | None = None
    version: int = 1
    auto_approved: bool = False


@dataclass
class DocumentStatusChangedEvent(DocumentDomainEvent):
    """The status field on ``documents`` transitioned.

    Consumed by D3 to append a ``document_status_history`` row. D1 also
    writes into that table for its own transitions — the event is only used
    when a transition is initiated elsewhere (e.g. LC review in D2).
    """

    document_id: uuid.UUID = ZERO_UUID
    old_status: str | None = None
    new_status: str = ""
    changed_by_user_id: uuid.UUID | None = None
    comments: str | None = None
