"""Deterministic ClickHouse backfill for distributor analytics data marts."""
# ruff: noqa: S608

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FASTAPI_ROOT = Path(__file__).resolve().parents[1]
if str(FASTAPI_ROOT) not in sys.path:
    sys.path.insert(0, str(FASTAPI_ROOT))

from infrastructure.clickhouse import get_clickhouse_client  # noqa: E402
from infrastructure.clickhouse_dwh import ensure_dwh_tables  # noqa: E402

DISTRIBUTOR_MARTS = (
    "dm_distributor_warehouse",
    "dm_distributor_applications",
    "dm_distributor_financials",
    "dm_distributor_exchange",
    "dm_distributor_sales_dc",
    "dm_distributor_sales_dc_regions",
)


@dataclass(frozen=True, slots=True)
class MartBackfill:
    columns: tuple[str, ...]
    select_sql: str


WAREHOUSE_COLUMNS = (
    "vehicle_id",
    "vin",
    "dealer_id",
    "dealer_name",
    "dealer_city",
    "mark_id",
    "model_id",
    "generation_id",
    "configuration_id",
    "complectation_id",
    "year",
    "base_price",
    "special_price",
    "dealer_cost",
    "discount_price",
    "color",
    "color_inter",
    "status",
    "is_available",
    "created_at",
    "updated_at",
)

APPLICATIONS_COLUMNS = (
    "lca_id",
    "application_id",
    "leasing_company_id",
    "dealer_company_id",
    "client_company_id",
    "vehicle_id",
    "display_number",
    "dealer_name",
    "dealer_city",
    "leasing_company_name",
    "mark_name",
    "model_name",
    "vehicle_mark_id",
    "vehicle_model_id",
    "application_status",
    "lca_status",
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
    "vehicle_price",
    "review_notes",
    "decision_comment",
    "submitted_at",
    "created_at",
    "updated_at",
)

FINANCIALS_COLUMNS = (
    "date",
    "dealer_company_id",
    "dealer_name",
    "dealer_city",
    "leasing_company_name",
    "kind",
    "application_count",
    "pipeline_amount",
    "approved_amount",
    "issued_amount",
    "total_down_payment",
    "total_down_payment_count",
    "down_payment_percent_sum",
    "down_payment_percent_count",
    "lease_term_months_sum",
    "lease_term_months_count",
    "rate_sum",
    "rate_count",
    "markup_sum",
    "markup_count",
    "updated_at",
)

EXCHANGE_COLUMNS = (
    "request_id",
    "lc_user_id",
    "vehicle_id",
    "requested_dealer_id",
    "requested_dealer_name",
    "requested_dealer_city",
    "mark",
    "model",
    "quantity",
    "expiration_date",
    "discount_type",
    "discount_value",
    "file_url",
    "file_name",
    "request_status",
    "accepted_bid_id",
    "batch_number",
    "batch_index",
    "bids_count",
    "accepted_bids",
    "average_price",
    "created_at",
    "updated_at",
)

SALES_DC_COLUMNS = (
    "lca_id",
    "application_id",
    "leasing_company_id",
    "display_number",
    "dealer_company_id",
    "client_company_id",
    "vehicle_id",
    "vehicle_price",
    "dealer_name",
    "dealer_city",
    "leasing_company_name",
    "mark_name",
    "model_name",
    "vehicle_mark_id",
    "vehicle_model_id",
    "status",
    "lca_status",
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
    "client_decision_action",
    "client_decision_at",
    "kind",
    "created_at",
    "updated_at",
)

SALES_DC_REGIONS_COLUMNS = (
    "application_id",
    "application_vehicle_id",
    "vehicle_id",
    "leasing_company_id",
    "dealer_id",
    "dealer_name",
    "dealer_city",
    "dealer_region",
    "mark_id",
    "model_id",
    "vin",
    "quantity",
    "unit_price",
    "total_price",
    "year",
    "base_price",
    "special_price",
    "discount_price",
    "color",
    "application_status",
    "lca_status",
    "application_total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "is_model_order",
    "created_at",
    "updated_at",
)

APPROVED_LCA_STATUSES = (
    "'approved_scoring'",
    "'approved_scoring_another_cond'",
    "'approved_final'",
    "'approved_final_another_cond'",
    "'selected_lc'",
    "'deal'",
)
APPROVED_LCA_STATUS_SQL = ", ".join(APPROVED_LCA_STATUSES)

