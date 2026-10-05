"""Status history persistence and durable LCA event outbox operations."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.messaging.status_events import (
    emit_document_status_changed,
    emit_leasing_app_status_changed,
)
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import DistributorDealerLink
from infrastructure.models.lca_status_history import (
    LcaStatusHistoryMetadata,
    LeasingCompanyApplicationStatusHistory,
)
from infrastructure.repository_timing import timed_repository

_HISTORY_AVAILABLE_FROM_KEY = "history_available_from"
_MAX_PUBLISH_ERROR_LENGTH = 2_000
_LCA_BASELINE_LOCK_NAMESPACE = 0x4C434148  # "LCAH"
_LCA_BASELINE_LOCK_RESOURCE = 0x42415345  # "BASE"


@timed_repository
async def append_document_status_history(
    *,
    document_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    comments: str | None = None,
) -> None:
    emit_document_status_changed(
        document_id=document_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=comments,
    )


@timed_repository
async def append_leasing_app_status_history(
    *,
    application_id: uuid.UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
) -> None:
    """Publish the legacy parent-application status event."""
    emit_leasing_app_status_changed(
        application_id=application_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason,
        company_id=company_id,
    )


def _history_to_dict(
    row: LeasingCompanyApplicationStatusHistory,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "lca_id": row.lca_id,
        "application_id": row.application_id,
        "old_status": row.old_status,
        "new_status": row.new_status,
        "changed_at": row.changed_at,
        "changed_by": row.changed_by,
        "reason": row.reason,
        "application_created_at": row.application_created_at,
        "lca_created_at": row.lca_created_at,
        "dealer_company_id": row.dealer_company_id,
        "distributor_id": row.distributor_id,
        "leasing_company_id": row.leasing_company_id,
        "is_baseline": row.is_baseline,
        "published_at": row.published_at,
        "publish_attempts": row.publish_attempts,
        "next_attempt_at": row.next_attempt_at,
        "last_publish_error": row.last_publish_error,
    }


async def _get_lca_history_projection(
    session: AsyncSession,
    lca_id: UUID,
) -> dict[str, Any] | None:
    stmt = (
        sa.select(
            LeasingCompanyApplication.id.label("lca_id"),
            LeasingCompanyApplication.application_id,
            LeasingCompanyApplication.leasing_company_id,
            LeasingCompanyApplication.status,
            LeasingCompanyApplication.created_at.label("lca_created_at"),
            LeasingApplication.created_at.label("application_created_at"),
            LeasingApplication.dealer_company_id,
            DistributorDealerLink.distributor_company_id.label("distributor_id"),
        )
        .select_from(LeasingCompanyApplication)
        .outerjoin(
            LeasingApplication,
            LeasingApplication.id == LeasingCompanyApplication.application_id,
        )
        .outerjoin(
            DistributorDealerLink,
            DistributorDealerLink.dealer_company_id
            == LeasingApplication.dealer_company_id,
        )
        .where(LeasingCompanyApplication.id == lca_id)
    )
    result = (await session.execute(stmt)).mappings().one_or_none()
    return dict(result) if result is not None else None


@timed_repository
async def append_lca_status_history(
    session: AsyncSession,
    *,
    lca_id: UUID,
    application_id: uuid.UUID | None,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    review_notes: str | None = None,
    decision_comment: str | None = None,
    company_id: UUID | None = None,
    reason: str | None = None,
    changed_at: datetime | None = None,
    is_baseline: bool = False,
) -> UUID:
    """Persist one LCA event in the caller's business transaction.

    The row doubles as an outbox record. Kafka delivery is performed later by
    the scheduled publisher, so a broker outage cannot lose a committed status
    transition.
    """
    _ = company_id  # Kept for a source-compatible transition from the v1 API.
    projection = await _get_lca_history_projection(session, lca_id)
    if projection is None:
        raise ValueError(f"LCA {lca_id} does not exist")

    event_time = changed_at or datetime.now(UTC)
    lca_created_at = projection.get("lca_created_at") or event_time
    row = LeasingCompanyApplicationStatusHistory(
        lca_id=lca_id,
        application_id=application_id or projection.get("application_id"),
        old_status=old_status,
        new_status=new_status,
        changed_at=event_time,
        changed_by=changed_by,
        reason=reason or review_notes or decision_comment,
        application_created_at=projection.get("application_created_at"),
        lca_created_at=lca_created_at,
        dealer_company_id=projection.get("dealer_company_id"),
        distributor_id=projection.get("distributor_id"),
        leasing_company_id=projection.get("leasing_company_id"),
        is_baseline=is_baseline,
    )
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def baseline_exists(session: AsyncSession, lca_id: UUID) -> bool:
    stmt = sa.select(sa.literal(True)).where(
        sa.exists().where(
            LeasingCompanyApplicationStatusHistory.lca_id == lca_id,
            LeasingCompanyApplicationStatusHistory.is_baseline.is_(True),
        )
    )
    return bool((await session.execute(stmt)).scalar_one_or_none())


@timed_repository
async def list_lca_baseline_source(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    stmt = (
        sa.select(
            LeasingCompanyApplication.id.label("lca_id"),
            LeasingCompanyApplication.application_id,
            LeasingCompanyApplication.status,
        )
        .order_by(LeasingCompanyApplication.id)
    )
    return [dict(row) for row in (await session.execute(stmt)).mappings().all()]


@timed_repository
async def count_baselines(session: AsyncSession) -> int:
    stmt = sa.select(sa.func.count()).select_from(
        LeasingCompanyApplicationStatusHistory
    ).where(LeasingCompanyApplicationStatusHistory.is_baseline.is_(True))
    return int((await session.execute(stmt)).scalar_one())


@timed_repository
async def list_baseline_lca_ids(session: AsyncSession) -> set[UUID]:
    stmt = sa.select(LeasingCompanyApplicationStatusHistory.lca_id).where(
        LeasingCompanyApplicationStatusHistory.is_baseline.is_(True)
    )
    return set((await session.execute(stmt)).scalars().all())


@timed_repository
async def try_lca_status_history_baseline_lock(
    session: AsyncSession,
) -> bool:
    """Try to serialize one baseline reconciliation transaction.

    The transaction-scoped lock is released automatically on commit or
    rollback, including when a worker exits unexpectedly.
    """
    result = await session.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(:namespace, :resource)"),
        {
            "namespace": _LCA_BASELINE_LOCK_NAMESPACE,
            "resource": _LCA_BASELINE_LOCK_RESOURCE,
        },
    )
    return bool(result.scalar_one())


@timed_repository
async def claim_unpublished_lca_events(
    session: AsyncSession,
    *,
    limit: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(UTC)
    stmt = (
        sa.select(LeasingCompanyApplicationStatusHistory)
        .where(
            LeasingCompanyApplicationStatusHistory.published_at.is_(None),
            sa.or_(
                LeasingCompanyApplicationStatusHistory.next_attempt_at.is_(None),
                LeasingCompanyApplicationStatusHistory.next_attempt_at
                <= current_time,
            ),
        )
        .order_by(
            LeasingCompanyApplicationStatusHistory.changed_at,
            LeasingCompanyApplicationStatusHistory.id,
        )
        .limit(max(1, limit))
        .with_for_update(skip_locked=True)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_history_to_dict(row) for row in rows]


@timed_repository
async def mark_lca_event_published(
    session: AsyncSession,
    *,
    event_id: UUID,
    published_at: datetime | None = None,
) -> None:
    row = await session.get(LeasingCompanyApplicationStatusHistory, event_id)
    if row is None:
        return
    row.published_at = published_at or datetime.now(UTC)
    row.next_attempt_at = None
    row.last_publish_error = None
    await session.flush()


@timed_repository
async def mark_lca_event_publish_failed(
    session: AsyncSession,
    *,
    event_id: UUID,
    error: str,
    now: datetime | None = None,
) -> int:
    row = await session.get(LeasingCompanyApplicationStatusHistory, event_id)
    if row is None:
        return 0
    attempts = int(row.publish_attempts or 0) + 1
    delay_seconds = min(3_600, 2 ** min(attempts, 12))
    current_time = now or datetime.now(UTC)
    row.publish_attempts = attempts
    row.next_attempt_at = current_time + timedelta(seconds=delay_seconds)
    row.last_publish_error = error[:_MAX_PUBLISH_ERROR_LENGTH]
    await session.flush()
    return attempts


@timed_repository
async def get_lca_outbox_stats(session: AsyncSession) -> dict[str, Any]:
    stmt = sa.select(
        sa.func.count(LeasingCompanyApplicationStatusHistory.id),
        sa.func.min(LeasingCompanyApplicationStatusHistory.changed_at),
    ).where(LeasingCompanyApplicationStatusHistory.published_at.is_(None))
    count, oldest = (await session.execute(stmt)).one()
    return {"backlog": int(count or 0), "oldest_changed_at": oldest}


@timed_repository
async def get_history_available_from(session: AsyncSession) -> date | None:
    row = await session.get(LcaStatusHistoryMetadata, _HISTORY_AVAILABLE_FROM_KEY)
    return row.date_value if row is not None else None


@timed_repository
async def set_history_available_from(
    session: AsyncSession,
    value: date,
) -> None:
    insert_stmt = pg_insert(LcaStatusHistoryMetadata).values(
        key=_HISTORY_AVAILABLE_FROM_KEY,
        date_value=value,
        updated_at=datetime.now(UTC),
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[LcaStatusHistoryMetadata.key],
        set_={
            "date_value": sa.func.least(
                LcaStatusHistoryMetadata.date_value,
                insert_stmt.excluded.date_value,
            ),
            "updated_at": datetime.now(UTC),
        },
    )
    await session.execute(stmt)
    await session.flush()
