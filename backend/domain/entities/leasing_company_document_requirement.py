"""LeasingCompanyDocumentRequirement entity — Phase 4 D2.

Describes which document types a given leasing company requires of every
applicant. One row per ``(leasing_company_id, document_type_id)``; the
DB uniqueness index enforces that. The entity surfaces domain-level
invariants around update payloads and actor authorization.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.errors import (
    RequirementsUpdateAccessDeniedError,
)


@dataclass
class LeasingCompanyDocumentRequirement:
    """A single requirement row for an LC."""

    id: UUID = field(default_factory=uuid.uuid4)
    leasing_company_id: UUID = field(default_factory=uuid.uuid4)
    document_type_id: UUID = field(default_factory=uuid.uuid4)
    is_required: bool = True
    is_mandatory: bool = False
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_dict(
        cls, data: dict[str, Any]
    ) -> LeasingCompanyDocumentRequirement:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key in {"id", "leasing_company_id", "document_type_id"}:
                if isinstance(raw, UUID):
                    cleaned[key] = raw
                elif isinstance(raw, str):
                    cleaned[key] = UUID(raw)
                else:
                    raise TypeError(f"{key} must be a UUID")
            elif key == "sort_order":
                cleaned[key] = int(raw) if raw is not None else 0
            elif key in {"is_required", "is_mandatory", "is_active"}:
                cleaned[key] = bool(raw) if raw is not None else True
            else:
                cleaned[key] = raw
        return cls(**cleaned)


def ensure_unique_per_type(rows: list[dict[str, Any]]) -> None:
    """Raise if the payload contains duplicate ``document_type_id`` entries."""
    seen: set[UUID] = set()
    for row in rows:
        type_id = row.get("document_type_id")
        if type_id is None:
            continue
        if type_id in seen:
            raise ValueError(
                f"Дублирующийся document_type_id в payload: {type_id}"
            )
        seen.add(type_id)


def ensure_can_update_for_lc(
    *,
    actor_role: str,
    actor_leasing_company_id: UUID | None,
    target_leasing_company_id: UUID,
) -> None:
    """Authorize a requirements-update call.

    - ``carcraft_employee`` may update any LC's requirements.
    - ``leasing_company`` may only update their own LC (matched by the
      resolved ``leasing_companies.id``).
    - Everyone else is rejected.
    """
    if actor_role == "carcraft_employee":
        return
    if actor_role == "leasing_company":
        if (
            actor_leasing_company_id is None
            or actor_leasing_company_id != target_leasing_company_id
        ):
            raise RequirementsUpdateAccessDeniedError()
        return
    raise RequirementsUpdateAccessDeniedError()


def ensure_can_read_for_lc(
    *,
    actor_role: str,
    actor_leasing_company_id: UUID | None,
    target_leasing_company_id: UUID,
) -> None:
    """Authorize a requirements-read call.

    Mirrors update permissions: employee sees everything, LC sees only
    their own. Other roles (clients, dealers) need requirements for
    application-scoped reads — they hit ``/documents/requirements/{app}``
    in D1 which resolves per-application requirements.
    """
    if actor_role == "carcraft_employee":
        return
    if actor_role == "leasing_company":
        if (
            actor_leasing_company_id is None
            or actor_leasing_company_id != target_leasing_company_id
        ):
            raise RequirementsUpdateAccessDeniedError()
        return
    raise RequirementsUpdateAccessDeniedError()