MART_BACKFILLS: dict[str, MartBackfill] = {
    "dm_distributor_warehouse": MartBackfill(
        columns=WAREHOUSE_COLUMNS,
        select_sql="""
SELECT
    v.vehicle_id,
    v.vin,
    v.dealer_id,
    c.name AS dealer_name,
    c.city AS dealer_city,
    v.mark_id,
    v.model_id,
    v.generation_id,
    v.configuration_id,
    v.complectation_id,
    v.year,
    v.base_price,
    v.special_price,
    v.dealer_cost,
    v.discount_price,
    v.color,
    v.color_inter,
    v.status,
    v.is_available,
    v.created_at,
    v.updated_at
FROM dwh_vehicles AS v FINAL
LEFT JOIN dwh_companies AS c FINAL ON v.dealer_id = c.company_id AND c._deleted = 0
WHERE v._deleted = 0
""".strip(),
    ),
    "dm_distributor_applications": MartBackfill(
        columns=APPLICATIONS_COLUMNS,
        select_sql="""
SELECT
    a.lca_id,
    a.application_id,
    a.leasing_company_id,
    a.dealer_company_id,
    a.client_company_id,
    coalesce(a.vehicle_id, v.vehicle_id) AS vehicle_id,
    a.display_number,
    coalesce(nullIf(a.dealer_name, ''), c.name) AS dealer_name,
    coalesce(nullIf(a.dealer_city, ''), c.city) AS dealer_city,
    a.leasing_company_name,
    coalesce(a.mark_name, v.mark_id) AS mark_name,
    coalesce(a.model_name, v.model_id) AS model_name,
    coalesce(a.vehicle_mark_id, v.mark_id) AS vehicle_mark_id,
    coalesce(a.vehicle_model_id, v.model_id) AS vehicle_model_id,
    a.application_status,
    a.status AS lca_status,
    a.total_amount,
    a.down_payment,
    a.down_payment_percent,
    a.lease_term_months,
    a.monthly_payment,
    a.total_cost,
    a.markup,
    a.rate,
    a.total_interest,
    a.buyout_amount,
    a.vat_refund,
    a.profit_tax_savings,
    a.total_savings,
    CAST(coalesce(v.special_price, v.discount_price, v.base_price), 'Nullable(Decimal(15,2))') AS vehicle_price,
    a.review_notes,
    a.decision_comment,
    a.submitted_at,
    a.created_at,
    a.updated_at
FROM dwh_leasing_company_applications AS a FINAL
LEFT JOIN dwh_vehicles AS v FINAL
    ON a.vehicle_id = v.vehicle_id AND v._deleted = 0
LEFT JOIN dwh_companies AS c FINAL
    ON coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) = c.company_id AND c._deleted = 0
WHERE a._deleted = 0
""".strip(),
    ),
    "dm_distributor_financials": MartBackfill(
        columns=FINANCIALS_COLUMNS,
        select_sql=f"""
SELECT
    toDate(coalesce(a.submitted_at, a.created_at, a.updated_at)) AS date,
    a.dealer_company_id,
    coalesce(nullIf(a.dealer_name, ''), c.name) AS dealer_name,
    coalesce(nullIf(a.dealer_city, ''), c.city) AS dealer_city,
    a.leasing_company_name,
    a.status AS kind,
    count() AS application_count,
    sum(cast(ifNull(a.total_amount, toDecimal64(0, 2)), 'Decimal(18,2)')) AS pipeline_amount,
    sumIf(
        cast(ifNull(a.total_amount, toDecimal64(0, 2)), 'Decimal(18,2)'),
        a.status IN ({APPROVED_LCA_STATUS_SQL})
    ) AS approved_amount,
    sumIf(
        cast(ifNull(a.total_amount, toDecimal64(0, 2)), 'Decimal(18,2)'),
        a.status = 'deal'
    ) AS issued_amount,
    sum(cast(ifNull(a.down_payment, toDecimal64(0, 2)), 'Decimal(18,2)')) AS total_down_payment,
    countIf(a.down_payment IS NOT NULL) AS total_down_payment_count,
    sum(cast(ifNull(a.down_payment_percent, toDecimal64(0, 2)), 'Decimal(18,4)')) AS down_payment_percent_sum,
    countIf(a.down_payment_percent IS NOT NULL) AS down_payment_percent_count,
    toUInt64(sum(ifNull(a.lease_term_months, 0))) AS lease_term_months_sum,
    countIf(a.lease_term_months IS NOT NULL) AS lease_term_months_count,
    sum(cast(ifNull(a.rate, toDecimal64(0, 2)), 'Decimal(18,4)')) AS rate_sum,
    countIf(a.rate IS NOT NULL) AS rate_count,
    sum(cast(ifNull(a.markup, toDecimal64(0, 2)), 'Decimal(18,4)')) AS markup_sum,
    countIf(a.markup IS NOT NULL) AS markup_count,
    max(a.updated_at) AS updated_at
FROM dwh_leasing_company_applications AS a FINAL
LEFT JOIN dwh_companies AS c FINAL
    ON a.dealer_company_id = c.company_id AND c._deleted = 0
WHERE a._deleted = 0
  AND coalesce(a.submitted_at, a.created_at, a.updated_at) IS NOT NULL
GROUP BY
    date,
    a.dealer_company_id,
    dealer_name,
    dealer_city,
    a.leasing_company_name,
    kind
""".strip(),
    ),
    "dm_distributor_exchange": MartBackfill(
        columns=EXCHANGE_COLUMNS,
        select_sql="""
SELECT
    r.request_id,
    r.lc_user_id,
    r.vehicle_id,
    v.dealer_id AS requested_dealer_id,
    c.name AS requested_dealer_name,
    c.city AS requested_dealer_city,
    v.mark_id AS mark,
    v.model_id AS model,
    r.quantity,
    (r.expiration_at AT TIME ZONE 'Europe/Moscow')::date AS expiration_date,
    r.discount_type,
    r.discount_value,
    r.file_url,
    r.file_name,
    r.status AS request_status,
    r.accepted_bid_id,
    r.batch_number,
    r.batch_index,
    ifNull(ba.bids_count, 0) AS bids_count,
    ifNull(ba.accepted_bids, 0) AS accepted_bids,
    CAST(ba.average_price, 'Nullable(Decimal(15,2))') AS average_price,
    r.created_at,
    greatest(r.updated_at, ifNull(ba.updated_at, r.updated_at)) AS updated_at
FROM dwh_exchange_requests AS r FINAL
LEFT JOIN dwh_vehicles AS v FINAL
    ON r.vehicle_id = v.vehicle_id AND v._deleted = 0
LEFT JOIN dwh_companies AS c FINAL
    ON v.dealer_id = c.company_id AND c._deleted = 0
LEFT JOIN (
    SELECT
        request_id,
        count() AS bids_count,
        countIf(is_accepted = 1) AS accepted_bids,
        avg(price) AS average_price,
        max(updated_at) AS updated_at
    FROM dwh_exchange_bids FINAL
    WHERE _deleted = 0
    GROUP BY request_id
) AS ba ON r.request_id = ba.request_id
WHERE r._deleted = 0
""".strip(),
    ),
    "dm_distributor_sales_dc": MartBackfill(
        columns=SALES_DC_COLUMNS,
        select_sql="""
SELECT
    a.lca_id,
    a.application_id,
    a.leasing_company_id,
    a.display_number,
    a.dealer_company_id,
    a.client_company_id,
    coalesce(a.vehicle_id, v.vehicle_id) AS vehicle_id,
    CAST(coalesce(v.special_price, v.discount_price, v.base_price), 'Nullable(Decimal(15,2))') AS vehicle_price,
    coalesce(nullIf(a.dealer_name, ''), c.name) AS dealer_name,
    coalesce(nullIf(a.dealer_city, ''), c.city) AS dealer_city,
    a.leasing_company_name,
    coalesce(a.mark_name, v.mark_id) AS mark_name,
    coalesce(a.model_name, v.model_id) AS model_name,
    coalesce(a.vehicle_mark_id, v.mark_id) AS vehicle_mark_id,
    coalesce(a.vehicle_model_id, v.model_id) AS vehicle_model_id,
    a.application_status AS status,
    a.status AS lca_status,
    a.total_amount,
    a.down_payment,
    a.down_payment_percent,
    a.lease_term_months,
    a.monthly_payment,
    a.total_cost,
    a.markup,
    a.rate,
    a.total_interest,
    a.buyout_amount,
    a.vat_refund,
    a.profit_tax_savings,
    a.total_savings,
    CAST(NULL, 'Nullable(String)') AS client_decision_action,
    CAST(NULL, 'Nullable(DateTime64(3))') AS client_decision_at,
    a.status AS kind,
    a.created_at,
    a.updated_at
FROM dwh_leasing_company_applications AS a FINAL
LEFT JOIN dwh_vehicles AS v FINAL
    ON a.vehicle_id = v.vehicle_id AND v._deleted = 0
LEFT JOIN dwh_companies AS c FINAL
    ON coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) = c.company_id AND c._deleted = 0
WHERE a._deleted = 0
  AND a.application_id IS NOT NULL
""".strip(),
    ),
    "dm_distributor_sales_dc_regions": MartBackfill(
        columns=SALES_DC_REGIONS_COLUMNS,
        select_sql="""
SELECT
    av.application_id,
    av.id AS application_vehicle_id,
    av.vehicle_id,
    a.leasing_company_id,
    coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) AS dealer_id,
    coalesce(nullIf(a.dealer_name, ''), c.name) AS dealer_name,
    coalesce(nullIf(a.dealer_city, ''), c.city) AS dealer_city,
    c.region AS dealer_region,
    coalesce(a.vehicle_mark_id, v.mark_id) AS mark_id,
    coalesce(a.vehicle_model_id, v.model_id) AS model_id,
    coalesce(av.vin, v.vin) AS vin,
    av.quantity,
    av.unit_price,
    av.total_price,
    v.year,
    v.base_price,
    v.special_price,
    v.discount_price,
    v.color,
    a.application_status,
    a.status AS lca_status,
    a.total_amount AS application_total_amount,
    a.down_payment,
    a.down_payment_percent,
    a.lease_term_months,
    a.monthly_payment,
    av.is_model_order,
    coalesce(av.created_at, a.created_at, v.created_at) AS created_at,
    greatest(
        av.updated_at,
        ifNull(a.updated_at, av.updated_at),
        ifNull(v.updated_at, av.updated_at)
    ) AS updated_at
FROM dwh_application_vehicles AS av FINAL
LEFT JOIN dwh_vehicles AS v FINAL
    ON av.vehicle_id = v.vehicle_id AND v._deleted = 0
LEFT JOIN dwh_leasing_company_applications AS a FINAL
    ON av.application_id = a.application_id AND a._deleted = 0
LEFT JOIN dwh_companies AS c FINAL
    ON coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) = c.company_id AND c._deleted = 0
WHERE av._deleted = 0
""".strip(),
    ),
}


