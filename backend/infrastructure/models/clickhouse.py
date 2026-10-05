"""SQLAlchemy 2.0 declarative models for ClickHouse analytics tables."""

from __future__ import annotations

from clickhouse_sqlalchemy import engines
from clickhouse_sqlalchemy.types import (
    UUID,
    Date,
    DateTime64,
    Decimal,
    Float32,
    Int32,
    Int64,
    Nullable,
    String,
    UInt8,
    UInt32,
    UInt64,
)
from sqlalchemy import Column, func
from sqlalchemy.orm import DeclarativeBase


class ClickHouseBase(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# DWH source-replica tables
# ---------------------------------------------------------------------------


class DWHLeasingCompanyApplications(ClickHouseBase):
    __tablename__ = "dwh_leasing_company_applications"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["lca_id", "leasing_company_id"],
        ),
    )

    lca_id = Column(UUID, primary_key=True)
    application_id = Column(Nullable(UUID))
    leasing_company_id = Column(Nullable(UUID))
    # Denormalized from parent leasing_application
    dealer_id = Column(Nullable(UUID))
    dealer_company_id = Column(Nullable(UUID))
    client_company_id = Column(Nullable(UUID))
    distributor_id = Column(Nullable(UUID))
    display_number = Column(Nullable(String))
    vehicle_id = Column(Nullable(UUID))
    # Application-level financial / meta fields (merged from dwh_leasing_applications)
    name = Column(Nullable(String))
    email = Column(Nullable(String))
    application_status = Column(Nullable(String))
    total_amount = Column(Nullable(Decimal(15, 2)))
    down_payment = Column(Nullable(Decimal(15, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(Int32))
    monthly_payment = Column(Nullable(Decimal(12, 2)))
    total_cost = Column(Nullable(Decimal(15, 2)))
    markup = Column(Nullable(Decimal(15, 2)))
    rate = Column(Nullable(Decimal(5, 2)))
    total_interest = Column(Nullable(Decimal(15, 2)))
    buyout_amount = Column(Nullable(Decimal(15, 2)))
    vat_refund = Column(Nullable(Decimal(15, 2)))
    profit_tax_savings = Column(Nullable(Decimal(15, 2)))
    total_savings = Column(Nullable(Decimal(15, 2)))
    selected_leasing_companies = Column(Nullable(String))
    leasing_company_comments = Column(Nullable(String))
    requested_documents = Column(Nullable(String))
    questionnaire_completed = Column(Nullable(UInt8), default=0)
    questionnaire_progress = Column(Nullable(Int32))
    current_stage = Column(Nullable(String))
    # Denormalized vehicle fields
    vehicle_mark_id = Column(Nullable(String))
    vehicle_model_id = Column(Nullable(String))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    leasing_company_name = Column(Nullable(String))
    mark_name = Column(Nullable(String))
    model_name = Column(Nullable(String))
    # LCA fields
    status = Column(Nullable(String))
    review_notes = Column(Nullable(String))
    decision_comment = Column(Nullable(String))
    response_pdf_s3_key = Column(Nullable(String))
    response_pdf_file_name = Column(Nullable(String))
    response_pdf_size = Column(Nullable(Int32))
    response_pdf_uploaded_at = Column(Nullable(DateTime64(3)))
    submitted_at = Column(Nullable(DateTime64(3)))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHLeasingProposals(ClickHouseBase):
    __tablename__ = "dwh_leasing_proposals"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["proposal_id", "leasing_company_application_id"],
        ),
    )

    proposal_id = Column(UUID, primary_key=True)
    leasing_company_application_id = Column(UUID)
    # Denormalized from parent application/LCA
    application_id = Column(Nullable(UUID))
    leasing_company_id = Column(Nullable(UUID))
    dealer_id = Column(Nullable(UUID))
    dealer_company_id = Column(Nullable(UUID))
    client_company_id = Column(Nullable(UUID))
    distributor_id = Column(Nullable(UUID))
    # Proposal fields
    kind = Column(Nullable(String))
    position = Column(Nullable(Int32))
    total_amount = Column(Nullable(Decimal(15, 2)))
    down_payment = Column(Nullable(Decimal(15, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(Int32))
    monthly_payment = Column(Nullable(Decimal(12, 2)))
    total_cost = Column(Nullable(Decimal(15, 2)))
    markup = Column(Nullable(Decimal(15, 2)))
    rate = Column(Nullable(Decimal(5, 2)))
    total_interest = Column(Nullable(Decimal(15, 2)))
    buyout_amount = Column(Nullable(Decimal(15, 2)))
    vat_refund = Column(Nullable(Decimal(15, 2)))
    profit_tax_savings = Column(Nullable(Decimal(15, 2)))
    total_savings = Column(Nullable(Decimal(15, 2)))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    leasing_company_name = Column(Nullable(String))
    client_decision_action = Column(Nullable(String))
    client_decision_at = Column(Nullable(DateTime64(3)))
    client_decision_comment = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHDocuments(ClickHouseBase):
    __tablename__ = "dwh_documents"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["document_id", "company_id"],
        ),
    )

    document_id = Column(UUID, primary_key=True)
    company_id = Column(UUID)
    document_type = Column(Nullable(String))
    file_path = Column(Nullable(String))
    file_name = Column(Nullable(String))
    file_size = Column(Nullable(Int32))
    s3_key = Column(Nullable(String))
    period_label = Column(Nullable(String))
    comments = Column(Nullable(String))
    is_required = Column(UInt8, default=0)
    status = Column(Nullable(String))
    version = Column(Nullable(Int32))
    parent_document_id = Column(Nullable(UUID))
    is_current_version = Column(UInt8, default=1)
    related_application_id = Column(Nullable(UUID))
    approved_by_leasing_company = Column(Nullable(UUID))
    leasing_company_status = Column(Nullable(String))
    leasing_company_comments = Column(Nullable(String))
    leasing_company_reviewed_at = Column(Nullable(DateTime64(3)))
    extracted_data = Column(Nullable(String))
    recognition_status = Column(Nullable(String))
    recognition_error = Column(Nullable(String))
    dbrain_task_id = Column(Nullable(String))
    recognized_at = Column(Nullable(DateTime64(3)))
    uploaded_at = Column(Nullable(DateTime64(3)))
    verified_at = Column(Nullable(DateTime64(3)))
    verified_by = Column(Nullable(UUID))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHVehicles(ClickHouseBase):
    __tablename__ = "dwh_vehicles"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["vehicle_id"],
        ),
    )

    vehicle_id = Column(UUID, primary_key=True)
    vin = Column(Nullable(String))
    dealer_id = Column(Nullable(UUID))
    mark_id = Column(Nullable(String))
    model_id = Column(Nullable(String))
    generation_id = Column(Nullable(String))
    configuration_id = Column(Nullable(String))
    complectation_id = Column(Nullable(String))
    year = Column(Nullable(Int32))
    base_price = Column(Nullable(Decimal(12, 2)))
    special_price = Column(Nullable(Decimal(12, 2)))
    dealer_cost = Column(Nullable(Decimal(12, 2)))
    discount_price = Column(Nullable(Decimal(12, 2)))
    color = Column(Nullable(String))
    color_inter = Column(Nullable(String))
    images = Column(Nullable(String))
    status = Column(Nullable(String))
    is_available = Column(UInt8, default=1)
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHApplicationVehicles(ClickHouseBase):
    __tablename__ = "dwh_application_vehicles"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["application_id", "id"],
        ),
    )

    id = Column(UUID, primary_key=True)
    application_id = Column(UUID)
    vehicle_id = Column(Nullable(UUID))
    modification_id = Column(Nullable(String))
    quantity = Column(Nullable(Int32))
    unit_price = Column(Nullable(Decimal(15, 2)))
    total_price = Column(Nullable(Decimal(15, 2)))
    comment = Column(Nullable(String))
    vin = Column(Nullable(String))
    vin_assigned_by = Column(Nullable(UUID))
    vin_assigned_at = Column(Nullable(DateTime64(3)))
    is_model_order = Column(UInt8, default=0)
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHCompanies(ClickHouseBase):
    __tablename__ = "dwh_companies"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["company_id"],
        ),
    )

    company_id = Column(UUID, primary_key=True)
    name = Column(Nullable(String))
    inn = Column(Nullable(String))
    kpp = Column(Nullable(String))
    ogrn = Column(Nullable(String))
    company_type = Column(Nullable(String))
    address = Column(Nullable(String))
    contact_info = Column(Nullable(String))
    legal_address = Column(Nullable(String))
    actual_address = Column(Nullable(String))
    phone = Column(Nullable(String))
    email = Column(Nullable(String))
    website = Column(Nullable(String))
    is_active = Column(UInt8, default=1)
    full_name = Column(Nullable(String))
    short_name = Column(Nullable(String))
    okpo = Column(Nullable(String))
    okato = Column(Nullable(String))
    legal_form = Column(Nullable(String))
    region = Column(Nullable(String))
    city = Column(Nullable(String))
    registration_date = Column(Nullable(Date))
    employees_count = Column(Nullable(Int32))
    main_okved_code = Column(Nullable(String))
    main_okved_description = Column(Nullable(String))
    director_full_name = Column(Nullable(String))
    bank_bik = Column(Nullable(String))
    bank_name = Column(Nullable(String))
    authorized_capital = Column(Nullable(Int64))
    net_profit = Column(Nullable(Int64))
    reporting_year = Column(Nullable(Int32))
    tax_system = Column(Nullable(String))
    enrichment_status = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHUsers(ClickHouseBase):
    __tablename__ = "dwh_users"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["user_id"],
        ),
    )

    user_id = Column(UUID, primary_key=True)
    email = Column(Nullable(String))
    name = Column(Nullable(String))
    role = Column(Nullable(String))
    company_id = Column(Nullable(UUID))
    phone = Column(Nullable(String))
    is_active = Column(UInt8, default=1)
    email_verified = Column(UInt8, default=0)
    phone_verified = Column(UInt8, default=0)
    last_login = Column(Nullable(DateTime64(3)))
    deleted_at = Column(Nullable(DateTime64(3)))
    mfa_enabled = Column(UInt8, default=0)
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHPurchaseOrders(ClickHouseBase):
    __tablename__ = "dwh_purchase_orders"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["order_id", "user_id"],
        ),
    )

    order_id = Column(UUID, primary_key=True)
    user_id = Column(UUID)
    vehicle_id = Column(UUID)
    purchase_type = Column(Nullable(String))
    status = Column(Nullable(String))
    total_price = Column(Decimal(15, 2))
    paid_amount = Column(Decimal(15, 2), default=0)
    remaining_amount = Column(Decimal(15, 2), default=0)
    leasing_application_id = Column(Nullable(UUID))
    cancellation_reason = Column(Nullable(String))
    cancellation_requested_at = Column(Nullable(DateTime64(3)))
    cancelled_at = Column(Nullable(DateTime64(3)))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHCalculations(ClickHouseBase):
    __tablename__ = "dwh_calculations"
    __table_args__ = (
        engines.MergeTree(order_by=["calc_id"]),
    )

    calc_id = Column(UUID, primary_key=True)
    user_id = Column(Nullable(UUID))
    vehicle_ids = Column(Nullable(String))
    total_amount = Column(Nullable(Decimal(15, 2)))
    down_payment = Column(Nullable(Decimal(15, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(Int32))
    monthly_payment = Column(Nullable(Decimal(12, 2)))
    total_cost = Column(Nullable(Decimal(15, 2)))
    markup = Column(Nullable(Decimal(15, 2)))
    rate = Column(Nullable(Decimal(5, 2)))
    total_interest = Column(Nullable(Decimal(15, 2)))
    buyout_amount = Column(Nullable(Decimal(15, 2)))
    vat_refund = Column(Nullable(Decimal(15, 2)))
    profit_tax_savings = Column(Nullable(Decimal(15, 2)))
    total_savings = Column(Nullable(Decimal(15, 2)))
    calculation_type = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))


