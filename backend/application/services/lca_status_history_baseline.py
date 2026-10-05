"""Idempotent reconciliation of the LCA status-history baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure import clickhouse_readonly
from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import status_history_repository as history_repo

_MOSCOW = ZoneInfo("Europe/Moscow")
_BASELINE_REASON = "Технический baseline истории статусов"


class LcaStatusHistoryBaselineState(StrEnum):
    """Outcome of one short reconciliation pass."""

    LOCKED = "locked"
    ALREADY_READY = "already_ready"
    WAITING_FOR_DELIVERY = "waiting_for_delivery"
    READY = "ready"
    DATA_ERROR = "data_error"


@dataclass(frozen=True, slots=True)
class LcaStatusHistoryBaselineResult:
    """Typed operational state returned to Taskiq and the manual CLI."""

    state: LcaStatusHistoryBaselineState
    total_lca: int = 0
    existing_baselines: int = 0
    created_baselines: int = 0
    postgres_baselines: int = 0
    clickhouse_baselines: int | None = None
    history_available_from: date | None = None
    errors: tuple[str, ...] = ()


def _aware_datetime(now: datetime | None) -> datetime:
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return reference


def _next_full_moscow_day(now: datetime | None) -> date:
    return _aware_datetime(now).astimezone(_MOSCOW).date() + timedelta(days=1)


async def _reconcile_locked_baseline(
    session: AsyncSession,
    now: datetime | None,
) -> LcaStatusHistoryBaselineResult:
    sources = await history_repo.list_lca_baseline_source(session)
    existing_ids = await history_repo.list_baseline_lca_ids(session)
    missing = [row for row in sources if row["lca_id"] not in existing_ids]
    invalid = [row for row in missing if not str(row.get("status") or "").strip()]
    total_lca = len(sources)
    existing_baselines = len(existing_ids)

    if invalid:
        await session.rollback()
        return LcaStatusHistoryBaselineResult(
            state=LcaStatusHistoryBaselineState.DATA_ERROR,
            total_lca=total_lca,
            existing_baselines=existing_baselines,
            postgres_baselines=existing_baselines,
            errors=tuple(f"LCA {row['lca_id']}: status is empty" for row in invalid),
        )

    baseline_time = _aware_datetime(now)
    for row in missing:
        await history_repo.append_lca_status_history(
            session,
            lca_id=row["lca_id"],
            application_id=row.get("application_id"),
            old_status=None,
            new_status=str(row["status"]),
            changed_at=baseline_time,
            is_baseline=True,
            reason=_BASELINE_REASON,
        )

    created_baselines = len(missing)
    postgres_baselines = await history_repo.count_baselines(session)
    if postgres_baselines != total_lca:
        await session.rollback()
        return LcaStatusHistoryBaselineResult(
            state=LcaStatusHistoryBaselineState.DATA_ERROR,
            total_lca=total_lca,
            existing_baselines=existing_baselines,
            created_baselines=created_baselines,
            postgres_baselines=postgres_baselines,
            errors=(
                "Количество baseline в PostgreSQL не совпало с "
                f"количеством LCA: {postgres_baselines} != {total_lca}",
            ),
        )

    if created_baselines:
        await session.commit()
        return LcaStatusHistoryBaselineResult(
            state=LcaStatusHistoryBaselineState.WAITING_FOR_DELIVERY,
            total_lca=total_lca,
            existing_baselines=existing_baselines,
            created_baselines=created_baselines,
            postgres_baselines=postgres_baselines,
        )

    clickhouse_baselines = (
        await clickhouse_readonly.count_lca_status_history_baselines()
    )
    if clickhouse_baselines < postgres_baselines:
        await session.rollback()
        return LcaStatusHistoryBaselineResult(
            state=LcaStatusHistoryBaselineState.WAITING_FOR_DELIVERY,
            total_lca=total_lca,
            existing_baselines=existing_baselines,
            postgres_baselines=postgres_baselines,
            clickhouse_baselines=clickhouse_baselines,
        )
    if clickhouse_baselines != postgres_baselines:
        await session.rollback()
        return LcaStatusHistoryBaselineResult(
            state=LcaStatusHistoryBaselineState.DATA_ERROR,
            total_lca=total_lca,
            existing_baselines=existing_baselines,
            postgres_baselines=postgres_baselines,
            clickhouse_baselines=clickhouse_baselines,
            errors=(
                "Количество baseline в ClickHouse не совпало с "
                f"PostgreSQL: {clickhouse_baselines} != {postgres_baselines}",
            ),
        )

    available_from = _next_full_moscow_day(now)
    await history_repo.set_history_available_from(session, available_from)
    await session.commit()
    return LcaStatusHistoryBaselineResult(
        state=LcaStatusHistoryBaselineState.READY,
        total_lca=total_lca,
        existing_baselines=existing_baselines,
        postgres_baselines=postgres_baselines,
        clickhouse_baselines=clickhouse_baselines,
        history_available_from=available_from,
    )


async def reconcile_lca_status_history_baseline(
    *,
    now: datetime | None = None,
) -> LcaStatusHistoryBaselineResult:
    """Create or verify the durable LCA baseline in one locked pass.

    Newly inserted outbox rows must commit before event-worker can deliver
    them, so that pass returns waiting_for_delivery. A later pass records the
    watermark only after PostgreSQL and ClickHouse both contain exactly one
    baseline for every current LCA.

    Infrastructure failures propagate to the task boundary for retry and
    logging. Invalid source data and impossible count relationships are
    returned as data_error without publishing a readiness watermark.
    """
    async with AsyncSessionLocal() as session:
        try:
            locked = await history_repo.try_lca_status_history_baseline_lock(session)
            if not locked:
                await session.rollback()
                result = LcaStatusHistoryBaselineResult(
                    state=LcaStatusHistoryBaselineState.LOCKED
                )
            else:
                existing_watermark = await history_repo.get_history_available_from(
                    session
                )
                if existing_watermark is not None:
                    await session.rollback()
                    result = LcaStatusHistoryBaselineResult(
                        state=LcaStatusHistoryBaselineState.ALREADY_READY,
                        history_available_from=existing_watermark,
                    )
                else:
                    result = await _reconcile_locked_baseline(session, now)
        except Exception:
            await session.rollback()
            raise
    return result
