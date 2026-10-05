"""Materialized View definitions for ClickHouse data marts.

These CREATE MATERIALIZED VIEW statements should be run after the
base DWH tables and data mart tables are created.  They select from
the DWH tables and populate the marts incrementally.

Design principle: all JOINs are eliminated by denormalizing related
fields into the DWH source tables at the emit stage (see
infrastructure/messaging/dwh_events.py).

Run via:  python -m clickhouse_sqlalchemy.tools alembic upgrade head
or apply manually via clickhouse-client.
"""

# ---------------------------------------------------------------------------
# dm_lk_daily_metrics — per-LC daily aggregates
# ---------------------------------------------------------------------------

DM_LK_DAILY_METRICS_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_lk_daily_metrics
TO dm_lk_daily_metrics AS
SELECT
    toDate(coalesce(submitted_at, created_at, updated_at)) AS date,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,  -- denormalized at source
    countIf(status IN ('submitted', 'under_review')) AS new_applications,
    countIf(status IN ('under_review', 'documents_required', 'under_review_with_docs')) AS reviewed_applications,
    countIf(status IN ('approved_scoring', 'approved_scoring_another_cond', 'approved_final', 'approved_final_another_cond')) AS approved_count,
    countIf(status IN ('rejected_prescoring', 'rejected_approved', 'closed')) AS rejected_count,
    countIf(status = 'deal') AS issued_count,
    sum(ifNull(total_amount, toDecimal64(0, 2))) AS total_requested_amount,
    sumIf(ifNull(total_amount, toDecimal64(0, 2)), status IN ('approved_scoring', 'approved_scoring_another_cond', 'approved_final', 'approved_final_another_cond')) AS total_approved_amount,
    0 AS review_time_sum_seconds,
    0 AS review_time_count,
    0 AS decision_time_sum_seconds,
    0 AS decision_time_count
FROM dwh_leasing_company_applications
WHERE _deleted = 0 AND leasing_company_id IS NOT NULL AND coalesce(submitted_at, created_at, updated_at) IS NOT NULL
GROUP BY date, leasing_company_id, distributor_id
"""

# ---------------------------------------------------------------------------
# dm_lk_application_funnel — per-application status history
# (now enriched with financial fields from unified dwh_lca)
# ---------------------------------------------------------------------------

DM_LK_APPLICATION_FUNNEL_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_lk_application_funnel
TO dm_lk_application_funnel AS
SELECT
    assumeNotNull(application_id) AS application_id,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,       -- denormalized at source
    dealer_id,            -- denormalized at source
    dealer_company_id,    -- denormalized at source
    client_company_id,    -- denormalized at source
    display_number,       -- denormalized at source
    vehicle_id,           -- denormalized at source
    vehicle_mark_id,
    vehicle_model_id,
    application_status,   -- denormalized at source
    status AS lca_status,
    coalesce(created_at, submitted_at, updated_at) AS created_at,
    submitted_at,
    if(status IN ('under_review', 'documents_required', 'under_review_with_docs'), coalesce(submitted_at, created_at, updated_at), CAST(NULL, 'Nullable(DateTime64(3))')) AS under_review_at,
    if(status IN ('approved_scoring', 'approved_scoring_another_cond', 'rejected_prescoring'), coalesce(updated_at, submitted_at, created_at), CAST(NULL, 'Nullable(DateTime64(3))')) AS prescoring_at,
    if(status IN ('approved_final', 'approved_final_another_cond', 'deal'), coalesce(updated_at, submitted_at, created_at), CAST(NULL, 'Nullable(DateTime64(3))')) AS approved_at,
    if(status IN ('rejected_prescoring', 'rejected_approved'), coalesce(updated_at, submitted_at, created_at), CAST(NULL, 'Nullable(DateTime64(3))')) AS rejected_at,
    if(status = 'deal', coalesce(updated_at, submitted_at, created_at), CAST(NULL, 'Nullable(DateTime64(3))')) AS issued_at,
    if(status = 'closed', coalesce(updated_at, submitted_at, created_at), CAST(NULL, 'Nullable(DateTime64(3))')) AS closed_at,
    review_notes,
    decision_comment,
    -- Financial fields (merged from application)
    CAST(total_amount, 'Nullable(Decimal(18,2))') AS total_amount,
    CAST(down_payment, 'Nullable(Decimal(18,2))') AS down_payment,
    CAST(down_payment_percent, 'Nullable(Decimal(5,2))') AS down_payment_percent,
    CAST(lease_term_months, 'Nullable(UInt8)') AS lease_term_months,
    CAST(monthly_payment, 'Nullable(Decimal(18,2))') AS monthly_payment,
    CAST(total_cost, 'Nullable(Decimal(18,2))') AS total_cost,
    CAST(markup, 'Nullable(Decimal(6,4))') AS markup,
    CAST(rate, 'Nullable(Decimal(6,4))') AS rate,
    CAST(total_interest, 'Nullable(Decimal(18,2))') AS total_interest,
    CAST(buyout_amount, 'Nullable(Decimal(18,2))') AS buyout_amount,
    CAST(vat_refund, 'Nullable(Decimal(18,2))') AS vat_refund,
    profit_tax_savings,
    total_savings,
    current_stage,
    questionnaire_completed,
    1 AS status_count,
    coalesce(submitted_at, now()) AS updated_at
FROM dwh_leasing_company_applications
WHERE _deleted = 0 AND application_id IS NOT NULL AND leasing_company_id IS NOT NULL AND coalesce(submitted_at, created_at, updated_at) IS NOT NULL
"""

