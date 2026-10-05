"""LeasingCompanyApplication aggregate — per-LC review status machine.

Each row in ``leasing_company_applications`` represents a specific LC's
decision on a submitted application.

The underlying PostgreSQL ``leasing_company_application_status`` enum
(``infrastructure/models/enums.py``) defines:

    submitted, under_review, documents_required, under_review_with_docs,
    approved_scoring, approved_scoring_another_cond, rejected_prescoring,
    approved_final, approved_final_another_cond, rejected_approved, selected_lc,
    deal, closed

Status machine
--------------

::

    submitted ──► under_review
    submitted ──► selected_lc
    selected_lc ──► under_review
    under_review ──► approved_scoring
    under_review ──► approved_scoring_another_cond
    under_review ──► approved_final
    under_review ──► approved_final_another_cond
    under_review ──► rejected_prescoring
    under_review ──► documents_required
    documents_required ──► under_review
    documents_required ──► under_review_with_docs
    documents_required ──► approved_scoring
    documents_required ──► approved_scoring_another_cond
    documents_required ──► approved_final
    documents_required ──► approved_final_another_cond
    documents_required ──► rejected_prescoring
    under_review_with_docs ──► approved_scoring
    under_review_with_docs ──► approved_scoring_another_cond
    under_review_with_docs ──► approved_final
    under_review_with_docs ──► approved_final_another_cond
    under_review_with_docs ──► rejected_prescoring
    under_review_with_docs ──► documents_required
    under_review_with_docs ──► closed
    approved_scoring ──► approved_final
    approved_scoring ──► approved_final_another_cond
    approved_scoring ──► documents_required
    approved_scoring_another_cond ──► approved_final
    approved_scoring_another_cond ──► approved_final_another_cond
    approved_scoring_another_cond ──► documents_required
    approved_final ──► deal
    approved_final_another_cond ──► deal
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.errors import (
    IncompleteProposalError,
    InvalidLeasingCompanyApplicationStatusError,
    LeasingCompanyAccessDeniedError,
    ResponseAlreadySubmittedError,
)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

LCA_STATUS_SUBMITTED = "submitted"
LCA_STATUS_UNDER_REVIEW = "under_review"
LCA_STATUS_APPROVED_SCORING = "approved_scoring"
LCA_STATUS_APPROVED_SCORING_ANOTHER_COND = "approved_scoring_another_cond"
LCA_STATUS_REJECTED_PRESCORING = "rejected_prescoring"
LCA_STATUS_DOCUMENTS_REQUIRED = "documents_required"
LCA_STATUS_UNDER_REVIEW_WITH_DOCS = "under_review_with_docs"
LCA_STATUS_APPROVED_FINAL = "approved_final"
LCA_STATUS_APPROVED_FINAL_ANOTHER_COND = "approved_final_another_cond"
LCA_STATUS_REJECTED_APPROVED = "rejected_approved"
LCA_STATUS_SELECTED_LC = "selected_lc"
LCA_STATUS_DEAL = "deal"
LCA_STATUS_CLOSED = "closed"

ALL_LCA_STATUSES: frozenset[str] = frozenset(
    {
        LCA_STATUS_SUBMITTED,
        LCA_STATUS_UNDER_REVIEW,
        LCA_STATUS_APPROVED_SCORING,
        LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
        LCA_STATUS_REJECTED_PRESCORING,
        LCA_STATUS_DOCUMENTS_REQUIRED,
        LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
        LCA_STATUS_APPROVED_FINAL,
        LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
        LCA_STATUS_REJECTED_APPROVED,
        LCA_STATUS_SELECTED_LC,
        LCA_STATUS_DEAL,
        LCA_STATUS_CLOSED,
    }
)

_TRANSITIONS: dict[str, frozenset[str]] = {
    LCA_STATUS_SUBMITTED: frozenset(
        {
            LCA_STATUS_UNDER_REVIEW,
            LCA_STATUS_SELECTED_LC,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_SELECTED_LC: frozenset(
        {
            LCA_STATUS_UNDER_REVIEW,
            LCA_STATUS_DEAL,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_UNDER_REVIEW: frozenset(
        {
            LCA_STATUS_APPROVED_SCORING,
            LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
            LCA_STATUS_APPROVED_FINAL,
            LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
            LCA_STATUS_REJECTED_PRESCORING,
            LCA_STATUS_REJECTED_APPROVED,
            LCA_STATUS_DOCUMENTS_REQUIRED,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_DOCUMENTS_REQUIRED: frozenset(
        {
            LCA_STATUS_UNDER_REVIEW,
            LCA_STATUS_UNDER_REVIEW_WITH_DOCS,
            LCA_STATUS_APPROVED_SCORING,
            LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
            LCA_STATUS_APPROVED_FINAL,
            LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
            LCA_STATUS_REJECTED_PRESCORING,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_UNDER_REVIEW_WITH_DOCS: frozenset(
        {
            LCA_STATUS_APPROVED_SCORING,
            LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
            LCA_STATUS_APPROVED_FINAL,
            LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
            LCA_STATUS_REJECTED_PRESCORING,
            LCA_STATUS_DOCUMENTS_REQUIRED,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_APPROVED_SCORING: frozenset(
        {
            LCA_STATUS_APPROVED_FINAL,
            LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
            LCA_STATUS_DOCUMENTS_REQUIRED,
            LCA_STATUS_REJECTED_APPROVED,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_APPROVED_SCORING_ANOTHER_COND: frozenset(
        {
            LCA_STATUS_APPROVED_FINAL,
            LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
            LCA_STATUS_DOCUMENTS_REQUIRED,
            LCA_STATUS_REJECTED_APPROVED,
            LCA_STATUS_CLOSED,
        }
    ),
    LCA_STATUS_APPROVED_FINAL: frozenset(
        {LCA_STATUS_SELECTED_LC, LCA_STATUS_DEAL, LCA_STATUS_CLOSED}
    ),
    LCA_STATUS_APPROVED_FINAL_ANOTHER_COND: frozenset(
        {LCA_STATUS_SELECTED_LC, LCA_STATUS_DEAL, LCA_STATUS_CLOSED}
    ),
    LCA_STATUS_REJECTED_PRESCORING: frozenset(),
    LCA_STATUS_REJECTED_APPROVED: frozenset(),
    LCA_STATUS_DEAL: frozenset(),
    LCA_STATUS_CLOSED: frozenset(),
}


def _coerce_field(key: str, raw: Any) -> Any:
    if key == "id":
        if isinstance(raw, uuid.UUID):
            result: Any = raw
        elif isinstance(raw, str):
            result = uuid.UUID(raw)
        else:
            raise TypeError("id must be a UUID")
    elif key in {"application_id", "leasing_company_id"}:
        if raw is None:
            result = None
        elif isinstance(raw, uuid.UUID):
            result = raw
        elif isinstance(raw, str):
            result = uuid.UUID(raw)
        else:
            raise TypeError(f"{key} must be a UUID or None")
    elif key == "response_pdf_size":
        result = int(raw) if raw is not None else None
    elif key == "status":
        result = str(raw) if raw else LCA_STATUS_SUBMITTED
    else:
        result = raw
    return result


@dataclass
class LeasingCompanyApplication:
    """Aggregate for a single LC's decision on an application."""

    id: UUID = field(default_factory=uuid.uuid4)
    application_id: uuid.UUID | None = None
    leasing_company_id: UUID | None = None
    status: str = LCA_STATUS_SUBMITTED
    review_notes: str | None = None
    decision_comment: str | None = None
    response_pdf_s3_key: str | None = None
    response_pdf_file_name: str | None = None
    response_pdf_size: int | None = None
    response_pdf_uploaded_at: datetime | None = None
    submitted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeasingCompanyApplication:
        """Create an entity from a repo-shape dict (extra keys ignored)."""
        names = {f.name for f in fields(cls)}
        cleaned = {k: _coerce_field(k, v) for k, v in data.items() if k in names}
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def ensure_owned_by_lc(self, *, leasing_company_id: UUID | None) -> None:
        """Only the owning LC (by id) may mutate this link."""
        if (
            leasing_company_id is None
            or leasing_company_id != self.leasing_company_id
        ):
            raise LeasingCompanyAccessDeniedError()

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------

    def ensure_can_change_status(self, new_status: str) -> None:
        """Validate a status transition.

        Raises:
            InvalidLeasingCompanyApplicationStatusError: If the transition
                is not allowed from ``self.status`` to ``new_status``.
        """
        if new_status not in ALL_LCA_STATUSES:
            raise InvalidLeasingCompanyApplicationStatusError(
                self.status, new_status
            )
        if new_status == self.status:
            raise InvalidLeasingCompanyApplicationStatusError(
                self.status, new_status
            )
        allowed = _TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidLeasingCompanyApplicationStatusError(
                self.status, new_status
            )

    def ensure_can_approve_scoring(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_APPROVED_SCORING)

    def ensure_can_approve_scoring_another_cond(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_APPROVED_SCORING_ANOTHER_COND)

    def ensure_can_approve_final(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_APPROVED_FINAL)

    def ensure_can_approve_final_another_cond(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_APPROVED_FINAL_ANOTHER_COND)

    def ensure_can_reject_prescoring(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_REJECTED_PRESCORING)

    def ensure_can_reject_approved(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_REJECTED_APPROVED)

    def ensure_can_request_documents(self) -> None:
        # Another batch is a new request even when the review status is unchanged.
        if self.status != LCA_STATUS_DOCUMENTS_REQUIRED:
            self.ensure_can_change_status(LCA_STATUS_DOCUMENTS_REQUIRED)

    def ensure_can_deal(self) -> None:
        self.ensure_can_change_status(LCA_STATUS_DEAL)

    def ensure_can_issue(self) -> None:
        self.ensure_can_deal()

    def is_terminal(self) -> bool:
        return self.status in {
            LCA_STATUS_REJECTED_PRESCORING,
            LCA_STATUS_REJECTED_APPROVED,
            LCA_STATUS_DEAL,
            LCA_STATUS_CLOSED,
        }

    # ------------------------------------------------------------------
    # Response submit guards (KP / PDF / decision flow)
    # ------------------------------------------------------------------

    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    def ensure_editable(self) -> None:
        """LC may only edit proposals / PDF before the response is submitted."""
        if self.is_submitted():
            raise ResponseAlreadySubmittedError()

    def ensure_can_submit_decision(
        self,
        action: str,
        *,
        proposals: list[Any],
        kind: str = "final",
    ) -> None:
        """Validate a final-decision submit.

        ``action`` is "approve" or "reject"; ``kind`` is "preliminary" or
        "final". Approve requires at least one complete proposal;
        reject does not. Re-submitting after the response is finalized is
        rejected.
        """
        if self.is_submitted():
            raise ResponseAlreadySubmittedError()
        if action == "approve":
            if not proposals or not any(
                getattr(p, "is_complete", lambda: False)() for p in proposals
            ):
                raise IncompleteProposalError()
            if kind == "preliminary":
                self.ensure_can_approve_scoring()
            else:
                self.ensure_can_approve_final()
        elif action == "reject":
            if kind == "preliminary":
                self.ensure_can_reject_prescoring()
            else:
                self.ensure_can_reject_approved()
        else:
            raise InvalidLeasingCompanyApplicationStatusError(
                self.status, action
            )


def cascade_application_status(statuses: list[str]) -> str | None:
    """Return the cascaded parent ``LeasingApplication.status`` for the given
    per-LC decisions.

    - Any LC in ``deal`` → parent ``issued``.
    - Every LC terminal (rejected or closed) → parent ``rejected``.
    - Otherwise no transition is required (``None``).
    """
    if not statuses:
        return None
    if LCA_STATUS_DEAL in statuses:
        return "issued"
    terminal = {
        LCA_STATUS_REJECTED_PRESCORING,
        LCA_STATUS_REJECTED_APPROVED,
        LCA_STATUS_CLOSED,
    }
    if all(s in terminal for s in statuses):
        return "rejected"
    return None
