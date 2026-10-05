import importlib.util
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.models.applications import ShoppingCart
from infrastructure.models.section_visibility import SectionVisibility
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User
from tests.legacy_compat import Vehicle

MIGRATION_101_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "101_catalog_storefronts.py"
)
MIGRATION_102_PATH = MIGRATION_101_PATH.with_name(
    "102_storefront_section_visibility.py"
)
MIGRATION_103_PATH = MIGRATION_101_PATH.with_name(
    "103_storefront_role_section_visibility.py"
)


def _load_migration(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    migration: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def test_revision_101_round_trip_collapses_cross_storefront_duplicates(
    db_session: AsyncSession,
    employee_user: User,
    test_vehicle: Vehicle,
) -> None:
    custom = Storefront(
        slug="migration-child", is_default=False, is_active=True, version=1
    )
    db_session.add(custom)
    await db_session.flush()
    db_session.add_all(
        [
            ShoppingCart(
                user_id=employee_user.id,
                storefront_id=DEFAULT_STOREFRONT_ID,
                vehicle_id=test_vehicle.id,
            ),
            ShoppingCart(
                user_id=employee_user.id,
                storefront_id=custom.id,
                vehicle_id=test_vehicle.id,
            ),
        ]
    )
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
                storefront_id=custom.id,
                section_key="models",
                is_visible=False,
                updated_by=employee_user.id,
            ),
        ]
    )
    await db_session.flush()

    migration_101 = _load_migration(MIGRATION_101_PATH, "migration_101")
    migration_102 = _load_migration(MIGRATION_102_PATH, "migration_102")
    migration_103 = _load_migration(MIGRATION_103_PATH, "migration_103")
    async_connection = await db_session.connection()

    def _round_trip(sync_connection: Connection) -> None:
        operations = Operations(MigrationContext.configure(sync_connection))
        original_op_101 = migration_101.op
        original_op_102 = migration_102.op
        original_op_103 = migration_103.op
        migration_101.op = operations
        migration_102.op = operations
        migration_103.op = operations
        try:
            migration_103.downgrade()
            migration_102.downgrade()
            migration_101.downgrade()
            assert (
                sync_connection.scalar(sa.text("SELECT count(*) FROM shopping_cart"))
                == 1
            )
            inspector = sa.inspect(sync_connection)
            assert not inspector.has_table("catalog_storefronts")
            assert "storefront_id" not in {
                column["name"]
                for column in inspector.get_columns("section_visibility")
            }

            migration_101.upgrade()
            sync_connection.execute(
                sa.text(
                    "INSERT INTO catalog_storefronts "
                    "(id, slug, is_default, is_active, version) "
                    "VALUES (CAST(:id AS uuid), :slug, FALSE, TRUE, 1)"
                ),
                {"id": str(custom.id), "slug": "migration-restored-child"},
            )
            migration_102.upgrade()

            assert (
                sync_connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM catalog_storefronts "
                        "WHERE id = CAST(:default_id AS uuid)"
                    ),
                    {"default_id": str(DEFAULT_STOREFRONT_ID)},
                )
                == 1
            )
            assert sync_connection.scalar(
                sa.text(
                    "SELECT storefront_id FROM shopping_cart"
                )
            ) == DEFAULT_STOREFRONT_ID

            custom_rows = sync_connection.execute(
                sa.text(
                    "SELECT section_key, is_visible FROM section_visibility "
                    "WHERE scope = 'public' "
                    "AND storefront_id = CAST(:storefront_id AS uuid)"
                ),
                {"storefront_id": str(custom.id)},
            ).all()
            assert {
                str(row[0]): bool(row[1])
                for row in custom_rows
            } == {
                "about": True,
                "catalog": True,
                "models": True,
                "special_equipment_catalog": False,
            }

            migration_103.upgrade()

            current_inspector = sa.inspect(sync_connection)
            assert "storefront_id" in {
                column["name"]
                for column in current_inspector.get_columns(
                    "section_visibility"
                )
            }
            assert {
                "uq_section_visibility_storefront_scope_section",
                "uq_section_visibility_global_scope_section",
            } <= {
                index["name"]
                for index in current_inspector.get_indexes(
                    "section_visibility"
                )
            }
            assert "ck_section_visibility_storefront_target" in {
                constraint["name"]
                for constraint in current_inspector.get_check_constraints(
                    "section_visibility"
                )
            }
            assert "fk_section_visibility_storefront_id" in {
                foreign_key["name"]
                for foreign_key in current_inspector.get_foreign_keys(
                    "section_visibility"
                )
            }
        finally:
            migration_101.op = original_op_101
            migration_102.op = original_op_102
            migration_103.op = original_op_103

    await async_connection.run_sync(_round_trip)
