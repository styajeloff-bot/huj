"""Frozen revision-110 PostgreSQL fixtures, isolated from the shared test DB."""
from __future__ import annotations

import importlib.util
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

_MIGRATION = Path(__file__).resolve().parents[2] / "alembic/versions/111_notification_delivery.py"
_DATABASE = "carcraft_test_migration35"
_OLD_TYPES = (
    "application_status", "document_request", "approval", "general",
    "document_status", "leasing_approval", "system", "exchange_new_request",
    "exchange_new_bid", "exchange_bid_updated", "exchange_bid_accepted",
)


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("notification_migration_111_under_test", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def migration_engine() -> AsyncIterator[AsyncEngine]:
    # Never use db_session/_engine: those fixtures rebuild the shared database.
    url = make_url(os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5433/carcraft_test"
    )).set(database=_DATABASE)
    assert url.database == _DATABASE
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as connection:
        if not await connection.scalar(sa.text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": _DATABASE}):
            await connection.exec_driver_sql('CREATE DATABASE "carcraft_test_migration35"')
    await admin.dispose()

    schema = f"notification_111_{uuid4().hex}"
    owner = create_async_engine(url, poolclass=NullPool)
    async with owner.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            values = ", ".join(f"'{value}'" for value in _OLD_TYPES)
            await connection.exec_driver_sql(f"CREATE TYPE notification_type AS ENUM ({values})")
            for statement in (
                "CREATE TABLE companies (id uuid PRIMARY KEY, company_type text NOT NULL, is_active boolean DEFAULT true)",
                "CREATE TABLE users (id uuid PRIMARY KEY, company_id uuid REFERENCES companies(id))",
                "CREATE TABLE user_companies (user_id uuid, company_id uuid)",
                "CREATE TABLE leasing_companies (id uuid PRIMARY KEY, company_id uuid)",
                "CREATE TABLE leasing_company_users (user_id uuid, leasing_company_id uuid)",
                "CREATE TABLE notifications (id uuid PRIMARY KEY, user_id uuid REFERENCES users(id), type notification_type NOT NULL, title text NOT NULL, message text NOT NULL, data jsonb)",
                "CREATE TABLE email_preferences (user_id uuid PRIMARY KEY)",
                "CREATE TABLE exchange_requests (id uuid PRIMARY KEY, lc_user_id uuid NOT NULL, expiration_date date)",
                "CREATE TABLE exchange_cart_items (id uuid PRIMARY KEY, expiration_date date)",
                "CREATE TABLE exchange_bids (id uuid PRIMARY KEY, dealer_id uuid NOT NULL, request_id uuid NOT NULL)",
                "CREATE TABLE application_vehicles (id uuid PRIMARY KEY, car_status text, reserve_expires_at date)",
            ):
                await connection.exec_driver_sql(statement)
        yield engine
    finally:
        await engine.dispose()
        # This is the exact random schema created above, inside the dedicated DB.
        async with owner.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await owner.dispose()


async def _run(engine: AsyncEngine, direction: str) -> None:
    migration = _migration()

    def run(connection: Connection) -> None:
        migration.op = Operations(MigrationContext.configure(connection))
        getattr(migration, direction)()

    async with engine.begin() as connection:
        await connection.run_sync(run)


@pytest.mark.asyncio
async def test_upgrade_backfills_only_proven_owners_and_converts_business_day(
    migration_engine: AsyncEngine, caplog: pytest.LogCaptureFixture,
) -> None:
    companies = {name: uuid4() for name in ("lc1", "lc2", "dealer1", "dealer2", "inactive_lc")}
    users = {name: uuid4() for name in ("primary", "member", "explicit", "ambiguous", "missing", "inactive", "dealer", "dealer_ambiguous")}
    request_ids = {name: uuid4() for name in ("primary", "member", "explicit", "ambiguous", "missing", "inactive")}
    bid_ids = {name: uuid4() for name in ("dealer", "dealer_ambiguous")}
    cart_id, empty_cart_id, explicit_lc_id = uuid4(), uuid4(), uuid4()
    async with migration_engine.begin() as connection:
        for name, company_id in companies.items():
            await connection.execute(sa.text("INSERT INTO companies VALUES (:id, :kind, :active)"), {
                "id": company_id, "kind": "dealer" if name.startswith("dealer") else "leasing_company", "active": name != "inactive_lc",
            })
        primary = {"primary": "lc1", "ambiguous": "lc1", "explicit": "dealer1", "inactive": "inactive_lc", "dealer": "dealer1", "dealer_ambiguous": "dealer1"}
        for name, user_id in users.items():
            await connection.execute(sa.text("INSERT INTO users VALUES (:id, :company)"), {"id": user_id, "company": companies[primary[name]] if name in primary else None})
        for user, company in (("primary", "lc1"), ("member", "lc1"), ("ambiguous", "lc2"), ("dealer", "dealer1"), ("dealer_ambiguous", "dealer2")):
            await connection.execute(sa.text("INSERT INTO user_companies VALUES (:user, :company)"), {"user": users[user], "company": companies[company]})
        await connection.execute(sa.text("INSERT INTO leasing_companies VALUES (:id, :company)"), {"id": explicit_lc_id, "company": companies["lc1"]})
        for user in ("explicit", "primary"):
            await connection.execute(sa.text("INSERT INTO leasing_company_users VALUES (:user, :lc)"), {"user": users[user], "lc": explicit_lc_id})
        for name, request_id in request_ids.items():
            await connection.execute(sa.text("INSERT INTO exchange_requests VALUES (:id, :user, :deadline)"), {"id": request_id, "user": users[name], "deadline": date(2026, 9, 7) if name != "missing" else None})
        for name, bid_id in bid_ids.items():
            await connection.execute(sa.text("INSERT INTO exchange_bids VALUES (:id, :user, :request)"), {"id": bid_id, "user": users[name], "request": request_ids["primary"]})
        await connection.execute(sa.text("INSERT INTO exchange_cart_items VALUES (:id, DATE '2026-09-07'), (:empty, NULL)"), {"id": cart_id, "empty": empty_cart_id})
        await connection.execute(sa.text("INSERT INTO email_preferences VALUES (:id)"), {"id": users["primary"]})

    await _run(migration_engine, "upgrade")
    async with migration_engine.connect() as connection:
        requests = {row.id: row for row in (await connection.execute(sa.text("SELECT * FROM exchange_requests"))).all()}
        for name in ("primary", "member", "explicit"):
            assert requests[request_ids[name]].lc_company_id == companies["lc1"]
        assert requests[request_ids["inactive"]].lc_company_id == companies["inactive_lc"]
        assert requests[request_ids["ambiguous"]].lc_company_id is None
        assert requests[request_ids["missing"]].lc_company_id is None
        assert requests[request_ids["primary"]].expiration_at == datetime(2026, 9, 7, 20, 59, 59, tzinfo=UTC)
        assert requests[request_ids["missing"]].expiration_at is None
        assert await connection.scalar(sa.text("SELECT expiration_at FROM exchange_cart_items WHERE id = :id"), {"id": cart_id}) == datetime(2026, 9, 7, 20, 59, 59, tzinfo=UTC)
        assert await connection.scalar(sa.text("SELECT expiration_at FROM exchange_cart_items WHERE id = :id"), {"id": empty_cart_id}) is None
        assert await connection.scalar(sa.text("SELECT dealer_company_id FROM exchange_bids WHERE id = :id"), {"id": bid_ids["dealer"]}) == companies["dealer1"]
        assert await connection.scalar(sa.text("SELECT dealer_company_id FROM exchange_bids WHERE id = :id"), {"id": bid_ids["dealer_ambiguous"]}) is None
        assert await connection.scalar(sa.text("SELECT exchange_emails FROM email_preferences")) is True
    unresolved = [record for record in caplog.records if record.message == "notification_owner_backfill_unresolved_records"]
    assert {str(request_ids["ambiguous"]), str(request_ids["missing"])}.issubset({identifier for record in unresolved for identifier in record.__dict__["record_ids"]})

    await _run(migration_engine, "downgrade")
    async with migration_engine.connect() as connection:
        assert await connection.scalar(sa.text("SELECT expiration_date FROM exchange_requests WHERE id = :id"), {"id": request_ids["primary"]}) == date(2026, 9, 7)
        assert await connection.scalar(sa.text("SELECT expiration_date FROM exchange_cart_items WHERE id = :id"), {"id": empty_cart_id}) is None
        assert await connection.scalar(sa.text("SELECT to_regclass('notification_event_outbox')")) is None


@pytest.mark.asyncio
async def test_upgrade_enforces_durable_dedup_and_preserves_inbox_on_downgrade(migration_engine: AsyncEngine) -> None:
    user_id, event_id, notification_id, batch_id, delivery_id = (uuid4() for _ in range(5))
    async with migration_engine.begin() as connection:
        await connection.execute(sa.text("INSERT INTO users VALUES (:id, NULL)"), {"id": user_id})
    await _run(migration_engine, "upgrade")
    async with migration_engine.begin() as connection:
        for _ in range(2):
            await connection.execute(sa.text("INSERT INTO notifications (id,user_id,type,title,message) VALUES (:id,:user,'system','legacy','retained')"), {"id": uuid4(), "user": user_id})
        await connection.execute(sa.text("INSERT INTO notifications (id,user_id,event_id,type,title,message,data,deleted_at) VALUES (:id,:user,:event,'exchange_deadline','deadline','retained','{}',now())"), {"id": notification_id, "user": user_id, "event": event_id})
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(sa.text("INSERT INTO notifications (id,user_id,event_id,type,title,message) VALUES (:id,:user,:event,'system','duplicate','must fail')"), {"id": uuid4(), "user": user_id, "event": event_id})
        await connection.execute(sa.text("INSERT INTO notification_event_receipts(event_id,payload) VALUES (:event,'{}')"), {"event": event_id})
        await connection.execute(sa.text("INSERT INTO notification_email_batches(id,user_id,delivery_mode,message_id) VALUES (:id,:user,'immediate','<stable@example.test>')"), {"id": batch_id, "user": user_id})
        await connection.execute(sa.text("INSERT INTO notification_email_deliveries(id,notification_id,event_id,user_id,recipient_role,batch_id,delivery_mode,next_attempt_at) VALUES (:id,:notification,:event,:user,'dealer',:batch,'immediate',now())"), {"id": delivery_id, "notification": notification_id, "event": event_id, "user": user_id, "batch": batch_id})
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(sa.text("INSERT INTO notification_email_deliveries SELECT :new_id, notification_id,event_id,user_id,recipient_role,recipient_company_id,batch_id,status,delivery_mode,attempt_count,next_attempt_at,processing_started_at,sent_at,failed_at,last_error,message_id,created_at,updated_at FROM notification_email_deliveries WHERE id=:id"), {"new_id": uuid4(), "id": delivery_id})
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(sa.text("DELETE FROM notifications WHERE id = :id"), {"id": notification_id})
        outbox = sa.text("INSERT INTO notification_event_outbox(event_id,event_type,entity_type,entity_id,aggregate_id,occurrence_key,payload,occurred_at) VALUES (:event,'exchange.deadline_1h','exchange_request',:entity,:entity,:key,'{}',now()) RETURNING sequence")
        first_sequence = await connection.scalar(outbox, {"event": uuid4(), "entity": uuid4(), "key": "deadline:one"})
        second_sequence = await connection.scalar(outbox, {"event": uuid4(), "entity": uuid4(), "key": "deadline:two"})
        assert second_sequence > first_sequence
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(outbox, {"event": uuid4(), "entity": uuid4(), "key": "deadline:one"})
        indexes = {row.indexname: row.indexdef for row in (await connection.execute(sa.text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname = current_schema()"))).all()}
        assert "WHERE (event_id IS NOT NULL)" in indexes["uq_notifications_event_user"]
        assert "confirmed" in indexes["idx_application_vehicles_reservation_due"]
        assert "reserve_expires_at IS NOT NULL" in indexes["idx_application_vehicles_reservation_due"]

    await _run(migration_engine, "downgrade")
    async with migration_engine.connect() as connection:
        assert await connection.scalar(sa.text("SELECT count(*) FROM notifications")) == 3
        assert await connection.scalar(sa.text("SELECT type::text FROM notifications WHERE id=:id"), {"id": notification_id}) == "system"
        assert tuple((await connection.execute(sa.text("SELECT unnest(enum_range(NULL::notification_type))::text"))).scalars()) == _OLD_TYPES
        assert await connection.scalar(sa.text("SELECT to_regclass('notification_email_deliveries')")) is None
