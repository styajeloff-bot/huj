"""Rollback-only 100k-row EXPLAIN harness for catalog task 21940.

The script deliberately does not use application tables. It creates an
isolated schema in one PostgreSQL transaction, mirrors the normalized
Mark -> Model -> Modification public read model, seeds deterministic data,
captures ``EXPLAIN`` JSON, and rolls the transaction back on every exit path.

Running the harness is guarded twice. The operator must pass the confirmation
value on the command line *and* through the environment.
"""
# ruff: noqa: S608

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from infrastructure.settings import settings  # noqa: E402

DISPOSABLE_CONFIRMATION = "carcraft-21940-catalog-performance"
DISPOSABLE_ENV = "CARCRAFT_SE_CATALOG_PERF_DISPOSABLE"
DEFAULT_ROWS = 100_000
PRODUCT_RELATION = "special_equipment_products"


@dataclass(frozen=True)
class ExplainCase:
    name: str
    sql: str
    parameters: Mapping[str, object]
    fail_on_product_seq_scan: bool = False
    required_indexes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExplainSummary:
    name: str
    execution_ms: float
    planning_ms: float
    actual_rows: int
    chosen_indexes: tuple[str, ...]
    node_types: tuple[str, ...]
    product_seq_scan: bool
    rows_removed_by_filter: int
    shared_hit_blocks: int
    shared_read_blocks: int
    temp_read_blocks: int
    temp_written_blocks: int
    sort_methods: tuple[str, ...]


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed an isolated rollback-only 100k catalog schema and capture "
            "PostgreSQL EXPLAIN JSON."
        )
    )
    parser.add_argument(
        "--confirm-disposable",
        required=True,
        help="Must exactly match the documented disposable E2E project name.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help="Deterministic product count; final acceptance uses exactly 100000.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional local JSON report path. The DSN is never written.",
    )
    return parser.parse_args(argv)


def _assert_disposable_confirmation(value: str) -> None:
    environment_value = os.getenv(DISPOSABLE_ENV)
    if value != DISPOSABLE_CONFIRMATION or environment_value != DISPOSABLE_CONFIRMATION:
        raise RuntimeError(
            "Refusing performance seed: both --confirm-disposable and "
            f"{DISPOSABLE_ENV} must equal {DISPOSABLE_CONFIRMATION!r}"
        )


def _walk_plan(node: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield node
    for child in node.get("Plans", ()):
        if isinstance(child, Mapping):
            yield from _walk_plan(child)


def summarize_explain(name: str, payload: object) -> ExplainSummary:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], Mapping):
        raise TypeError(f"Unexpected EXPLAIN JSON for {name}")
    document = payload[0]
    root = document.get("Plan")
    if not isinstance(root, Mapping):
        raise TypeError(f"EXPLAIN JSON has no Plan for {name}")

    nodes = tuple(_walk_plan(root))
    index_names = tuple(
        sorted(
            {
                str(node["Index Name"])
                for node in nodes
                if node.get("Index Name")
            }
        )
    )
    node_types = tuple(sorted({str(node.get("Node Type", "unknown")) for node in nodes}))
    product_seq_scan = any(
        node.get("Node Type") == "Seq Scan"
        and node.get("Relation Name") == PRODUCT_RELATION
        for node in nodes
    )
    sort_methods = tuple(
        sorted(
            {
                str(node["Sort Method"])
                for node in nodes
                if node.get("Sort Method")
            }
        )
    )

    def total(key: str) -> int:
        return sum(int(node.get(key, 0) or 0) for node in nodes)

    return ExplainSummary(
        name=name,
        execution_ms=float(document.get("Execution Time", 0.0) or 0.0),
        planning_ms=float(document.get("Planning Time", 0.0) or 0.0),
        actual_rows=int(root.get("Actual Rows", 0) or 0),
        chosen_indexes=index_names,
        node_types=node_types,
        product_seq_scan=product_seq_scan,
        rows_removed_by_filter=total("Rows Removed by Filter"),
        # PostgreSQL's root counters already include child nodes. Summing all
        # nodes would double-count buffers, while rows-removed is node-local.
        shared_hit_blocks=int(root.get("Shared Hit Blocks", 0) or 0),
        shared_read_blocks=int(root.get("Shared Read Blocks", 0) or 0),
        temp_read_blocks=int(root.get("Temp Read Blocks", 0) or 0),
        temp_written_blocks=int(root.get("Temp Written Blocks", 0) or 0),
        sort_methods=sort_methods,
    )