class DWHQuestionnaires(ClickHouseBase):
    __tablename__ = "dwh_questionnaires"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["application_id", "questionnaire_id"],
        ),
    )

    questionnaire_id = Column(UUID, primary_key=True)
    application_id = Column(UUID)
    full_company_name = Column(Nullable(String))
    short_company_name = Column(Nullable(String))
    inn = Column(Nullable(String))
    ogrn = Column(Nullable(String))
    kpp = Column(Nullable(String))
    okpo = Column(Nullable(String))
    okato = Column(Nullable(String))
    okved_main = Column(Nullable(String))
    tax_system = Column(Nullable(String))
    legal_form = Column(Nullable(String))
    legal_address = Column(Nullable(String))
    actual_address = Column(Nullable(String))
    phone = Column(Nullable(String))
    email = Column(Nullable(String))
    director_full_name = Column(Nullable(String))
    director_position = Column(Nullable(String))
    director_phone = Column(Nullable(String))
    director_email = Column(Nullable(String))
    founders = Column(Nullable(String))
    beneficiaries = Column(Nullable(String))
    has_beneficiary = Column(UInt8, default=0)
    management_bodies = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHExchangeRequests(ClickHouseBase):
    __tablename__ = "dwh_exchange_requests"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["request_id", "lc_user_id"],
        ),
    )

    request_id = Column(UUID, primary_key=True)
    lc_user_id = Column(UUID)
    vehicle_id = Column(UUID)
    quantity = Column(Int32, default=1)
    expiration_date = Column(Nullable(Date))
    discount_type = Column(Nullable(String))
    discount_value = Column(Nullable(Decimal(15, 2)))
    file_url = Column(Nullable(String))
    file_name = Column(Nullable(String))
    status = Column(Nullable(String))
    accepted_bid_id = Column(Nullable(UUID))
    batch_number = Column(Nullable(Int32))
    batch_index = Column(Nullable(Int32))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHExchangeBids(ClickHouseBase):
    __tablename__ = "dwh_exchange_bids"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["bid_id", "request_id"],
        ),
    )

    bid_id = Column(UUID, primary_key=True)
    request_id = Column(UUID)
    dealer_id = Column(UUID)
    price = Column(Decimal(15, 2))
    comment = Column(Nullable(String))
    is_accepted = Column(UInt8, default=0)
    kp_file_url = Column(Nullable(String))
    kp_file_name = Column(Nullable(String))
    kp_status = Column(Nullable(String))
    kp_dealer_comment = Column(Nullable(String))
    kp_sent_at = Column(Nullable(DateTime64(3)))
    kp_responded_at = Column(Nullable(DateTime64(3)))
    quantity = Column(Int32, default=1)
    bid_file_url = Column(Nullable(String))
    bid_file_name = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHSupportPrograms(ClickHouseBase):
    __tablename__ = "dwh_support_programs"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["program_id"],
        ),
    )

    program_id = Column(UUID, primary_key=True)
    name = Column(Nullable(String))
    mark_id = Column(Nullable(String))
    model_id = Column(Nullable(String))
    model_ids = Column(Nullable(String))
    complectation_ids = Column(Nullable(String))
    vin = Column(Nullable(String))
    vins = Column(Nullable(String))
    dealer_group_id = Column(Nullable(UUID))
    distributor_id = Column(Nullable(UUID))
    support_type = Column(Nullable(String))
    support_params = Column(Nullable(String))
    production_year_from = Column(Nullable(Int32))
    production_year_to = Column(Nullable(Int32))
    production_date_from = Column(Nullable(Date))
    production_date_to = Column(Nullable(Date))
    delivery_date_from = Column(Nullable(Date))
    delivery_date_to = Column(Nullable(Date))
    starts_at = Column(Nullable(Date))
    ends_at = Column(Nullable(Date))
    is_active = Column(UInt8, default=1)
    is_compatible = Column(UInt8, default=0)
    compatible_support_ids = Column(Nullable(String))
    show_to_leasing_company = Column(UInt8, default=1)
    show_to_client = Column(UInt8, default=1)
    comment = Column(Nullable(String))
    created_by = Column(Nullable(UUID))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


