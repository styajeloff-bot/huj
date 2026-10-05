
"""PostgreSQL persistence invariants of the independent monetization module."""
import asyncio
import os
import re
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from domain.monetization.errors import MonetizationConflict
from infrastructure.models import Base
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import monetization_repository as repo
from tests.legacy_compat import Mark, Vehicle

Record = dict[str, Any]
_OWNED_DATABASE = re.compile(r"carcraft_monetization_sql_[0-9a-f]{32}\Z")


@pytest_asyncio.fixture(scope="module")
async def monetization_engine() -> AsyncIterator[AsyncEngine]:
    """Own a separate database because concurrency tests must really commit.

    Never request conftest's shared engine: later tests rely on its pristine
    seed data. UUID name, owner and OID checks also constrain final cleanup.
    """
    configured_url = make_url(
        os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://postgres:password@localhost:5433/carcraft_test",
        )
    )
    database_name = f"carcraft_monetization_sql_{uuid4().hex}"
    assert _OWNED_DATABASE.fullmatch(database_name)
    url = configured_url.set(drivername="postgresql+asyncpg", database=database_name)
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    engine = create_async_engine(url, poolclass=NullPool)
    ownership: tuple[int, int] | None = None
    try:
        async with admin.connect() as connection:
            assert not await connection.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            )
            await connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            row = (
                await connection.execute(
                    sa.text(
                        "SELECT oid, datdba FROM pg_database WHERE datname = :name "
                        "AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
                    ),
                    {"name": database_name},
                )
            ).one()
            ownership = (row.oid, row.datdba)
        async with engine.begin() as connection:
            await connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog_storefronts "
                    "(id, slug, is_default, is_active, version, contact_email, contact_phone) VALUES "
                    "('00000000-0000-0000-0000-000000000001', NULL, TRUE, TRUE, 1, "
                    "'monetization@example.test', '+70000000000')"
                )
            )
        yield engine
    finally:
        await engine.dispose()
        if ownership is not None:
            async with admin.connect() as connection:
                row = (
                    await connection.execute(
                        sa.text(
                            "SELECT oid, datdba FROM pg_database WHERE datname = :name "
                            "AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
                        ),
                        {"name": database_name},
                    )
                ).one()
                assert (row.oid, row.datdba) == ownership
                assert _OWNED_DATABASE.fullmatch(database_name)
                await connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
        await admin.dispose()