_BASE_SELECT = """
SELECT
    p.id,
    p.code,
    p.slug,
    p.modification_id,
    modification.name AS modification_name,
    model.id AS model_id,
    model.name AS model_name,
    mark.id AS mark_id,
    mark.name AS mark_name,
    p.seller_company_id,
    c.name AS seller_company_name,
    p.description,
    p.price,
    p.currency_code,
    p.manufacture_year,
    p.vin,
    p.no_vin,
    p.condition,
    p.owners_count,
    p.mileage_km,
    p.engine_hours,
    p.publication_status,
    p.sale_status,
    p.published_at,
    p.lock_version,
    p.updated_at
FROM special_equipment_products AS p
JOIN special_equipment_modifications AS modification
    ON modification.id = p.modification_id
JOIN special_equipment_models AS model ON model.id = modification.model_id
JOIN special_equipment_marks AS mark ON mark.id = model.mark_id
LEFT JOIN companies AS c ON c.id = p.seller_company_id
"""


def _attribute_text_search_predicate(parameter: str) -> str:
    return f"""
EXISTS (
    SELECT 1
    FROM special_equipment_modification_attribute_values AS attribute_value
    WHERE attribute_value.modification_id = p.modification_id
      AND attribute_value.attribute_id = CAST(:attribute_id AS uuid)
      AND lower(attribute_value.value_text)
          LIKE ('%' || lower(:{parameter}) || '%')
)
"""


def _count_query(where: str = "") -> str:
    return (
        "SELECT count(*) FROM ("
        + _BASE_SELECT
        + (f" WHERE {where}" if where else "")
        + ") AS registry_count"
    )


