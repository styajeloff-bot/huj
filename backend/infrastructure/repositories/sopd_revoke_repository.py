"""Persistence helpers for SOPD partial revoke requests and facts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.sopd_revocations import (
    SopdRevokedOperator,
    SopdRevokeRequest,
)
from infrastructure.repository_timing import timed_repository

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
TYPE_LEASING_COMPANY = "leasing_company"
TYPE_CONTRACTOR = "contractor"


def _request_to_dict(record: SopdRevokeRequest) -> dict[str, Any]:
    return {
        "id": record.id,
        "signature_request_id": record.signature_request_id,
        "user_id": record.user_id,
        "application_id": record.application_id,
        "status": record.status,
        "selected_leasing_company_ids": list(record.selected_leasing_company_ids),
        "revoked_leasing_company_ids": list(record.revoked_leasing_company_ids),
        "revoked_contractor_ids": list(record.revoked_contractor_ids),
        "excluded_contractor_ids": list(record.excluded_contractor_ids),
        "operators_snapshot": record.operators_snapshot,
        "document_s3_key": record.document_s3_key,
        "requested_at": record.requested_at,
        "confirmed_at": record.confirmed_at,
        "revoke_ip": str(record.revoke_ip) if record.revoke_ip is not None else None,
        "revoke_user_agent": record.revoke_user_agent,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _operator_to_dict(record: SopdRevokedOperator) -> dict[str, Any]:
    return {
        "id": record.id,
        "revoke_request_id": record.revoke_request_id,
        "signature_request_id": record.signature_request_id,
        "user_id": record.user_id,
        "operator_type": record.operator_type,
        "leasing_company_id": record.leasing_company_id,
        "contractor_id": record.contractor_id,
        "operator_name": record.operator_name,
        "operator_inn": record.operator_inn,
        "created_at": record.created_at,
    }


@timed_repository
async def cancel_pending_for_signature(
    session: AsyncSession, *, signature_request_id: uuid.UUID
) -> int:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SopdRevokeRequest)
        .where(
            SopdRevokeRequest.signature_request_id == signature_request_id,
            SopdRevokeRequest.status == STATUS_PENDING,
        )
        .values(status=STATUS_CANCELLED, updated_at=now)
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)


@timed_repository
async def create_pending(
    session: AsyncSession,
    *,
    signature_request_id: uuid.UUID,
    user_id: uuid.UUID,
    application_id: uuid.UUID | None,
    selected_leasing_company_ids: list[uuid.UUID],
    revoked_leasing_company_ids: list[uuid.UUID],
    revoked_contractor_ids: list[uuid.UUID],
    excluded_contractor_ids: list[uuid.UUID],
    operators_snapshot: dict[str, Any],
) -> dict[str, Any]:
    record = SopdRevokeRequest(
        signature_request_id=signature_request_id,
        user_id=user_id,
        application_id=application_id,
        status=STATUS_PENDING,
        selected_leasing_company_ids=selected_leasing_company_ids,
        revoked_leasing_company_ids=revoked_leasing_company_ids,
        revoked_contractor_ids=revoked_contractor_ids,
        excluded_contractor_ids=excluded_contractor_ids,
        operators_snapshot=operators_snapshot,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return _request_to_dict(record)


@timed_repository
async def get_latest_pending(
    session: AsyncSession, *, signature_request_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SopdRevokeRequest)
        .where(
            SopdRevokeRequest.signature_request_id == signature_request_id,
            SopdRevokeRequest.status == STATUS_PENDING,
        )
        .order_by(SopdRevokeRequest.created_at.desc())
        .limit(1)
    )
    record = result.scalars().first()
    return _request_to_dict(record) if record is not None else None


@timed_repository
async def get_by_id(
    session: AsyncSession, *, revoke_request_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SopdRevokeRequest).where(
            SopdRevokeRequest.id == revoke_request_id
        )
    )
    record = result.scalars().first()
    return _request_to_dict(record) if record is not None else None


@timed_repository
async def get_latest_confirmed_for_signature(
    session: AsyncSession, *, signature_request_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SopdRevokeRequest)
        .where(
            SopdRevokeRequest.signature_request_id == signature_request_id,
            SopdRevokeRequest.status == STATUS_CONFIRMED,
            SopdRevokeRequest.document_s3_key.isnot(None),
        )
        .order_by(SopdRevokeRequest.confirmed_at.desc())
        .limit(1)
    )
    record = result.scalars().first()
    return _request_to_dict(record) if record is not None else None


@timed_repository
async def confirm_request(
    session: AsyncSession,
    *,
    revoke_request_id: uuid.UUID,
    revoke_ip: str | None,
    revoke_user_agent: str | None,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SopdRevokeRequest)
        .where(
            SopdRevokeRequest.id == revoke_request_id,
            SopdRevokeRequest.status == STATUS_PENDING,
        )
        .values(
            status=STATUS_CONFIRMED,
            confirmed_at=now,
            revoke_ip=revoke_ip,
            revoke_user_agent=revoke_user_agent,
            updated_at=now,
        )
        .returning(SopdRevokeRequest)
    )
    record = result.scalars().first()
    return _request_to_dict(record) if record is not None else None


@timed_repository
async def set_document_key(
    session: AsyncSession,
    *,
    revoke_request_id: uuid.UUID,
    document_s3_key: str,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SopdRevokeRequest)
        .where(SopdRevokeRequest.id == revoke_request_id)
        .values(document_s3_key=document_s3_key, updated_at=now)
        .returning(SopdRevokeRequest)
    )
    record = result.scalars().first()
    return _request_to_dict(record) if record is not None else None


@timed_repository
async def list_revoked_operators(
    session: AsyncSession, *, signature_request_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(SopdRevokedOperator, SopdRevokeRequest)
        .join(
            SopdRevokeRequest,
            SopdRevokeRequest.id == SopdRevokedOperator.revoke_request_id,
        )
        .where(SopdRevokedOperator.signature_request_id == signature_request_id)
        .order_by(SopdRevokedOperator.created_at.asc())
    )
    items: list[dict[str, Any]] = []
    for operator, request in result.all():
        item = _operator_to_dict(operator)
        item["confirmed_at"] = request.confirmed_at
        item["document_s3_key"] = request.document_s3_key
        items.append(item)
    return items


@timed_repository
async def insert_operator_facts(
    session: AsyncSession,
    *,
    revoke_request_id: uuid.UUID,
    signature_request_id: uuid.UUID,
    user_id: uuid.UUID,
    operators: list[dict[str, Any]],
) -> None:
    if not operators:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "revoke_request_id": revoke_request_id,
            "signature_request_id": signature_request_id,
            "user_id": user_id,
            "operator_type": operator["operator_type"],
            "leasing_company_id": operator.get("leasing_company_id"),
            "contractor_id": operator.get("contractor_id"),
            "operator_name": operator["operator_name"],
            "operator_inn": operator["operator_inn"],
        }
        for operator in operators
    ]
    stmt = pg_insert(SopdRevokedOperator).values(rows)
    stmt = stmt.on_conflict_do_nothing()
    await session.execute(stmt)
    await session.flush()