def build_truncate_sql(mart: str) -> str:
    _get_backfill(mart)
    return f"TRUNCATE TABLE {mart}"


def build_insert_sql(mart: str) -> str:
    backfill = _get_backfill(mart)
    columns = ", ".join(backfill.columns)
    return f"INSERT INTO {mart} ({columns})\n{backfill.select_sql}"


def build_backfill_statements() -> list[str]:
    statements: list[str] = []
    for mart in DISTRIBUTOR_MARTS:
        statements.append(build_truncate_sql(mart))
        statements.append(build_insert_sql(mart))
    return statements


def run_backfill(client: Any) -> dict[str, int]:
    ensure_dwh_tables(client)

    row_counts: dict[str, int] = {}
    insert_settings = {"max_partitions_per_insert_block": 10000}
    for mart in DISTRIBUTOR_MARTS:
        client.query(build_truncate_sql(mart))
        client.query(build_insert_sql(mart), settings=insert_settings)
        row_counts[mart] = _read_count(client, mart)
        print(f"{mart}: {row_counts[mart]} rows")  # noqa: T201
    return row_counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Truncate and rebuild dm_distributor_* ClickHouse marts."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive TRUNCATE TABLE operations before backfill.",
    )
    args = parser.parse_args(argv)
    if not args.yes:
        parser.error("refusing to truncate distributor marts without --yes")

    client = get_clickhouse_client()
    run_backfill(client)
    return 0


def _get_backfill(mart: str) -> MartBackfill:
    try:
        return MART_BACKFILLS[mart]
    except KeyError as exc:
        raise ValueError(f"unknown distributor mart: {mart}") from exc


def _read_count(client: Any, mart: str) -> int:
    result = client.query(f"SELECT count() FROM {mart}")
    first_row = getattr(result, "first_row", None)
    if first_row is not None:
        return int(first_row[0])
    rows = getattr(result, "result_rows", None)
    if rows:
        return int(rows[0][0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
