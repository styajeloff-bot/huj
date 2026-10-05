"""D2 — Application documents cross-domain event consumers.

Kept in a standalone module (not under ``application/tasks/``) because
that package has a pre-existing import-time failure in
``compensations.py`` — importing the package fails at module load.
D1 used the same workaround; we mirror it here.

Subscriber layout
-----------------

- :func:`handle_document_uploaded` — consumes ``DocumentUploadedEvent``
  from D1 (emitted when a document is attached to an application). If
  the document is linked to an application, we create / update the
  matching ``application_documents`` row. If the document was
  auto-approved on upload, we mirror that into ``application_documents``
  with ``status='approved'`` and ``auto_approved=True`` so the LC view
  reflects the fast-path.

The subscriber is exposed as a module-level coroutine (not a
``@broker.subscriber``) so the function can be unit-tested by feeding
in a payload dict. The event-worker process wires it to a topic when
cross-domain events are eventually published by D1.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from typing import Any

from application.errors import ServiceError
from domain.entities.application_document import (
    STATUS_APPROVED,
    STATUS_SUBMITTED,
)
from domain.events.documents_events import DocumentUploadedEvent
from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import (
    application_documents_repository as repo,
)

logger = logging.getLogger("carcraft-backend")


def _coerce_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _event_from_payload(payload: dict[str, Any]) -> DocumentUploadedEvent:
    """Rebuild a :class:`DocumentUploadedEvent` from a broker payload.

    Unknown / missing fields fall back to dataclass defaults so a sloppy
    producer can't crash the consumer.
    """
    safe: dict[str, Any] = {
        k: v for k, v in payload.items() if k in DocumentUploadedEvent.__dataclass_fields__
    }
    # occurred_at arrives as a string over the wire; skip it — the
    # default factory picks up the consumer time which is acceptable
    # for these downstream writes.
    safe.pop("occurred_at", None)
    uuid_keys = {
        "document_id",
        "company_id",
        "uploaded_by_user_id",
        "parent_document_id",
    }
    for key in uuid_keys:
        if key in safe:
            safe[key] = _coerce_uuid(safe[key]) or uuid.UUID(int=0)
    # version stays int
    if "version" in safe:
        try:
            safe["version"] = int(safe["version"])
        except (TypeError, ValueError):
            safe["version"] = 1
    if "application_id" in safe and safe["application_id"] is not None:
        raw_app_id = safe["application_id"]
        # Treat 0 as None (backward-compatible with int era where 0 meant "no app")
        if raw_app_id in {0, "0", "00000000-0000-0000-0000-000000000000"}:
            safe["application_id"] = None
        elif isinstance(raw_app_id, uuid.UUID):
            safe["application_id"] = raw_app_id
        else:
            safe["application_id"] = uuid.UUID(str(raw_app_id))
    return DocumentUploadedEvent(**safe)


async def handle_document_uploaded(payload: dict[str, Any]) -> None:
    """Process a ``DocumentUploadedEvent`` payload.

    This is the testable entry-point — wiring to a Kafka topic happens
    where / when the event is actually published upstream. Failures are
    logged but never re-raised: audit gaps are preferable to a stalled
    consumer group.
    """
    try:
        event = _event_from_payload(payload)
    except Exception as exc:
        logger.warning("d2_doc_uploaded_bad_payload err=%s", exc)
        return

    if not event.application_id or not event.document_id:
        return  # nothing to attach

    try:
        async with AsyncSessionLocal() as session:
            try:
                await _attach_document(event, session)
                await session.commit()
            except (ServiceError, Exception) as exc:
                await session.rollback()
                logger.warning(
                    "d2_doc_uploaded_persist_failed doc=%s app=%s err=%s",
                    event.document_id,
                    event.application_id,
                    exc,
                )
    except Exception as exc:
        logger.warning("d2_doc_uploaded_session_failed err=%s", exc)


async def _attach_document(
    event: DocumentUploadedEvent, session: Any
) -> None:
    """Create or update per-LC rows for the freshly uploaded document.

    We fan out one row per LC on the application's selected-LCs list.
    auto_approved fires → status=approved immediately; otherwise
    the row starts as submitted and waits for an LC review.
    """
    application_id = event.application_id
    if application_id is None:
        return
    application = await repo.get_application(session, application_id)
    if application is None:
        logger.info(
            "d2_doc_uploaded_app_missing app=%s", application_id
        )
        return
    selected = list(application.get("selected_leasing_companies") or [])
    if not selected:
        return
    status = STATUS_APPROVED if event.auto_approved else STATUS_SUBMITTED
    for lc_id in selected:
        await repo.upsert_application_document(
            session,
            application_id=application_id,
            document_id=event.document_id,
            leasing_company_id=lc_id,
            status=status,
            auto_approved=bool(event.auto_approved),
        )


def event_to_dict(event: DocumentUploadedEvent) -> dict[str, Any]:
    """Serialize an event to a broker-publishable dict."""
    out = asdict(event)
    # datetime is JSON-unfriendly across brokers; stringify upfront.
    if event.occurred_at is not None:
        out["occurred_at"] = event.occurred_at.isoformat()
    return out


__all__ = [
    "event_to_dict",
    "handle_document_uploaded",
]