def _cases(rows: int) -> tuple[ExplainCase, ...]:
    model_id = "22000000-0000-0000-0000-000000000500"
    modification_id = "23000000-0000-0000-0000-000000005000"
    attribute_id = "24000000-0000-0000-0000-000000000001"
    exact_id = f"10000000-0000-0000-0000-{rows // 2:012d}"
    exact_vin = f"PERF{rows // 2:012d}"
    default_order = " ORDER BY p.published_at DESC, p.id DESC LIMIT 25"
    public = (
        "p.publication_status = 'published' "
        "AND p.sale_status IN ('available', 'on_order')"
    )
    available = (
        "p.publication_status = 'published' "
        "AND p.sale_status = 'available'"
    )
    on_order = (
        "p.publication_status = 'published' "
        "AND p.sale_status = 'on_order'"
    )
    model = public + " AND model.id = CAST(:model_id AS uuid)"
    modification = (
        public + " AND modification.id = CAST(:modification_id AS uuid)"
    )
    mark_name = public + " AND lower(mark.name) LIKE ('%' || lower(:q) || '%')"
    model_name = public + " AND lower(model.name) LIKE ('%' || lower(:q) || '%')"
    modification_name = (
        public
        + " AND lower(modification.name) LIKE ('%' || lower(:q) || '%')"
    )
    description_search = (
        public + " AND lower(p.description) LIKE ('%' || lower(:q) || '%')"
    )
    attribute_search = (
        public + " AND " + _attribute_text_search_predicate("attribute_search")
    )
    return (
        ExplainCase(
            "public_default_list",
            _BASE_SELECT + f" WHERE {public}" + default_order,
            {},
            fail_on_product_seq_scan=True,
            required_indexes=("idx_special_equipment_products_published",),
        ),
        ExplainCase("public_default_count", _count_query(public), {}),
        ExplainCase(
            "available_list",
            _BASE_SELECT + f" WHERE {available}" + default_order,
            {},
            fail_on_product_seq_scan=True,
        ),
        ExplainCase("available_count", _count_query(available), {}),
        ExplainCase(
            "on_order_list",
            _BASE_SELECT + f" WHERE {on_order}" + default_order,
            {},
            fail_on_product_seq_scan=True,
        ),
        ExplainCase("on_order_count", _count_query(on_order), {}),
        ExplainCase(
            "model_filter_list",
            _BASE_SELECT + f" WHERE {model}" + default_order,
            {"model_id": model_id},
            fail_on_product_seq_scan=True,
            required_indexes=(
                "idx_special_equipment_modifications_model",
                "idx_special_equipment_products_modification",
            ),
        ),
        ExplainCase(
            "model_filter_count",
            _count_query(model),
            {"model_id": model_id},
        ),
        ExplainCase(
            "modification_filter_list",
            _BASE_SELECT + f" WHERE {modification}" + default_order,
            {"modification_id": modification_id},
            fail_on_product_seq_scan=True,
            required_indexes=("idx_special_equipment_products_modification",),
        ),
        ExplainCase(
            "modification_filter_count",
            _count_query(modification),
            {"modification_id": modification_id},
        ),
        ExplainCase(
            "mark_name_search",
            _BASE_SELECT + f" WHERE {mark_name}" + default_order,
            {"q": "редкая марка 00500"},
            fail_on_product_seq_scan=True,
            required_indexes=("idx_se_marks_name_search",),
        ),
        ExplainCase(
            "mark_name_search_count",
            _count_query(mark_name),
            {"q": "редкая марка 00500"},
        ),
        ExplainCase(
            "model_name_search",
            _BASE_SELECT + f" WHERE {model_name}" + default_order,
            {"q": "редкая модель 0500"},
            fail_on_product_seq_scan=True,
            required_indexes=("idx_se_models_name_search",),
        ),
        ExplainCase(
            "model_name_search_count",
            _count_query(model_name),
            {"q": "редкая модель 0500"},
        ),
        ExplainCase(
            "modification_name_search",
            _BASE_SELECT + f" WHERE {modification_name}" + default_order,
            {"q": "редкая модификация 05000"},
            fail_on_product_seq_scan=True,
            required_indexes=("idx_se_modifications_name_search",),
        ),
        ExplainCase(
            "modification_name_search_count",
            _count_query(modification_name),
            {"q": "редкая модификация 05000"},
        ),
        ExplainCase(
            "product_description_search",
            _BASE_SELECT + f" WHERE {description_search}" + default_order,
            {"q": "гидромолота"},
            fail_on_product_seq_scan=True,
            required_indexes=("idx_se_products_description_search",),
        ),
        ExplainCase(
            "product_description_search_count",
            _count_query(description_search),
            {"q": "гидромолота"},
        ),
        ExplainCase(
            "attribute_text_search",
            _BASE_SELECT + f" WHERE {attribute_search}" + default_order,
            {
                "attribute_id": attribute_id,
                "attribute_search": "гидравлический",
            },
            fail_on_product_seq_scan=True,
            required_indexes=(
                "idx_se_modification_attribute_values_text_search",
            ),
        ),
        ExplainCase(
            "attribute_text_search_count",
            _count_query(attribute_search),
            {
                "attribute_id": attribute_id,
                "attribute_search": "гидравлический",
            },
        ),
        ExplainCase(
            "search_exact_uuid",
            _BASE_SELECT
            + f" WHERE {public} AND p.id = CAST(:q_uuid AS uuid)"
            + default_order,
            {"q_uuid": exact_id},
            fail_on_product_seq_scan=True,
            required_indexes=("special_equipment_products_pkey",),
        ),
        ExplainCase(
            "search_exact_uuid_count",
            _count_query(public + " AND p.id = CAST(:q_uuid AS uuid)"),
            {"q_uuid": exact_id},
            fail_on_product_seq_scan=True,
            required_indexes=("special_equipment_products_pkey",),
        ),
        ExplainCase(
            "search_exact_vin",
            _BASE_SELECT
            + f" WHERE {public} AND upper(p.vin) = upper(:q)"
            + default_order,
            {"q": exact_vin},
            fail_on_product_seq_scan=True,
            required_indexes=("uq_special_equipment_products_vin",),
        ),
        ExplainCase(
            "search_exact_vin_count",
            _count_query(public + " AND upper(p.vin) = upper(:q)"),
            {"q": exact_vin},
            fail_on_product_seq_scan=True,
            required_indexes=("uq_special_equipment_products_vin",),
        ),
        ExplainCase(
            "normalized_name_sort",
            _BASE_SELECT
            + f" WHERE {public} ORDER BY lower(mark.name), "
            "lower(model.name), lower(modification.name), p.id LIMIT 25",
            {},
        ),
        ExplainCase(
            "deep_offset",
            _BASE_SELECT
            + f" WHERE {public} ORDER BY p.published_at DESC, p.id DESC "
            "OFFSET 30000 LIMIT 25",
            {},
        ),
    )


