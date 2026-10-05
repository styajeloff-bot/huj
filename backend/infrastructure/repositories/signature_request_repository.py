"""CRUD for signature_requests.

All public functions return dicts (CLAUDE.md: repos never return ORM
objects). Transitions enforced at the application layer — this repo only
persists state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.signature_requests import SignatureRequest
from infrastructure.models.users import User
from infrastructure.repository_timing import timed_repository

# Canonical status values — mirrored in the domain layer.
STATUS_PENDING = "pending"
STATUS_SIGNED_ELECTRONIC = "signed_electronic"
STATUS_SIGNED_PHYSICAL = "signed_physical"
STATUS_CANCELLED = "cancelled"
STATUS_REVOKED = "revoked"

# Canonical document types — frontend cabinet filters by these.
DOC_TYPE_SOPD = "sopd"
DOC_TYPE_DIRECTOR_DOC_PREFIX = "director_doc_"


def is_director_doc_type(document_type: str) -> bool:
    return document_type.startswith(DOC_TYPE_DIRECTOR_DOC_PREFIX)


def _to_dict(record: SignatureRequest) -> dict[str, Any]:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "invited_by_user_id": record.invited_by_user_id,
        "application_id": record.application_id,
        "document_type": record.document_type,
        "status": record.status,
        "signature_method": record.signature_method,
        "subject_snapshot": record.subject_snapshot,
        "signed_pdf_s3_key": record.signed_pdf_s3_key,
        "signing_ip": record.signing_ip,
        "signing_user_agent": record.signing_user_agent,
        "sent_at": record.sent_at,
        "signed_at": record.signed_at,
        "revoked_at": record.revoked_at,
        "revoke_requested_at": record.revoke_requested_at,
        "revoke_ip": str(record.revoke_ip) if record.revoke_ip is not None else None,
        "revoke_user_agent": record.revoke_user_agent,
        "cancelled_at": record.cancelled_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@timed_repository
async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    application_id: uuid.UUID | None,
    document_type: str,
    subject_snapshot: dict[str, Any],
    sent_at: datetime | None = None,
    invited_by_user_id: UUID | None = None,
) -> dict[str, Any]:
    record = SignatureRequest(
        user_id=user_id,
        invited_by_user_id=invited_by_user_id,
        application_id=application_id,
        document_type=document_type,
        status=STATUS_PENDING,
        subject_snapshot=subject_snapshot,
        sent_at=sent_at,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)


@timed_repository
async def get_by_id(session: AsyncSession, request_id: UUID) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SignatureRequest).where(SignatureRequest.id == request_id)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def update_subject_snapshot(
    session: AsyncSession,
    *,
    request_id: UUID,
    subject_snapshot: dict[str, Any],
    expected_status: str | None = None,
    expected_document_type: str | None = None,
    invited_by_user_id: UUID | None = None,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    where = [SignatureRequest.id == request_id]
    if expected_status is not None:
        where.append(SignatureRequest.status == expected_status)
    if expected_document_type is not None:
        where.append(SignatureRequest.document_type == expected_document_type)
    if invited_by_user_id is not None:
        where.append(SignatureRequest.invited_by_user_id == invited_by_user_id)
    result = await session.execute(
        sa.update(SignatureRequest)
        .where(*where)
        .values(subject_snapshot=subject_snapshot, updated_at=now)
        .returning(SignatureRequest)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def list_signers_with_phone_for_application(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    document_type: str = DOC_TYPE_SOPD,
) -> list[dict[str, Any]]:
    """Return signers of a given document type on the application along
    with their user phone, ordered newest-first.

    Used when the questionnaire's ``director_phone`` is empty — the post-
    upload SMS flow falls back to a signer whose ``subject_snapshot``
    matches the questionnaire's ``director_full_name``.
    """
    stmt = (
        sa.select(
            User.phone.label("phone"),
            SignatureRequest.subject_snapshot.label("snapshot"),
        )
        .join(SignatureRequest, SignatureRequest.user_id == User.id)
        .where(
            SignatureRequest.application_id == application_id,
            SignatureRequest.document_type == document_type,
        )
        .order_by(SignatureRequest.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [{"phone": row.phone, "snapshot": row.snapshot} for row in rows]


@timed_repository
async def list_for_user(
    session: AsyncSession, user_id: UUID, *, statuses: list[str] | None = None
) -> list[dict[str, Any]]:
    stmt = sa.select(SignatureRequest).where(SignatureRequest.user_id == user_id)
    if statuses:
        stmt = stmt.where(SignatureRequest.status.in_(statuses))
    stmt = stmt.order_by(SignatureRequest.created_at.desc())
    result = await session.execute(stmt)
    return [_to_dict(r) for r in result.scalars().all()]


@timed_repository
async def request_revoke(
    session: AsyncSession, *, request_id: UUID
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SignatureRequest)
        .where(
            SignatureRequest.id == request_id,
            SignatureRequest.status.in_(
                [STATUS_SIGNED_ELECTRONIC, STATUS_SIGNED_PHYSICAL]
            ),
        )
        .values(revoke_requested_at=now, updated_at=now)
        .returning(SignatureRequest)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


async def mark_revoked(
    session: AsyncSession,
    *,
    request_id: UUID,
    revoke_ip: str | None,
    revoke_user_agent: str | None,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SignatureRequest)
        .where(
            SignatureRequest.id == request_id,
            SignatureRequest.status.in_(
                [STATUS_SIGNED_ELECTRONIC, STATUS_SIGNED_PHYSICAL]
            ),
        )
        .values(
            status=STATUS_REVOKED,
            revoked_at=now,
            revoke_ip=revoke_ip,
            revoke_user_agent=revoke_user_agent,
            updated_at=now,
        )
        .returning(SignatureRequest)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def mark_signed(
    session: AsyncSession,
    *,
    request_id: UUID,
    method: str,
    signed_pdf_s3_key: str,
    signing_ip: str | None,
    signing_user_agent: str | None,
) -> dict[str, Any] | None:
    """Finalize a signature attempt.

    ``method`` is ``'electronic'`` (PEP flow) or ``'physical'`` (scan upload).
    Only pending rows transition; if the row is already signed/cancelled,
    returns ``None`` — the caller should treat this as a conflict.
    """
    status = (
        STATUS_SIGNED_ELECTRONIC if method == "electronic" else STATUS_SIGNED_PHYSICAL
    )
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SignatureRequest)
        .where(
            SignatureRequest.id == request_id,
            SignatureRequest.status == STATUS_PENDING,
        )
        .values(
            status=status,
            signature_method=method,
            signed_pdf_s3_key=signed_pdf_s3_key,
            signing_ip=signing_ip,
            signing_user_agent=signing_user_agent,
            signed_at=now,
            updated_at=now,
        )
        .returning(SignatureRequest)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def backfill_application_id(
    session: AsyncSession,
    *,
    invited_by_user_id: UUID,
    application_id: uuid.UUID,
) -> int:
    """Attach a newly-created application to pending invites issued by the
    applicant. Only touches rows that still have ``application_id IS NULL``
    — signed/cancelled rows are preserved as-is. Returns row count."""
    result = await session.execute(
        sa.update(SignatureRequest)
        .where(
            SignatureRequest.invited_by_user_id == invited_by_user_id,
            SignatureRequest.application_id.is_(None),
        )
        .values(application_id=application_id, updated_at=datetime.now(UTC))
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0)


@timed_repository
async def list_for_application(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    document_type: str = DOC_TYPE_SOPD,
) -> list[dict[str, Any]]:
    """Return all signature requests of a given document type on the
    application, newest-first."""
    stmt = (
        sa.select(SignatureRequest)
        .where(
            SignatureRequest.application_id == application_id,
            SignatureRequest.document_type == document_type,
        )
        .order_by(SignatureRequest.created_at.desc())
    )
    result = await session.execute(stmt)
    return [_to_dict(r) for r in result.scalars().all()]


@timed_repository
async def mark_cancelled(
    session: AsyncSession, *, request_id: UUID
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SignatureRequest)
        .where(
            SignatureRequest.id == request_id,
            SignatureRequest.status == STATUS_PENDING,
        )
        .values(status=STATUS_CANCELLED, cancelled_at=now, updated_at=now)
        .returning(SignatureRequest)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None
