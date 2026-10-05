import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.models.section_visibility import SectionVisibility
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "102_storefront_section_visibility.py"
)
MIGRATION_103_PATH = MIGRATION_PATH.with_name(
    "103_storefront_role_section_visibility.py"
)

MigrationAssertion = Callable[[Connection], None]


def _public_matrix(
    connection: Connection,
    storefront_id: object,
) -> dict[str, bool]:
    rows = connection.execute(
        sa.text(
            "SELECT section_key, is_visible FROM section_visibility "
            "WHERE scope = 'public' "
            "AND storefront_id = CAST(:storefront_id AS uuid)"
        ),
        {"storefront_id": str(storefront_id)},
    ).all()
    return {
        str(row[0]): bool(row[1])
        for row in rows
    }


async def _run_round_trip(
    db_session: AsyncSession,
    *,
    after_downgrade: MigrationAssertion,
    after_upgrade: MigrationAssertion,
) -> None:
    spec = importlib.util.spec_from_file_location("migration_102", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    spec_103 = importlib.util.spec_from_file_location(
        "migration_103",
        MIGRATION_103_PATH,
    )
    assert spec_103 is not None and spec_103.loader is not None
    migration_103: Any = importlib.util.module_from_spec(spec_103)
    spec_103.loader.exec_module(migration_103)
    async_connection = await db_session.connection()

    def run(sync_connection: Connection) -> None:
        operations = Operations(MigrationContext.configure(sync_connection))
        original_op = migration.op
        original_op_103 = migration_103.op
        migration.op = operations
        migration_103.op = operations
        try:
            migration_103.downgrade()
            migration.downgrade()
            after_downgrade(sync_connection)
            migration.upgrade()
            after_upgrade(sync_connection)
            migration_103.upgrade()
        finally:
            migration.op = original_op
            migration_103.op = original_op_103

    await async_connection.run_sync(run)


async def test_revision_102_round_trip_materializes_custom_public_snapshots(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom_storefronts = [
        Storefront(
            slug="visibility-migration-child",
            is_default=False,
            is_active=True,
        ),
        Storefront(
            slug="visibility-migration-second",
            is_default=False,
            is_active=False,
        ),
    ]
    db_session.add_all(custom_storefronts)
    await db_session.flush()
    db_session.add_all(
        [
            SectionVisibility(
                scope="public",
                storefront_id=DEFAULT_STOREFRONT_ID,
                section_key="models",
                is_visible=True,
                updated_by=employee_user.id,
            ),
            SectionVisibility(
                scope="public",
                storefront_id=DEFAULT_STOREFRONT_ID,
                section_key="special_equipment_catalog",
                is_visible=True,
                updated_by=employee_user.id,
            ),
            SectionVisibility(
                scope="public",
                storefront_id=custom_storefronts[0].id,
                section_key="models",
                is_visible=False,
                updated_by=employee_user.id,
            ),
            SectionVisibility(
                scope="public",
                storefront_id=custom_storefronts[1].id,
                section_key="catalog",
                is_visible=False,
                updated_by=employee_user.id,
            ),
            SectionVisibility(
                scope="dealer",
                storefront_id=DEFAULT_STOREFRONT_ID,
                section_key="applications",
                is_visible=False,
                updated_by=employee_user.id,
            ),
        ]
    )
    await db_session.flush()

    def after_downgrade(connection: Connection) -> None:
        columns = {
            column["name"]
            for column in sa.inspect(connection).get_columns(
                "section_visibility"
            )
        }
        assert "storefront_id" not in columns
        public_rows = connection.execute(
            sa.text(
                "SELECT section_key, is_visible FROM section_visibility "
                "WHERE scope = 'public' ORDER BY section_key"
            )
        ).all()
        assert public_rows == [
            ("models", True),
            ("special_equipment_catalog", True),
        ]

    def after_upgrade(connection: Connection) -> None:
        expected = {
            "about": True,
            "catalog": True,
            "models": True,
            "special_equipment_catalog": False,
        }
        for storefront in custom_storefronts:
            assert _public_matrix(connection, storefront.id) == expected
        root_storefront_ids = set(
            connection.scalars(
                sa.text(
                    "SELECT storefront_id FROM section_visibility "
                    "WHERE scope = 'public' "
                    "AND section_key IN ('models', 'special_equipment_catalog')"
                )
            ).all()
        )
        assert root_storefront_ids == {
            DEFAULT_STOREFRONT_ID,
            *(storefront.id for storefront in custom_storefronts),
        }
        global_storefront_id = connection.scalar(
            sa.text(
                "SELECT storefront_id FROM section_visibility "
                "WHERE scope = 'dealer' AND section_key = 'applications'"
            )
        )
        assert global_storefront_id is None
        indexes = {
            index["name"]
            for index in sa.inspect(connection).get_indexes(
                "section_visibility"
            )
        }
        assert {
            "uq_section_visibility_public_storefront_section",
            "uq_section_visibility_global_scope_section",
        } <= indexes

    await _run_round_trip(
        db_session,
        after_downgrade=after_downgrade,
        after_upgrade=after_upgrade,
    )


async def test_revision_102_materializes_defaults_without_public_overrides(
    db_session: AsyncSession,
) -> None:
    custom_storefronts = [
        Storefront(
            slug="visibility-empty-first",
            is_default=False,
            is_active=True,
        ),
        Storefront(
            slug="visibility-empty-second",
            is_default=False,
            is_active=False,
        ),
    ]
    db_session.add_all(custom_storefronts)
    await db_session.flush()

    def after_downgrade(connection: Connection) -> None:
        public_count = connection.scalar(
            sa.text(
                "SELECT count(*) FROM section_visibility WHERE scope = 'public'"
            )
        )
        assert public_count == 0

    def after_upgrade(connection: Connection) -> None:
        expected = {
            "about": True,
            "catalog": True,
            "models": False,
            "special_equipment_catalog": False,
        }
        for storefront in custom_storefronts:
            assert _public_matrix(connection, storefront.id) == expected

    await _run_round_trip(
        db_session,
        after_downgrade=after_downgrade,
        after_upgrade=after_upgrade,
    )