async def _execute_batch(
    conn: AsyncConnection,
    sql: str,
    parameters: Mapping[str, object] | None = None,
) -> None:
    """Execute a trusted static SQL batch one statement at a time.

    asyncpg rejects multiple commands in one prepared statement.  These SQL
    literals are owned by the harness, so splitting terminal semicolons is
    safe and keeps every command in the surrounding rollback-only transaction.
    """

    for raw_statement in sql.split(";"):
        statement = raw_statement.strip()
        if statement:
            await conn.execute(sa.text(statement), dict(parameters or {}))


async def _create_schema(conn: AsyncConnection, schema: str) -> None:
    # ``schema`` is generated from uuid4().hex and therefore identifier-safe.
    await conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    await conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
    await conn.execute(sa.text("SET LOCAL statement_timeout = '180s'"))
    await conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    await conn.execute(
        sa.text(
            "SELECT pg_advisory_xact_lock(hashtext("
            "'carcraft-21940-special-equipment-catalog-performance'))"
        )
    )
    await _execute_batch(
        conn,
        """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE special_equipment_marks (
    id uuid PRIMARY KEY,
    code varchar(100) NOT NULL UNIQUE,
    name varchar(255) NOT NULL,
    slug varchar(255) NOT NULL UNIQUE
);
CREATE TABLE special_equipment_models (
    id uuid PRIMARY KEY,
    mark_id uuid NOT NULL REFERENCES special_equipment_marks(id),
    code varchar(100) NOT NULL UNIQUE,
    name varchar(255) NOT NULL,
    slug varchar(255) NOT NULL
);
CREATE TABLE special_equipment_modifications (
    id uuid PRIMARY KEY,
    model_id uuid NOT NULL REFERENCES special_equipment_models(id),
    code varchar(100) NOT NULL UNIQUE,
    name varchar(255) NOT NULL,
    slug varchar(255) NOT NULL
);
CREATE TABLE special_equipment_attributes (
    id uuid PRIMARY KEY,
    code varchar(100) NOT NULL UNIQUE,
    name varchar(255) NOT NULL
);
CREATE TABLE companies (
    id uuid PRIMARY KEY,
    name varchar(255) NOT NULL
);
CREATE TABLE special_equipment_products (
    id uuid PRIMARY KEY,
    code varchar(100) NOT NULL UNIQUE,
    slug varchar(255) NOT NULL UNIQUE,
    modification_id uuid NOT NULL REFERENCES special_equipment_modifications(id),
    seller_company_id uuid REFERENCES companies(id),
    description text,
    price numeric(15, 2),
    currency_code char(3) NOT NULL DEFAULT 'RUB',
    manufacture_year smallint,
    vin varchar(17),
    no_vin boolean NOT NULL DEFAULT false,
    condition varchar(10) NOT NULL,
    owners_count integer,
    mileage_km bigint,
    engine_hours bigint,
    publication_status varchar(20) NOT NULL,
    sale_status varchar(20) NOT NULL,
    published_at timestamptz,
    lock_version bigint NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL
);
CREATE TABLE special_equipment_modification_attribute_values (
    modification_id uuid NOT NULL
        REFERENCES special_equipment_modifications(id),
    attribute_id uuid NOT NULL REFERENCES special_equipment_attributes(id),
    value_text text,
    PRIMARY KEY (modification_id, attribute_id)
);

CREATE INDEX idx_special_equipment_models_mark
    ON special_equipment_models (mark_id, name, id);
CREATE INDEX idx_special_equipment_modifications_model
    ON special_equipment_modifications (model_id, name, id);
CREATE INDEX idx_special_equipment_products_modification
    ON special_equipment_products (modification_id, updated_at DESC, id DESC);
CREATE INDEX idx_special_equipment_products_published
    ON special_equipment_products (published_at DESC, id DESC)
    WHERE publication_status = 'published';
CREATE INDEX idx_se_products_public_availability
    ON special_equipment_products (sale_status, published_at DESC, id DESC)
    WHERE publication_status = 'published'
      AND sale_status IN ('available', 'on_order');
CREATE UNIQUE INDEX uq_special_equipment_products_vin
    ON special_equipment_products (upper(vin)) WHERE vin IS NOT NULL;
CREATE INDEX idx_se_marks_name_search
    ON special_equipment_marks USING gin (lower(name) gin_trgm_ops);
CREATE INDEX idx_se_models_name_search
    ON special_equipment_models USING gin (lower(name) gin_trgm_ops);
CREATE INDEX idx_se_modifications_name_search
    ON special_equipment_modifications USING gin (lower(name) gin_trgm_ops);
CREATE INDEX idx_se_products_description_search
    ON special_equipment_products USING gin (lower(description) gin_trgm_ops)
    WHERE description IS NOT NULL;
CREATE INDEX idx_se_modification_attribute_values_text_search
    ON special_equipment_modification_attribute_values
    USING gin (lower(value_text) gin_trgm_ops)
    WHERE value_text IS NOT NULL;
""",
    )


