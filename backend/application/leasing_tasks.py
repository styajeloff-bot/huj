"""Leasing-domain event consumers (Phase 4 D3).

Kept at the ``application/`` package level (alongside ``tasks/``) because
the ``application/tasks/__init__.py`` is used by the taskiq-scheduled jobs
runner and mixing faststream Kafka consumers with taskiq cron jobs in the
same module breaks discovery. The event-worker binds to this module
separately.

Two consumers are wired here:

- ``on_document_status_changed`` — D1 publishes ``DocumentStatusChangedEvent``
  when a document transitions through a route D1 owns. D3 appends a row to
  ``document_status_history`` unless D1 already wrote one (idempotency is
  best-effort: the event simply carries the transition, we always write).

- ``on_document_reviewed`` — D2 publishes ``DocumentReviewedEvent`` after
  approving or rejecting an application-document. D3 listens to keep the
  audit trail consistent. The event type is owned by D2 so we import it
  defensively to avoid a hard dependency if D2 hasn't landed yet.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from domain.events.documents_events import DocumentStatusChangedEvent
from infrastructure.database import AsyncSessionLocal
from infrastructure.messaging.broker import broker
from infrastructure.repositories import status_history_repository as hist_repo

logger = logging.getLogger("carcraft-backend")

_DOCUMENT_STATUS_TOPIC = "documents.status_changed.v1"
_DOCUMENT_REVIEWED_TOPIC = "application_documents.reviewed.v1"


def _event_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


@broker.subscriber(_DOCUMENT_STATUS_TOPIC)
async def on_document_status_changed(event: DocumentStatusChangedEvent) -> None:
    """Persist a ``document_status_history`` entry from the D1 event."""
    async with AsyncSessionLocal() as session:
        try:
            await hist_repo.append_document_status_history(
                document_id=event.document_id,
                old_status=event.old_status,
                new_status=event.new_status,
                changed_by=event.changed_by_user_id,
                comments=event.comments,
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "leasing_tasks.on_document_status_changed error=%s", exc
            )
            raise


@broker.subscriber(_DOCUMENT_REVIEWED_TOPIC)
async def on_document_reviewed(event: dict[str, Any]) -> None:
    """Append a history row when D2 reports a document review decision.

    The payload is decoded as a plain dict because D2 may evolve the event
    shape independently; we pull only the fields we need and ignore the
    rest. Expected keys: ``document_id`` (UUID string), ``new_status`` (str),
    ``old_status`` (str|None), ``reviewer_user_id`` (UUID string|None),
    ``reviewer_comments`` (str|None).
    """
    document_id = _event_uuid(event.get("document_id"))
    new_status = str(event.get("new_status") or "")
    if document_id is None or not new_status:
        return
    old_status = event.get("old_status")
    raw_reviewer = event.get("reviewer_user_id")
    reviewer = _event_uuid(raw_reviewer)
    if raw_reviewer is not None and reviewer is None:
        return
    comments = event.get("reviewer_comments", event.get("comments"))
    async with AsyncSessionLocal() as session:
        try:
            await hist_repo.append_document_status_history(
                document_id=document_id,
                old_status=str(old_status) if old_status is not None else None,
                new_status=new_status,
                changed_by=reviewer,
                comments=str(comments) if comments is not None else None,
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "leasing_tasks.on_document_reviewed error=%s", exc
            )
            raise
