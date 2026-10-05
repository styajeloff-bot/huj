"""Status-history value objects — Phase 4 D3 domain layer.

Lightweight projections used by the status-management queries. Two
variants share the same shape — the concrete ``entity_type`` is carried
inline so the router can expose a uniform timeline per entity.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

ENTITY_DOCUMENT = "document"
ENTITY_LEASING_APPLICATION = "leasing_application"

ALL_ENTITY_TYPES: frozenset[str] = frozenset(
    {ENTITY_DOCUMENT, ENTITY_LEASING_APPLICATION}
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
class StatusHistoryEntry:
    """A single status-history row — decoupled from the ORM schema.

    Document history originates from ``document_status_history``; leasing
    application history is extracted from the shared ``audit_log`` because
    no dedicated table exists.
    """

    id: UUID = field(default_factory=uuid.uuid4)
    entity_type: str = ENTITY_DOCUMENT
    entity_id: UUID = field(default_factory=uuid.uuid4)
    old_status: str | None = None
    new_status: str = ""
    changed_by: UUID | None = None
    comments: str | None = None
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusHistoryEntry:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key in {"id", "entity_id"}:
                cleaned[key] = _required_uuid(raw, key)
            elif key == "changed_by":
                cleaned[key] = _optional_uuid(raw, key)
            elif key == "entity_type":
                cleaned[key] = str(raw) if raw else ENTITY_DOCUMENT
            elif key == "new_status":
                cleaned[key] = str(raw) if raw is not None else ""
            else:
                cleaned[key] = raw
        return cls(**cleaned)
