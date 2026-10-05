"""Repository contracts on real, disposable, Alembic-built PostgreSQL databases.

These tests deliberately never request ``db_session`` or ``_engine``: those
fixtures build metadata, which cannot detect drift in deployed migration chains.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import shutil
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.dialects.postgresql.base import PGInspector
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import AddConstraint, CreateTable

from infrastructure.models import Base
from infrastructure.models.applications import LeasingCompanyApplication
from infrastructure.repositories import (
    email_preferences_repository,
    notification_repository,
)

_BACKEND = Path(__file__).resolve().parents[2]
_OWNED_DATABASE = re.compile(r"carcraft_schema_contract_[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class MigratedDatabase:
    url: URL
    engine: AsyncEngine

    async def migrate(self, direction: str, revision: str) -> None:
        assert direction in {"upgrade", "downgrade"}
        await self.alembic(direction, revision)

    async def alembic(self, *arguments: str, cwd: Path = _BACKEND) -> None:
        assert _OWNED_DATABASE.fullmatch(self.url.database or "")
        environment = {
            **os.environ,
            "DB_HOST": self.url.host or "localhost",
            "DB_PORT": str(self.url.port or 5432),
            "DB_USER": self.url.username or "",
            "DB_PASSWORD": self.url.password or "",
            "DB_NAME": self.url.database or "",
            # DATABASE_URL takes precedence over DB_* in Settings. Always override
            # an inherited deployment URL with our explicitly owned database.
            "DATABASE_URL": self.url.render_as_string(hide_password=False),
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (str(_BACKEND), os.environ.get("PYTHONPATH", ""))
                if part
            ),
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            *arguments,
            cwd=cwd,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        assert process.returncode == 0, output.decode()


@pytest_asyncio.fixture
async def migrated_database(
    request: pytest.FixtureRequest,
) -> AsyncIterator[MigratedDatabase]:
    """Own a UUID database; never modify the configured/shared database itself."""
    configured_url = make_url(
        os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://postgres:password@localhost:5433/carcraft_test",
        )
    )
    database_name = f"carcraft_schema_contract_{uuid4().hex}"
    assert _OWNED_DATABASE.fullmatch(database_name)
    url = configured_url.set(drivername="postgresql+asyncpg", database=database_name)
    admin = create_async_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
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
                        "SELECT oid, datdba FROM pg_database "
                        "WHERE datname = :name AND datdba = "
                        "(SELECT oid FROM pg_roles WHERE rolname = current_user)"
                    ),
                    {"name": database_name},
                )
            ).one()
            ownership = (row.oid, row.datdba)
        database = MigratedDatabase(url, engine)
        await database.migrate("upgrade", getattr(request, "param", "head"))
        yield database
    finally:
        await engine.dispose()
        if ownership is not None:
            async with admin.connect() as connection:
                row = (
                    await connection.execute(
                        sa.text(
                            "SELECT oid, datdba FROM pg_database "
                            "WHERE datname = :name AND datdba = "
                            "(SELECT oid FROM pg_roles WHERE rolname = current_user)"
                        ),
                        {"name": database_name},
                    )
                ).one()
                # Refuse cleanup if this is not exactly the database we created.
                assert (row.oid, row.datdba) == ownership
                assert _OWNED_DATABASE.fullmatch(database_name)
                await connection.exec_driver_sql(f'DROP DATABASE "{database_name}"')
        await admin.dispose()


async def _insert_user(session: AsyncSession) -> UUID:
    user_id = uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO users (id, phone, email, role, mfa_enabled) "
            "VALUES (:id, :phone, :email, 'client', false)"
        ),
        {
            "id": user_id,
            "phone": f"+7{user_id.int % 10**10:010d}",
            "email": f"{user_id.hex}@schema-contract.test",
        },
    )
    return user_id


async def test_notification_repository_defaults_on_migrated_schema(
    migrated_database: MigratedDatabase,
) -> None:
    async with AsyncSession(
        migrated_database.engine, expire_on_commit=False
    ) as session:
        user_id = await _insert_user(session)
        notification_id = await notification_repository.create_notification(
            session,
            user_id=user_id,
            notification_type="system",
            title="Migration-built inbox",
            message="Unread on first creation",
        )
        await session.commit()
    async with AsyncSession(migrated_database.engine) as session:
        assert await notification_repository.get_counts(session, user_id) == {
            "total_count": 1,
            "unread_count": 1,
        }
        unread, count = await notification_repository.list_by_user(
            session,
            user_id,
            is_read=False,
        )
        assert count == 1
        assert [item["id"] for item in unread] == [notification_id]
        assert unread[0]["is_read"] is False
        assert await notification_repository.mark_all_as_read(session, user_id) == 1
        await session.commit()
    async with AsyncSession(migrated_database.engine) as session:
        assert await notification_repository.get_counts(session, user_id) == {
            "total_count": 1,
            "unread_count": 0,
        }
        assert await notification_repository.list_by_user(
            session,
            user_id,
            is_read=False,
        ) == ([], 0)
        stored = await notification_repository.get_by_id(session, notification_id)
        assert stored is not None
        assert stored["is_read"] is True
        assert stored["read_at"] is not None


async def test_first_email_preferences_insert_and_update_survive_new_sessions(
    migrated_database: MigratedDatabase,
) -> None:
    async with AsyncSession(migrated_database.engine) as session:
        user_id = await _insert_user(session)
        assert (
            await session.scalar(
                sa.text("SELECT count(*) FROM email_preferences WHERE user_id = :user"),
                {"user": user_id},
            )
            == 0
        )
        preferences = await email_preferences_repository.get_or_create(session, user_id)
        assert preferences["application_status_emails"] is True
        assert preferences["document_request_emails"] is True
        assert preferences["document_status_emails"] is True
        assert preferences["leasing_approval_emails"] is True
        assert preferences["system_emails"] is True
        assert preferences["exchange_emails"] is True
        assert preferences["weekly_digest"] is True
        assert preferences["marketing_emails"] is False
        assert preferences["email_frequency"] == "immediate"
        await session.commit()
    async with AsyncSession(migrated_database.engine) as session:
        updated = await email_preferences_repository.update_preferences(
            session,
            user_id,
            {
                "application_status_emails": False,
                "exchange_emails": False,
                "email_frequency": "daily",
            },
        )
        assert updated is not None
        await session.commit()
    async with AsyncSession(migrated_database.engine) as session:
        persisted = await email_preferences_repository.get_or_create(session, user_id)
        assert persisted["updated_at"] is not None
        assert persisted["updated_at"].utcoffset() is not None
        assert updated["updated_at"] is not None
        # The legacy updater constructs UTC then strips tzinfo. Its returned
        # ORM value can be naive or already reloaded from timestamptz. Compare
        # the exact instant and every field, without discarding timezone on the
        # persisted value or hiding an actual clock/offset change.
        expected_updated_at = updated["updated_at"]
        if expected_updated_at.tzinfo is None:
            expected_updated_at = expected_updated_at.replace(tzinfo=UTC)
        assert persisted == {
            **updated,
            "updated_at": expected_updated_at.astimezone(UTC),
        }
        assert updated["application_status_emails"] is False
        assert updated["exchange_emails"] is False
        assert updated["email_frequency"] == "daily"
        assert updated["document_request_emails"] is True
        assert (
            await session.scalar(
                sa.text("SELECT count(*) FROM email_preferences WHERE user_id = :user"),
                {"user": user_id},
            )
            == 1
        )


async def test_legacy_lc_enum_values_are_readable_through_typed_orm(
    migrated_database: MigratedDatabase,
) -> None:
    statuses = {uuid4(): status for status in ("prescoring", "issued")}
    async with migrated_database.engine.begin() as connection:
        for row_id, status in statuses.items():
            await connection.execute(
                sa.text(
                    "INSERT INTO leasing_company_applications (id, status) "
                    "VALUES (:id, CAST(:status AS leasing_company_application_status))"
                ),
                {"id": row_id, "status": status},
            )
    async with AsyncSession(migrated_database.engine) as session:
        rows = (
            (await session.execute(sa.select(LeasingCompanyApplication)))
            .scalars()
            .all()
        )
        assert {row.id: row.status for row in rows} == statuses


async def _schema_invariants(engine: AsyncEngine) -> dict[str, list[tuple]]:
    queries = {
        "constraints": """
            SELECT c.relname, p.conname, p.contype::text, p.convalidated,
                   pg_get_constraintdef(p.oid, true)
            FROM pg_constraint p JOIN pg_class c ON c.oid = p.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' ORDER BY c.relname, p.conname
        """,
        "indexes": """
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' ORDER BY tablename, indexname
        """,
        "enums": """
            SELECT t.typname, e.enumsortorder, e.enumlabel
            FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public' ORDER BY t.typname, e.enumsortorder
        """,
    }
    async with engine.connect() as connection:
        return {
            name: [
                tuple(row) for row in (await connection.execute(sa.text(query))).all()
            ]
            for name, query in queries.items()
        }


async def _column_defaults(engine: AsyncEngine) -> dict[tuple[str, str], str | None]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text(
                    "SELECT table_name, column_name, column_default "
                    "FROM information_schema.columns WHERE table_schema = 'public'"
                )
            )
        ).all()
        return {(row.table_name, row.column_name): row.column_default for row in rows}


async def _preserved_rows(engine: AsyncEngine) -> dict[str, list[dict]]:
    tables = (
        "users",
        "notifications",
        "email_preferences",
        "notification_event_receipts",
        "notification_email_batches",
        "notification_email_deliveries",
    )
    async with engine.connect() as connection:
        return {
            table: list(
                (
                    await connection.execute(
                        sa.text(
                            f"SELECT to_jsonb(t) FROM {table} t ORDER BY to_jsonb(t)::text"  # noqa: S608
                        )
                    )
                ).scalars()
            )
            for table in tables
        }


@pytest.mark.parametrize("migrated_database", ["111"], indirect=True)
async def test_112_upgrade_downgrade_reupgrade_preserves_data_and_schema(
    migrated_database: MigratedDatabase,
) -> None:
    database = migrated_database
    before_schema = await _schema_invariants(database.engine)
    before_defaults = await _column_defaults(database.engine)
    # NOT VALID is deliberate for legacy rows; migration must not validate it.
    assert sum(not row[3] for row in before_schema["constraints"] if row[2] == "c") >= 4
    assert any(
        row[1] == "fk_application_vehicles_car_status"
        for row in before_schema["constraints"]
    )
    assert any(
        row[1] == "ck_catalog_storefronts_slug_format"
        for row in before_schema["constraints"]
    )
    timestamp = datetime(2026, 8, 1, 12, 30, tzinfo=UTC)
    async with AsyncSession(database.engine) as session:
        user_id = await _insert_user(session)
        for is_read in (None, False, True):
            for read_at in (None, timestamp):
                await session.execute(
                    sa.text(
                        "INSERT INTO notifications "
                        "(id,user_id,type,title,message,is_read,read_at) "
                        "VALUES (:id,:user,'system','legacy','keep',:read,:at)"
                    ),
                    {"id": uuid4(), "user": user_id, "read": is_read, "at": read_at},
                )
        await session.execute(
            sa.text(
                "INSERT INTO email_preferences (user_id,application_status_emails,"
                "document_request_emails,document_status_emails,leasing_approval_emails,"
                "system_emails,weekly_digest,marketing_emails,email_frequency,exchange_emails) "
                "VALUES (:user,false,true,false,true,false,true,false,'weekly',false)"
            ),
            {"user": user_id},
        )
        event_id, batch_id = uuid4(), uuid4()
        notification_id = await session.scalar(
            sa.text("SELECT id FROM notifications ORDER BY id LIMIT 1")
        )
        await session.execute(
            sa.text(
                "INSERT INTO notification_event_receipts (event_id,payload) "
                "VALUES (:event,jsonb_build_object('fixture',true))"
            ),
            {"event": event_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO notification_email_batches "
                "(id,user_id,delivery_mode,message_id) "
                "VALUES (:id,:user,'weekly','<preserved@schema-contract.test>')"
            ),
            {"id": batch_id, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO notification_email_deliveries "
                "(id,notification_id,event_id,user_id,recipient_role,batch_id,"
                "delivery_mode,next_attempt_at) "
                "VALUES (:id,:notification,:event,:user,'client',:batch,'weekly',now())"
            ),
            {
                "id": uuid4(),
                "notification": notification_id,
                "event": event_id,
                "user": user_id,
                "batch": batch_id,
            },
        )
        await session.commit()
    before_rows = await _preserved_rows(database.engine)
    expected_rows = {
        **before_rows,
        "notifications": [
            {**row, "is_read": row["read_at"] is not None}
            if row["is_read"] is None
            else row
            for row in before_rows["notifications"]
        ],
    }
    # Compare identity-sorted rows independently of changed JSON values.
    expected_rows["notifications"].sort(key=lambda row: row["id"])
    after_defaults: dict[tuple[str, str], str | None] | None = None
    for direction, revision in (
        ("upgrade", "112"),
        ("downgrade", "111"),
        ("upgrade", "112"),
    ):
        await database.migrate(direction, revision)
        assert await _schema_invariants(database.engine) == before_schema
        rows = await _preserved_rows(database.engine)
        rows["notifications"].sort(key=lambda row: row["id"])
        assert rows == expected_rows
        defaults = await _column_defaults(database.engine)
        assert defaults.keys() == before_defaults.keys()
        if direction == "downgrade":
            assert defaults == before_defaults
        else:
            added = {
                key for key, value in defaults.items() if value != before_defaults[key]
            }
            assert len(added) == 112
            assert all(
                before_defaults[key] is None and defaults[key] is not None
                for key in added
            )
            if after_defaults is None:
                after_defaults = defaults
            else:
                assert defaults == after_defaults


@pytest.mark.parametrize("migrated_database", ["116"], indirect=True)
async def test_116_downgrade_reupgrade_restores_group_tables_and_preserves_inbox(
    migrated_database: MigratedDatabase,
) -> None:
    database = migrated_database
    group_tables = {
        "notification_document_upload_groups",
        "notification_document_upload_members",
    }
    async with database.engine.connect() as connection:
        before_tables = set(
            await connection.run_sync(lambda conn: sa.inspect(conn).get_table_names())
        )
        assert group_tables <= before_tables
        assert await connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "116"
    before_schema = await _schema_invariants(database.engine)
    before_defaults = await _column_defaults(database.engine)
    async with AsyncSession(database.engine) as session:
        user_id = await _insert_user(session)
        notification_id = await notification_repository.create_notification(
            session,
            user_id=user_id,
            notification_type="system",
            title="Unrelated migration 116 sentinel",
            message="Preserve identity, content and read/delete history",
        )
        await notification_repository.mark_as_read(session, notification_id)
        await notification_repository.delete_by_id(session, notification_id)
        await session.execute(
            sa.text(
                "INSERT INTO notification_event_receipts (event_id, payload) "
                "VALUES (:event, jsonb_build_object('sentinel', 'migration-116'))"
            ),
            {"event": uuid4()},
        )
        await session.commit()
    expected_rows = await _preserved_rows(database.engine)
    assert len(expected_rows["notifications"]) == 1
    sentinel = expected_rows["notifications"][0]
    assert sentinel["id"] == str(notification_id)
    assert sentinel["is_read"] is True
    assert sentinel["read_at"] is not None and sentinel["deleted_at"] is not None
    assert len(expected_rows["notification_event_receipts"]) == 1

    for direction, revision in (("downgrade", "115"), ("upgrade", "116")):
        await database.migrate(direction, revision)
        async with database.engine.connect() as connection:
            actual_tables = set(
                await connection.run_sync(lambda conn: sa.inspect(conn).get_table_names())
            )
            assert await connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == revision
        assert actual_tables == (
            before_tables - group_tables if direction == "downgrade" else before_tables
        )
        assert await _preserved_rows(database.engine) == expected_rows
    # Re-upgrade reconstructs the exact FK/index/CHECK/default contracts, not
    # merely two tables with matching names. No metadata.create_all is involved.
    assert await _schema_invariants(database.engine) == before_schema
    assert await _column_defaults(database.engine) == before_defaults


async def test_migrated_head_has_strict_empty_autogenerate_and_enum_parity(
    migrated_database: MigratedDatabase,
) -> None:
    # Exercise the production environment, including its comparison settings.
    await migrated_database.alembic("check")

    def compare_strictly(connection: Connection) -> None:
        context = MigrationContext.configure(
            connection,
            opts={
                "compare_type": True,
                "compare_server_default": True,
            },
        )
        assert compare_metadata(context, Base.metadata) == []

    def enum_labels(connection: Connection) -> dict[str, list[str]]:
        inspector = sa.inspect(connection)
        assert isinstance(inspector, PGInspector)
        return {item["name"]: item["labels"] for item in inspector.get_enums()}

    async with migrated_database.engine.connect() as connection:
        await connection.run_sync(compare_strictly)
        actual = await connection.run_sync(enum_labels)
    expected: dict[str, list[str]] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.native_enum:
                assert column.type.name is not None
                if column.type.name in expected:
                    assert expected[column.type.name] == column.type.enums
                expected[column.type.name] = column.type.enums
    assert actual == expected


async def test_real_autogenerate_renders_only_pass_in_disposable_script_directory(
    migrated_database: MigratedDatabase,
    tmp_path: Path,
) -> None:
    def copy_script_directory() -> set[str]:
        shutil.copytree(_BACKEND / "alembic", tmp_path / "alembic")
        shutil.copy2(_BACKEND / "alembic.ini", tmp_path / "alembic.ini")
        return {path.name for path in (tmp_path / "alembic/versions").glob("*.py")}

    before_files = await asyncio.to_thread(copy_script_directory)
    await migrated_database.alembic(
        "revision",
        "--autogenerate",
        "-m",
        "temporary strict schema parity probe",
        cwd=tmp_path,
    )

    def generated_module() -> ast.Module:
        new_files = [
            path
            for path in (tmp_path / "alembic/versions").glob("*.py")
            if path.name not in before_files
        ]
        assert len(new_files) == 1
        return ast.parse(new_files[0].read_text(encoding="utf-8"))

    module = await asyncio.to_thread(generated_module)
    operations = {
        node.name: node.body
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in {"upgrade", "downgrade"}
    }
    assert set(operations) == {"upgrade", "downgrade"}
    for body in operations.values():
        assert len(body) == 1 and isinstance(body[0], ast.Pass), ast.dump(module)
    async with migrated_database.engine.connect() as connection:
        # The throwaway generated revision must never be applied.
        assert (
            await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "122"
        )


CheckContracts = dict[tuple[str, str], tuple[str, bool]]


def _live_check_contracts(
    connection: Connection,
) -> tuple[CheckContracts, CheckContracts]:
    """Let PostgreSQL parse ORM CHECKs, without copying FK/index/default metadata."""
    actual = {
        (row.table_name, row.conname): (row.expression, row.convalidated)
        for row in connection.execute(
            sa.text(
                "SELECT c.relname AS table_name, p.conname, p.convalidated, "
                "pg_get_expr(p.conbin, p.conrelid) AS expression "
                "FROM pg_constraint p JOIN pg_class c ON c.oid = p.conrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND p.contype = 'c'"
            )
        )
    }
    expected: CheckContracts = {}
    for model_table in Base.metadata.tables.values():
        checks = [
            item
            for item in model_table.constraints
            if isinstance(item, sa.CheckConstraint)
        ]
        if not checks:
            continue
        temporary = sa.Table(
            f"orm_check_{uuid4().hex}",
            sa.MetaData(),
            *(
                sa.Column(column.name, column.type, nullable=True)
                for column in model_table.columns
            ),
            prefixes=["TEMPORARY"],
            postgresql_on_commit="DROP",
        )
        # Execute DDL directly: Table.create would invoke ENUM creation events.
        connection.execute(CreateTable(temporary))
        for check in checks:
            assert check.name is not None
            parsed_check = sa.CheckConstraint(
                check.sqltext,
                name=check.name,
                postgresql_not_valid=check.dialect_options["postgresql"].get(
                    "not_valid", False
                ),
            )
            temporary.append_constraint(parsed_check)
            # ALTER ADD retains NOT VALID even for an initially empty table.
            connection.execute(AddConstraint(parsed_check))
        parsed_rows = connection.execute(
            sa.text(
                "SELECT conname, pg_get_expr(conbin, conrelid) AS expression, convalidated "
                "FROM pg_constraint WHERE conrelid = to_regclass(:table_name) AND contype = 'c'"
            ),
            {"table_name": temporary.name},
        )
        expected.update(
            {
                (model_table.name, row.conname): (row.expression, row.convalidated)
                for row in parsed_rows
            }
        )
    return actual, expected


async def test_live_check_contracts_match_names_expressions_and_validation(
    migrated_database: MigratedDatabase,
) -> None:
    async with migrated_database.engine.begin() as connection:
        actual, expected = await connection.run_sync(_live_check_contracts)
        assert actual == expected


async def test_live_check_comparison_detects_unregistered_and_missing_constraints(
    migrated_database: MigratedDatabase,
) -> None:
    async with migrated_database.engine.begin() as connection:
        await connection.exec_driver_sql(
            "ALTER TABLE catalog_storefronts DROP CONSTRAINT ck_catalog_storefronts_slug_format"
        )
        await connection.exec_driver_sql(
            "ALTER TABLE catalog_storefronts ADD CONSTRAINT unexpected_check CHECK (slug <> '') NOT VALID"
        )
        actual, expected = await connection.run_sync(_live_check_contracts)
        assert actual != expected
        assert actual.keys() - expected.keys() == {
            ("catalog_storefronts", "unexpected_check")
        }
        assert expected.keys() - actual.keys() == {
            ("catalog_storefronts", "ck_catalog_storefronts_slug_format")
        }


@pytest.mark.parametrize("changed_contract", ["expression", "validation"])
async def test_live_check_comparison_detects_expression_and_validation_drift(
    migrated_database: MigratedDatabase,
    changed_contract: str,
) -> None:
    key = ("catalog_storefronts", "ck_catalog_storefronts_slug_format")
    expressions = {
        "expression": "slug IS NULL OR char_length(slug) > 0",
        "validation": "slug IS NULL OR slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
    }
    suffix = " NOT VALID" if changed_contract == "validation" else ""
    async with migrated_database.engine.begin() as connection:
        await connection.exec_driver_sql(
            "ALTER TABLE catalog_storefronts DROP CONSTRAINT ck_catalog_storefronts_slug_format"
        )
        await connection.exec_driver_sql(
            "ALTER TABLE catalog_storefronts ADD CONSTRAINT ck_catalog_storefronts_slug_format "
            f"CHECK ({expressions[changed_contract]}){suffix}"
        )
        actual, expected = await connection.run_sync(_live_check_contracts)
        assert actual.keys() == expected.keys()
        assert {name for name in actual if actual[name] != expected[name]} == {key}
        expression, validated = actual[key]
        expected_expression, expected_validated = expected[key]
        if changed_contract == "expression":
            assert expression != expected_expression
            assert validated == expected_validated
        else:
            assert expression == expected_expression
            assert validated is False and expected_validated is True
