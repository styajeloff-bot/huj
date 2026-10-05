import importlib.util
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "109_storefront_public_ui.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_109", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def test_revision_109_backfills_defaults_and_round_trips(
    db_session: AsyncSession,
) -> None:
    migration = _load_migration()
    async_connection = await db_session.connection()

    def run(connection: Connection) -> None:
        operations = Operations(MigrationContext.configure(connection))
        original_op = migration.op
        migration.op = operations
        custom_id = uuid4()
        try:
            migration.downgrade()
            columns = {
                column["name"]
                for column in sa.inspect(connection).get_columns("catalog_storefronts")
            }
            assert "home_page_key" not in columns
            connection.execute(
                sa.text(
                    "INSERT INTO catalog_storefronts "
                    "(id, slug, is_default, is_active, version) "
                    "VALUES (:id, 'public-ui-migration', FALSE, TRUE, 1)"
                ),
                {"id": custom_id},
            )

            migration.upgrade()

            row = connection.execute(
                sa.text(
                    "SELECT home_page_key, public_page_titles, catalog_blocks, "
                    "public_ui_updated_by, public_ui_updated_at "
                    "FROM catalog_storefronts WHERE id = :id"
                ),
                {"id": custom_id},
            ).one()
            assert row.home_page_key == "home"
            assert row.public_page_titles == {
                "home": "Главная",
                "about": "О нас",
                "catalog": "Каталог",
                "models": "Модели",
                "special_equipment_catalog": "Спецтехника",
            }
            assert row.catalog_blocks == {
                "special_offers": {
                    "title": "Выбрать автомобиль по специальной цене",
                    "is_visible": True,
                },
                "all_vehicles": {
                    "title": "Выбрать автомобиль из каталога",
                    "is_visible": True,
                },
            }
            assert row.public_ui_updated_by is None
            assert row.public_ui_updated_at is not None

            nested = connection.begin_nested()
            try:
                with pytest.raises(IntegrityError):
                    connection.execute(
                        sa.text(
                            "UPDATE catalog_storefronts "
                            "SET home_page_key = 'unknown' WHERE id = :id"
                        ),
                        {"id": custom_id},
                    )
            finally:
                nested.rollback()

            constraints = {
                item["name"]
                for item in sa.inspect(connection).get_check_constraints(
                    "catalog_storefronts"
                )
            }
            assert {
                "ck_catalog_storefronts_home_page_key",
                "ck_catalog_storefronts_public_page_titles",
                "ck_catalog_storefronts_catalog_blocks",
            } <= constraints

            migration.downgrade()
            migration.upgrade()
        finally:
            migration.op = original_op

    await async_connection.run_sync(run)