@pytest_asyncio.fixture
async def monetization_session(
    monetization_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(monetization_engine, expire_on_commit=False) as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.mark.asyncio
async def test_program_retains_repeated_participants_and_same_block_references(
    monetization_session: AsyncSession,
) -> None:
    from infrastructure.models.companies import Company, LeasingCompany

    company_id, leasing_id, actor_id = uuid4(), uuid4(), uuid4()
    monetization_session.add(
        Company(id=company_id, name="Test LC", company_type="leasing_company")
    )
    await monetization_session.flush()
    monetization_session.add(LeasingCompany(id=leasing_id, company_id=company_id))
    await monetization_session.flush()
    row = {
        "participant_type": "leasing",
        "base_type": "property_value",
        "calc_type": "percent",
        "value": Decimal("2.5"),
        "vat_excluded": False,
    }
    program = await repo.create_program(
        monetization_session,
        {
            "name": "Independent expenses",
            "leasing_company_id": str(leasing_id),
            "period_start": date(2026, 1, 1),
            "period_end": None,
            "sources": [
                {
                    "source_type": "platform",
                    "expenses": [dict(row, local_id="e1"), dict(row, local_id="e2")],
                    "incomes": [],
                }
            ],
        },
        actor_id,
    )
    loaded = await repo.get_program(monetization_session, program["id"])
    assert loaded is not None
    assert [item["local_id"] for item in loaded["sources"][0]["expenses"]] == [
        "e1",
        "e2",
    ]
    assert loaded["sources"][0]["expenses"][0]["value"] == Decimal("2.5")
    assert loaded["sources"][0]["incomes"] == []


@pytest_asyncio.fixture
async def monetization_seed(monetization_engine: AsyncEngine) -> dict[str, str]:
    leasing_id, lc_company_id, dealer_id = uuid4(), uuid4(), uuid4()
    async with (
        AsyncSession(monetization_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        session.add_all(
            [
                Company(
                    id=lc_company_id, name="Snapshot LC", company_type="leasing_company"
                ),
                Company(id=dealer_id, name="Snapshot dealer", company_type="dealer"),
            ]
        )
        await session.flush()
        session.add(LeasingCompany(id=leasing_id, company_id=lc_company_id))
    return {
        "leasing_company_id": str(leasing_id),
        "lc_company_id": str(lc_company_id),
        "dealer_company_id": str(dealer_id),
        "actor_id": str(uuid4()),
    }


def _program_payload(seed: dict[str, str], **overrides: Any) -> Record:
    return {
        "name": "Internal conditions",
        "leasing_company_id": seed["leasing_company_id"],
        "period_start": date(2026, 1, 1),
        "period_end": None,
        "sources": [
            {
                "source_type": "exchange",
                "expenses": [
                    {
                        "local_id": "expense-1",
                        "participant_type": "leasing",
                        "base_type": "none",
                        "calc_type": "amount",
                        "value": Decimal("100"),
                        "vat_excluded": False,
                    }
                ],
                "incomes": [
                    {
                        "local_id": "income-1",
                        "participant_type": "dealer",
                        "base_type": "expense_amount",
                        "calc_type": "percent",
                        "value": Decimal("50"),
                        "expense_ref": "expense-1",
                        "vat_excluded": False,
                    }
                ],
            }
        ],
        **overrides,
    }


def _deal_context(seed: dict[str, str], **overrides: Any) -> Record:
    return {
        "exchange_request_id": str(uuid4()),
        "source_type": "exchange",
        "leasing_company_id": seed["leasing_company_id"],
        "dealer_company_id": seed["dealer_company_id"],
        "base_amount": Decimal("1500000.50"),
        "application_number": "EX-123",
        "vehicles": [{"brand": "Sollers", "vin": "MONETIZATION000001"}],
        **overrides,
    }


def _deal_amounts(program: Record) -> list[Record]:
    source = program["sources"][0]
    expense_id = str(uuid4())
    return [
        {
            "id": expense_id,
            "program_source_id": source["id"],
            "source_participant_id": source["expenses"][0]["id"],
            "side": "expense",
            "participant_type": "leasing",
            "raw_amount": Decimal("100"),
            "amount": Decimal("100"),
            "clip": "none",
            "vat_excluded": False,
        },
        {
            "id": str(uuid4()),
            "program_source_id": source["id"],
            "source_participant_id": source["incomes"][0]["id"],
            "side": "income",
            "participant_type": "dealer",
            "raw_amount": Decimal("50"),
            "amount": Decimal("50"),
            "expense_ref_amount_id": expense_id,
            "clip": "none",
            "vat_excluded": False,
        },
    ]


async def _save_program(
    engine: AsyncEngine, seed: dict[str, str], **overrides: Any
) -> Record:
    async with AsyncSession(engine) as session, session.begin():
        return await repo.create_program(
            session, _program_payload(seed, **overrides), seed["actor_id"]
        )


async def _save_deal(
    engine: AsyncEngine, seed: dict[str, str], program: Record, **overrides: Any
) -> Record:
    async with AsyncSession(engine) as session, session.begin():
        return await repo.insert_deal(
            session, _deal_context(seed, **overrides), program, _deal_amounts(program)
        )


@pytest.mark.asyncio
async def test_concurrent_overlapping_active_programs_have_one_winner(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    gate = asyncio.Event()

    async def create() -> Record:
        async with AsyncSession(monetization_engine) as session, session.begin():
            await gate.wait()
            return await repo.create_program(
                session,
                _program_payload(monetization_seed),
                monetization_seed["actor_id"],
            )

    tasks = [asyncio.create_task(create()) for _ in range(2)]
    gate.set()
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True), timeout=10
    )
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, MonetizationConflict) for item in results) == 1


@pytest.mark.asyncio
async def test_inactive_duplicate_cannot_be_activated_while_period_overlaps(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    await _save_program(
        monetization_engine, monetization_seed, period_end=date(2026, 6, 30)
    )
    duplicate = await _save_program(
        monetization_engine,
        monetization_seed,
        status="inactive",
        period_start=date(2026, 6, 30),
    )
    async with AsyncSession(monetization_engine) as session, session.begin():
        with pytest.raises(MonetizationConflict, match="пересекаются"):
            await repo.set_program_status(session, duplicate["id"], "active")
    async with AsyncSession(monetization_engine) as session:
        loaded = await repo.get_program(session, duplicate["id"])
        assert loaded is not None
        assert loaded["status"] == "inactive"


@pytest.mark.asyncio
async def test_concurrent_source_capture_returns_same_financial_snapshot(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    program = await _save_program(monetization_engine, monetization_seed)
    context = _deal_context(monetization_seed)
    gate = asyncio.Event()

    async def capture() -> Record:
        async with AsyncSession(monetization_engine) as session, session.begin():
            await gate.wait()
            return await repo.insert_deal(
                session, context, program, _deal_amounts(program)
            )

    tasks = [asyncio.create_task(capture()) for _ in range(2)]
    gate.set()
    first, second = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert first["id"] == second["id"]
    assert first["amounts"] == second["amounts"]
    async with AsyncSession(monetization_engine) as session, session.begin():
        await repo.set_program_status(session, program["id"], "inactive")
        saved = await repo.find_source_deal(session, context)
        assert saved is not None
        assert saved["id"] == first["id"]


@pytest.mark.asyncio
async def test_concurrent_vin_capture_cannot_consume_same_vin_twice(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    program = await _save_program(
        monetization_engine, monetization_seed, vin="MONETIZATION000001"
    )
    gate = asyncio.Event()

    async def capture() -> Record:
        async with AsyncSession(monetization_engine) as session, session.begin():
            await gate.wait()
            return await repo.insert_deal(
                session,
                _deal_context(monetization_seed),
                program,
                _deal_amounts(program),
            )

    tasks = [asyncio.create_task(capture()) for _ in range(2)]
    gate.set()
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True), timeout=10
    )
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, MonetizationConflict) for item in results) == 1


