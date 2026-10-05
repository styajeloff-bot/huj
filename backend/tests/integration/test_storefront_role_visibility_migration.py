import importlib.util
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
    / "103_storefront_role_section_visibility.py"
)

ROLE_DEFAULTS: dict[str, dict[str, bool]] = {
    "leasing_company": {
        "leasing_applications": True,
        "documents": True,
        "document_requirements": True,
        "compensations": True,
        "exchange": True,
        "leasing_analytics": True,
        "security": True,
        "employees": True,
    },
    "dealer": {
        "applications": True,
        "clients": True,
        "inventory": True,
        "reports": True,
        "distributor_analytics": True,
        "exchange": True,
        "compensations": True,
        "employees": True,
    },
    "distributor": {
        "applications": True,
        "warehouses": True,
        "distributor_analytics": True,
        "dealers": True,
        "companies": True,
        "support": True,
        "compensations": True,
        "catalog": True,
        "employees": True,
    },
}


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_103", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _matrix(
    connection: Connection,
    scope: str,
    storefront_id: object,
) -> dict[str, bool]:
    rows = connection.execute(
        sa.text(
            "SELECT section_key, is_visible FROM section_visibility "
            "WHERE scope = :scope "
            "AND storefront_id = CAST(:storefront_id AS uuid)"
        ),
        {"scope": scope, "storefront_id": str(storefront_id)},
    ).all()
    return {str(row[0]): bool(row[1]) for row in rows}


async def test_revision_103_round_trip_scopes_existing_role_overrides(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom_storefronts = [
        Storefront(slug="role-migration-active", is_default=False, is_active=True),
        Storefront(
            slug="role-migration-inactive",
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
                storefront_id=custom_storefronts[0].id,
                section_key="catalog",
                is_visible=False,
                updated_by=employee_user.id,
            ),
        ]
    )
    await db_session.flush()

    migration = _load_migration()
    async_connection = await db_session.connection()

    def run(sync_connection: Connection) -> None:
        operations = Operations(MigrationContext.configure(sync_connection))
        original_op = migration.op
        migration.op = operations
        try:
            migration.downgrade()
            sync_connection.execute(
                sa.text(
                    "INSERT INTO section_visibility "
                    "(scope, storefront_id, section_key, is_visible, updated_by) "
                    "VALUES "
                    "('leasing_company', NULL, 'documents', FALSE, :actor), "
                    "('dealer', NULL, 'applications', FALSE, :actor), "
                    "('distributor', NULL, 'catalog', FALSE, :actor), "
                    "('carcraft_employee', NULL, "
                    "'special_equipment_import', TRUE, :actor)"
                ),
                {"actor": employee_user.id},
            )

            migration.upgrade()

            expected_by_scope = {
                "leasing_company": {
                    **ROLE_DEFAULTS["leasing_company"],
                    "documents": False,
                },
                "dealer": {
                    **ROLE_DEFAULTS["dealer"],
                    "applications": False,
                },
                "distributor": {
                    **ROLE_DEFAULTS["distributor"],
                    "catalog": False,
                },
            }
            for storefront in custom_storefronts:
                for scope, expected in expected_by_scope.items():
                    assert _matrix(sync_connection, scope, storefront.id) == expected

            scoped_root_ids = set(
                sync_connection.scalars(
                    sa.text(
                        "SELECT DISTINCT storefront_id FROM section_visibility "
                        "WHERE scope IN "
                        "('leasing_company', 'dealer', 'distributor')"
                    )
                ).all()
            )
            assert DEFAULT_STOREFRONT_ID in scoped_root_ids
            assert None not in scoped_root_ids
            assert sync_connection.scalar(
                sa.text(
                    "SELECT storefront_id FROM section_visibility "
                    "WHERE scope = 'carcraft_employee'"
                )
            ) is None

            public_rows = sync_connection.execute(
                sa.text(
                    "SELECT storefront_id, section_key, is_visible "
                    "FROM section_visibility WHERE scope = 'public' "
                    "ORDER BY section_key"
                )
            ).all()
            assert public_rows == [
                (custom_storefronts[0].id, "catalog", False),
                (DEFAULT_STOREFRONT_ID, "models", True),
            ]

            sync_connection.execute(
                sa.text(
                    "UPDATE section_visibility SET is_visible = TRUE "
                    "WHERE scope = 'leasing_company' "
                    "AND storefront_id = CAST(:storefront_id AS uuid) "
                    "AND section_key = 'documents'"
                ),
                {"storefront_id": str(custom_storefronts[0].id)},
            )

            migration.downgrade()

            assert sync_connection.scalar(
                sa.text(
                    "SELECT count(*) FROM section_visibility "
                    "WHERE scope IN "
                    "('leasing_company', 'dealer', 'distributor') "
                    "AND storefront_id IS NOT NULL"
                )
            ) == 0
            assert sync_connection.scalar(
                sa.text(
                    "SELECT is_visible FROM section_visibility "
                    "WHERE scope = 'leasing_company' "
                    "AND storefront_id IS NULL AND section_key = 'documents'"
                )
            ) is False

            migration.upgrade()

            for storefront in custom_storefronts:
                assert _matrix(
                    sync_connection,
                    "leasing_company",
                    storefront.id,
                )["documents"] is False
            indexes = {
                item["name"]
                for item in sa.inspect(sync_connection).get_indexes(
                    "section_visibility"
                )
            }
            assert {
                "uq_section_visibility_storefront_scope_section",
                "uq_section_visibility_global_scope_section",
            } <= indexes
        finally:
            migration.op = original_op

    await async_connection.run_sync(run)


async def test_revision_103_materializes_full_defaults_without_role_overrides(
    db_session: AsyncSession,
) -> None:
    custom = Storefront(
        slug="role-migration-no-overrides",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()
    migration = _load_migration()
    async_connection = await db_session.connection()

    def run(sync_connection: Connection) -> None:
        operations = Operations(MigrationContext.configure(sync_connection))
        original_op = migration.op
        migration.op = operations
        try:
            migration.downgrade()
            migration.upgrade()
            for scope, expected in ROLE_DEFAULTS.items():
                assert _matrix(sync_connection, scope, custom.id) == expected
            migration.downgrade()
            migration.upgrade()
            for scope, expected in ROLE_DEFAULTS.items():
                assert _matrix(sync_connection, scope, custom.id) == expected
        finally:
            migration.op = original_op

    await async_connection.run_sync(run)
