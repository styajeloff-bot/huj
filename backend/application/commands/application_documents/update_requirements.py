"""Replace the set of document-type requirements for a leasing company.

Mirrors Express: delete all existing rows, then insert one row per item
in the payload. Uniqueness per ``document_type_id`` is enforced by the
DB; we surface it as a domain-level check before the DELETE so we fail
fast with a clean error.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_company_document_requirement import (
    ensure_can_update_for_lc,
    ensure_unique_per_type,
)
from domain.errors import (
    DocumentTypeNotFoundError,
    InvalidDocumentReviewError,
    LeasingCompanyNotFoundError,
)
from infrastructure.repositories import (
    application_documents_repository as ad_repo,
)
from infrastructure.repositories import (
    leasing_company_document_requirements_repository as lcdr_repo,
)

logger = logging.getLogger("carcraft-backend")


@dataclass
class RequirementInput:
    """One item in the update payload.

    The Express API accepts either ``document_type`` (type_code string)
    or ``document_type_id`` (integer). We accept both and resolve the
    missing side via ``document_types``.
    """

    document_type: str | None = None
    document_type_id: UUID | None = None
    is_required: bool = False
    is_mandatory: bool = False
    sort_order: int = 0


@dataclass
class UpdateRequirementsCommand:
    leasing_company_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_leasing_company_id: UUID | None
    requirements: list[RequirementInput] = field(default_factory=list)


async def handle_update_requirements(
    cmd: UpdateRequirementsCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    # Authorization — LCs only touch their own, employees may touch any.
    ensure_can_update_for_lc(
        actor_role=cmd.actor_role,
        actor_leasing_company_id=cmd.actor_leasing_company_id,
        target_leasing_company_id=cmd.leasing_company_id,
    )

    # Precheck that the LC exists so we don't delete and then fail to
    # insert, leaving the requirements table empty.
    if not await ad_repo.leasing_company_exists(
        session, cmd.leasing_company_id
    ):
        raise LeasingCompanyNotFoundError(cmd.leasing_company_id)

    resolved: list[dict[str, Any]] = []
    for item in cmd.requirements:
        type_id = item.document_type_id
        if type_id is None:
            if not item.document_type:
                raise InvalidDocumentReviewError(
                    "Укажите document_type или document_type_id"
                )
            resolved_id = await lcdr_repo.get_document_type_id(
                session, item.document_type
            )
            if resolved_id is None:
                raise DocumentTypeNotFoundError(item.document_type)
            type_id = resolved_id
        resolved.append(
            {
                "document_type_id": type_id,
                "is_required": bool(item.is_required),
                "is_mandatory": bool(item.is_mandatory),
                "sort_order": int(item.sort_order or 0),
            }
        )

    try:
        ensure_unique_per_type(resolved)
    except ValueError as exc:
        raise InvalidDocumentReviewError(str(exc)) from exc

    deleted = await lcdr_repo.delete_requirements_for_lc(
        session, cmd.leasing_company_id
    )
    inserted_ids: list[UUID] = []
    for row in resolved:
        new_id = await lcdr_repo.insert_requirement(
            session,
            leasing_company_id=cmd.leasing_company_id,
            document_type_id=row["document_type_id"],
            is_required=bool(row["is_required"]),
            is_mandatory=bool(row["is_mandatory"]),
            sort_order=int(row["sort_order"]),
        )
        inserted_ids.append(new_id)

    logger.info(
        "lcdr_update lc=%s deleted=%d inserted=%d",
        cmd.leasing_company_id,
        deleted,
        len(inserted_ids),
    )
    return {
        "message": "Требования обновлены",
        "leasing_company_id": cmd.leasing_company_id,
        "updated_count": len(inserted_ids),
        "deleted_count": deleted,
    }
