import re
from logging.config import fileConfig
from pathlib import Path
from typing import Any

import clickhouse_sqlalchemy
from clickhouse_sqlalchemy import Table, engines, types
from sqlalchemy import Column, MetaData, create_engine, func

from alembic import context
from alembic.ddl.impl import DefaultImpl
from infrastructure.models.clickhouse import ClickHouseBase
from infrastructure.settings import settings

# side-effect: registers the clickhouse dialect
_ = clickhouse_sqlalchemy


class ClickHouseAlembicImpl(DefaultImpl):
    """Minimal Alembic adapter compatible with the installed Alembic release.

    clickhouse-sqlalchemy 0.3.2 imports a private comparator removed in
    Alembic 1.18. Runtime migrations only need dialect registration and a
    MergeTree-backed version table; autogeneration remains intentionally
    disabled for ClickHouse engines.
    """

    __dialect__ = "clickhouse"
    transactional_ddl = False

    def version_table_impl(
        self,
        *,
        version_table: str,
        version_table_schema: str | None,
        version_table_pk: bool,
        **_kwargs: Any,
    ) -> Table:
        del version_table_pk
        metadata = MetaData()
        changed_at = Column("changed_at", types.DateTime, server_default=func.now())
        return Table(
            version_table,
            metadata,
            Column("version_num", types.String, nullable=False),
            changed_at,
            engines.ReplacingMergeTree(
                version=changed_at,
                order_by=func.tuple(),
            ),
            schema=version_table_schema,
        )

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ClickHouseBase.metadata

_NUM_RE = re.compile(r"^(\d+)")


def include_object(
    _object: Any,
    _name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: Any | None,
) -> bool:
    """Skip MATERIALIZED VIEW objects — they are managed separately."""
    return type_ != "materialized_view"


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
    url = settings.clickhouse_dsn
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transactional_ddl=False,
        include_object=include_object,
        process_revision_directives=_next_revision_id,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        settings.clickhouse_dsn,
        connect_args={"ch_settings": {"mutations_sync": "1"}},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transactional_ddl=False,
            include_object=include_object,
            process_revision_directives=_next_revision_id,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