# ---------------------------------------------------------------------------
# dm_lk_proposals — proposal metrics
# ---------------------------------------------------------------------------

DM_LK_PROPOSALS_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_lk_proposals
TO dm_lk_proposals AS
SELECT
    proposal_id,
    leasing_company_application_id AS lca_id,
    assumeNotNull(application_id) AS application_id,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,
    dealer_id,
    kind,
    CAST(total_amount, 'Nullable(Decimal(18,2))') AS total_amount,
    CAST(down_payment, 'Nullable(Decimal(18,2))') AS down_payment,
    CAST(down_payment_percent, 'Nullable(Decimal(5,2))') AS down_payment_percent,
    toUInt8(ifNull(lease_term_months, 0)) AS lease_term_months,
    CAST(monthly_payment, 'Nullable(Decimal(18,2))') AS monthly_payment,
    CAST(total_cost, 'Nullable(Decimal(18,2))') AS total_cost,
    CAST(markup, 'Nullable(Decimal(6,4))') AS markup,
    CAST(rate, 'Nullable(Decimal(6,4))') AS rate,
    CAST(total_interest, 'Nullable(Decimal(18,2))') AS total_interest,
    CAST(buyout_amount, 'Nullable(Decimal(18,2))') AS buyout_amount,
    CAST(vat_refund, 'Nullable(Decimal(18,2))') AS vat_refund,
    CAST(profit_tax_savings, 'Nullable(Decimal(18,2))') AS profit_tax_savings,
    CAST(total_savings, 'Nullable(Decimal(18,2))') AS total_savings,
    client_decision_action,
    client_decision_comment,
    client_decision_at,
    if(client_decision_at IS NULL OR created_at IS NULL, CAST(NULL, 'Nullable(Float32)'), CAST(dateDiff('hour', assumeNotNull(created_at), assumeNotNull(client_decision_at)), 'Nullable(Float32)')) AS decision_speed_hours,
    assumeNotNull(coalesce(created_at, updated_at)) AS proposal_created_at,
    updated_at
FROM dwh_leasing_proposals
WHERE _deleted = 0 AND application_id IS NOT NULL AND leasing_company_id IS NOT NULL AND coalesce(created_at, updated_at) IS NOT NULL
"""

# ---------------------------------------------------------------------------
# dm_lk_financial_pipeline — financial aggregates
# ---------------------------------------------------------------------------

DM_LK_FINANCIAL_PIPELINE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_lk_financial_pipeline
TO dm_lk_financial_pipeline AS
SELECT
    toDate(coalesce(created_at, updated_at)) AS date,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,       -- denormalized at source
    sum(ifNull(total_amount, toDecimal64(0, 2))) AS pipeline_amount,
    sumIf(ifNull(total_amount, toDecimal64(0, 2)), client_decision_action = 'accepted') AS approved_amount,
    sumIf(ifNull(total_amount, toDecimal64(0, 2)), kind = 'final' AND client_decision_action = 'accepted') AS issued_amount,
    sum(ifNull(CAST(markup, 'Nullable(Decimal(18,4))'), toDecimal64(0, 4))) AS total_markup_sum,
    countIf(markup IS NOT NULL) AS markup_count,
    sum(ifNull(CAST(rate, 'Nullable(Decimal(18,4))'), toDecimal64(0, 4))) AS total_rate_sum,
    countIf(rate IS NOT NULL) AS rate_count,
    sum(lease_term_months) AS avg_lease_term_months_sum,
    countIf(lease_term_months IS NOT NULL) AS avg_lease_term_count
FROM dwh_leasing_proposals
WHERE _deleted = 0 AND leasing_company_id IS NOT NULL AND coalesce(created_at, updated_at) IS NOT NULL
GROUP BY date, leasing_company_id, distributor_id
"""

