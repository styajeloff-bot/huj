"""Real-storage integration checks for the LCA status-history pipeline."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import clickhouse_connect
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure import clickhouse_readonly
from infrastructure.clickhouse_dwh import _DWH_TABLES
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.lca_status_history import (
    LeasingCompanyApplicationStatusHistory,
)
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import status_history_repository as history_repo


def _clickhouse_test_client() -> clickhouse_connect.driver.Client:
    if os.getenv("RUN_CLICKHOUSE_INTEGRATION") != "1":
        pytest.skip("isolated ClickHouse integration instance is not enabled")
    return clickhouse_connect.get_client(
        host=os.getenv("TEST_CLICKHOUSE_HOST", "127.0.0.1"),
        port=int(os.getenv("TEST_CLICKHOUSE_PORT", "8123")),
        username=os.getenv("TEST_CLICKHOUSE_USER", "default"),
        password=os.getenv("TEST_CLICKHOUSE_PASSWORD", ""),
        database=os.getenv("TEST_CLICKHOUSE_DATABASE", "default"),
    )


def _create_lca_history_test_table(
    client: clickhouse_connect.driver.Client,
) -> str:
    table_name = f"test_lca_status_history_{uuid4().hex}"
    ddl = _DWH_TABLES["dwh_lca_status_history"].replace(
        "dwh_lca_status_history",
        table_name,
        1,
    )
    client.command(ddl)
    return table_name


@pytest.mark.asyncio
async def test_lca_status_and_history_roll_back_atomically(
    db_session: AsyncSession,
) -> None:
    """A real PostgreSQL savepoint must undo both business and outbox rows."""
    company = Company(
        name="LCA history atomicity test",
        company_type="other",
    )
    db_session.add(company)
    await db_session.flush()

    application = LeasingApplication(
        company_id=company.id,
        status="active",
    )
    db_session.add(application)
    await db_session.flush()

    lca = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=None,
        status="submitted",
    )
    db_session.add(lca)
    await db_session.flush()
    lca_id = lca.id

    savepoint = await db_session.begin_nested()
    await lca_repo.update_link_status(
        db_session,
        link_id=lca_id,
        new_status="under_review",
    )
    await history_repo.append_lca_status_history(
        db_session,
        lca_id=lca_id,
        application_id=application.id,
        old_status="submitted",
        new_status="under_review",
    )

    history_during_transaction = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(LeasingCompanyApplicationStatusHistory)
        .where(LeasingCompanyApplicationStatusHistory.lca_id == lca_id)
    )
    assert history_during_transaction == 1

    await savepoint.rollback()
    db_session.expire_all()

    persisted_lca = await db_session.get(LeasingCompanyApplication, lca_id)
    assert persisted_lca is not None
    assert persisted_lca.status == "submitted"
    history_after_rollback = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(LeasingCompanyApplicationStatusHistory)
        .where(LeasingCompanyApplicationStatusHistory.lca_id == lca_id)
    )
    assert history_after_rollback == 0


def test_clickhouse_duplicate_delivery_collapses_by_event_id() -> None:
    """Exercise the production ReplacingMergeTree DDL against real ClickHouse.

    This check is opt-in so it cannot accidentally create a table in a shared
    or production ClickHouse. Point it only at an isolated test instance:
    ``RUN_CLICKHOUSE_INTEGRATION=1 TEST_CLICKHOUSE_HOST=127.0.0.1 ...``.
    """
    client = _clickhouse_test_client()
    table_name = _create_lca_history_test_table(client)
    columns = [
        "event_id",
        "lca_id",
        "application_id",
        "old_status",
        "new_status",
        "changed_at",
        "changed_by",
        "reason",
        "application_created_at",
        "lca_created_at",
        "dealer_company_id",
        "distributor_id",
        "leasing_company_id",
        "is_baseline",
        "ingested_at",
    ]
    event_id = uuid4()
    lca_id = uuid4()
    changed_at = datetime.now(UTC)
    first_ingestion = changed_at + timedelta(seconds=1)
    row = [
        event_id,
        lca_id,
        None,
        "submitted",
        "under_review",
        changed_at,
        None,
        None,
        None,
        changed_at,
        None,
        None,
        None,
        0,
        first_ingestion,
    ]

    try:
        client.insert(table_name, [row], column_names=columns)
        duplicate = [*row]
        duplicate[-1] = first_ingestion + timedelta(seconds=1)
        client.insert(table_name, [duplicate], column_names=columns)

        result = client.query(
            f"SELECT count(), uniqExact(event_id) FROM {table_name} FINAL"  # noqa: S608
        )
        assert result.result_rows == [(1, 1)]
    finally:
        client.command(f"DROP TABLE IF EXISTS {table_name}")
        client.close()


@pytest.mark.asyncio
async def test_clickhouse_executes_production_funnel_cte_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execute the production CTE against isolated deterministic rows."""
    client = _clickhouse_test_client()
    table_name = _create_lca_history_test_table(client)
    columns = [
        "event_id",
        "lca_id",
        "application_id",
        "old_status",
        "new_status",
        "changed_at",
        "changed_by",
        "reason",
        "application_created_at",
        "lca_created_at",
        "dealer_company_id",
        "distributor_id",
        "leasing_company_id",
        "is_baseline",
        "ingested_at",
    ]
    start_utc = datetime(2026, 7, 9, 21, tzinfo=UTC)
    end_utc = datetime(2026, 7, 10, 21, tzinfo=UTC)
    old_created_at = start_utc - timedelta(days=30)
    repeated_lca = uuid4()
    baseline_lca = uuid4()
    terminal_lca = uuid4()
    reopened_lca = uuid4()
    boundary_lca = uuid4()

    def _row(
        lca_id: object,
        status: str,
        changed_at: datetime,
        *,
        lca_created_at: datetime,
        baseline: bool = False,
    ) -> list[object]:
        return [
            uuid4(),
            lca_id,
            None,
            None,
            status,
            changed_at,
            None,
            None,
            None,
            lca_created_at,
            None,
            None,
            None,
            1 if baseline else 0,
            changed_at + timedelta(seconds=1),
        ]

    rows = [
        _row(
            repeated_lca,
            "submitted",
            start_utc + timedelta(minutes=5),
            lca_created_at=start_utc + timedelta(minutes=5),
        ),
        _row(
            repeated_lca,
            "under_review",
            start_utc + timedelta(hours=1),
            lca_created_at=start_utc + timedelta(minutes=5),
        ),
        _row(
            repeated_lca,
            "submitted",
            start_utc + timedelta(hours=2),
            lca_created_at=start_utc + timedelta(minutes=5),
        ),
        _row(
            baseline_lca,
            "under_review",
            start_utc - timedelta(minutes=1),
            lca_created_at=old_created_at,
            baseline=True,
        ),
        _row(
            terminal_lca,
            "deal",
            start_utc - timedelta(minutes=1),
            lca_created_at=old_created_at,
        ),
        _row(
            reopened_lca,
            "closed",
            start_utc - timedelta(minutes=1),
            lca_created_at=old_created_at,
        ),
        _row(
            reopened_lca,
            "under_review",
            start_utc + timedelta(hours=1),
            lca_created_at=old_created_at,
        ),
        _row(
            boundary_lca,
            "submitted",
            start_utc,
            lca_created_at=start_utc,
        ),
        _row(
            boundary_lca,
            "deal",
            end_utc,
            lca_created_at=start_utc,
        ),
    ]

    async def _execute(
        query: str,
        params: dict[str, object],
    ) -> list[dict[str, object]]:
        isolated_query = query.replace("dwh_lca_status_history", table_name)
        result = client.query(isolated_query, parameters=params)
        return [dict(zip(result.column_names, row, strict=True)) for row in result.result_rows]

    try:
        client.insert(table_name, rows, column_names=columns)
        monkeypatch.setattr(clickhouse_readonly, "query_clickhouse", _execute)
        statuses = ("submitted", "under_review", "deal", "closed")
        terminals = frozenset({"deal", "closed"})

        created = await clickhouse_readonly.get_application_status_funnel(
            start_utc=start_utc,
            end_utc=end_utc,
            selection_mode="created_in_period",
            status_codes=statuses,
            terminal_statuses=terminals,
            scope_dealer_ids=None,
        )
        created_by_status = {row["status"]: row for row in created}
        assert created_by_status["submitted"] == {
            "status": "submitted",
            "events_count": 2,
            "end_state_count": 2,
            "selected_count": 2,
        }
        assert created_by_status["under_review"]["events_count"] == 1
        assert created_by_status["deal"]["events_count"] == 0
        assert created_by_status["deal"]["end_state_count"] == 0

        active = await clickhouse_readonly.get_application_status_funnel(
            start_utc=start_utc,
            end_utc=end_utc,
            selection_mode="active_during_period",
            status_codes=statuses,
            terminal_statuses=terminals,
            scope_dealer_ids=None,
        )
        active_by_status = {row["status"]: row for row in active}
        assert active_by_status["submitted"]["events_count"] == 2
        assert active_by_status["submitted"]["end_state_count"] == 2
        assert active_by_status["under_review"]["events_count"] == 2
        assert active_by_status["under_review"]["end_state_count"] == 2
        assert active_by_status["deal"]["end_state_count"] == 0
        assert {row["selected_count"] for row in active} == {4}
    finally:
        client.command(f"DROP TABLE IF EXISTS {table_name}")
        client.close()
