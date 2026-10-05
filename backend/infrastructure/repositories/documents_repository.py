"""Documents repository — Phase 4 D1 core.

Owns ORM access for ``documents``, ``document_status_history`` and
``document_applications`` (M2M). Read-only reads for
``leasing_applications`` fields needed by ownership checks (no writes to
D3's tables — those go via events).

Returns plain dicts / lists of dicts. ORM objects never escape this module.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyDocumentRequirement,
)
from infrastructure.models.documents import (
    Document,
    DocumentApplication,
)
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Dict shape helpers
# ---------------------------------------------------------------------------

def _doc_to_dict(row: Document) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "document_type": row.document_type,
        "file_name": row.file_name,
        "file_path": row.file_path,
        "file_size": row.file_size,
        "s3_key": row.s3_key,
        "period_label": row.period_label,
        "comments": row.comments,
        "is_required": row.is_required,
        "status": row.status,
        "version": row.version,
        "parent_document_id": row.parent_document_id,
        "is_current_version": row.is_current_version,
        "related_application_id": row.related_application_id,
        "leasing_company_status": row.leasing_company_status,
        "leasing_company_comments": row.leasing_company_comments,
        "leasing_company_reviewed_at": row.leasing_company_reviewed_at,
        "extracted_data": row.extracted_data,
        "recognition_status": row.recognition_status,
        "recognition_error": row.recognition_error,
        "recognition_task_id": row.dbrain_task_id,
        "recognized_at": row.recognized_at,
        "uploaded_at": row.uploaded_at,
        "verified_at": row.verified_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@timed_repository
async def get_by_id(
    session: AsyncSession, document_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(Document, document_id)
    if row is None:
        return None
    return _doc_to_dict(row)

@timed_repository
async def list_for_company(
    session: AsyncSession,
    *,
    company_id: UUID,
    only_current: bool = True,
) -> list[dict[str, Any]]:
    stmt = select(Document).where(Document.company_id == company_id)
    if only_current:
        stmt = stmt.where(Document.is_current_version.is_(True))
    stmt = stmt.order_by(Document.created_at.desc().nullslast(), Document.id.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [_doc_to_dict(r) for r in rows]

@timed_repository
async def count_by_application_ids(
    session: AsyncSession,
    *,
    application_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Return ``{application_id: distinct_document_count}`` for a batch.

    Counts every document linked through ``related_application_id`` *or*
    the ``document_applications`` M2M, deduped by document id. Used by the
    LC cabinet list to render the per-card "прикреплённые документы" badge.
    """
    if not application_ids:
        return {}
    direct_stmt = (
        select(
            Document.related_application_id,
            Document.id,
        )
        .where(
            Document.related_application_id.in_(application_ids),
            Document.is_current_version.is_(True),
        )
    )
    m2m_stmt = (
        select(
            DocumentApplication.application_id,
            DocumentApplication.document_id,
        )
        .join(Document, Document.id == DocumentApplication.document_id)
        .where(
            DocumentApplication.application_id.in_(application_ids),
            Document.is_current_version.is_(True),
        )
    )
    seen: dict[uuid.UUID, set[uuid.UUID]] = {aid: set() for aid in application_ids}
    for app_id, doc_id in (await session.execute(direct_stmt)).all():
        if app_id is None:
            continue
        seen.setdefault(app_id, set()).add(doc_id)
    for app_id, doc_id in (await session.execute(m2m_stmt)).all():
        seen.setdefault(app_id, set()).add(doc_id)
    return {aid: len(ids) for aid, ids in seen.items()}

