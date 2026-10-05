"""ApplicationDocumentRequest aggregate — Phase 4 D2.

Represents one LC asking the applicant to upload a document of a given
type. Requests are grouped by ``request_batch_id`` and the document type is
unique only inside that batch, so a later request preserves the old history.

Status machine (``application_document_requests.status``)::

    requested ──► provided          (document uploaded by client)
    requested ──► approved          (LC auto-approves / reviews existing doc)
    requested ──► rejected          (LC rejects request up-front)
    provided ──► approved
    provided ──► rejected
    provided ──► requested          (LC asks for revision — rare)

The entity does not own the transitions exhaustively — the status field
is most often driven by reviews landing elsewhere; this class focuses on
the creation invariants + ownership checks the command handlers need.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.errors import (
    ApplicationNotOwnedError,
    DocumentAccessDeniedError,
)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_REQUESTED = "requested"
STATUS_PROVIDED = "provided"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_SUPERSEDED = "superseded"

ALL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_REQUESTED,
        STATUS_PROVIDED,
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_SUPERSEDED,
    }
)


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
class ApplicationDocumentRequest:
    """Aggregate root for one application_document_requests row."""

    id: UUID = field(default_factory=uuid.uuid4)
    application_id: UUID = field(default_factory=uuid.uuid4)
    leasing_company_id: UUID = field(default_factory=uuid.uuid4)
    request_batch_id: UUID = field(default_factory=uuid.uuid4)
    document_type: str = ""
    display_name: str = ""
    status: str = STATUS_REQUESTED
    is_required: bool = True
    request_message: str | None = None
    requested_by: UUID | None = None
    rejection_reason: str | None = None
    requested_at: datetime | None = None
    provided_at: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    deadline: datetime | None = None
    reminder_sent_at: datetime | None = None

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(
        cls, data: dict[str, Any]
    ) -> ApplicationDocumentRequest:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key in {
                "id",
                "application_id",
                "leasing_company_id",
                "request_batch_id",
            }:
                cleaned[key] = _required_uuid(raw, key)
            elif key in {"requested_by", "reviewed_by"}:
                cleaned[key] = _optional_uuid(raw, key)
            elif key == "is_required":
                cleaned[key] = bool(raw) if raw is not None else True
            elif key == "status":
                cleaned[key] = str(raw) if raw else STATUS_REQUESTED
            elif key in {"document_type", "display_name"}:
                cleaned[key] = str(raw) if raw is not None else ""
            else:
                cleaned[key] = raw
        cleaned.setdefault("status", STATUS_REQUESTED)
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization / invariants
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_can_create(
        *,
        actor_role: str,
        actor_leasing_company_id: UUID | None,
        target_leasing_company_id: UUID,
        application_selected_lcs: list[UUID],
    ) -> None:
        """Validate who may create a request for a given (application, LC).

        - ``carcraft_employee`` may create on behalf of any LC selected
          by the application.
        - ``leasing_company`` may only create requests for themselves,
          and only if they are in the application's ``selected_leasing_companies``.
        - Any other role is denied.
        """
        if target_leasing_company_id not in application_selected_lcs:
            raise ApplicationNotOwnedError(
                "ЛК не выбрана в заявке — запрос документов невозможен"
            )
        if actor_role == "carcraft_employee":
            return
        if actor_role == "leasing_company":
            if (
                actor_leasing_company_id is None
                or actor_leasing_company_id != target_leasing_company_id
            ):
                raise DocumentAccessDeniedError()
            return
        raise DocumentAccessDeniedError()

    def ensure_owned_by_lc(self, leasing_company_id: UUID) -> None:
        if self.leasing_company_id != leasing_company_id:
            raise DocumentAccessDeniedError()
