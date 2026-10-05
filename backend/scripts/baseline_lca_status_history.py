#!/usr/bin/env python3
"""Create and verify the one-time LCA history baseline.

The script is idempotent. It records baseline rows in PostgreSQL, drains the
durable outbox, waits until event-worker has inserted them into ClickHouse,
and only then stores ``history_available_from`` for API use.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# Allow direct execution as ``python scripts/baseline_lca_status_history.py``.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from application.services.lca_status_history_baseline import (  # noqa: E402
    LcaStatusHistoryBaselineResult,
    LcaStatusHistoryBaselineState,
    reconcile_lca_status_history_baseline,
)
from application.tasks.lca_status_history import (  # noqa: E402
    PUBLISH_BATCH_SIZE,
    publish_lca_status_history_batch,
)
from infrastructure import clickhouse_readonly  # noqa: E402
from infrastructure.database import AsyncSessionLocal  # noqa: E402
from infrastructure.messaging.admin import ensure_topics  # noqa: E402
from infrastructure.messaging.broker import start_broker, stop_broker  # noqa: E402
from infrastructure.repositories import (  # noqa: E402
    status_history_repository as history_repo,
)

logger = logging.getLogger("carcraft-backend")

@dataclass
class BaselineReport:
    dry_run: bool
    watermark_preexisting: bool = False
    total_lca: int = 0
    existing_baselines: int = 0
    created_baselines: int = 0
    skipped_baselines: int = 0
    published_events: int = 0
    postgres_baselines: int = 0
    clickhouse_baselines: int = 0
    history_available_from: date | None = None
    errors: list[str] = field(default_factory=list)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the durable LCA status-history baseline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect rows without writing PostgreSQL, Kafka, or ClickHouse",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=180,
        help="Seconds to wait for event-worker ClickHouse ingestion",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path for the JSON report (stdout is always emitted)",
    )
    return parser.parse_args()


async def _clickhouse_baseline_count() -> int:
    return await clickhouse_readonly.count_lca_status_history_baselines()


async def _create_postgres_baselines(report: BaselineReport) -> None:
    baseline_time = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        try:
            sources = await history_repo.list_lca_baseline_source(session)
            existing_ids = await history_repo.list_baseline_lca_ids(session)
            existing_watermark = await history_repo.get_history_available_from(
                session
            )
            report.total_lca = len(sources)
            report.existing_baselines = len(existing_ids)
            report.skipped_baselines = len(existing_ids)
            if existing_watermark is not None:
                report.watermark_preexisting = True
                report.history_available_from = existing_watermark
                await session.rollback()
                return

            missing = [row for row in sources if row["lca_id"] not in existing_ids]
            invalid = [row for row in missing if not row.get("status")]
            for row in invalid:
                report.errors.append(f"LCA {row['lca_id']}: status is empty")
            if invalid:
                await session.rollback()
                return
            if report.dry_run:
                report.created_baselines = len(missing)
                await session.rollback()
                return

            for row in missing:
                await history_repo.append_lca_status_history(
                    session,
                    lca_id=row["lca_id"],
                    application_id=row.get("application_id"),
                    old_status=None,
                    new_status=str(row["status"]),
                    changed_at=baseline_time,
                    is_baseline=True,
                    reason="Технический baseline истории статусов",
                )
                report.created_baselines += 1
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _drain_outbox(report: BaselineReport) -> None:
    await ensure_topics()
    await start_broker()
    try:
        while True:
            result = await publish_lca_status_history_batch(
                limit=PUBLISH_BATCH_SIZE
            )
            report.published_events += result["published"]
            if result["claimed"] == 0:
                break
            if result["failed"]:
                break
    finally:
        await stop_broker()

    async with AsyncSessionLocal() as session:
        stats = await history_repo.get_lca_outbox_stats(session)
    if stats["backlog"]:
        report.errors.append(
            f"В outbox осталось неопубликованных событий: {stats['backlog']}"
        )


async def _wait_for_clickhouse(expected: int, timeout_seconds: int) -> int:
    deadline = asyncio.get_running_loop().time() + max(1, timeout_seconds)
    actual = 0
    while True:
        actual = await _clickhouse_baseline_count()
        if actual == expected:
            return actual
        if asyncio.get_running_loop().time() >= deadline:
            return actual
        await asyncio.sleep(2)


def _apply_reconciliation_result(
    report: BaselineReport,
    result: LcaStatusHistoryBaselineResult,
) -> None:
    if result.state is not LcaStatusHistoryBaselineState.ALREADY_READY:
        report.total_lca = result.total_lca
        report.existing_baselines = result.existing_baselines
        report.created_baselines += result.created_baselines
        report.skipped_baselines = result.existing_baselines
        report.postgres_baselines = result.postgres_baselines
    if result.clickhouse_baselines is not None:
        report.clickhouse_baselines = result.clickhouse_baselines
    if result.history_available_from is not None:
        report.history_available_from = result.history_available_from
    report.errors.extend(result.errors)


async def _reconcile_until_unlocked(
    timeout_seconds: int,
) -> LcaStatusHistoryBaselineResult:
    deadline = asyncio.get_running_loop().time() + max(1, timeout_seconds)
    while True:
        result = await reconcile_lca_status_history_baseline()
        if result.state is not LcaStatusHistoryBaselineState.LOCKED:
            return result
        if asyncio.get_running_loop().time() >= deadline:
            return result
        await asyncio.sleep(2)


async def run(args: argparse.Namespace) -> BaselineReport:
    report = BaselineReport(dry_run=bool(args.dry_run))
    if report.dry_run:
        await _create_postgres_baselines(report)
        return report

    result = await _reconcile_until_unlocked(args.wait_timeout)
    _apply_reconciliation_result(report, result)
    if result.state in {
        LcaStatusHistoryBaselineState.LOCKED,
        LcaStatusHistoryBaselineState.DATA_ERROR,
        LcaStatusHistoryBaselineState.ALREADY_READY,
        LcaStatusHistoryBaselineState.READY,
    }:
        if result.state is LcaStatusHistoryBaselineState.LOCKED:
            report.errors.append("Baseline уже подготавливается другим процессом")
        elif result.state is LcaStatusHistoryBaselineState.ALREADY_READY:
            report.watermark_preexisting = True
        return report

    await _drain_outbox(report)
    if report.errors:
        return report

    report.clickhouse_baselines = await _wait_for_clickhouse(
        report.postgres_baselines,
        args.wait_timeout,
    )
    if report.clickhouse_baselines != report.postgres_baselines:
        report.errors.append(
            "Количество baseline в ClickHouse не совпало с PostgreSQL: "
            f"{report.clickhouse_baselines} != {report.postgres_baselines}"
        )
        return report

    result = await _reconcile_until_unlocked(args.wait_timeout)
    _apply_reconciliation_result(report, result)
    if result.state is LcaStatusHistoryBaselineState.ALREADY_READY:
        report.watermark_preexisting = True
    elif result.state is LcaStatusHistoryBaselineState.LOCKED:
        report.errors.append("Не удалось получить блокировку для записи watermark")
    elif result.state is LcaStatusHistoryBaselineState.WAITING_FOR_DELIVERY:
        report.errors.append(
            "Состав baseline изменился во время ожидания доставки; повторите запуск"
        )
    return report


def _write_report(report: BaselineReport, path: Path | None) -> None:
    payload: dict[str, Any] = asdict(report)
    payload["history_available_from"] = (
        report.history_available_from.isoformat()
        if report.history_available_from
        else None
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)  # noqa: T201
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    report = asyncio.run(run(args))
    _write_report(report, args.report)
    if report.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
