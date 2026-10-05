SET max_partitions_per_insert_block = 10000;

TRUNCATE TABLE dm_lk_daily_metrics;
TRUNCATE TABLE dm_lk_application_funnel;
TRUNCATE TABLE dm_lk_proposals;
TRUNCATE TABLE dm_lk_financial_pipeline;

INSERT INTO dm_lk_daily_metrics (
    date,
    leasing_company_id,
    distributor_id,
    new_applications,
    reviewed_applications,
    approved_count,
    rejected_count,
    issued_count,
    total_requested_amount,
    total_approved_amount,
    review_time_sum_seconds,
    review_time_count,
    decision_time_sum_seconds,
    decision_time_count
)
SELECT
    toDate(coalesce(submitted_at, created_at, updated_at)) AS date,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,
    toUInt32(countIf(status IN ('submitted', 'under_review'))) AS new_applications,
    toUInt32(countIf(status IN ('under_review', 'documents_required', 'under_review_with_docs'))) AS reviewed_applications,
    toUInt32(countIf(status IN ('approved_scoring', 'approved_scoring_another_cond', 'approved_final', 'approved_final_another_cond'))) AS approved_count,
    toUInt32(countIf(status IN ('rejected_prescoring', 'rejected_approved', 'closed'))) AS rejected_count,
    toUInt32(countIf(status = 'deal')) AS issued_count,
    CAST(sum(ifNull(total_amount, toDecimal64(0, 2))), 'Decimal(18,2)') AS total_requested_amount,
    CAST(sumIf(ifNull(total_amount, toDecimal64(0, 2)), status IN ('approved_scoring', 'approved_scoring_another_cond', 'approved_final', 'approved_final_another_cond')), 'Decimal(18,2)') AS total_approved_amount,
    toUInt64(0) AS review_time_sum_seconds,
    toUInt32(0) AS review_time_count,
    toUInt64(0) AS decision_time_sum_seconds,
    toUInt32(0) AS decision_time_count
FROM dwh_leasing_company_applications FINAL
WHERE _deleted = 0
  AND leasing_company_id IS NOT NULL
  AND coalesce(submitted_at, created_at, updated_at) IS NOT NULL
GROUP BY date, leasing_company_id, distributor_id;

INSERT INTO dm_lk_application_funnel (
    application_id,
    leasing_company_id,
    distributor_id,
    dealer_id,
    dealer_company_id,
    client_company_id,
    display_number,
    vehicle_id,
    vehicle_mark_id,
    vehicle_model_id,
    application_status,
    lca_status,
    created_at,
    submitted_at,
    under_review_at,
    prescoring_at,
    approved_at,
    rejected_at,
    issued_at,
    closed_at,
    review_notes,
    decision_comment,
    total_amount,
    down_payment,
    down_payment_percent,
    lease_term_months,
    monthly_payment,
    total_cost,
    markup,
    rate,
    total_interest,
    buyout_amount,
    vat_refund,
    profit_tax_savings,
    total_savings,
    current_stage,
    questionnaire_completed,
    status_count,
    updated_at
)
SELECT
    assumeNotNull(application_id) AS application_id,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,
    dealer_id,
    dealer_company_id,
    client_company_id,
    display_number,
    vehicle_id,
    vehicle_mark_id,
    vehicle_model_id,
    application_status,
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
    CAST(profit_tax_savings, 'Nullable(Decimal(18,2))') AS profit_tax_savings,
    CAST(total_savings, 'Nullable(Decimal(18,2))') AS total_savings,
    current_stage,
    questionnaire_completed,
    toUInt32(1) AS status_count,
    assumeNotNull(coalesce(updated_at, submitted_at, created_at, now64(3))) AS updated_at
FROM dwh_leasing_company_applications FINAL
WHERE _deleted = 0
  AND application_id IS NOT NULL
  AND leasing_company_id IS NOT NULL
  AND coalesce(submitted_at, created_at, updated_at) IS NOT NULL;

INSERT INTO dm_lk_proposals (
    proposal_id,
    lca_id,
    application_id,
    leasing_company_id,
    distributor_id,
    dealer_id,
    kind,
    total_amount,
    down_payment,
    down_payment_percent,
    lease_term_months,
    monthly_payment,
    total_cost,
    markup,
    rate,
    total_interest,
    buyout_amount,
    vat_refund,
    profit_tax_savings,
    total_savings,
    client_decision_action,
    client_decision_comment,
    client_decision_at,
    decision_speed_hours,
    proposal_created_at,
    updated_at
)
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
    assumeNotNull(coalesce(updated_at, created_at)) AS updated_at
FROM dwh_leasing_proposals FINAL
WHERE _deleted = 0
  AND proposal_id IS NOT NULL
  AND leasing_company_application_id IS NOT NULL
  AND application_id IS NOT NULL
  AND leasing_company_id IS NOT NULL
  AND coalesce(created_at, updated_at) IS NOT NULL;

INSERT INTO dm_lk_financial_pipeline (
    date,
    leasing_company_id,
    distributor_id,
    pipeline_amount,
    approved_amount,
    issued_amount,
    total_markup_sum,
    markup_count,
    total_rate_sum,
    rate_count,
    avg_lease_term_months_sum,
    avg_lease_term_count
)
SELECT
    toDate(coalesce(created_at, updated_at)) AS date,
    assumeNotNull(leasing_company_id) AS leasing_company_id,
    distributor_id,
    CAST(sum(ifNull(total_amount, toDecimal64(0, 2))), 'Decimal(18,2)') AS pipeline_amount,
    CAST(sumIf(ifNull(total_amount, toDecimal64(0, 2)), client_decision_action = 'accepted'), 'Decimal(18,2)') AS approved_amount,
    CAST(sumIf(ifNull(total_amount, toDecimal64(0, 2)), kind = 'final' AND client_decision_action = 'accepted'), 'Decimal(18,2)') AS issued_amount,
    CAST(sum(ifNull(CAST(markup, 'Nullable(Decimal(18,4))'), toDecimal64(0, 4))), 'Decimal(18,4)') AS total_markup_sum,
    toUInt32(countIf(markup IS NOT NULL)) AS markup_count,
    CAST(sum(ifNull(CAST(rate, 'Nullable(Decimal(18,4))'), toDecimal64(0, 4))), 'Decimal(18,4)') AS total_rate_sum,
    toUInt32(countIf(rate IS NOT NULL)) AS rate_count,
    toUInt64(sum(ifNull(lease_term_months, 0))) AS avg_lease_term_months_sum,
    toUInt32(countIf(lease_term_months IS NOT NULL)) AS avg_lease_term_count
FROM dwh_leasing_proposals FINAL
WHERE _deleted = 0
  AND leasing_company_id IS NOT NULL
  AND coalesce(created_at, updated_at) IS NOT NULL
GROUP BY date, leasing_company_id, distributor_id;