async def _seed(conn: AsyncConnection, rows: int) -> None:
    await _execute_batch(
        conn,
        """
INSERT INTO special_equipment_marks (id, code, name, slug)
SELECT
    ('21000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    'mark-' || lpad(series::text, 5, '0'),
    CASE WHEN series = 500 THEN 'Редкая марка 00500'
        ELSE 'Марка ' || lpad(series::text, 5, '0') END,
    'perf-mark-' || lpad(series::text, 5, '0')
FROM generate_series(1, :mark_rows) AS series;

INSERT INTO special_equipment_models (id, mark_id, code, name, slug)
SELECT
    ('22000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    ('21000000-0000-0000-0000-' ||
        lpad(((series - 1) % :mark_rows + 1)::text, 12, '0'))::uuid,
    'model-' || lpad(series::text, 6, '0'),
    CASE WHEN series = 500 THEN 'Редкая модель 0500'
        ELSE 'Модель ' || lpad(series::text, 6, '0') END,
    'perf-model-' || lpad(series::text, 6, '0')
FROM generate_series(1, :rows) AS series;

INSERT INTO special_equipment_modifications (id, model_id, code, name, slug)
SELECT
    ('23000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    ('22000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    'modification-' || lpad(series::text, 6, '0'),
    CASE WHEN series = 5000 THEN 'Редкая модификация 05000'
        ELSE 'Модификация ' || lpad(series::text, 6, '0') END,
    'perf-modification-' || lpad(series::text, 6, '0')
FROM generate_series(1, :rows) AS series;

INSERT INTO special_equipment_attributes (id, code, name)
VALUES (
    '24000000-0000-0000-0000-000000000001'::uuid,
    'benchmark_text',
    'Текстовая характеристика'
);

INSERT INTO companies (id, name)
SELECT
    ('30000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    'Продавец ' || lpad(series::text, 2, '0')
FROM generate_series(1, 10) AS series;
""",
        {"rows": rows, "mark_rows": rows // 5},
    )
    await _execute_batch(
        conn,
        """
INSERT INTO special_equipment_products (
    id, code, slug, modification_id, seller_company_id, description,
    price, currency_code, manufacture_year, vin, no_vin, condition,
    owners_count, mileage_km, engine_hours, publication_status, sale_status,
    published_at, lock_version, updated_at
)
SELECT
    ('10000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    'equipment-' || lpad(series::text, 6, '0'),
    'equipment-' || lpad(series::text, 6, '0'),
    ('23000000-0000-0000-0000-' ||
        lpad(series::text, 12, '0'))::uuid,
    ('30000000-0000-0000-0000-' || lpad(((series - 1) % 10 + 1)::text, 12, '0'))::uuid,
    CASE WHEN series = 75000
        THEN 'Редкое описание гидромолота'
        ELSE 'Детерминированная запись performance harness ' || series END,
    ((series % 50000000) + 100000)::numeric(15, 2),
    'RUB',
    (2000 + series % 27)::smallint,
    'PERF' || lpad(series::text, 12, '0'),
    false,
    'used',
    1,
    series * 10,
    NULL,
    CASE
        WHEN series % 10 < 8 THEN 'published'
        WHEN series % 10 < 9 THEN 'draft'
        ELSE 'archived'
    END,
    CASE series % 5
        WHEN 0 THEN 'available'
        WHEN 1 THEN 'on_order'
        WHEN 2 THEN 'reserved'
        WHEN 3 THEN 'sold'
        ELSE 'unavailable'
    END,
    CASE WHEN series % 10 < 8
        THEN timestamptz '2026-01-01 00:00:00+00' + series * interval '1 second'
        ELSE NULL
    END,
    1,
    timestamptz '2026-01-01 00:00:00+00' + series * interval '1 second'
FROM generate_series(1, :rows) AS series;

INSERT INTO special_equipment_modification_attribute_values (
    modification_id, attribute_id, value_text
)
SELECT
    ('23000000-0000-0000-0000-' || lpad(series::text, 12, '0'))::uuid,
    '24000000-0000-0000-0000-000000000001'::uuid,
    CASE WHEN series % 2500 = 0
        THEN 'Редкий гидравлический поиск ' || series
        ELSE 'Стандартная характеристика ' || series END
FROM generate_series(1, :rows) AS series;
""",
        {"rows": rows},
    )
    seeded_products = int(
        await conn.scalar(sa.text("SELECT count(*) FROM special_equipment_products"))
        or 0
    )
    seeded_values = int(
        await conn.scalar(
            sa.text(
                "SELECT count(*) FROM "
                "special_equipment_modification_attribute_values"
            )
        )
        or 0
    )
    if seeded_products != rows or seeded_values != rows:
        raise RuntimeError("Deterministic performance seed count mismatch")
    await _execute_batch(
        conn,
        """
ANALYZE special_equipment_marks;
ANALYZE special_equipment_models;
ANALYZE special_equipment_modifications;
ANALYZE special_equipment_attributes;
ANALYZE companies;
ANALYZE special_equipment_products;
ANALYZE special_equipment_modification_attribute_values;
""",
    )


async def _explain(conn: AsyncConnection, case: ExplainCase) -> ExplainSummary:
    statement = sa.text(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, TIMING OFF, SUMMARY ON) "
        + case.sql
    )
    payload = (await conn.execute(statement, dict(case.parameters))).scalar_one()
    return summarize_explain(case.name, payload)


