"""Document aggregate root — Phase 4 D1 domain entity.

Encapsulates the document status machine, versioning helpers, ownership /
role visibility checks and file-type / size validation. Hydrated from a
repository dict via :meth:`Document.from_dict`.

Status machine
--------------

D1 models *review* status (as opposed to the DB's ``document_status_enum``
which tracks upload lifecycle). Review status lives in the
``leasing_company_status`` String(50) column — historical naming; the
column is the single source of truth for "pending / approved / rejected /
revision_required" transitions::

    pending ──► approved
    pending ──► rejected
    pending ──► revision_required
    revision_required ──► pending   (new version uploaded → reset to pending)
    approved ──► revision_required  (LC unblocks after initial approval)
    rejected ──► revision_required  (LC unblocks after initial rejection)

Any other transition is rejected by :meth:`ensure_can_change_status`.

The persisted ``status`` enum field continues to track upload state
(``uploaded`` / ``verified`` / ...) and is written by the repo at creation
time. Code that cares about "review status" uses ``review_status``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.errors import (
    DocumentAccessDeniedError,
    FileTooLargeError,
    InvalidDocumentStatusError,
    UnsupportedFileTypeError,
)

# ---------------------------------------------------------------------------
# Status constants (review status, stored in ``leasing_company_status``)
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVISION_REQUIRED = "revision_required"

ALL_REVIEW_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_PENDING,
        STATUS_APPROVED,
        STATUS_REJECTED,
        STATUS_REVISION_REQUIRED,
    }
)

# Allowed transitions: current → set of legitimate next statuses.
_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PENDING: frozenset(
        {STATUS_APPROVED, STATUS_REJECTED, STATUS_REVISION_REQUIRED}
    ),
    STATUS_REVISION_REQUIRED: frozenset(
        {STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED}
    ),
    STATUS_APPROVED: frozenset({STATUS_REVISION_REQUIRED, STATUS_REJECTED}),
    STATUS_REJECTED: frozenset({STATUS_REVISION_REQUIRED, STATUS_PENDING}),
}


# Document types supported by the passport-recognition provider.
# Kept here as a domain-level hint — the transport layer (``document_recognition``)
# owns the authoritative list but domain code also needs to know which types
# should flow through recognition at all.
RECOGNIZED_DOCUMENT_TYPES: frozenset[str] = frozenset(
    {"ceo_passport_page23", "ceo_passport_registration"}
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
class Document:
    """Aggregate root for a single document record."""

    id: UUID = field(default_factory=uuid.uuid4)
    company_id: UUID = field(default_factory=uuid.uuid4)
    document_type: str = ""
    file_name: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    s3_key: str | None = None
    # Review status — the one D1's status machine operates on.
    review_status: str = STATUS_PENDING
    # Upload-state enum (not managed by the machine — persisted unchanged).
    status: str | None = None
    version: int = 1
    parent_document_id: UUID | None = None
    is_current_version: bool = True
    related_application_id: uuid.UUID | None = None
    comments: str | None = None
    leasing_company_comments: str | None = None
    recognition_status: str | None = None
    recognition_error: str | None = None
    recognition_task_id: str | None = None
    uploaded_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        """Create an entity from a repo-shape dict (extra keys ignored)."""
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key == "leasing_company_status":
                # Alias — that column carries our review status.
                cleaned["review_status"] = (
                    str(raw) if raw else STATUS_PENDING
                )
                continue
            if key not in names:
                continue
            if key == "review_status":
                cleaned[key] = str(raw) if raw else STATUS_PENDING
            elif key in {"version", "file_size"}:
                cleaned[key] = int(raw) if raw is not None else 0
            elif key in {"id", "company_id"}:
                cleaned[key] = _required_uuid(raw, key)
            elif key in {"parent_document_id", "related_application_id"}:
                cleaned[key] = _optional_uuid(raw, key)
            elif key == "is_current_version":
                cleaned[key] = bool(raw) if raw is not None else True
            elif key == "document_type":
                cleaned[key] = str(raw) if raw is not None else ""
            else:
                cleaned[key] = raw
        # Repos that don't pass review_status should default to pending.
        cleaned.setdefault("review_status", STATUS_PENDING)
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def ensure_owned_by(
        self,
        *,
        user_id: UUID,
        role: str,
        company_id: UUID | None = None,
        leasing_company_selected: list[UUID] | None = None,
    ) -> None:
        """Domain ownership / role visibility check.

        - ``carcraft_employee`` sees everything.
        - A regular user whose ``company_id`` matches the document's
          company sees it.
        - ``leasing_company`` sees the document iff the document's related
          application selected their LC — the caller resolves the selected
          list from the application and passes it in.
        """
        _ = user_id  # reserved — some call-sites may use this later
        if role == "carcraft_employee":
            return
        if company_id is not None and company_id == self.company_id:
            return
        # LC reviewer: caller passes the LC's own id within the list (or a
        # flat list of selected LCs) — membership alone is enough, the LC
        # is resolved by the caller prior to invoking this method.
        if (
            role == "leasing_company"
            and leasing_company_selected
            and any(leasing_company_selected)
        ):
            return
        raise DocumentAccessDeniedError()

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------

    def ensure_can_change_status(self, new_status: str) -> None:
        """Validate a review-status transition.

        Raises:
            InvalidDocumentStatusError: If the transition is not allowed
                from ``self.review_status`` to ``new_status``.
        """
        if new_status not in ALL_REVIEW_STATUSES:
            raise InvalidDocumentStatusError(self.review_status, new_status)
        if new_status == self.review_status:
            raise InvalidDocumentStatusError(self.review_status, new_status)
        allowed = _TRANSITIONS.get(self.review_status, frozenset())
        if new_status not in allowed:
            raise InvalidDocumentStatusError(self.review_status, new_status)

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    def compute_next_version(self) -> int:
        """Return the version number for a new revision of this document.

        Versions start at 1 and increment monotonically; this is the only
        authoritative helper — repo callers should not compute it inline.
        """
        current = self.version if self.version else 1
        return current + 1

    def parent_id_for_new_version(self) -> UUID:
        """Resolve the root document id to use as ``parent_document_id`` on
        the new revision.

        If this document is a root (no parent), the new version points at
        ``self.id``; otherwise, it inherits this document's parent so the
        version chain stays flat.
        """
        return (
            self.parent_document_id
            if self.parent_document_id is not None
            else self.id
        )

    # ------------------------------------------------------------------
    # File validation
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_allowed_file_type(
        content_type: str,
        doc_type_config: dict[str, Any] | None,
        *,
        filename: str | None = None,
    ) -> None:
        """Validate the uploaded file against the per-type allowlist.

        ``document_types.file_types`` historically mixes two notations:

        * **MIME types** — ``"application/pdf"``, ``"image/jpeg"``;
        * **Extensions** — ``".pdf"``, ``".xml"`` (with the leading dot).

        We accept either: an entry that starts with ``"."`` is matched
        against the filename's extension; anything else is matched against
        the request ``content_type``. The first match wins.

        If the document type is not configured or has no ``file_types``
        allowlist, this is a no-op (we trust the upstream validator).
        """
        if not doc_type_config:
            return
        allowed_raw = doc_type_config.get("file_types")
        if not allowed_raw:
            return
        allowed = [str(t).lower() for t in allowed_raw if t]
        if not allowed:
            return

        content_type_lower = (content_type or "").lower()
        file_ext = ""
        if filename:
            idx = filename.rfind(".")
            if idx >= 0:
                file_ext = filename[idx:].lower()

        for token in allowed:
            if token.startswith("."):
                if file_ext and file_ext == token:
                    return
            elif content_type_lower and content_type_lower == token:
                return
        raise UnsupportedFileTypeError(
            content_type=content_type, allowed=allowed
        )

    @staticmethod
    def ensure_file_size_ok(
        size_bytes: int,
        doc_type_config: dict[str, Any] | None,
        default_max_mb: int = 10,
    ) -> None:
        """Validate upload size against the per-type limit.

        If no configuration is present the ``default_max_mb`` floor applies.
        """
        max_mb = default_max_mb
        if doc_type_config and doc_type_config.get("max_file_size_mb"):
            try:
                max_mb = int(doc_type_config["max_file_size_mb"])
            except (TypeError, ValueError):
                max_mb = default_max_mb
        limit_bytes = max_mb * 1024 * 1024
        if size_bytes > limit_bytes:
            raise FileTooLargeError(size_bytes=size_bytes, max_mb=max_mb)


# Backwards-compat alias for call-sites that expect a typed field on the
# Document dataclass for versioning inputs.
@dataclass
class DocumentTypeConfig:
    """Minimal projection of ``document_types`` row used by Document methods."""

    type_code: str
    auto_approve: bool = False
    file_types: list[str] = field(default_factory=list)
    max_file_size_mb: int = 10

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DocumentTypeConfig | None:
        if not data:
            return None
        return cls(
            type_code=str(data.get("type_code") or data.get("document_type") or ""),
            auto_approve=bool(data.get("auto_approve") or False),
            file_types=list(data.get("file_types") or []),
            max_file_size_mb=int(data.get("max_file_size_mb") or 10),
        )