@timed_repository
async def list_for_application(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Return every document linked to ``application_id`` either via the
    ``related_application_id`` column or through the ``document_applications``
    M2M.
    """
    # M2M ids first
    m2m_ids_stmt = select(DocumentApplication.document_id).where(
        DocumentApplication.application_id == application_id
    )
    m2m_ids = {
        row[0] if isinstance(row[0], UUID) else UUID(row[0])
        for row in (await session.execute(m2m_ids_stmt)).all()
    }
    direct_stmt = select(Document.id).where(
        Document.related_application_id == application_id
    )
    direct_ids = {
        row[0] if isinstance(row[0], UUID) else UUID(row[0])
        for row in (await session.execute(direct_stmt)).all()
    }
    all_ids = m2m_ids | direct_ids
    if not all_ids:
        return []
    hydrate = (
        select(Document)
        .where(Document.id.in_(all_ids))
        .order_by(Document.created_at.desc().nullslast(), Document.id.desc())
    )
    rows = (await session.execute(hydrate)).scalars().all()
    return [_doc_to_dict(r) for r in rows]


@timed_repository
async def list_sopd_passport_metadata(
    session: AsyncSession, *, application_id: UUID, signer_key: str,
) -> list[dict[str, str]]:
    """Expose only page kind, filename and status of this signer's passport."""
    rows = await list_for_application(session, application_id=application_id)
    pages: dict[str, dict[str, str]] = {}
    for row in rows:
        document_type = row.get("document_type")
        metadata = row.get("extracted_data") or {}
        if (
            document_type not in {"sopd_passport_main", "sopd_passport_registration"}
            or metadata.get("signer_key") != signer_key
        ):
            continue
        page = str(metadata.get("page") or document_type.removeprefix("sopd_passport_"))
        if page not in pages:
            pages[page] = {
                "page": page,
                "fileName": str(row.get("file_name") or ""),
                "status": str(row.get("status") or "uploaded"),
            }
    return [pages[page] for page in ("main", "registration") if page in pages]


@timed_repository
async def list_versions(
    session: AsyncSession, document_id: UUID
) -> list[dict[str, Any]]:
    """Return all versions of the chain rooted at the document's parent.

    If ``document_id`` points at a root, returns the root plus any children.
    If it points at a child, returns the root plus all siblings.
    """
    anchor = await session.get(Document, document_id)
    if anchor is None:
        return []
    root_id = (
        anchor.parent_document_id
        if anchor.parent_document_id is not None
        else anchor.id
    )
    stmt = (
        select(Document)
        .where(
            (Document.id == root_id) | (Document.parent_document_id == root_id)
        )
        .order_by(Document.version.asc().nullsfirst(), Document.id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_doc_to_dict(r) for r in rows]

@timed_repository
async def get_current_version_in_chain(
    session: AsyncSession, document_id: UUID
) -> dict[str, Any] | None:
    """Locate the currently-active version in the chain ``document_id`` belongs to."""
    anchor = await session.get(Document, document_id)
    if anchor is None:
        return None
    root_id = (
        anchor.parent_document_id
        if anchor.parent_document_id is not None
        else anchor.id
    )
    stmt = select(Document).where(
        ((Document.id == root_id) | (Document.parent_document_id == root_id))
        & (Document.is_current_version.is_(True))
    )
    row = (await session.execute(stmt)).scalars().first()
    return _doc_to_dict(row) if row else None

@timed_repository
async def get_application(
    session: AsyncSession, application_id: uuid.UUID
) -> dict[str, Any] | None:
    """Tiny projection of ``leasing_applications`` needed by access checks."""
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "status": row.status,
        "selected_leasing_companies": list(row.selected_leasing_companies)
        if row.selected_leasing_companies is not None
        else [],
        "requested_documents": row.requested_documents,
    }

@timed_repository
async def list_requirements_for_lcs(
    session: AsyncSession, leasing_company_ids: list[UUID]
) -> list[dict[str, Any]]:
    """Return requirements + display metadata joined from ``document_types``.

    Produces a de-duplicated view per ``document_type`` — if multiple LCs
    require the same type, the most restrictive (``is_required`` /
    ``is_mandatory``) wins.
    """
    if not leasing_company_ids:
        return []
    from infrastructure.models.documents import DocumentType  # local import

    stmt = (
        select(
            DocumentType.type_code,
            DocumentType.display_name,
            DocumentType.description,
            DocumentType.file_types,
            DocumentType.max_file_size_mb,
            DocumentType.auto_approve,
            DocumentType.validation_rules,
            LeasingCompanyDocumentRequirement.is_required,
            LeasingCompanyDocumentRequirement.is_mandatory,
            LeasingCompanyDocumentRequirement.sort_order,
        )
        .join(
            DocumentType,
            DocumentType.id == LeasingCompanyDocumentRequirement.document_type_id,
        )
        .where(
            LeasingCompanyDocumentRequirement.leasing_company_id.in_(
                leasing_company_ids
            ),
            LeasingCompanyDocumentRequirement.is_active.is_(True),
        )
        .order_by(
            LeasingCompanyDocumentRequirement.sort_order.asc().nullslast(),
            DocumentType.type_code.asc(),
        )
    )
    result = await session.execute(stmt)
    seen: dict[str, dict[str, Any]] = {}
    for row in result.all():
        type_code = row.type_code
        if not type_code:
            continue
        entry = seen.get(type_code)
        payload = {
            "document_type": type_code,
            "display_name": row.display_name,
            "description": row.description,
            "file_types": list(row.file_types) if row.file_types else [],
            "max_file_size_mb": row.max_file_size_mb,
            "auto_approve": bool(row.auto_approve),
            "validation_rules": row.validation_rules,
            "is_required": bool(row.is_required),
            "is_mandatory": bool(row.is_mandatory),
            "sort_order": row.sort_order,
        }
        if entry is None:
            seen[type_code] = payload
        else:
            # Merge: the most restrictive wins for required/mandatory.
            entry["is_required"] = entry["is_required"] or payload["is_required"]
            entry["is_mandatory"] = (
                entry["is_mandatory"] or payload["is_mandatory"]
            )
    return list(seen.values())

@timed_repository
async def find_existing_for_company_by_type(
    session: AsyncSession,
    *,
    company_id: UUID,
    document_types: list[str],
) -> dict[str, dict[str, Any]]:
    """Return a ``{document_type: document_dict}`` map of already-uploaded
    (current-version) documents a given company has.
    """
    if not document_types:
        return {}
    stmt = (
        select(Document)
        .where(
            Document.company_id == company_id,
            Document.document_type.in_(document_types),
            Document.is_current_version.is_(True),
        )
        .order_by(Document.created_at.desc().nullslast())
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.document_type not in out:
            out[r.document_type] = _doc_to_dict(r)
    return out

# ---------------------------------------------------------------------------
# Writes — documents
# ---------------------------------------------------------------------------

@timed_repository
async def create_document(
    session: AsyncSession,
    *,
    company_id: UUID,
    document_type: str,
    file_name: str,
    s3_key: str,
    file_size: int,
    file_path: str | None = None,
    related_application_id: uuid.UUID | None = None,
    review_status: str = "pending",
    status: str = "uploaded",
    recognition_status: str | None = None,
    recognition_error: str | None = None,
    recognition_task_id: str | None = None,
    extracted_data: dict[str, Any] | None = None,
    period_label: str | None = None,
) -> UUID:
    now = datetime.now(UTC)
    row = Document(
        company_id=company_id,
        document_type=document_type,
        file_name=file_name,
        file_path=file_path,
        s3_key=s3_key,
        file_size=file_size,
        status=status,
        version=1,
        is_current_version=True,
        related_application_id=related_application_id,
        leasing_company_status=review_status,
        recognition_status=recognition_status,
        recognition_error=recognition_error,
        dbrain_task_id=recognition_task_id,
        extracted_data=extracted_data,
        period_label=period_label,
        uploaded_at=now,
    )
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def create_version(
    session: AsyncSession,
    *,
    parent_document_id: UUID,
    company_id: UUID,
    document_type: str,
    file_name: str,
    s3_key: str,
    file_size: int,
    version: int,
    file_path: str | None = None,
    related_application_id: uuid.UUID | None = None,
) -> UUID:
    """Insert a new version row and flag the previous current as stale."""
    now = datetime.now(UTC)
    # Un-mark current version in the same chain.
    chain_stmt = select(Document).where(
        (
            (Document.id == parent_document_id)
            | (Document.parent_document_id == parent_document_id)
        )
        & (Document.is_current_version.is_(True))
    )
    existing = (await session.execute(chain_stmt)).scalars().all()
    for prev in existing:
        prev.is_current_version = False
    row = Document(
        company_id=company_id,
        document_type=document_type,
        file_name=file_name,
        file_path=file_path,
        s3_key=s3_key,
        file_size=file_size,
        status="uploaded",
        version=version,
        parent_document_id=parent_document_id,
        is_current_version=True,
        related_application_id=related_application_id,
        leasing_company_status="pending",
        uploaded_at=now,
    )
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def update_review_status(
    session: AsyncSession,
    document_id: UUID,
    *,
    new_status: str,
    comments: str | None = None,
    reviewer_user_id: UUID | None = None,
) -> bool:
    row = await session.get(Document, document_id)
    if row is None:
        return False
    row.leasing_company_status = new_status
    row.leasing_company_comments = comments
    cast("Any", row).leasing_company_reviewed_at = datetime.now(UTC)
    row.approved_by_leasing_company = reviewer_user_id
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def update_recognition(
    session: AsyncSession,
    document_id: UUID,
    *,
    recognition_status: str,
    extracted_data: dict[str, Any] | None,
    recognition_task_id: str | None,
    recognition_error: str | None,
    review_status: str | None = None,
) -> bool:
    row = await session.get(Document, document_id)
    if row is None:
        return False
    row.recognition_status = recognition_status
    row.extracted_data = extracted_data
    row.dbrain_task_id = recognition_task_id
    row.recognition_error = recognition_error
    cast("Any", row).recognized_at = datetime.now(UTC)
    if review_status is not None:
        row.leasing_company_status = review_status
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def link_to_application(
    session: AsyncSession,
    *,
    document_id: UUID,
    application_id: uuid.UUID,
) -> bool:
    """Create a row in the ``document_applications`` M2M (idempotent)."""
    exists_stmt = select(DocumentApplication).where(
        and_(
            DocumentApplication.document_id == document_id,
            DocumentApplication.application_id == application_id,
        )
    )
    existing = (await session.execute(exists_stmt)).scalar_one_or_none()
    if existing is not None:
        return False
    row = DocumentApplication(
        document_id=document_id,
        application_id=application_id,
    )
    session.add(row)
    await session.flush()
    return True

@timed_repository
async def find_document_id_by_type_for_applications(
    session: AsyncSession,
    *,
    application_ids: list[uuid.UUID],
    document_type: str,
) -> UUID | None:
    """Return any ``documents.id`` of ``document_type`` already linked to one
    of ``application_ids`` (via M2M or ``related_application_id``).

    Used by attach-helpers to reuse an existing blob when resubmitting or
    fanning out — we link the same document to the remaining apps instead of
    re-downloading / re-rendering and bloating the documents table.
    """
    if not application_ids:
        return None
    m2m_stmt = (
        select(Document.id)
        .join(
            DocumentApplication, DocumentApplication.document_id == Document.id
        )
        .where(
            and_(
                DocumentApplication.application_id.in_(application_ids),
                Document.document_type == document_type,
            )
        )
        .limit(1)
    )
    row = (await session.execute(m2m_stmt)).first()
    if row is not None:
        return row[0] if isinstance(row[0], UUID) else UUID(row[0])
    direct_stmt = (
        select(Document.id)
        .where(
            and_(
                Document.related_application_id.in_(application_ids),
                Document.document_type == document_type,
            )
        )
        .limit(1)
    )
    row = (await session.execute(direct_stmt)).first()
    if row is not None:
        return row[0] if isinstance(row[0], UUID) else UUID(row[0])
    return None

@timed_repository
async def list_application_ids_with_document_type(
    session: AsyncSession,
    *,
    application_ids: list[uuid.UUID],
    document_type: str,
) -> set[uuid.UUID]:
    """Subset of ``application_ids`` that already has a ``document_type`` doc.

    Checks both the ``document_applications`` M2M and the legacy
    ``related_application_id`` column.
    """
    if not application_ids:
        return set()
    m2m_stmt = (
        select(DocumentApplication.application_id)
        .join(Document, Document.id == DocumentApplication.document_id)
        .where(
            and_(
                DocumentApplication.application_id.in_(application_ids),
                Document.document_type == document_type,
            )
        )
    )
    direct_stmt = (
        select(Document.related_application_id)
        .where(
            and_(
                Document.related_application_id.in_(application_ids),
                Document.document_type == document_type,
            )
        )
    )
    seen: set[uuid.UUID] = set()
    for m2m_row in (await session.execute(m2m_stmt)).all():
        seen.add(m2m_row[0])
    for direct_row in (await session.execute(direct_stmt)).all():
        if direct_row[0] is not None:
            seen.add(direct_row[0])
    return seen

# ---------------------------------------------------------------------------
# Writes — status history
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Reference checks used by handlers
# ---------------------------------------------------------------------------

@timed_repository
async def count_for_company(
    session: AsyncSession, company_id: UUID
) -> int:
    stmt = select(func.count(Document.id)).where(
        Document.company_id == company_id
    )
    return int((await session.execute(stmt)).scalar() or 0)

# ---------------------------------------------------------------------------
# Soft-delete / restore / recognition reset (Phase 7a G2)
# ---------------------------------------------------------------------------

@timed_repository
async def soft_delete(
    session: AsyncSession,
    document_id: UUID,
) -> bool:
    """Soft-hide a document.

    The ``documents`` table does not carry a dedicated ``is_deleted``
    column, so we flag ``is_current_version=False`` to make the row
    disappear from current listings. ``list_for_company(only_current=True)``
    and ``find_existing_for_company_by_type`` both filter on
    ``is_current_version``.

    Returns ``False`` when the document does not exist.
    """
    row = await session.get(Document, document_id)
    if row is None:
        return False
    row.is_current_version = False
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def restore(
    session: AsyncSession,
    document_id: UUID,
) -> bool:
    """Restore a previously soft-deleted document.

    Flips ``is_current_version`` back to ``True``. If another version in
    the same chain is currently active, that other row is demoted so we
    never end up with two current versions simultaneously.
    """
    anchor = await session.get(Document, document_id)
    if anchor is None:
        return False
    root_id = (
        anchor.parent_document_id
        if anchor.parent_document_id is not None
        else anchor.id
    )
    # Demote any current sibling first.
    chain_stmt = select(Document).where(
        (
            (Document.id == root_id)
            | (Document.parent_document_id == root_id)
        )
        & (Document.id != anchor.id)
        & (Document.is_current_version.is_(True))
    )
    existing = (await session.execute(chain_stmt)).scalars().all()
    for prev in existing:
        prev.is_current_version = False
    anchor.is_current_version = True
    cast("Any", anchor).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def reset_recognition(
    session: AsyncSession,
    document_id: UUID,
) -> bool:
    """Clear recognition metadata so a fresh DBRAIN run can be scheduled."""
    row = await session.get(Document, document_id)
    if row is None:
        return False
    row.recognition_status = "pending"
    row.extracted_data = None
    row.dbrain_task_id = None
    row.recognition_error = None
    row.recognized_at = None
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def collect_lc_ids_for_company(
    session: AsyncSession,
    *,
    company_id: UUID,
) -> list[UUID]:
    """Collect every leasing-company id that has been selected on any of
    the company's applications.

    Used by the "user-enhanced" listing to aggregate requirements across
    every application the user's company is involved in. Returns a
    deduplicated, ordered list.
    """
    from infrastructure.models.applications import LeasingApplication

    stmt = select(LeasingApplication.selected_leasing_companies).where(
        LeasingApplication.company_id == company_id
    )
    result = await session.execute(stmt)
    out: set[UUID] = set()
    for row in result.all():
        ids = row[0]
        if not ids:
            continue
        for lc_id in ids:
            if lc_id is None:
                continue
            if isinstance(lc_id, UUID):
                out.add(lc_id)
            else:
                out.add(UUID(lc_id))
    return sorted(out)

@timed_repository
async def list_user_documents(
    session: AsyncSession,
    *,
    company_id: UUID,
    only_current: bool = True,
) -> list[dict[str, Any]]:
    """User-scoped listing.

    The ``documents`` schema keys ownership by ``company_id`` (Express
    historically did the same — "user documents" are the documents
    attached to the user's company). Thin wrapper around
    :func:`list_for_company` so handler code reads declaratively.
    """
    return await list_for_company(
        session, company_id=company_id, only_current=only_current
    )

__all__ = [
    "collect_lc_ids_for_company",
    "count_for_company",
    "create_document",
    "create_version",
    "find_existing_for_company_by_type",
    "get_application",
    "get_by_id",
    "get_current_version_in_chain",
    "link_to_application",
    "list_for_application",
    "list_for_company",
    "list_requirements_for_lcs",
    "list_user_documents",
    "list_versions",
    "reset_recognition",
    "restore",
    "soft_delete",
    "update_recognition",
    "update_review_status",
]
