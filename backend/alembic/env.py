import asyncio
import re
from logging.config import fileConfig
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from infrastructure.models import (
    Base,
    accounting,
    accounting_metadata,
    accounting_normalized,
    applications,
    catalog,
    catalog_import_jobs,
    companies,
    compensations,
    documents,
    email_preferences,
    exchange,
    lca_status_history,
    misc,
    notification_delivery,
    payments,
    positions,
    section_visibility,
    signature_requests,
    sopd_cache,
    special_equipment,
    special_equipment_commerce,
    special_equipment_import,
    special_equipment_registry,
    support,
    user_company_access,
    users,
    vehicles,
)
from infrastructure.settings import settings

# Ensure all model modules are imported so Alembic autogenerate can discover tables.
_MODEL_MODULES = [
    accounting,
    accounting_metadata,
    accounting_normalized,
    applications,
    catalog,
    catalog_import_jobs,
    companies,
    compensations,
    documents,
    email_preferences,
    exchange,
    lca_status_history,
    misc,
    notification_delivery,
    payments,
    positions,
    signature_requests,
    special_equipment,
    special_equipment_commerce,
    special_equipment_import,
    special_equipment_registry,
    sopd_cache,
    support,
    users,
    user_company_access,
    vehicles,
    section_visibility,
]

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_NUM_RE = re.compile(r"^(\d+)")
_UUID_REQUIRED_COLUMNS = (
    ("companies", "id"),
    ("users", "id"),
    ("users", "company_id"),
    ("vehicles", "id"),
    ("vehicles", "dealer_id"),
    ("support_programs", "id"),
    ("distributors", "id"),
    ("compensations", "id"),
    ("compensations", "applied_support_id"),
)


def _next_revision_id(
    _context: object,
    _revision: object,
    directives: list,
) -> None:
    """Auto-assign sequential numeric revision IDs (003, 004, …)."""
    if not directives:
        return
    script = directives[0]
    versions_dir = Path(__file__).resolve().parent / "versions"
    max_num = 0
    for f in versions_dir.glob("*.py"):
        m = _NUM_RE.match(f.stem)
        if m:
            max_num = max(max_num, int(m.group(1)))
    script.rev_id = str(max_num + 1).zfill(3)


def run_migrations_offline() -> None:
    url = settings.database_dsn
    context.configure(
        url=url,
        target_metadata=target_metadata,
        compare_server_default=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=_next_revision_id,
    )
    with context.begin_transaction():
        context.run_migrations()


def _find_legacy_non_uuid_columns(connection: sa.engine.Connection) -> list[str]:
    mismatches: list[str] = []
    for table_name, column_name in _UUID_REQUIRED_COLUMNS:
        row = (
            connection.execute(
                sa.text(
                    """
                    SELECT udt_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            )
            .mappings()
            .one_or_none()
        )
        if row is not None and row["udt_name"] != "uuid":
            mismatches.append(f"{table_name}.{column_name}={row['udt_name']}")
    return mismatches


def _reset_legacy_non_uuid_schema(connection: sa.engine.Connection) -> None:
    mismatches = _find_legacy_non_uuid_columns(connection)
    if not mismatches:
        return

    print(  # noqa: T201
        "Detected legacy non-UUID PostgreSQL schema; dropping public schema "
        f"before Alembic upgrade: {', '.join(mismatches)}"
    )
    connection.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
    connection.execute(sa.text("CREATE SCHEMA public"))
    connection.execute(sa.text("SET search_path TO public"))
    connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))


def do_run_migrations(connection: sa.engine.Connection) -> None:
    _reset_legacy_non_uuid_schema(connection)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_server_default=True,
        process_revision_directives=_next_revision_id,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_dsn, poolclass=pool.NullPool)
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