class DWHCompensations(ClickHouseBase):
    __tablename__ = "dwh_compensations"
    __table_args__ = (
        engines.ReplacingMergeTree(
            version="updated_at",
            order_by=["compensation_id", "application_id"],
        ),
    )

    compensation_id = Column(UUID, primary_key=True)
    applied_support_id = Column(UUID)
    application_id = Column(Nullable(UUID))
    exchange_request_id = Column(Nullable(UUID))
    source = Column(String, default="platform")
    vehicle_id = Column(Nullable(UUID))
    payer = Column(Nullable(String))
    recipient = Column(Nullable(String))
    calculation_base = Column(Nullable(String))
    calculation_base_amount = Column(Decimal(15, 2))
    value_type = Column(Nullable(String))
    value = Column(Decimal(15, 2))
    min_amount = Column(Nullable(Decimal(15, 2)))
    max_amount = Column(Nullable(Decimal(15, 2)))
    min_percent = Column(Nullable(Decimal(10, 4)))
    max_percent = Column(Nullable(Decimal(10, 4)))
    amount = Column(Decimal(15, 2))
    status = Column(Nullable(String))
    payment_schedule_type = Column(Nullable(String))
    payment_schedule_period = Column(Nullable(String))
    payment_schedule_value = Column(Nullable(String))
    due_date = Column(Nullable(Date))
    paid_at = Column(Nullable(DateTime64(3)))
    documents = Column(Nullable(String))
    comment = Column(Nullable(String))
    created_by = Column(Nullable(UUID))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))
    _deleted = Column(UInt8, default=0)


