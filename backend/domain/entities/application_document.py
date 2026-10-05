"""ApplicationDocument aggregate root — Phase 4 D2.

Represents a per-LC review record of a document attached to an application.
Each (application, document, leasing_company) triple has its own status
from the perspective of that LC — one document submitted to several LCs
can be approved by one and rejected by another.

Status machine (LC review state, stored in ``application_documents.status``)::

    submitted ──► approved
    submitted ──► rejected
    submitted ──► revision_requested
    revision_requested ──► submitted     (client re-submits — handled elsewhere)
    approved ──► revision_requested      (LC walks back approval)
    rejected ──► revision_requested      (LC unlocks after initial rejection)

Any other transition is rejected by :meth:`ensure_can_review`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.errors import (
    DocumentAccessDeniedError,
    InvalidDocumentReviewError,
)

# ---------------------------------------------------------------------------
# Status constants (per-LC review status)
# ---------------------------------------------------------------------------

STATUS_SUBMITTED = "submitted"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVISION_REQUESTED = "revision_requested"

ALL_REVIEW_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_SUBMITTED,
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_REVISION_REQUESTED,
    }
)

# Review endpoint only accepts these (pending not writable from outside).
REVIEW_TARGET_STATUSES: frozenset[str] = frozenset(
    {STATUS_APPROVED, STATUS_REJECTED, STATUS_REVISION_REQUESTED}
)

_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_SUBMITTED: frozenset(
        {STATUS_APPROVED, STATUS_REJECTED, STATUS_REVISION_REQUESTED}
    ),
    STATUS_REVISION_REQUESTED: frozenset(
        {STATUS_SUBMITTED, STATUS_APPROVED, STATUS_REJECTED}
    ),
    STATUS_APPROVED: frozenset(
        {STATUS_REVISION_REQUESTED, STATUS_REJECTED}
    ),
    STATUS_REJECTED: frozenset(
        {STATUS_REVISION_REQUESTED, STATUS_APPROVED}
    ),
}


def _required_uuid(raw: Any, field_name: str) -> UUID:
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str):
        return UUID(raw)
    raise TypeError(f"{field_name} must be a UUID")


def _optional_uuid(raw: Any, field_name: str) -> UUID | None:
    if raw is None:
        return None
    try:
        return _required_uuid(raw, field_name)
    except TypeError as exc:
        raise TypeError(f"{field_name} must be a UUID or None") from exc


@dataclass
class ApplicationDocument:
    """Aggregate root for an application_documents row."""

    id: UUID = field(default_factory=uuid.uuid4)
    application_id: UUID = field(default_factory=uuid.uuid4)
    document_id: UUID = field(default_factory=uuid.uuid4)
    document_request_id: UUID | None = None
    leasing_company_id: UUID = field(default_factory=uuid.uuid4)
    status: str = STATUS_SUBMITTED
    reviewer_comments: str | None = None
    reviewed_by: UUID | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    revision_requested_at: datetime | None = None
    auto_approved: bool = False

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApplicationDocument:
        """Create an entity from a repo-shape dict (extra keys ignored)."""
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key in {
                "id",
                "application_id",
                "document_id",
                "leasing_company_id",
            }:
                cleaned[key] = _required_uuid(raw, key)
            elif key in {"document_request_id", "reviewed_by"}:
                cleaned[key] = _optional_uuid(raw, key)
            elif key == "auto_approved":
                cleaned[key] = bool(raw) if raw is not None else False
            elif key == "status":
                cleaned[key] = str(raw) if raw else STATUS_SUBMITTED
            else:
                cleaned[key] = raw
        cleaned.setdefault("status", STATUS_SUBMITTED)
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def ensure_owned_by_lc(self, leasing_company_id: UUID) -> None:
        """Only the row's owning LC may review it."""
        if self.leasing_company_id != leasing_company_id:
            raise DocumentAccessDeniedError()

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------

    def ensure_can_review(self, new_status: str) -> None:
        """Validate an LC-side review transition.

        Raises:
            InvalidDocumentReviewError: If the transition is not allowed.
        """
        if new_status not in REVIEW_TARGET_STATUSES:
            raise InvalidDocumentReviewError(
                f"Недопустимый статус ревью: {new_status}"
            )
        if new_status == self.status:
            raise InvalidDocumentReviewError(
                f"Документ уже в статусе '{new_status}'"
            )
        allowed = _TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidDocumentReviewError(
                f"Недопустимый переход: {self.status} → {new_status}"
            )
