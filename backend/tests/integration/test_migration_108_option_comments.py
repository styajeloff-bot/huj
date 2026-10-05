"""PostgreSQL roundtrip coverage for legacy option JSON in migration 108."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio
MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "108_add_application_option_comments.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "migration_108_option_comments_under_test",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    migration: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def test_revision_108_legacy_json_upgrade_downgrade_roundtrip(
    db_session: AsyncSession,
) -> None:
    schema = f"option_comments_107_{uuid4().hex}"
    row_id = uuid4()
    legacy_equipments = [
        {"equipment_code": "alarm", "price": "100.00"},
        {
            "equipment_code": "tires",
            "price": "250.00",
            "comment": "preserve me",
        },
    ]
    legacy_services = [{"service_code": "insurance", "price": "50.00"}]
    async_connection = await db_session.connection()

    def exercise(sync_connection: Connection) -> None:
        quoted_schema = sync_connection.dialect.identifier_preparer.quote_schema(schema)
        migration = _load_migration()
        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(sync_connection))
        try:
            sync_connection.exec_driver_sql(f"CREATE SCHEMA {quoted_schema}")
            sync_connection.exec_driver_sql(f"SET search_path TO {quoted_schema}")
            sync_connection.exec_driver_sql(
                "CREATE TABLE application_vehicles ("
                "id uuid PRIMARY KEY, equipments jsonb NOT NULL, services jsonb NOT NULL)"
            )
            sync_connection.execute(
                sa.text(
                    "INSERT INTO application_vehicles (id, equipments, services) "
                    "VALUES (:id, CAST(:equipments AS jsonb), CAST(:services AS jsonb))"
                ),
                {
                    "id": row_id,
                    "equipments": json.dumps(legacy_equipments),
                    "services": json.dumps(legacy_services),
                },
            )

            migration.upgrade()
            upgraded = sync_connection.execute(
                sa.text(
                    "SELECT equipments, services FROM application_vehicles "
                    "WHERE id = :id"
                ),
                {"id": row_id},
            ).one()
            assert upgraded.equipments == [
                {**legacy_equipments[0], "comment": None},
                legacy_equipments[1],
            ]
            assert upgraded.services == [
                {**legacy_services[0], "comment": None},
            ]

            migration.downgrade()
            downgraded = sync_connection.execute(
                sa.text(
                    "SELECT equipments, services FROM application_vehicles "
                    "WHERE id = :id"
                ),
                {"id": row_id},
            ).one()
            assert downgraded.equipments == legacy_equipments
            assert downgraded.services == legacy_services
        finally:
            migration.op = original_op
            sync_connection.exec_driver_sql("SET search_path TO public")
            sync_connection.exec_driver_sql(
                f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"
            )

    await async_connection.run_sync(exercise)
