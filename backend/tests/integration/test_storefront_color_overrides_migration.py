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
    Path(__file__).resolve().parents[2] / "alembic" / "versions"
    / "114_storefront_color_overrides.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("migration_114", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def test_color_overrides_migration_preserves_existing_appearance(
    db_session: AsyncSession,
) -> None:
    migration = _load_migration()
    assert migration.down_revision == "113"
    connection = await db_session.connection()

    def run(sync: Connection) -> None:
        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(sync))
        storefront_id, font_id = uuid4(), uuid4()
        try:
            migration.downgrade()
            sync.execute(sa.text(
                "INSERT INTO catalog_storefront_fonts "
                "(id, name, original_filename, storage_key, size_bytes, checksum_sha256) "
                "VALUES (:id, 'Migration Font', 'font.ttf', 'font.woff2', 12, :checksum)"
            ), {"id": font_id, "checksum": "a" * 64})
            sync.execute(sa.text(
                "INSERT INTO catalog_storefronts "
                "(id, slug, is_default, is_active, version, appearance_primary_color, "
                "appearance_background_color, appearance_surface_color, "
                "appearance_text_color, appearance_border_radius, font_id) "
                "VALUES (:id, 'theme-migration', FALSE, TRUE, 7, '#AABBCC', '#102030', "
                "'#AABBCC', '#405060', 'none', :font_id)"
            ), {"id": storefront_id, "font_id": font_id})
            migration.upgrade()
            row = sync.execute(sa.text(
                "SELECT version, appearance_primary_color, appearance_background_color, "
                "appearance_surface_color, appearance_text_color, "
                "appearance_border_radius, font_id, appearance_color_overrides "
                "FROM catalog_storefronts WHERE id = :id"
            ), {"id": storefront_id}).one()
            assert tuple(row) == (
                7, "#AABBCC", "#102030", "#AABBCC", "#405060", "none", font_id, {},
            )
            with sync.begin_nested() as nested:
                with pytest.raises(IntegrityError):
                    sync.execute(sa.text(
                        "UPDATE catalog_storefronts SET appearance_color_overrides = '[]' "
                        "WHERE id = :id"
                    ), {"id": storefront_id})
                nested.rollback()
            migration.downgrade()
            migration.upgrade()
        finally:
            migration.op = original_op

    await connection.run_sync(run)
