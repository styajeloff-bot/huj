"""Application documents repository — Phase 4 D2 core.

Owns ORM access for:
- ``application_documents`` (M2M document↔application with per-LC status)
- ``application_document_requests`` (LC requests a document of a given type)
- ``document_leasing_company_approvals`` (per-LC approval state — helper)

Read-only reads for:
- ``documents`` (to validate the referenced document exists; owned by D1)
- ``leasing_applications`` (selected_leasing_companies; owned by Phase 3)

Returns plain dicts / lists of dicts. ORM objects never escape this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import (
    ApplicationDocument,
    ApplicationDocumentRequest,
    Document,
    DocumentLeasingCompanyApproval,
)
from infrastructure.models.users import User
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Dict shape helpers
# ---------------------------------------------------------------------------


def _ad_to_dict(row: ApplicationDocument) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "document_id": row.document_id,
        "document_request_id": row.document_request_id,
        "user_title": row.user_title,
        "leasing_company_id": row.leasing_company_id,
        "status": row.status,
        "reviewer_comments": row.reviewer_comments,
        "reviewed_by": row.reviewed_by,
        "submitted_at": row.submitted_at,
        "reviewed_at": row.reviewed_at,
        "revision_requested_at": row.revision_requested_at,
        "auto_approved": row.auto_approved,
    }


def _adr_to_dict(row: ApplicationDocumentRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "leasing_company_id": row.leasing_company_id,
        "request_batch_id": row.request_batch_id,
        "document_type": row.document_type,
        "display_name": row.display_name,
        "has_form": row.has_form,
        "form_schema": row.form_schema,
        "form_data": row.form_data,
        "idempotency_key": row.idempotency_key,
        "status": row.status,
        "is_required": row.is_required,
        "request_message": row.request_message,
        "requested_by": row.requested_by,
        "rejection_reason": row.rejection_reason,
        "requested_at": row.requested_at,
        "provided_at": row.provided_at,
        "reviewed_at": row.reviewed_at,
        "reviewed_by": row.reviewed_by,
        "deadline": row.deadline,
        "reminder_sent_at": row.reminder_sent_at,
    }


# ---------------------------------------------------------------------------
# Reads — document requests
# ---------------------------------------------------------------------------


@timed_repository
async def list_requests_for_application(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(ApplicationDocumentRequest)
        .where(ApplicationDocumentRequest.application_id == application_id)
        .order_by(ApplicationDocumentRequest.requested_at.desc().nullslast())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_adr_to_dict(r) for r in rows]


@timed_repository
async def list_request_history(
    session: AsyncSession,
    *,
    application_id: UUID,
    leasing_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Return request history enriched with author, LC, and uploaded file."""
    stmt = (
        select(
            ApplicationDocumentRequest.id.label("request_id"),
            ApplicationDocumentRequest.application_id,
            ApplicationDocumentRequest.leasing_company_id,
            ApplicationDocumentRequest.request_batch_id,
            ApplicationDocumentRequest.document_type,
            ApplicationDocumentRequest.display_name,
            ApplicationDocumentRequest.has_form,
            ApplicationDocumentRequest.form_schema,
            ApplicationDocumentRequest.form_data,
            ApplicationDocumentRequest.status,
            ApplicationDocumentRequest.is_required,
            ApplicationDocumentRequest.request_message,
            ApplicationDocumentRequest.requested_by,
            ApplicationDocumentRequest.requested_at,
            ApplicationDocumentRequest.provided_at,
            Company.name.label("leasing_company_name"),
            User.name.label("requested_by_name"),
            ApplicationDocument.id.label("application_document_id"),
            ApplicationDocument.status.label("document_review_status"),
            ApplicationDocument.user_title,
            Document.id.label("document_id"),
            Document.file_name,
            Document.file_size,
            Document.status.label("document_status"),
            Document.uploaded_at,
        )
        .outerjoin(
            LeasingCompany,
            LeasingCompany.id == ApplicationDocumentRequest.leasing_company_id,
        )
        .outerjoin(Company, Company.id == LeasingCompany.company_id)
        .outerjoin(User, User.id == ApplicationDocumentRequest.requested_by)
        .outerjoin(
            ApplicationDocument,
            ApplicationDocument.document_request_id == ApplicationDocumentRequest.id,
        )
        .outerjoin(Document, Document.id == ApplicationDocument.document_id)
        .where(ApplicationDocumentRequest.application_id == application_id)
    )
    if leasing_company_id is not None:
        stmt = stmt.where(
            ApplicationDocumentRequest.leasing_company_id == leasing_company_id
        )
    stmt = stmt.order_by(
        ApplicationDocumentRequest.requested_at.desc().nullslast(),
        ApplicationDocumentRequest.request_batch_id.desc(),
        ApplicationDocumentRequest.id.asc(),
        Document.uploaded_at.asc().nullslast(),
        Document.id.asc(),
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": row["request_id"],
            "application_id": row["application_id"],
            "leasing_company_id": row["leasing_company_id"],
            "leasing_company_name": row["leasing_company_name"],
            "request_batch_id": row["request_batch_id"],
            "document_type": row["document_type"],
            "display_name": row["display_name"],
            "has_form": row["has_form"],
            "form_schema": row["form_schema"],
            "form_data": row["form_data"],
            "status": row["status"],
            "is_required": row["is_required"],
            "request_message": row["request_message"],
            "requested_by": row["requested_by"],
            "requested_by_name": row["requested_by_name"],
            "requested_at": row["requested_at"],
            "provided_at": row["provided_at"],
            "document": (
                {
                    "id": row["document_id"],
                    "application_document_id": row["application_document_id"],
                    "file_name": row["file_name"],
                    "user_title": row["user_title"],
                    "file_size": row["file_size"],
                    "uploaded_at": row["uploaded_at"],
                    "status": row["document_status"],
                    "review_status": row["document_review_status"],
                }
                if row["document_id"] is not None
                else None
            ),
        }
        for row in rows
    ]