# ---------------------------------------------------------------------------
# Data marts
# ---------------------------------------------------------------------------


class DMLKDailyMetrics(ClickHouseBase):
    __tablename__ = "dm_lk_daily_metrics"
    __table_args__ = (
        engines.SummingMergeTree(order_by=["date", "leasing_company_id"]),
    )

    date = Column(Date, primary_key=True)
    leasing_company_id = Column(UUID)
    distributor_id = Column(Nullable(UUID))
    new_applications = Column(UInt32)
    reviewed_applications = Column(UInt32)
    approved_count = Column(UInt32)
    rejected_count = Column(UInt32)
    issued_count = Column(UInt32)
    total_requested_amount = Column(Decimal(18, 2))
    total_approved_amount = Column(Decimal(18, 2))
    review_time_sum_seconds = Column(UInt64)
    review_time_count = Column(UInt32)
    decision_time_sum_seconds = Column(UInt64)
    decision_time_count = Column(UInt32)


class DMLKApplicationFunnel(ClickHouseBase):
    __tablename__ = "dm_lk_application_funnel"
    __table_args__ = (
        engines.MergeTree(
            order_by=[
                "leasing_company_id",
                "lca_status",
                "created_at",
                "application_id",
            ],
        ),
    )

    application_id = Column(UUID, primary_key=True)
    leasing_company_id = Column(UUID)
    distributor_id = Column(Nullable(UUID))
    dealer_id = Column(Nullable(UUID))
    dealer_company_id = Column(Nullable(UUID))
    client_company_id = Column(Nullable(UUID))
    display_number = Column(Nullable(String))
    vehicle_id = Column(Nullable(UUID))
    vehicle_mark_id = Column(Nullable(String))
    vehicle_model_id = Column(Nullable(String))
    application_status = Column(Nullable(String))
    lca_status = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))
    submitted_at = Column(Nullable(DateTime64(3)))
    under_review_at = Column(Nullable(DateTime64(3)))
    prescoring_at = Column(Nullable(DateTime64(3)))
    approved_at = Column(Nullable(DateTime64(3)))
    rejected_at = Column(Nullable(DateTime64(3)))
    issued_at = Column(Nullable(DateTime64(3)))
    closed_at = Column(Nullable(DateTime64(3)))
    review_notes = Column(Nullable(String))
    decision_comment = Column(Nullable(String))
    total_amount = Column(Nullable(Decimal(18, 2)))
    down_payment = Column(Nullable(Decimal(18, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(UInt8))
    monthly_payment = Column(Nullable(Decimal(18, 2)))
    total_cost = Column(Nullable(Decimal(18, 2)))
    markup = Column(Nullable(Decimal(6, 4)))
    rate = Column(Nullable(Decimal(6, 4)))
    total_interest = Column(Nullable(Decimal(18, 2)))
    buyout_amount = Column(Nullable(Decimal(18, 2)))
    vat_refund = Column(Nullable(Decimal(18, 2)))
    profit_tax_savings = Column(Nullable(Decimal(18, 2)))
    total_savings = Column(Nullable(Decimal(18, 2)))
    current_stage = Column(Nullable(String))
    questionnaire_completed = Column(UInt8, default=0)
    status_count = Column(UInt32, default=1)
    updated_at = Column(DateTime64(3))


class DMLKProposals(ClickHouseBase):
    __tablename__ = "dm_lk_proposals"
    __table_args__ = (
        engines.MergeTree(
            order_by=[
                "leasing_company_id",
                "kind",
                "proposal_created_at",
                "application_id",
                "proposal_id",
            ],
        ),
    )

    proposal_id = Column(UUID, primary_key=True)
    lca_id = Column(UUID)
    application_id = Column(UUID)
    leasing_company_id = Column(UUID)
    distributor_id = Column(Nullable(UUID))
    dealer_id = Column(Nullable(UUID))
    kind = Column(Nullable(String))
    total_amount = Column(Nullable(Decimal(18, 2)))
    down_payment = Column(Nullable(Decimal(18, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(UInt8)
    monthly_payment = Column(Nullable(Decimal(18, 2)))
    total_cost = Column(Nullable(Decimal(18, 2)))
    markup = Column(Nullable(Decimal(6, 4)))
    rate = Column(Nullable(Decimal(6, 4)))
    total_interest = Column(Nullable(Decimal(18, 2)))
    buyout_amount = Column(Nullable(Decimal(18, 2)))
    vat_refund = Column(Nullable(Decimal(18, 2)))
    profit_tax_savings = Column(Nullable(Decimal(18, 2)))
    total_savings = Column(Nullable(Decimal(18, 2)))
    client_decision_action = Column(Nullable(String))
    client_decision_comment = Column(Nullable(String))
    client_decision_at = Column(Nullable(DateTime64(3)))
    decision_speed_hours = Column(Nullable(Float32))
    proposal_created_at = Column(DateTime64(3))
    updated_at = Column(DateTime64(3))


class DMLKFinancialPipeline(ClickHouseBase):
    __tablename__ = "dm_lk_financial_pipeline"
    __table_args__ = (
        engines.SummingMergeTree(order_by=["date", "leasing_company_id"]),
    )

    date = Column(Date, primary_key=True)
    leasing_company_id = Column(UUID)
    distributor_id = Column(Nullable(UUID))
    pipeline_amount = Column(Decimal(18, 2))
    approved_amount = Column(Decimal(18, 2))
    issued_amount = Column(Decimal(18, 2))
    total_markup_sum = Column(Decimal(18, 4))
    markup_count = Column(UInt32)
    total_rate_sum = Column(Decimal(18, 4))
    rate_count = Column(UInt32)
    avg_lease_term_months_sum = Column(UInt64)
    avg_lease_term_count = Column(UInt32)


class DMDistributorFinancials(ClickHouseBase):
    __tablename__ = "dm_distributor_financials"
    __table_args__ = (
        engines.SummingMergeTree(
            order_by=[
                "date",
                "dealer_company_id",
                "dealer_name",
                "dealer_city",
                "leasing_company_name",
                "kind",
            ],
        ),
    )

    date = Column(Date, primary_key=True)
    dealer_company_id = Column(Nullable(UUID))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    leasing_company_name = Column(Nullable(String))
    kind = Column(Nullable(String))
    application_count = Column(UInt64)
    pipeline_amount = Column(Decimal(18, 2))
    approved_amount = Column(Decimal(18, 2))
    issued_amount = Column(Decimal(18, 2))
    total_down_payment = Column(Decimal(18, 2))
    total_down_payment_count = Column(UInt64)
    down_payment_percent_sum = Column(Decimal(18, 4))
    down_payment_percent_count = Column(UInt64)
    lease_term_months_sum = Column(UInt64)
    lease_term_months_count = Column(UInt64)
    rate_sum = Column(Decimal(18, 4))
    rate_count = Column(UInt64)
    markup_sum = Column(Decimal(18, 4))
    markup_count = Column(UInt64)
    updated_at = Column(DateTime64(3))


class DMDistributorApplications(ClickHouseBase):
    __tablename__ = "dm_distributor_applications"
    __table_args__ = (
        engines.SummingMergeTree(
            order_by=["dealer_company_id", "application_status", "created_at", "lca_id"],
        ),
    )

    lca_id = Column(UUID, primary_key=True)
    application_id = Column(Nullable(UUID))
    leasing_company_id = Column(Nullable(UUID))
    dealer_company_id = Column(Nullable(UUID))
    client_company_id = Column(Nullable(UUID))
    vehicle_id = Column(Nullable(UUID))
    display_number = Column(Nullable(String))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    leasing_company_name = Column(Nullable(String))
    mark_name = Column(Nullable(String))
    model_name = Column(Nullable(String))
    vehicle_mark_id = Column(Nullable(String))
    vehicle_model_id = Column(Nullable(String))
    application_status = Column(Nullable(String))
    lca_status = Column(Nullable(String))
    total_amount = Column(Nullable(Decimal(15, 2)))
    down_payment = Column(Nullable(Decimal(15, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(Int32))
    monthly_payment = Column(Nullable(Decimal(12, 2)))
    total_cost = Column(Nullable(Decimal(15, 2)))
    markup = Column(Nullable(Decimal(15, 2)))
    rate = Column(Nullable(Decimal(5, 2)))
    total_interest = Column(Nullable(Decimal(15, 2)))
    buyout_amount = Column(Nullable(Decimal(15, 2)))
    vat_refund = Column(Nullable(Decimal(15, 2)))
    profit_tax_savings = Column(Nullable(Decimal(15, 2)))
    total_savings = Column(Nullable(Decimal(15, 2)))
    vehicle_price = Column(Nullable(Decimal(15, 2)))
    review_notes = Column(Nullable(String))
    decision_comment = Column(Nullable(String))
    submitted_at = Column(Nullable(DateTime64(3)))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))


class DMDistributorWarehouse(ClickHouseBase):
    __tablename__ = "dm_distributor_warehouse"
    __table_args__ = (
        engines.SummingMergeTree(order_by=["dealer_id", "vehicle_id"]),
    )

    vehicle_id = Column(UUID, primary_key=True)
    vin = Column(Nullable(String))
    dealer_id = Column(Nullable(UUID))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    mark_id = Column(Nullable(String))
    model_id = Column(Nullable(String))
    generation_id = Column(Nullable(String))
    configuration_id = Column(Nullable(String))
    complectation_id = Column(Nullable(String))
    year = Column(Nullable(Int32))
    base_price = Column(Nullable(Decimal(12, 2)))
    special_price = Column(Nullable(Decimal(12, 2)))
    dealer_cost = Column(Nullable(Decimal(12, 2)))
    discount_price = Column(Nullable(Decimal(12, 2)))
    color = Column(Nullable(String))
    color_inter = Column(Nullable(String))
    status = Column(Nullable(String))
    is_available = Column(UInt8, default=1)
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))


class DMDistributorExchange(ClickHouseBase):
    __tablename__ = "dm_distributor_exchange"
    __table_args__ = (
        engines.SummingMergeTree(
            order_by=[
                "requested_dealer_id",
                "request_status",
                "created_at",
                "request_id",
            ],
        ),
    )

    request_id = Column(UUID, primary_key=True)
    lc_user_id = Column(UUID)
    vehicle_id = Column(UUID)
    requested_dealer_id = Column(Nullable(UUID))
    requested_dealer_name = Column(Nullable(String))
    requested_dealer_city = Column(Nullable(String))
    mark = Column(Nullable(String))
    model = Column(Nullable(String))
    quantity = Column(Int32, default=1)
    expiration_date = Column(Nullable(Date))
    discount_type = Column(Nullable(String))
    discount_value = Column(Nullable(Decimal(15, 2)))
    file_url = Column(Nullable(String))
    file_name = Column(Nullable(String))
    request_status = Column(Nullable(String))
    accepted_bid_id = Column(Nullable(UUID))
    batch_number = Column(Nullable(Int32))
    batch_index = Column(Nullable(Int32))
    bids_count = Column(UInt64, default=0)
    accepted_bids = Column(UInt64, default=0)
    average_price = Column(Nullable(Decimal(15, 2)))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))


class DMDistributorSalesDC(ClickHouseBase):
    __tablename__ = "dm_distributor_sales_dc"
    __table_args__ = (
        engines.SummingMergeTree(
            order_by=[
                "dealer_company_id",
                "status",
                "created_at",
                "application_id",
                "lca_id",
            ],
        ),
    )

    lca_id = Column(UUID, primary_key=True)
    application_id = Column(UUID)
    leasing_company_id = Column(Nullable(UUID))
    display_number = Column(Nullable(String))
    dealer_company_id = Column(Nullable(UUID))
    client_company_id = Column(Nullable(UUID))
    vehicle_id = Column(Nullable(UUID))
    vehicle_price = Column(Nullable(Decimal(15, 2)))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    leasing_company_name = Column(Nullable(String))
    mark_name = Column(Nullable(String))
    model_name = Column(Nullable(String))
    vehicle_mark_id = Column(Nullable(String))
    vehicle_model_id = Column(Nullable(String))
    status = Column(Nullable(String))
    lca_status = Column(Nullable(String))
    total_amount = Column(Nullable(Decimal(15, 2)))
    down_payment = Column(Nullable(Decimal(15, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(Int32))
    monthly_payment = Column(Nullable(Decimal(12, 2)))
    total_cost = Column(Nullable(Decimal(15, 2)))
    markup = Column(Nullable(Decimal(15, 2)))
    rate = Column(Nullable(Decimal(5, 2)))
    total_interest = Column(Nullable(Decimal(15, 2)))
    buyout_amount = Column(Nullable(Decimal(15, 2)))
    vat_refund = Column(Nullable(Decimal(15, 2)))
    profit_tax_savings = Column(Nullable(Decimal(15, 2)))
    total_savings = Column(Nullable(Decimal(15, 2)))
    client_decision_action = Column(Nullable(String))
    client_decision_at = Column(Nullable(DateTime64(3)))
    kind = Column(Nullable(String))
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))


class DMDistributorSalesDCRegions(ClickHouseBase):
    __tablename__ = "dm_distributor_sales_dc_regions"
    __table_args__ = (
        engines.SummingMergeTree(
            order_by=[
                "dealer_id",
                "dealer_region",
                "created_at",
                "application_id",
                "application_vehicle_id",
            ],
        ),
    )

    application_id = Column(UUID, primary_key=True)
    application_vehicle_id = Column(UUID, primary_key=True)
    vehicle_id = Column(Nullable(UUID))
    leasing_company_id = Column(Nullable(UUID))
    dealer_id = Column(Nullable(UUID))
    dealer_name = Column(Nullable(String))
    dealer_city = Column(Nullable(String))
    dealer_region = Column(Nullable(String))
    mark_id = Column(Nullable(String))
    model_id = Column(Nullable(String))
    vin = Column(Nullable(String))
    quantity = Column(Nullable(Int32))
    unit_price = Column(Nullable(Decimal(15, 2)))
    total_price = Column(Nullable(Decimal(15, 2)))
    year = Column(Nullable(Int32))
    base_price = Column(Nullable(Decimal(12, 2)))
    special_price = Column(Nullable(Decimal(12, 2)))
    discount_price = Column(Nullable(Decimal(12, 2)))
    color = Column(Nullable(String))
    application_status = Column(Nullable(String))
    lca_status = Column(Nullable(String))
    application_total_amount = Column(Nullable(Decimal(15, 2)))
    down_payment = Column(Nullable(Decimal(15, 2)))
    down_payment_percent = Column(Nullable(Decimal(5, 2)))
    lease_term_months = Column(Nullable(Int32))
    monthly_payment = Column(Nullable(Decimal(12, 2)))
    is_model_order = Column(UInt8, default=0)
    created_at = Column(Nullable(DateTime64(3)))
    updated_at = Column(DateTime64(3))


# ---------------------------------------------------------------------------
# Audit / history tables
# ---------------------------------------------------------------------------


class DWHLcaStatusHistory(ClickHouseBase):
    __tablename__ = "dwh_lca_status_history"

    event_id = Column(UUID, primary_key=True)
    lca_id = Column(UUID)
    application_id = Column(Nullable(UUID))
    old_status = Column(Nullable(String))
    new_status = Column(String)
    changed_at = Column(DateTime64(3, timezone="UTC"))
    changed_by = Column(Nullable(UUID))
    reason = Column(Nullable(String))
    application_created_at = Column(
        Nullable(DateTime64(3, timezone="UTC"))
    )
    lca_created_at = Column(DateTime64(3, timezone="UTC"))
    dealer_company_id = Column(Nullable(UUID))
    distributor_id = Column(Nullable(UUID))
    leasing_company_id = Column(Nullable(UUID))
    is_baseline = Column(UInt8, default=0)
    ingested_at = Column(DateTime64(3, timezone="UTC"))
    __table_args__ = (
        engines.ReplacingMergeTree(
            version=ingested_at,
            partition_by=func.toYYYYMM(changed_at),
            order_by=[lca_id, changed_at, event_id],
        ),
    )


class AuthAuditLog(ClickHouseBase):
    __tablename__ = "auth_audit_log"
    __table_args__ = (
        engines.MergeTree(order_by=["event", "timestamp"]),
    )

    event = Column(String, primary_key=True)
    timestamp = Column(DateTime64(3))
    user_id = Column(Nullable(UUID))
    phone = Column(Nullable(String))
    payload = Column(String)


# ClickHouse 26 rejects nullable sorting keys unless the table opts in. Several
# historical DWH keys are intentionally nullable, so keep SQLAlchemy-created
# tables aligned with the hand-written DDL in ``clickhouse_dwh.py``.
for _table in ClickHouseBase.metadata.tables.values():
    _engine = getattr(_table, "engine", None)
    if isinstance(_engine, engines.MergeTree):
        _engine.settings.setdefault("allow_nullable_key", 1)
        _engine.settings.setdefault("index_granularity", 8192)
