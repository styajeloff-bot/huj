"""Persistence for director-doc signing invitations.

Each row tracks the post-upload SMS sent to the company general director
for one document slot. Slot identity is the triple
``(application_id, document_type, period_label)`` — ``period_label`` is
nullable, so the unique index uses ``COALESCE(period_label, '')``.

Repository only persists state; idempotency decisions live in the
application service that calls ``find_by_slot`` before ``create``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.documents import DirectorDocSigningInvitation
from infrastructure.repository_timing import timed_repository


def _to_dict(record: DirectorDocSigningInvitation) -> dict[str, Any]:
    return {
        "id": record.id,
        "application_id": record.application_id,
        "document_type": record.document_type,
        "period_label": record.period_label,
        "document_id": record.document_id,
        "signature_request_id": record.signature_request_id,
        "director_user_id": record.director_user_id,
        "director_phone": record.director_phone,
        "sms_sent_at": record.sms_sent_at,
        "sms_error": record.sms_error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }

def _slot_match(period_label: str | None) -> Any:
    if period_label is None:
        return DirectorDocSigningInvitation.period_label.is_(None)
    return DirectorDocSigningInvitation.period_label == period_label

@timed_repository
async def find_by_slot(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    document_type: str,
    period_label: str | None,
) -> dict[str, Any] | None:
    stmt = sa.select(DirectorDocSigningInvitation).where(
        DirectorDocSigningInvitation.application_id == application_id,
        DirectorDocSigningInvitation.document_type == document_type,
        _slot_match(period_label),
    )
    record = (await session.execute(stmt)).scalars().first()
    return _to_dict(record) if record else None

@timed_repository
async def create(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    document_type: str,
    period_label: str | None,
    document_id: UUID | None,
    signature_request_id: UUID | None,
    director_user_id: UUID | None,
    director_phone: str | None,
) -> dict[str, Any]:
    record = DirectorDocSigningInvitation(
        application_id=application_id,
        document_type=document_type,
        period_label=period_label,
        document_id=document_id,
        signature_request_id=signature_request_id,
        director_user_id=director_user_id,
        director_phone=director_phone,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)

@timed_repository
async def mark_sms_sent(
    session: AsyncSession, *, invitation_id: UUID
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        sa.update(DirectorDocSigningInvitation)
        .where(DirectorDocSigningInvitation.id == invitation_id)
        .values(sms_sent_at=now, sms_error=None, updated_at=now)
    )
    await session.flush()

@timed_repository
async def mark_sms_failed(
    session: AsyncSession, *, invitation_id: UUID, error: str
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        sa.update(DirectorDocSigningInvitation)
        .where(DirectorDocSigningInvitation.id == invitation_id)
        .values(sms_error=error[:1000], updated_at=now)
    )
    await session.flush()

@timed_repository
async def get_by_signature_request_id(
    session: AsyncSession, signature_request_id: UUID
) -> dict[str, Any] | None:
    stmt = sa.select(DirectorDocSigningInvitation).where(
        DirectorDocSigningInvitation.signature_request_id == signature_request_id
    )
    record = (await session.execute(stmt)).scalars().first()
    return _to_dict(record) if record else None

@timed_repository
async def list_for_application(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    stmt = (
        sa.select(DirectorDocSigningInvitation)
        .where(DirectorDocSigningInvitation.application_id == application_id)
        .order_by(DirectorDocSigningInvitation.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_dict(r) for r in rows]