# ---------------------------------------------------------------------------
# dm_distributor_financials — distributor financial aggregates
# (over dwh_leasing_proposals with denormalized dealer/LC fields)
# ---------------------------------------------------------------------------

DM_DISTRIBUTOR_FINANCIALS_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_distributor_financials
TO dm_distributor_financials AS
SELECT
    toDate(coalesce(a.created_at, a.updated_at)) AS date,
    a.dealer_company_id AS dealer_company_id,
    a.dealer_name AS dealer_name,
    a.dealer_city AS dealer_city,
    a.leasing_company_name AS leasing_company_name,
    a.status AS kind,
    count() AS application_count,
    sum(ifNull(a.total_amount, toDecimal64(0, 2))) AS pipeline_amount,
    sumIf(ifNull(a.total_amount, toDecimal64(0, 2)), a.status IN ('approved_scoring', 'approved_final', 'approved')) AS approved_amount,
    sumIf(ifNull(a.total_amount, toDecimal64(0, 2)), a.status IN ('deal', 'issued')) AS issued_amount,
    sum(ifNull(a.down_payment, toDecimal64(0, 2))) AS total_down_payment,
    countIf(a.down_payment IS NOT NULL) AS total_down_payment_count,
    sum(ifNull(a.down_payment_percent, toDecimal64(0, 2))) AS down_payment_percent_sum,
    countIf(a.down_payment_percent IS NOT NULL) AS down_payment_percent_count,
    sum(toUInt64(ifNull(a.lease_term_months, 0))) AS lease_term_months_sum,
    countIf(a.lease_term_months IS NOT NULL) AS lease_term_months_count,
    sum(ifNull(a.rate, toDecimal64(0, 2))) AS rate_sum,
    countIf(a.rate IS NOT NULL) AS rate_count,
    sum(ifNull(a.markup, toDecimal64(0, 2))) AS markup_sum,
    countIf(a.markup IS NOT NULL) AS markup_count,
    max(a.updated_at) AS updated_at
FROM dwh_leasing_company_applications AS a
WHERE a._deleted = 0
GROUP BY date, dealer_company_id, dealer_name, dealer_city, leasing_company_name, kind
"""

# ---------------------------------------------------------------------------
# dm_distributor_applications — distributor LCA detail
# (over dwh_leasing_company_applications)
# ---------------------------------------------------------------------------

DM_DISTRIBUTOR_APPLICATIONS_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_distributor_applications
TO dm_distributor_applications AS
SELECT
    a.lca_id AS lca_id,
    a.application_id AS application_id,
    a.leasing_company_id AS leasing_company_id,
    a.dealer_company_id AS dealer_company_id,
    a.client_company_id AS client_company_id,
    coalesce(a.vehicle_id, v.vehicle_id) AS vehicle_id,
    a.display_number AS display_number,
    coalesce(a.dealer_name, c.name) AS dealer_name,
    coalesce(a.dealer_city, c.city) AS dealer_city,
    a.leasing_company_name AS leasing_company_name,
    coalesce(a.mark_name, v.mark_id) AS mark_name,
    coalesce(a.model_name, v.model_id) AS model_name,
    coalesce(a.vehicle_mark_id, v.mark_id) AS vehicle_mark_id,
    coalesce(a.vehicle_model_id, v.model_id) AS vehicle_model_id,
    a.application_status AS application_status,
    a.status AS lca_status,
    a.total_amount AS total_amount,
    a.down_payment AS down_payment,
    a.down_payment_percent AS down_payment_percent,
    a.lease_term_months AS lease_term_months,
    a.monthly_payment AS monthly_payment,
    a.total_cost AS total_cost,
    a.markup AS markup,
    a.rate AS rate,
    a.total_interest AS total_interest,
    a.buyout_amount AS buyout_amount,
    a.vat_refund AS vat_refund,
    a.profit_tax_savings AS profit_tax_savings,
    a.total_savings AS total_savings,
    CAST(coalesce(v.special_price, v.discount_price, v.base_price), 'Nullable(Decimal(15,2))') AS vehicle_price,
    a.review_notes AS review_notes,
    a.decision_comment AS decision_comment,
    a.submitted_at AS submitted_at,
    a.created_at AS created_at,
    a.updated_at AS updated_at
FROM dwh_leasing_company_applications AS a
LEFT JOIN dwh_vehicles AS v ON a.vehicle_id = v.vehicle_id
LEFT JOIN dwh_companies AS c ON coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) = c.company_id
WHERE a._deleted = 0
"""