@pytest.mark.asyncio
async def test_failed_capture_rolls_back_deal_and_every_amount(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    program = await _save_program(monetization_engine, monetization_seed)
    context = _deal_context(monetization_seed)
    amounts = _deal_amounts(program)
    amounts[1]["amount"] = Decimal("-1")
    with pytest.raises(sa.exc.IntegrityError):
        async with AsyncSession(monetization_engine) as session, session.begin():
            await repo.insert_deal(session, context, program, amounts)
    async with AsyncSession(monetization_engine) as session:
        assert await repo.find_source_deal(session, context) is None
        valid = await repo.insert_deal(
            session, context, program, _deal_amounts(program)
        )
        assert len(valid["amounts"]) == 2


@pytest.mark.asyncio
async def test_adjustment_serializes_confirmation_and_preserves_previous_documents(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    program = await _save_program(monetization_engine, monetization_seed)
    deal = await _save_deal(monetization_engine, monetization_seed, program)
    actor_id = monetization_seed["actor_id"]
    async with AsyncSession(monetization_engine) as session, session.begin():
        await repo.add_document(
            session,
            deal["id"],
            {
                "participant_type": "dealer",
                "revision": 1,
                "filename": "before.pdf",
                "object_key": "monetization/test/before.pdf",
                "content_type": "application/pdf",
                "size_bytes": 123,
            },
            actor_id,
        )
        await repo.update_deal(
            session,
            deal["id"],
            {"confirmations": {"dealer": {"user_id": actor_id, "revision": 1}}},
        )
    locked, release = asyncio.Event(), asyncio.Event()

    async def adjust() -> None:
        async with AsyncSession(monetization_engine) as session, session.begin():
            current = await repo.lock_deal(session, deal["id"])
            assert current is not None
            locked.set()
            await release.wait()
            changed = [dict(item) for item in current["amounts"]]
            changed[0]["amount"] = Decimal("110")
            await repo.replace_amounts(
                session, deal["id"], changed, actor_id, revision=2
            )
            await repo.update_deal(
                session, deal["id"], {"revision": 2, "confirmations": {}}
            )

    async def confirm_read() -> Record | None:
        await locked.wait()
        async with AsyncSession(monetization_engine) as session, session.begin():
            return await repo.lock_deal(session, deal["id"])

    adjustment = asyncio.create_task(adjust())
    confirmation = asyncio.create_task(confirm_read())
    try:
        await locked.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(confirmation), timeout=0.15)
    finally:
        release.set()
    await asyncio.wait_for(adjustment, timeout=10)
    current = await asyncio.wait_for(confirmation, timeout=10)
    assert current is not None
    assert current["revision"] == 2
    assert current["confirmations"] == {}
    assert current["amounts"][0]["amount"] == Decimal("110")
    assert current["documents"][0]["stale"] is True
    assert current["adjustments"][0]["old_value"] == Decimal("100")
    assert current["adjustments"][0]["new_value"] == Decimal("110")


@pytest.mark.asyncio
async def test_company_membership_revocation_and_file_scope_are_current(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    seed = monetization_seed
    user_id, outsider_id, outsider_company_id = uuid4(), uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(
            Company(id=outsider_company_id, name="Other dealer", company_type="dealer")
        )
        await session.flush()
        session.add_all(
            [
                User(
                    id=user_id,
                    phone=str(uuid4())[:20],
                    role="dealer",
                    company_id=UUID(seed["dealer_company_id"]),
                ),
                User(
                    id=outsider_id,
                    phone=str(uuid4())[:20],
                    role="dealer",
                    company_id=outsider_company_id,
                ),
            ]
        )
    program = await _save_program(monetization_engine, seed)
    deal = await _save_deal(monetization_engine, seed, program)
    async with AsyncSession(monetization_engine) as session, session.begin():
        document = await repo.add_document(
            session,
            deal["id"],
            {
                "participant_type": "dealer",
                "revision": 1,
                "filename": "deal.pdf",
                "object_key": "monetization/test/deal.pdf",
                "content_type": "application/pdf",
                "size_bytes": 123,
            },
            seed["actor_id"],
        )
        own = await repo.resolve_actor(
            session, user_id, "dealer", seed["dealer_company_id"]
        )
        assert own is not None
        outsider = await repo.resolve_actor(
            session, outsider_id, "dealer", outsider_company_id
        )
        assert outsider is not None
        assert own is not None and outsider is not None
        assert await repo.get_document(session, document["id"], own) is not None
        assert await repo.get_deal(session, deal["id"], outsider) is None
        assert await repo.get_document(session, document["id"], outsider) is None
        session.add(
            UserCompany(
                user_id=user_id,
                company_id=UUID(seed["dealer_company_id"]),
                can_view_applications=False,
            )
        )
        await session.flush()
        assert (
            await repo.resolve_actor(
                session, user_id, "dealer", seed["dealer_company_id"]
            )
            is None
        )
        assert (
            await repo.resolve_actor(
                session, user_id, "client", seed["dealer_company_id"]
            )
            is None
        )


@pytest.mark.asyncio
async def test_deal_company_labels_remain_snapshot_after_source_change(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    program = await _save_program(monetization_engine, monetization_seed)
    deal = await _save_deal(monetization_engine, monetization_seed, program)
    async with AsyncSession(monetization_engine) as session, session.begin():
        await session.execute(
            sa.update(Company)
            .where(Company.id == UUID(monetization_seed["dealer_company_id"]))
            .values(name="Renamed elsewhere")
        )
        saved = await repo.get_deal(session, deal["id"])
        assert saved is not None
        assert saved["dealer_company"]["name"] == "Snapshot dealer"
        assert saved["program_name"] == "Internal conditions"
        assert saved["base_amount"] == Decimal("1500000.50")


@pytest.mark.asyncio
async def test_condition_request_waits_for_concurrent_first_lca(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    from infrastructure.models.applications import (
        LeasingApplication,
        LeasingCompanyApplication,
    )

    seed = monetization_seed
    application_id, client_id = uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(Company(id=client_id, name="Request client", company_type="other"))
        await session.flush()
        session.add(
            LeasingApplication(
                id=application_id,
                company_id=client_id,
                dealer_company_id=UUID(seed["dealer_company_id"]),
            )
        )
    lca_written, release = asyncio.Event(), asyncio.Event()

    async def create_lca() -> None:
        async with AsyncSession(monetization_engine) as session, session.begin():
            session.add(
                LeasingCompanyApplication(
                    id=uuid4(),
                    application_id=application_id,
                    leasing_company_id=UUID(seed["leasing_company_id"]),
                )
            )
            await session.flush()
            lca_written.set()
            await release.wait()

    async def request_commission() -> Record:
        await lca_written.wait()
        async with AsyncSession(monetization_engine) as session, session.begin():
            return await repo.create_condition_request(
                session,
                {
                    "application_id": application_id,
                    "dealer_company_id": seed["dealer_company_id"],
                    "leasing_company_id": seed["leasing_company_id"],
                    "requested_calc_type": "percent",
                    "requested_value": Decimal("2"),
                },
                seed["actor_id"],
            )

    creation = asyncio.create_task(create_lca())
    request = asyncio.create_task(request_commission())
    try:
        await asyncio.wait_for(lca_written.wait(), timeout=5)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(request), timeout=0.15)
    finally:
        release.set()
    await asyncio.wait_for(creation, timeout=10)
    with pytest.raises(MonetizationConflict, match="до первой заявки в ЛК"):
        await asyncio.wait_for(request, timeout=10)
    async with AsyncSession(monetization_engine) as session:
        assert (
            await repo.list_condition_requests(
                session, application_id, {"role": "carcraft_employee"}
            )
            == []
        )


@pytest.mark.asyncio
async def test_migration_up_down_up_in_disposable_schema(
    monetization_engine: AsyncEngine,
) -> None:
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).parents[2] / "alembic" / "versions" / "120_monetization.py"
    spec = importlib.util.spec_from_file_location("monetization_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = "monetization_migration_" + uuid4().hex
    async with monetization_engine.begin() as connection:
        await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(
            sa.text(f'SET LOCAL search_path TO "{schema}", public')
        )
        await connection.execute(
            sa.text("CREATE TABLE leasing_companies (id uuid PRIMARY KEY)")
        )

        def migrate(sync_connection: Connection) -> None:
            with Operations.context(MigrationContext.configure(sync_connection)):
                module.upgrade()
                assert (
                    len(sa.inspect(sync_connection).get_table_names(schema=schema))
                    == 10
                )
                module.downgrade()
                assert sa.inspect(sync_connection).get_table_names(schema=schema) == [
                    "leasing_companies"
                ]
                module.upgrade()

        await connection.run_sync(migrate)
        await connection.execute(sa.text("SET LOCAL search_path TO public"))
        await connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.mark.asyncio
async def test_negotiation_values_are_informational_and_keep_application_amount(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    from infrastructure.models.applications import LeasingApplication

    seed = monetization_seed
    application_id, client_id = uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(
            Company(id=client_id, name="Unchanged client", company_type="other")
        )
        await session.flush()
        session.add(
            LeasingApplication(
                id=application_id,
                company_id=client_id,
                dealer_company_id=UUID(seed["dealer_company_id"]),
                total_amount=Decimal("1500000.50"),
            )
        )
    async with AsyncSession(monetization_engine) as session, session.begin():
        request = await repo.create_condition_request(
            session,
            {
                "application_id": application_id,
                "dealer_company_id": seed["dealer_company_id"],
                "leasing_company_id": seed["leasing_company_id"],
                "requested_calc_type": "percent",
                "requested_value": Decimal("2.5"),
            },
            seed["actor_id"],
        )
        assert request["requested_value"] == Decimal("2.5")
        assert request["leasing_company"]["name"] == "Snapshot LC"
        await repo.update_condition_request(
            session,
            request["id"],
            {
                "status": "countered",
                "counter_calc_type": "percent",
                "counter_value": Decimal("3"),
            },
        )
        accepted = await repo.update_condition_request(
            session, request["id"], {"status": "accepted"}
        )
        assert accepted["requested_value"] == Decimal("2.5")
        assert accepted["counter_value"] == Decimal("3")
        application = await repo.lock_application(
            session, application_id, {"role": "carcraft_employee"}
        )
        assert application is not None
        assert application["total_amount"] == Decimal("1500000.50")


@pytest.mark.asyncio
async def test_paid_deal_cannot_be_mutated_through_repository(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    program = await _save_program(monetization_engine, monetization_seed)
    deal = await _save_deal(monetization_engine, monetization_seed, program)
    async with AsyncSession(monetization_engine) as session, session.begin():
        await repo.update_deal(session, deal["id"], {"status": "paid"})
    async with AsyncSession(monetization_engine) as session, session.begin():
        with pytest.raises(MonetizationConflict):
            await repo.update_deal(session, deal["id"], {"status": "pending_approval"})
        with pytest.raises(MonetizationConflict):
            await repo.replace_amounts(
                session, deal["id"], deal["amounts"], monetization_seed["actor_id"], 2
            )


@pytest.mark.asyncio
async def test_leasing_company_link_is_a_current_canonical_membership(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    from infrastructure.models.companies import LeasingCompanyUser

    user_id = uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(User(id=user_id, phone=str(uuid4())[:20], role="leasing_company"))
        await session.flush()
        session.add(
            LeasingCompanyUser(
                user_id=user_id,
                leasing_company_id=UUID(monetization_seed["leasing_company_id"]),
            )
        )
    async with AsyncSession(monetization_engine) as session:
        actor = await repo.resolve_actor(
            session, user_id, "leasing_company", monetization_seed["lc_company_id"]
        )
        assert actor is not None
        assert actor["leasing_company_ids"] == [UUID(monetization_seed["leasing_company_id"])]
        assert actor["company_ids"] == [UUID(monetization_seed["lc_company_id"])]


@pytest.mark.asyncio
async def test_support_files_keep_existing_organization_restrictions(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    from infrastructure.models.support import SupportBillOfLading, SupportProgram

    support_id, document_id = uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(
            SupportProgram(
                id=support_id,
                name="Internal support files",
                support_type="down_payment_compensation",
                support_params={},
            )
        )
        await session.flush()
        session.add(
            SupportBillOfLading(
                id=document_id,
                support_program_id=support_id,
                file_name="restricted.pdf",
                file_path="supports/internal.pdf",
                file_size=100,
            )
        )
    actor = {
        "role": "leasing_company",
        "company_id": monetization_seed["lc_company_id"],
        "leasing_company_ids": [monetization_seed["leasing_company_id"]],
    }
    async with AsyncSession(monetization_engine) as session:
        visible = await repo.get_support(session, support_id, actor)
        assert visible is not None
        assert visible["name"] == "Internal support files"
        assert visible["documents"] == []
        assert visible["compatible_programs"] == []
        assert await repo.get_support_document(session, document_id, actor) is None
        admin = {"role": "carcraft_employee"}
        detail = await repo.get_support(session, support_id, admin)
        assert detail is not None
        assert detail["documents"][0]["filename"] == "restricted.pdf"
        document = await repo.get_support_document(session, document_id, admin)
        assert document is not None
        assert document["object_key"] == "supports/internal.pdf"


@pytest.mark.asyncio
async def test_raw_amount_retains_decimal_precision_and_complete_source_context(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str]
) -> None:
    from datetime import UTC, datetime

    from domain.monetization.programs import calculate_program

    seed = monetization_seed
    payload = _program_payload(seed)
    payload["sources"][0]["expenses"][0].update(
        base_type="property_value", calc_type="percent", value=Decimal("0.01")
    )
    payload["sources"][0]["incomes"][0]["value"] = Decimal("33.33")
    async with AsyncSession(monetization_engine) as session, session.begin():
        program = await repo.create_program(session, payload, seed["actor_id"])
        context = _deal_context(
            seed,
            base_amount=Decimal("100.01"),
            occurred_at=datetime(2026, 9, 16, tzinfo=UTC),
            supports=[{"name": "Historical support"}],
        )
        calculated = calculate_program(program, context)
        deal = await repo.insert_deal(session, context, program, calculated)
    async with AsyncSession(monetization_engine) as session:
        saved = await repo.get_deal(session, deal["id"])
        assert saved is not None
        assert saved["amounts"][1]["raw_amount"] == Decimal("0.0033333333")
        assert saved["amounts"][1]["amount"] == Decimal("0")
        assert saved["source_snapshot"]["base_amount"] == "100.01"
        assert saved["source_snapshot"]["supports"] == [{"name": "Historical support"}]
        assert saved["occurred_at"] == datetime(2026, 9, 16, tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["confirm", "issue", "status"])
async def test_real_lca_transition_captures_final_proposal_once(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str],
    path: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.commands.leasing import confirm_deal, issue_application
    from application.commands.leasing_applications_lc import change_status
    from infrastructure.models.applications import (
        LeasingApplication,
        LeasingCompanyApplication,
        LeasingProposal,
    )
    from infrastructure.repositories import monetization_source_repository

    seed = monetization_seed
    application_id, link_id, proposal_id, client_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(Company(id=client_id, name="Monetization client", company_type="other"))
        session.add(User(id=UUID(seed["actor_id"]), phone=str(uuid4())[:20], role="carcraft_employee"))
        await session.flush()
        session.add(LeasingApplication(id=application_id, company_id=client_id,
            dealer_company_id=UUID(seed["dealer_company_id"]), source_type="platform",
            status="issued", total_amount=Decimal("9999999.99")))
        await session.flush()
        session.add(LeasingCompanyApplication(id=link_id, application_id=application_id,
            leasing_company_id=UUID(seed["leasing_company_id"]),
            status="selected_lc" if path == "confirm" else "approved_final"))
        await session.flush()
        session.add(LeasingProposal(id=proposal_id, leasing_company_application_id=link_id,
            kind="final", total_amount=Decimal("2345678.91"), client_decision_action="accepted"))
        payload = _program_payload(seed)
        payload["sources"][0]["source_type"] = "platform"
        await repo.create_program(session, payload, seed["actor_id"])

    # Events are delivered after the router commits; this seam exercises the
    # source transaction and its real notification outbox, without Kafka I/O.
    for module in (confirm_deal, issue_application, change_status):
        monkeypatch.setattr(module, "emit_lca_changed", lambda *_a, **_k: None)
        if hasattr(module, "emit_leasing_application_changed"):
            monkeypatch.setattr(module, "emit_leasing_application_changed", lambda *_a, **_k: None)
    async with AsyncSession(monetization_engine) as session, session.begin():
        if path == "confirm":
            await confirm_deal.handle_confirm_deal(confirm_deal.ConfirmDealCommand(
                application_id, UUID(seed["actor_id"]), UUID(seed["leasing_company_id"])), session)
        elif path == "issue":
            await issue_application.handle_issue_application(issue_application.IssueApplicationCommand(
                application_id, UUID(seed["actor_id"]), UUID(seed["leasing_company_id"])), session)
        else:
            await change_status.handle_change_leasing_app_status(change_status.ChangeLeasingAppStatusCommand(
                link_id, UUID(seed["actor_id"]), "carcraft_employee", "deal"), session)
        facts = await monetization_source_repository.lca_source(session, link_id)
        captured = await repo.find_source_deal(session, facts)
        assert captured is not None
        assert captured["base_amount"] == Decimal("2345678.91")
        assert captured["source_type"] == "platform"
        assert captured["source_snapshot"]["final_proposal_id"] == proposal_id
        assert await session.scalar(sa.select(LeasingApplication.total_amount).where(
            LeasingApplication.id == application_id)) == Decimal("9999999.99")


@pytest.mark.asyncio
async def test_source_capture_unknown_history_is_reported_without_source_mutation(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str],
) -> None:
    from application.commands.monetization.integration import capture_source_transition
    from infrastructure.models.applications import (
        LeasingApplication,
        LeasingCompanyApplication,
    )
    seed = monetization_seed
    app_id, link_id = uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(User(id=UUID(seed["actor_id"]), phone=str(uuid4())[:20], role="carcraft_employee"))
        session.add(LeasingApplication(id=app_id, company_id=UUID(seed["dealer_company_id"]),
            dealer_company_id=UUID(seed["dealer_company_id"]), total_amount=Decimal("1234567.89")))
        await session.flush()
        session.add(LeasingCompanyApplication(id=link_id, application_id=app_id,
            leasing_company_id=UUID(seed["leasing_company_id"]), status="deal"))
        await session.flush()
        result = await capture_source_transition(session, actor_user_id=UUID(seed["actor_id"]),
                                                 leasing_company_application_id=link_id)
        assert result["deal"] is None
        assert "Источник" in result["reason"]
        assert await session.scalar(sa.select(LeasingCompanyApplication.status).where(
            LeasingCompanyApplication.id == link_id)) == "deal"
        assert await session.scalar(sa.select(LeasingApplication.source_type).where(
            LeasingApplication.id == app_id)) is None
        assert await session.scalar(sa.text("SELECT count(*) FROM notification_event_outbox WHERE event_type = 'monetization.capture_failed' AND entity_id = :id"), {"id": link_id}) == 1


@pytest.mark.asyncio
async def test_real_exchange_acceptance_uses_accepted_bid_and_quantity(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.commands.exchange import approve_bid
    from infrastructure.messaging import status_events
    from infrastructure.models.exchange import ExchangeBid, ExchangeRequest
    from infrastructure.models.support import SupportProgram
    distributor_id, support_id = uuid4(), uuid4()
    seed = monetization_seed
    request_id, bid_id, vehicle_id, lc_user = uuid4(), uuid4(), uuid4(), uuid4()
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add_all([
            User(id=lc_user, phone=str(uuid4())[:20], role="leasing_company", company_id=UUID(seed["lc_company_id"])),
            User(id=UUID(seed["actor_id"]), phone=str(uuid4())[:20], role="dealer", company_id=UUID(seed["dealer_company_id"])),
            Vehicle(id=vehicle_id, dealer_id=UUID(seed["dealer_company_id"])),
        ])
        session.add(Company(id=distributor_id, name="Origin distributor", company_type="distributor"))
        await session.flush()
        session.add(SupportProgram(id=support_id, name="Original support", distributor_id=distributor_id,
            support_type="vehicle_discount_dealer_invoice", support_params={"value_type": "amount", "value": 100}))
        await session.flush()
        session.add(ExchangeRequest(id=request_id, vehicle_id=vehicle_id, lc_user_id=lc_user,
            lc_company_id=UUID(seed["lc_company_id"]), selected_support_ids=[support_id], quantity=8, discount_type="percent", discount_value=Decimal("15")))
        await session.flush()
        session.add(ExchangeBid(id=bid_id, request_id=request_id, dealer_id=UUID(seed["actor_id"]),
            dealer_company_id=UUID(seed["dealer_company_id"]), distributor_id=distributor_id, price=Decimal("1234567.89"), quantity=3,
            kp_status="accepted"))
        await repo.create_program(session, _program_payload(seed), seed["actor_id"])
    for name in ("emit_exchange_bid_changed", "emit_exchange_request_changed"):
        monkeypatch.setattr(approve_bid, name, lambda *_a, **_k: None)
    for name in ("emit_exchange_bid_status_changed", "emit_exchange_request_status_changed"):
        monkeypatch.setattr(status_events, name, lambda *_a, **_k: None)
    async with AsyncSession(monetization_engine) as session, session.begin():
        await approve_bid.handle_approve_bid(approve_bid.ApproveBidCommand(bid_id, lc_user,
            company_id=UUID(seed["lc_company_id"])), session)
        captured = await repo.find_source_deal(session, {"exchange_request_id": request_id})
        assert captured is not None
        assert captured["base_amount"] == Decimal("3703703.67")
        assert captured["source_snapshot"]["supports"][0]["dealer_company_id"] == UUID(seed["dealer_company_id"])
        assert captured["source_snapshot"]["supports"][0]["distributor_company_id"] == distributor_id
        assert captured["source_snapshot"]["supports"][0]["name"] == "Original support"
        assert captured["source_snapshot"]["bid_quantity"] == 3
        assert captured["source_snapshot"]["request_quantity"] == 8
        assert await session.scalar(sa.select(ExchangeBid.price).where(ExchangeBid.id == bid_id)) == Decimal("1234567.89")
        assert await session.scalar(sa.select(ExchangeRequest.discount_value).where(ExchangeRequest.id == request_id)) == Decimal("15")


@pytest.mark.asyncio
async def test_provenance_migration_preserves_history_and_prevents_reclassification(
    monetization_engine: AsyncEngine,
) -> None:
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import DBAPIError

    path = Path(__file__).parents[2] / "alembic" / "versions" / "121_monetization_sources.py"
    spec = importlib.util.spec_from_file_location("source_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = "source_migration_" + uuid4().hex
    async with monetization_engine.begin() as connection:
        await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
        await connection.execute(sa.text("CREATE TABLE leasing_applications (id uuid PRIMARY KEY, total_amount numeric)"))
        await connection.execute(sa.text("CREATE TABLE application_applied_supports (id uuid PRIMARY KEY)"))
        old_id, new_id = uuid4(), uuid4()
        await connection.execute(sa.text("INSERT INTO leasing_applications (id,total_amount) VALUES (:id,100)"), {"id": old_id})
        def upgrade(sync: Connection) -> None:
            with Operations.context(MigrationContext.configure(sync)):
                module.upgrade()
        await connection.run_sync(upgrade)
        assert await connection.scalar(sa.text("SELECT source_type FROM leasing_applications WHERE id=:id"), {"id": old_id}) is None
        await connection.execute(sa.text("INSERT INTO leasing_applications (id,source_type) VALUES (:id,'platform')"), {"id": new_id})
        for row_id in (old_id, new_id):
            with pytest.raises(DBAPIError, match="Источник заявки"):
                async with connection.begin_nested():
                    await connection.execute(sa.text("UPDATE leasing_applications SET source_type='dealer_account' WHERE id=:id"), {"id": row_id})
        await connection.execute(sa.text("UPDATE leasing_applications SET total_amount=200 WHERE id=:id"), {"id": old_id})
        def downgrade(sync: Connection) -> None:
            with Operations.context(MigrationContext.configure(sync)):
                module.downgrade()
                module.upgrade()
        await connection.run_sync(downgrade)
        await connection.execute(sa.text("SET LOCAL search_path TO public"))
        await connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))



@pytest.mark.asyncio
async def test_allocated_units_match_vin_and_support_on_the_same_actual_vehicle(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str],
) -> None:
    from datetime import UTC, datetime, timedelta

    from application.commands.monetization.integration import capture_source_transition
    from infrastructure.models.applications import (
        ApplicationVehicle,
        ApplicationVehicleAllocation,
        CarsStatus,
        LeasingApplication,
        LeasingCompanyApplication,
        LeasingProposal,
    )
    from infrastructure.models.support import ApplicationAppliedSupport, SupportProgram
    from infrastructure.repositories import monetization_source_repository

    seed = monetization_seed
    app_id, link_id, line_id, first, second, removed, support_id = [uuid4() for _ in range(7)]
    mark_a, mark_b = "m-" + uuid4().hex, "m-" + uuid4().hex
    async with AsyncSession(monetization_engine) as session, session.begin():
        session.add(User(id=UUID(seed["actor_id"]), phone=str(uuid4())[:20], role="carcraft_employee"))
        session.add_all([Mark(id=mark_a, name="Allocated A"), Mark(id=mark_b, name="Allocated B")])
        if await session.get(CarsStatus, "confirmed") is None:
            session.add(CarsStatus(status_name="confirmed", status_display_name="Confirmed"))
        await session.flush()
        session.add_all([
            Vehicle(id=first, vin="ALLOCATEDMON00001", mark_id=mark_a, dealer_id=UUID(seed["dealer_company_id"])),
            Vehicle(id=second, vin="ALLOCATEDMON00002", mark_id=mark_b, dealer_id=UUID(seed["dealer_company_id"])),
            Vehicle(id=removed, vin="ALLOCATEDMON00003", mark_id=mark_b, dealer_id=UUID(seed["dealer_company_id"])),
            LeasingApplication(id=app_id, company_id=UUID(seed["dealer_company_id"]), source_type="platform", dealer_company_id=UUID(seed["dealer_company_id"])),
            SupportProgram(id=support_id, name="Allocated support", support_type="vehicle_discount_dealer_invoice"),
        ])
        await session.flush()
        session.add(LeasingCompanyApplication(id=link_id, application_id=app_id,
            leasing_company_id=UUID(seed["leasing_company_id"]), status="deal"))
        session.add(ApplicationVehicle(id=line_id, application_id=app_id, vehicle_id=None,
            dealer_company_id=UUID(seed["dealer_company_id"]), is_model_order=True,
            fulfillment_version=1, quantity=2, confirmed_quantity=2, car_status="confirmed"))
        await session.flush()
        session.add(LeasingProposal(leasing_company_application_id=link_id, kind="final", total_amount=Decimal("2222222.22")))
        for vehicle_id, vin, released in ((first, "ALLOCATEDMON00001", None), (second, "ALLOCATEDMON00002", None), (removed, "ALLOCATEDMON00003", datetime.now(UTC))):
            session.add(ApplicationVehicleAllocation(application_vehicle_id=line_id, vehicle_id=vehicle_id,
                vin=vin, unit_price=Decimal("1111111.11"), reserved_until=datetime.now(UTC)+timedelta(days=1),
                created_by=UUID(seed["actor_id"]), released_at=released))
        session.add(ApplicationAppliedSupport(application_id=app_id, vehicle_id=first,
            support_program_id=support_id, name="Allocated support", support_type="vehicle_discount_dealer_invoice",
            dealer_company_id=UUID(seed["dealer_company_id"])))
        payload = _program_payload(seed, brand="Allocated B", vin="ALLOCATEDMON00002", support_program_id=support_id)
        payload["sources"][0]["source_type"] = "platform"
        await repo.create_program(session, payload, seed["actor_id"])
        await session.flush()
        facts = await monetization_source_repository.lca_source(session, link_id)
        assert {row["vehicle_id"] for row in facts["vehicles"]} == {first, second}
        assert {row["quantity"] for row in facts["vehicles"]} == {1}
        result = await capture_source_transition(session, actor_user_id=UUID(seed["actor_id"]), leasing_company_application_id=link_id)
        assert result["deal"] is None  # The other unit's support cannot satisfy this VIN.
        session.add(ApplicationAppliedSupport(application_id=app_id, vehicle_id=second,
            support_program_id=support_id, name="Allocated support", support_type="vehicle_discount_dealer_invoice",
            dealer_company_id=UUID(seed["dealer_company_id"])))
        await session.flush()
        result = await capture_source_transition(session, actor_user_id=UUID(seed["actor_id"]), leasing_company_application_id=link_id)
        assert result["deal"] is not None
        assert result["deal"]["base_amount"] == Decimal("2222222.22")
        assert result["deal"]["consumed_vin"] == "ALLOCATEDMON00002"


@pytest.mark.asyncio
async def test_repository_preserves_uuid_values_in_rows_and_json_snapshots(
    monetization_engine: AsyncEngine, monetization_seed: dict[str, str],
) -> None:
    seed = monetization_seed
    program = await _save_program(monetization_engine, seed)
    assert isinstance(program["id"], UUID)
    assert isinstance(program["leasing_company_id"], UUID)
    assert isinstance(program["sources"][0]["id"], UUID)
    assert isinstance(program["sources"][0]["expenses"][0]["id"], UUID)
    deal = await _save_deal(monetization_engine, seed, program)
    assert isinstance(deal["id"], UUID)
    assert isinstance(deal["amounts"][0]["id"], UUID)
    assert isinstance(deal["dealer_company"]["id"], UUID)
    assert isinstance(deal["source_snapshot"]["exchange_request_id"], UUID)
    async with AsyncSession(monetization_engine) as session, session.begin():
        updated = await repo.update_deal(session, deal["id"],
            {"confirmations": {"dealer": {"user_id": UUID(seed["actor_id"]), "revision": 1}}})
        assert isinstance(updated["confirmations"]["dealer"]["user_id"], UUID)
