"""Leasing LC workflow domain events (Phase 4 — D3).

D3 is the author of these events. Consumers are external — notifications /
Phase 3 consumer on ``LeasingApplication`` status (cascaded on full-approve
/ full-reject) — and the writes themselves happen in the D3 handler.

Events are published through the faststream broker when the DB transaction
commits; consumer wiring lives in the event-worker (``application/tasks/``
in other agents; D3's own subscriber lives in ``application/leasing_tasks``).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(kw_only=True)
class LeasingDomainEvent:
    """Base for leasing-domain events."""

    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(kw_only=True)
class LeasingApplicationApprovedEvent(LeasingDomainEvent):
    """Every LC on a submitted application approved — parent application
    transitioned to ``approved``.

    Consumed by notifications to inform the applicant; Phase 3 consumers
    may also drive the ``approved → issued`` hand-off.
    """

    application_id: uuid.UUID
    approved_by_lc_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass(kw_only=True)
class LeasingApplicationRejectedEvent(LeasingDomainEvent):
    """Every LC on a submitted application rejected — parent application
    transitioned to ``rejected``.
    """

    application_id: uuid.UUID
    rejected_by_lc_ids: list[uuid.UUID] = field(default_factory=list)
    reason: str | None = None


@dataclass(kw_only=True)
class LeasingCompanyApplicationStatusChangedEvent(LeasingDomainEvent):
    """A per-LC review status transitioned (approve / reject / document_request).

    Notifications subscribe to this to inform the applicant about a given
    LC's decision.
    """

    application_id: uuid.UUID
    leasing_company_id: uuid.UUID
    old_status: str | None = None
    new_status: str
    changed_by_user_id: uuid.UUID | None = None
    reason: str | None = None