def _violations(
    cases: Sequence[ExplainCase], summaries: Sequence[ExplainSummary]
) -> list[str]:
    by_name = {summary.name: summary for summary in summaries}
    failures: list[str] = []
    for case in cases:
        summary = by_name[case.name]
        if case.fail_on_product_seq_scan and summary.product_seq_scan:
            failures.append(f"{case.name}: Seq Scan on {PRODUCT_RELATION}")
        missing = set(case.required_indexes) - set(summary.chosen_indexes)
        if missing:
            failures.append(
                f"{case.name}: required index not chosen: {', '.join(sorted(missing))}"
            )
    return failures


async def _run(args: argparse.Namespace) -> dict[str, object]:
    _assert_disposable_confirmation(args.confirm_disposable)
    if args.rows != DEFAULT_ROWS:
        raise RuntimeError(
            f"Final performance contract requires exactly {DEFAULT_ROWS} rows"
        )

    engine = create_async_engine(
        settings.database_dsn,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "server_settings": {"application_name": "se_catalog_perf_21940"}
        },
    )
    schema = f"se_registry_perf_{uuid4().hex}"
    transaction = None
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                await _create_schema(conn, schema)
                await _seed(conn, args.rows)
                cases = _cases(args.rows)
                summaries = [await _explain(conn, case) for case in cases]
                failures = _violations(cases, summaries)
                report: dict[str, object] = {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "rows": args.rows,
                    "rolled_back": True,
                    "cases": [asdict(summary) for summary in summaries],
                    "failures": failures,
                }
            finally:
                await transaction.rollback()
                transaction = None
    finally:
        if transaction is not None:
            await transaction.rollback()
        await engine.dispose()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    try:
        report = asyncio.run(_run(args))
    except Exception as exc:
        # Connection exceptions may contain host/database metadata.  Keep
        # stdout/stderr suitable for redacted E2E evidence by exposing only
        # the exception class; operators inspect container logs locally.
        sys.stderr.write(
            f"performance harness failed safely: {type(exc).__name__}\n"
        )
        return 2

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