@timed_repository
async def get_request_by_id(
    session: AsyncSession, request_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(ApplicationDocumentRequest, request_id)
    if row is None:
        return None
    return _adr_to_dict(row)


@timed_repository
async def get_request_by_id_for_update(
    session: AsyncSession, request_id: UUID
) -> dict[str, Any] | None:
    """Lock a request row for the duration of a requested-document upload."""
    stmt = (
        select(ApplicationDocumentRequest)
        .where(ApplicationDocumentRequest.id == request_id)
        .with_for_update()
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _adr_to_dict(row)


@timed_repository
async def get_response_document_for_request(
    session: AsyncSession, request_id: UUID
) -> dict[str, Any] | None:
    """Return the sole uploaded response document for an idempotent replay."""
    stmt = (
        select(Document)
        .join(ApplicationDocument, ApplicationDocument.document_id == Document.id)
        .where(ApplicationDocument.document_request_id == request_id)
        .order_by(Document.created_at.asc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": row.id, "company_id": row.company_id,
        "document_type": row.document_type, "file_name": row.file_name,
        "file_path": row.file_path, "file_size": row.file_size,
        "s3_key": row.s3_key, "status": row.status,
        "related_application_id": row.related_application_id,
        "uploaded_at": row.uploaded_at, "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@timed_repository
async def list_response_documents_for_request(
    session: AsyncSession, request_id: UUID
) -> list[dict[str, Any]]:
    """Return every response document in upload order for an idempotent replay."""
    stmt = (
        select(Document, ApplicationDocument.user_title)
        .join(ApplicationDocument, ApplicationDocument.document_id == Document.id)
        .where(ApplicationDocument.document_request_id == request_id)
        .order_by(Document.created_at.asc(), Document.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id, "company_id": row.company_id,
            "document_type": row.document_type, "file_name": row.file_name, "user_title": user_title,
            "file_path": row.file_path, "file_size": row.file_size,
            "s3_key": row.s3_key, "status": row.status,
            "related_application_id": row.related_application_id,
            "uploaded_at": row.uploaded_at, "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row, user_title in rows
    ]


@timed_repository
async def list_request_display_names_for_documents(
    session: AsyncSession, *, application_id: UUID
) -> dict[UUID, str]:
    """Map response document ids to the display name of their exact request."""
    stmt = (
        select(ApplicationDocument.document_id, ApplicationDocumentRequest.display_name)
        .join(
            ApplicationDocumentRequest,
            ApplicationDocumentRequest.id == ApplicationDocument.document_request_id,
        )
        .where(ApplicationDocument.application_id == application_id)
    )
    return dict((await session.execute(stmt)).tuples().all())


@timed_repository
async def list_request_owner_leasing_company_ids_for_documents(
    session: AsyncSession, *, application_id: UUID
) -> dict[UUID, set[UUID]]:
    """Map each response document to every LC that owns its request.

    A document uploaded for an ``ApplicationDocumentRequest`` is private to
    the requesting LC. An absent entry means an ordinary application document
    and therefore retains its existing visibility rules. A set prevents an
    inconsistent duplicate association from accidentally exposing metadata.
    """
    stmt = (
        select(
            ApplicationDocument.document_id,
            ApplicationDocumentRequest.leasing_company_id,
        )
        .join(
            ApplicationDocumentRequest,
            ApplicationDocumentRequest.id == ApplicationDocument.document_request_id,
        )
        .where(ApplicationDocument.application_id == application_id)
    )
    owner_lcs: dict[UUID, set[UUID]] = {}
    for document_id, leasing_company_id in (await session.execute(stmt)).tuples():
        owner_lcs.setdefault(document_id, set()).add(leasing_company_id)
    return owner_lcs


@timed_repository
async def save_request_form_data_and_idempotency(
    session: AsyncSession, *, request_id: UUID, form_data: dict[str, Any] | None,
    idempotency_key: str,
) -> None:
    """Called while the request row is locked; no sensitive values are logged."""
    row = await session.get(ApplicationDocumentRequest, request_id)
    if row is None:
        return
    row.form_data = form_data
    row.idempotency_key = idempotency_key
    await session.flush()


@timed_repository
async def find_request(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
    document_type: str,
) -> dict[str, Any] | None:
    stmt = (
        select(ApplicationDocumentRequest)
        .where(
            and_(
                ApplicationDocumentRequest.application_id == application_id,
                ApplicationDocumentRequest.leasing_company_id == leasing_company_id,
                ApplicationDocumentRequest.document_type == document_type,
            )
        )
        .order_by(
            ApplicationDocumentRequest.requested_at.desc().nullslast(),
            ApplicationDocumentRequest.id.desc(),
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _adr_to_dict(row)


# ---------------------------------------------------------------------------
# Writes — document requests
# ---------------------------------------------------------------------------


@timed_repository
async def create_requests_batch(
    session: AsyncSession,
    *,
    application_id: UUID,
    leasing_company_id: UUID,
    request_batch_id: UUID,
    requested_by: UUID,
    requested_at: datetime,
    documents: list[dict[str, Any]],
    request_message: str | None,
) -> list[dict[str, Any]]:
    """Persist an independent batch, preserving earlier outstanding requests."""
    rows = [
        ApplicationDocumentRequest(
            application_id=application_id,
            leasing_company_id=leasing_company_id,
            request_batch_id=request_batch_id,
            document_type=document["slug"],
            display_name=document["display_name"],
            has_form=bool(document.get("has_form", False)),
            form_schema=document.get("form_schema"),
            status="requested",
            is_required=True,
            request_message=request_message,
            requested_by=requested_by,
            requested_at=requested_at,
        )
        for document in documents
    ]
    session.add_all(rows)
    await session.flush()
    return [_adr_to_dict(row) for row in rows]


@timed_repository
async def mark_request_provided(
    session: AsyncSession,
    *,
    request_id: UUID,
    provided_at: datetime,
) -> bool:
    stmt = (
        update(ApplicationDocumentRequest)
        .where(
            ApplicationDocumentRequest.id == request_id,
            ApplicationDocumentRequest.status == "requested",
        )
        .values(status="provided", provided_at=provided_at)
        .returning(ApplicationDocumentRequest.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


@timed_repository
async def mark_request_approved(
    session: AsyncSession,
    *,
    request_id: UUID,
    reviewed_by: UUID | None = None,
) -> bool:
    """Close one concrete request, never matching historical requests by type."""
    now = datetime.now(UTC)
    values: dict[str, Any] = {"status": "approved", "reviewed_at": now}
    if reviewed_by is not None:
        values["reviewed_by"] = reviewed_by
    stmt = (
        update(ApplicationDocumentRequest)
        .where(
            ApplicationDocumentRequest.id == request_id,
            ApplicationDocumentRequest.status.in_(("requested", "provided")),
        )
        .values(**values)
        .returning(ApplicationDocumentRequest.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


@timed_repository
async def list_lc_display_statuses(
    session: AsyncSession, *, application_id: UUID
) -> dict[UUID, str | None]:
    """Project LC statuses from this application's unresolved required requests."""
    request_priorities = (
        select(
            ApplicationDocumentRequest.application_id.label("application_id"),
            ApplicationDocumentRequest.leasing_company_id.label("leasing_company_id"),
            case(
                (
                    and_(
                        ApplicationDocumentRequest.is_required.is_(True),
                        ApplicationDocumentRequest.status == "provided",
                        ApplicationDocument.id.is_(None),
                    ),
                    2,
                ),
                (
                    and_(
                        ApplicationDocumentRequest.is_required.is_(True),
                        ApplicationDocumentRequest.status == "requested",
                        ApplicationDocument.id.is_(None),
                    ),
                    1,
                ),
                else_=0,
            ).label("request_priority"),
        )
        .outerjoin(
            ApplicationDocument,
            and_(
                ApplicationDocument.document_request_id == ApplicationDocumentRequest.id,
                ApplicationDocument.application_id
                == ApplicationDocumentRequest.application_id,
                ApplicationDocument.leasing_company_id
                == ApplicationDocumentRequest.leasing_company_id,
                ApplicationDocument.status == "approved",
            ),
        )
        .where(ApplicationDocumentRequest.application_id == application_id)
        .subquery()
    )
    priority_by_lc = (
        select(
            request_priorities.c.application_id,
            request_priorities.c.leasing_company_id,
            func.max(request_priorities.c.request_priority).label("request_priority"),
        )
        .group_by(
            request_priorities.c.application_id,
            request_priorities.c.leasing_company_id,
        )
        .subquery()
    )
    stmt = (
        select(
            LeasingCompanyApplication.leasing_company_id,
            LeasingCompanyApplication.status,
            priority_by_lc.c.request_priority,
        )
        .outerjoin(
            priority_by_lc,
            and_(
                priority_by_lc.c.application_id
                == LeasingCompanyApplication.application_id,
                priority_by_lc.c.leasing_company_id
                == LeasingCompanyApplication.leasing_company_id,
            ),
        )
        .where(LeasingCompanyApplication.application_id == application_id)
    )
    return {
        leasing_company_id: (
            "under_review_with_docs"
            if priority == 2
            else "documents_required"
            if priority == 1
            else status
        )
        for leasing_company_id, status, priority in (await session.execute(stmt)).tuples()
        if leasing_company_id is not None
    }


@timed_repository
async def has_pending_required_requests(
    session: AsyncSession,
    *,
    application_id: UUID,
    leasing_company_id: UUID,
) -> bool:
    pending = select(ApplicationDocumentRequest.id).where(
        ApplicationDocumentRequest.application_id == application_id,
        ApplicationDocumentRequest.leasing_company_id == leasing_company_id,
        ApplicationDocumentRequest.is_required.is_(True),
        ApplicationDocumentRequest.status == "requested",
    )
    return bool(await session.scalar(select(pending.exists())))


@timed_repository
async def create_request(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
    document_type: str,
    is_required: bool = True,
    request_message: str | None = None,
    deadline: datetime | None = None,
) -> UUID:
    row = ApplicationDocumentRequest(
        application_id=application_id,
        leasing_company_id=leasing_company_id,
        document_type=document_type,
        display_name=document_type,
        status="requested",
        is_required=is_required,
        request_message=request_message,
        deadline=deadline,
    )
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def update_request_status_by_type(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
    document_type: str,
    new_status: str,
    reviewed_by: UUID | None = None,
    rejection_reason: str | None = None,
) -> bool:
    """Update status of the request matching (app, lc, type). No-op on miss."""
    stmt = (
        select(ApplicationDocumentRequest)
        .where(
            and_(
                ApplicationDocumentRequest.application_id == application_id,
                ApplicationDocumentRequest.leasing_company_id == leasing_company_id,
                ApplicationDocumentRequest.document_type == document_type,
            )
        )
        .order_by(
            ApplicationDocumentRequest.requested_at.desc().nullslast(),
            ApplicationDocumentRequest.id.desc(),
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False
    row.status = new_status
    if reviewed_by is not None:
        row.reviewed_by = reviewed_by
    now = datetime.now(UTC)
    cast("Any", row).reviewed_at = now
    if new_status == "rejected" and rejection_reason is not None:
        row.rejection_reason = rejection_reason
    if new_status == "provided" and row.provided_at is None:
        cast("Any", row).provided_at = now
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Reads — application documents (per-LC review state)
# ---------------------------------------------------------------------------


@timed_repository
async def get_application_document(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    document_id: UUID,
    leasing_company_id: UUID,
) -> dict[str, Any] | None:
    stmt = select(ApplicationDocument).where(
        and_(
            ApplicationDocument.application_id == application_id,
            ApplicationDocument.document_id == document_id,
            ApplicationDocument.leasing_company_id == leasing_company_id,
        )
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _ad_to_dict(row)


@timed_repository
async def get_application_document_by_id(
    session: AsyncSession, application_document_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(ApplicationDocument, application_document_id)
    if row is None:
        return None
    return _ad_to_dict(row)


@timed_repository
async def list_application_document_statuses(
    session: AsyncSession,
    *,
    application_id: UUID,
    leasing_company_id: UUID,
) -> dict[UUID, str | None]:
    """Return review statuses for one application's current LC only."""
    stmt = select(ApplicationDocument.document_id, ApplicationDocument.status).where(
        ApplicationDocument.application_id == application_id,
        ApplicationDocument.leasing_company_id == leasing_company_id,
    )
    return dict((await session.execute(stmt)).tuples().all())


# ---------------------------------------------------------------------------
# Writes — application documents
# ---------------------------------------------------------------------------


@timed_repository
async def approve_submitted_application_document(
    session: AsyncSession,
    *,
    application_id: UUID,
    document_id: UUID,
    leasing_company_id: UUID,
    reviewed_by: UUID,
) -> tuple[bool, UUID | None]:
    """Approve one submitted document and return its exact linked request ID."""
    stmt = (
        update(ApplicationDocument)
        .where(
            ApplicationDocument.application_id == application_id,
            ApplicationDocument.document_id == document_id,
            ApplicationDocument.leasing_company_id == leasing_company_id,
            ApplicationDocument.status == "submitted",
        )
        .values(
            status="approved",
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(UTC),
        )
        .returning(ApplicationDocument.document_request_id)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        return False, None
    return True, row[0]


@timed_repository
async def upsert_application_document(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    document_id: UUID,
    leasing_company_id: UUID,
    status: str,
    reviewer_comments: str | None = None,
    reviewed_by: UUID | None = None,
    auto_approved: bool = False,
    document_request_id: UUID | None = None,
    user_title: str | None = None,
) -> tuple[UUID, bool]:
    """Insert or update an ``application_documents`` row.

    Returns ``(id, created)`` — ``created`` is True if a new row was inserted.
    """
    existing = await get_application_document(
        session,
        application_id=application_id,
        document_id=document_id,
        leasing_company_id=leasing_company_id,
    )
    now = datetime.now(UTC)
    if existing is None:
        row = ApplicationDocument(
            application_id=application_id,
            document_id=document_id,
            leasing_company_id=leasing_company_id,
            document_request_id=document_request_id,
            user_title=user_title,
            status=status,
            reviewer_comments=reviewer_comments,
            reviewed_by=reviewed_by,
            auto_approved=auto_approved,
            reviewed_at=now if reviewed_by is not None else None,
            revision_requested_at=(now if status == "revision_requested" else None),
        )
        session.add(row)
        await session.flush()
        return row.id, True
    stmt = select(ApplicationDocument).where(ApplicationDocument.id == existing["id"])
    row = (await session.execute(stmt)).scalar_one()
    row.status = status
    row.reviewer_comments = reviewer_comments
    if reviewed_by is not None:
        row.reviewed_by = reviewed_by
        cast("Any", row).reviewed_at = now
    if status == "revision_requested":
        cast("Any", row).revision_requested_at = now
    if document_request_id is not None:
        row.document_request_id = document_request_id
    if user_title is not None:
        row.user_title = user_title
    if auto_approved:
        row.auto_approved = True
    await session.flush()
    return row.id, False


# ---------------------------------------------------------------------------
# Writes — per-LC approval helper (document_leasing_company_approvals)
# ---------------------------------------------------------------------------


@timed_repository
async def upsert_lc_approval(
    session: AsyncSession,
    *,
    document_id: UUID,
    leasing_company_id: UUID,
    status: str,
    comments: str | None = None,
    reviewed_by: UUID | None = None,
) -> UUID:
    """Create or update one ``document_leasing_company_approvals`` row."""
    stmt = select(DocumentLeasingCompanyApproval).where(
        and_(
            DocumentLeasingCompanyApproval.document_id == document_id,
            DocumentLeasingCompanyApproval.leasing_company_id == leasing_company_id,
        )
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        new_row = DocumentLeasingCompanyApproval(
            document_id=document_id,
            leasing_company_id=leasing_company_id,
            status=status,
            comments=comments,
            reviewed_by=reviewed_by,
            reviewed_at=now if reviewed_by is not None else None,
        )
        session.add(new_row)
        await session.flush()
        return new_row.id
    row.status = status
    row.comments = comments
    if reviewed_by is not None:
        row.reviewed_by = reviewed_by
        cast("Any", row).reviewed_at = now
    await session.flush()
    return row.id


# ---------------------------------------------------------------------------
# Read helpers — references used by handlers
# ---------------------------------------------------------------------------


@timed_repository
async def get_application(
    session: AsyncSession, application_id: uuid.UUID
) -> dict[str, Any] | None:
    """Tiny projection of ``leasing_applications`` used by D2 handlers."""
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
    }


@timed_repository
async def document_request_visible_to_lc(
    session: AsyncSession, *, document_id: UUID, leasing_company_id: UUID
) -> bool:
    """A response file is private to the LC that created its request."""
    stmt = (
        select(ApplicationDocumentRequest.leasing_company_id)
        .join(ApplicationDocument, ApplicationDocument.document_request_id == ApplicationDocumentRequest.id)
        .where(ApplicationDocument.document_id == document_id)
        .limit(1)
    )
    owner_lc = (await session.execute(stmt)).scalar_one_or_none()
    return owner_lc is None or owner_lc == leasing_company_id


@timed_repository
async def get_document(
    session: AsyncSession, document_id: UUID
) -> dict[str, Any] | None:
    """Read-only — D1 owns writes to ``documents``."""
    row = await session.get(Document, document_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "document_type": row.document_type,
        "file_name": row.file_name,
        "status": row.status,
        "related_application_id": row.related_application_id,
        "leasing_company_status": row.leasing_company_status,
    }


@timed_repository
async def leasing_company_exists(
    session: AsyncSession, leasing_company_id: UUID
) -> bool:
    row = await session.get(LeasingCompany, leasing_company_id)
    return row is not None


@timed_repository
async def list_pending_reviews(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """Return uploaded documents awaiting the LC's review.

    Surface: documents uploaded to fulfil an outstanding
    ``application_document_requests`` entry that belongs to this LC, where
    no ``application_documents`` review row yet exists for this LC — or
    the existing one is in ``revision_requested`` status. Sorted so that
    required requests and overdue deadlines surface first.
    """
    la_alias = LeasingApplication
    # Join documents to their application (via related_application_id) and
    # to the request-row that demands them.
    ad_exists = (
        select(ApplicationDocument.id)
        .where(
            ApplicationDocument.application_id == la_alias.id,
            ApplicationDocument.document_id == Document.id,
            ApplicationDocument.leasing_company_id == leasing_company_id,
            ApplicationDocument.status != "revision_requested",
        )
        .correlate(la_alias, Document)
        .exists()
    )
    base = (
        select(
            Document.id.label("document_id"),
            Document.document_type,
            Document.file_name,
            Document.file_size,
            Document.uploaded_at,
            la_alias.id.label("application_id"),
            la_alias.total_amount,
            la_alias.created_at.label("application_created_at"),
            la_alias.company_id.label("application_company_id"),
            ApplicationDocumentRequest.is_required,
            ApplicationDocumentRequest.request_message,
            ApplicationDocumentRequest.deadline,
        )
        .join(la_alias, la_alias.id == Document.related_application_id)
        .join(
            ApplicationDocumentRequest,
            and_(
                ApplicationDocumentRequest.application_id == la_alias.id,
                ApplicationDocumentRequest.document_type == Document.document_type,
                ApplicationDocumentRequest.leasing_company_id == leasing_company_id,
            ),
        )
        .where(
            la_alias.status.in_(("submitted", "under_review")),
            ApplicationDocumentRequest.status == "provided",
            Document.status.in_(("uploaded", "under_review", "verified")),
            ~ad_exists,
        )
    )

    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar() or 0)

    stmt = (
        base.order_by(
            ApplicationDocumentRequest.is_required.desc(),
            ApplicationDocumentRequest.deadline.asc().nullslast(),
            Document.uploaded_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        {
            "document_id": r.document_id,
            "document_type": r.document_type,
            "file_name": r.file_name,
            "file_size": r.file_size,
            "uploaded_at": r.uploaded_at,
            "application_id": r.application_id,
            "application_company_id": r.application_company_id,
            "total_amount": (
                float(r.total_amount) if r.total_amount is not None else None
            ),
            "application_created_at": r.application_created_at,
            "is_required": bool(r.is_required) if r.is_required is not None else False,
            "request_message": r.request_message,
            "deadline": r.deadline,
        }
        for r in rows
    ]
    return items, total


__all__ = [
    "create_request",
    "create_requests_batch",
    "find_request",
    "get_application",
    "get_application_document",
    "get_application_document_by_id",
    "get_document",
    "get_request_by_id",
    "get_request_by_id_for_update",
    "has_pending_required_requests",
    "leasing_company_exists",
    "list_lc_display_statuses",
    "list_pending_reviews",
    "list_request_history",
    "list_request_owner_leasing_company_ids_for_documents",
    "list_requests_for_application",
    "mark_request_approved",
    "mark_request_provided",
    "update_request_status_by_type",
    "upsert_application_document",
    "upsert_lc_approval",
]