# ---------------------------------------------------------------------------
# dm_distributor_warehouse — distributor vehicle warehouse
# (over dwh_vehicles JOIN dwh_companies for dealer_name/dealer_city)
# ---------------------------------------------------------------------------

DM_DISTRIBUTOR_WAREHOUSE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_distributor_warehouse
TO dm_distributor_warehouse AS
SELECT
    v.vehicle_id AS vehicle_id,
    v.vin AS vin,
    v.dealer_id AS dealer_id,
    c.name AS dealer_name,
    c.city AS dealer_city,
    v.mark_id AS mark_id,
    v.model_id AS model_id,
    v.generation_id AS generation_id,
    v.configuration_id AS configuration_id,
    v.complectation_id AS complectation_id,
    v.year AS year,
    v.base_price AS base_price,
    v.special_price AS special_price,
    v.dealer_cost AS dealer_cost,
    v.discount_price AS discount_price,
    v.color AS color,
    v.color_inter AS color_inter,
    v.status AS status,
    v.is_available AS is_available,
    v.created_at AS created_at,
    v.updated_at AS updated_at
FROM dwh_vehicles AS v
LEFT JOIN dwh_companies AS c ON v.dealer_id = c.company_id
WHERE v._deleted = 0
"""

# ---------------------------------------------------------------------------
# dm_distributor_exchange — request-scoped distributor exchange pipeline
# (over dwh_exchange_requests with requested vehicle/dealer enrichment)
# ---------------------------------------------------------------------------

DM_DISTRIBUTOR_EXCHANGE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_distributor_exchange
TO dm_distributor_exchange AS
SELECT
    r.request_id AS request_id,
    r.lc_user_id AS lc_user_id,
    r.vehicle_id AS vehicle_id,
    v.dealer_id AS requested_dealer_id,
    c.name AS requested_dealer_name,
    c.city AS requested_dealer_city,
    v.mark_id AS mark,
    v.model_id AS model,
    r.quantity AS quantity,
    r.expiration_date AS expiration_date,
    r.discount_type AS discount_type,
    r.discount_value AS discount_value,
    r.file_url AS file_url,
    r.file_name AS file_name,
    r.status AS request_status,
    r.accepted_bid_id AS accepted_bid_id,
    r.batch_number AS batch_number,
    r.batch_index AS batch_index,
    ifNull(ba.bids_count, 0) AS bids_count,
    ifNull(ba.accepted_bids, 0) AS accepted_bids,
    CAST(ba.average_price, 'Nullable(Decimal(15,2))') AS average_price,
    r.created_at AS created_at,
    greatest(r.updated_at, ifNull(ba.updated_at, r.updated_at)) AS updated_at
FROM dwh_exchange_requests AS r
LEFT JOIN dwh_vehicles AS v ON r.vehicle_id = v.vehicle_id
LEFT JOIN dwh_companies AS c ON v.dealer_id = c.company_id
LEFT JOIN (
    SELECT
        request_id,
        count() AS bids_count,
        countIf(is_accepted = 1) AS accepted_bids,
        avg(price) AS average_price,
        max(updated_at) AS updated_at
    FROM dwh_exchange_bids
    WHERE _deleted = 0
    GROUP BY request_id
) AS ba ON r.request_id = ba.request_id
WHERE r._deleted = 0
"""

# ---------------------------------------------------------------------------
# dm_distributor_sales_dc — distributor sales pipeline detail (dealer center)
# (over dwh_leasing_company_applications with vehicle/dealer enrichment)
# ---------------------------------------------------------------------------

DM_DISTRIBUTOR_SALES_DC_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_distributor_sales_dc
TO dm_distributor_sales_dc AS
SELECT
    a.lca_id AS lca_id,
    assumeNotNull(a.application_id) AS application_id,
    a.leasing_company_id AS leasing_company_id,
    a.display_number AS display_number,
    a.dealer_company_id AS dealer_company_id,
    a.client_company_id AS client_company_id,
    coalesce(a.vehicle_id, v.vehicle_id) AS vehicle_id,
    CAST(coalesce(v.special_price, v.discount_price, v.base_price), 'Nullable(Decimal(15,2))') AS vehicle_price,
    coalesce(a.dealer_name, c.name) AS dealer_name,
    coalesce(a.dealer_city, c.city) AS dealer_city,
    a.leasing_company_name AS leasing_company_name,
    coalesce(a.mark_name, v.mark_id) AS mark_name,
    coalesce(a.model_name, v.model_id) AS model_name,
    coalesce(a.vehicle_mark_id, v.mark_id) AS vehicle_mark_id,
    coalesce(a.vehicle_model_id, v.model_id) AS vehicle_model_id,
    a.application_status AS status,
    a.status AS lca_status,
    a.total_amount AS total_amount,
    a.down_payment AS down_payment,
    a.down_payment_percent AS down_payment_percent,
    a.lease_term_months AS lease_term_months,
    a.monthly_payment AS monthly_payment,
    a.total_cost AS total_cost,
    a.markup AS markup,
    a.rate AS rate,
    a.total_interest AS total_interest,
    a.buyout_amount AS buyout_amount,
    a.vat_refund AS vat_refund,
    a.profit_tax_savings AS profit_tax_savings,
    a.total_savings AS total_savings,
    CAST(NULL, 'Nullable(String)') AS client_decision_action,
    CAST(NULL, 'Nullable(DateTime64(3))') AS client_decision_at,
    a.status AS kind,
    a.created_at AS created_at,
    a.updated_at AS updated_at
FROM dwh_leasing_company_applications AS a
LEFT JOIN dwh_vehicles AS v ON a.vehicle_id = v.vehicle_id
LEFT JOIN dwh_companies AS c ON coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) = c.company_id
WHERE a._deleted = 0 AND a.application_id IS NOT NULL
"""

# ---------------------------------------------------------------------------
# dm_distributor_sales_dc_regions — distributor regional sales detail
# (over dwh_application_vehicles JOIN dwh_vehicles JOIN dwh_leasing_company_applications)
# ---------------------------------------------------------------------------

DM_DISTRIBUTOR_SALES_DC_REGIONS_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dm_distributor_sales_dc_regions
TO dm_distributor_sales_dc_regions AS
SELECT
    av.application_id AS application_id,
    av.id AS application_vehicle_id,
    av.vehicle_id AS vehicle_id,
    a.leasing_company_id AS leasing_company_id,
    coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) AS dealer_id,
    coalesce(a.dealer_name, c.name) AS dealer_name,
    coalesce(a.dealer_city, c.city) AS dealer_city,
    c.region AS dealer_region,
    coalesce(a.vehicle_mark_id, v.mark_id) AS mark_id,
    coalesce(a.vehicle_model_id, v.model_id) AS model_id,
    av.vin AS vin,
    av.quantity AS quantity,
    av.unit_price AS unit_price,
    av.total_price AS total_price,
    v.year AS year,
    v.base_price AS base_price,
    v.special_price AS special_price,
    v.discount_price AS discount_price,
    v.color AS color,
    a.application_status AS application_status,
    a.status AS lca_status,
    a.total_amount AS application_total_amount,
    a.down_payment AS down_payment,
    a.down_payment_percent AS down_payment_percent,
    a.lease_term_months AS lease_term_months,
    a.monthly_payment AS monthly_payment,
    av.is_model_order AS is_model_order,
    a.created_at AS created_at,
    a.updated_at AS updated_at
FROM dwh_application_vehicles AS av
LEFT JOIN dwh_vehicles AS v ON av.vehicle_id = v.vehicle_id
LEFT JOIN dwh_leasing_company_applications AS a ON av.application_id = a.application_id
LEFT JOIN dwh_companies AS c ON coalesce(a.dealer_company_id, a.dealer_id, v.dealer_id) = c.company_id
WHERE av._deleted = 0
  AND a._deleted = 0
"""

# ---------------------------------------------------------------------------
# All MV creation statements in order
# ---------------------------------------------------------------------------

ALL_MV_STATEMENTS = [
    DM_DISTRIBUTOR_WAREHOUSE_MV,
    DM_DISTRIBUTOR_APPLICATIONS_MV,
    DM_DISTRIBUTOR_FINANCIALS_MV,
    DM_DISTRIBUTOR_EXCHANGE_MV,
    DM_DISTRIBUTOR_SALES_DC_MV,
    DM_DISTRIBUTOR_SALES_DC_REGIONS_MV,
    DM_LK_DAILY_METRICS_MV,
    DM_LK_APPLICATION_FUNNEL_MV,
    DM_LK_PROPOSALS_MV,
    DM_LK_FINANCIAL_PIPELINE_MV,
]
