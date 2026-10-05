"""Reconcile missing database defaults and preserve notification read history.

Revision ID: 112
Revises: 111
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "112"
down_revision: str | None = "111"
branch_labels: str | None = None
depends_on: str | None = None

# Frozen schema contract audited after base -> 111. Do not import live models:
# future ORM changes must not change what this historical revision installs.
# These 112 columns had no database default. Existing UUID defaults on
# application_applied_supports, catalog_storefronts, compensation_templates and
# support_program_compatibilities are deliberately outside this revision.
_SERVER_DEFAULTS: tuple[tuple[str, str, str], ...] = (
    ("accounting_metadata", "fetch_status", "'pending'"),
    ("accounting_metadata", "fetch_attempts", "0"),
    ("accounting_metadata", "is_active", "true"),
    ("accounting_reports", "fetch_status", "'pending'"),
    ("accounting_reports", "fetch_attempts", "0"),
    ("application_document_requests", "status", "'requested'"),
    ("application_document_requests", "is_required", "true"),
    ("application_documents", "status", "'submitted'"),
    ("application_documents", "auto_approved", "false"),
    ("application_questionnaires", "legal_address_matches_registration", "true"),
    ("application_questionnaires", "director_actual_same_as_registration", "false"),
    ("application_questionnaires", "founders", "'[]'"),
    ("application_questionnaires", "beneficiaries", "'[]'"),
    ("application_questionnaires", "has_beneficiary", "false"),
    ("application_questionnaires", "other_representatives", "'[]'"),
    ("application_questionnaires", "management_bodies", "'[]'"),
    ("application_vehicles", "quantity", "1"),
    ("application_vehicles", "is_model_order", "false"),
    ("balance_sheet", "period_code", "34"),
    ("balance_sheet", "source_type", "'api_fns'"),
    ("balance_sheet", "is_active", "true"),
    ("calculation_history", "buyout_amount", "0"),
    ("capital_changes", "period_code", "34"),
    ("capital_changes", "source_type", "'api_fns'"),
    ("capital_changes", "is_active", "true"),
    ("cash_flow", "period_code", "34"),
    ("cash_flow", "source_type", "'api_fns'"),
    ("cash_flow", "is_active", "true"),
    ("catalog_import_jobs", "status", "'queued'"),
    ("client_profiles", "notification_settings", "'{}'"),
    ("client_profiles", "two_factor_enabled", "false"),
    ("companies", "is_active", "true"),
    ("companies", "enrichment_attempts", "0"),
    ("compensations", "calculation_base_amount", "0"),
    ("compensations", "amount", "0"),
    ("compensations", "documents", "'[]'"),
    ("dealer_options", "sort_order", "'0'"),
    ("dealer_options", "is_active", "true"),
    ("distributors", "is_active", "true"),
    ("document_leasing_company_approvals", "status", "'pending'"),
    ("document_types", "is_required_for_all", "false"),
    ("document_types", "max_file_size_mb", "10"),
    ("document_types", "auto_approve", "false"),
    ("documents", "is_required", "false"),
    ("documents", "status", "'not_uploaded'"),
    ("documents", "version", "1"),
    ("documents", "is_current_version", "true"),
    ("documents", "leasing_company_status", "'pending'"),
    ("email_preferences", "application_status_emails", "true"),
    ("email_preferences", "document_request_emails", "true"),
    ("email_preferences", "document_status_emails", "true"),
    ("email_preferences", "leasing_approval_emails", "true"),
    ("email_preferences", "system_emails", "true"),
    ("email_preferences", "weekly_digest", "true"),
    ("email_preferences", "marketing_emails", "false"),
    ("email_preferences", "email_frequency", "'immediate'"),
    ("exchange_cart_items", "quantity", "'1'"),
    ("exchange_request_files", "file_type", "'kp'"),
    ("exchange_requests", "quantity", "'1'"),
    ("exchange_requests", "status", "'open'"),
    ("featured_vehicles", "position", "'0'"),
    ("featured_vehicles", "is_active", "true"),
    ("financial_result", "period_code", "34"),
    ("financial_result", "source_type", "'api_fns'"),
    ("financial_result", "is_active", "true"),
    ("leasing_application_vehicle_calculations", "quantity", "1"),
    ("leasing_application_vehicle_calculations", "sort_order", "0"),
    ("leasing_applications", "status", "'active'"),
    ("leasing_applications", "buyout_amount", "0"),
    ("leasing_applications", "questionnaire_completed", "false"),
    ("leasing_applications", "questionnaire_progress", "0"),
    ("leasing_applications", "current_stage", "'leasing_companies'"),
    ("leasing_companies", "average_down_payment_percent", "30"),
    ("leasing_companies", "average_lease_term_months", "72"),
    ("leasing_companies", "average_markup_percent", "10.0"),
    ("leasing_companies", "min_down_payment_percent", "10"),
    ("leasing_companies", "max_lease_term_months", "84"),
    ("leasing_companies", "is_active", "true"),
    ("leasing_company_applications", "status", "'under_review'"),
    ("leasing_company_document_requirements", "is_required", "true"),
    ("leasing_company_document_requirements", "is_mandatory", "false"),
    ("leasing_company_document_requirements", "sort_order", "0"),
    ("leasing_company_document_requirements", "is_active", "true"),
    ("leasing_payment_schedule", "is_paid", "false"),
    ("magic_links", "purpose", "'activation'"),
    ("model", "category", "'B (Легковые автомобили)'"),
    ("nds_declaration", "period_code", "34"),
    ("nds_declaration", "total_tax_payable", "0"),
    ("nds_declaration", "total_deductions", "0"),
    ("nds_declaration", "source_type", "'xml_file'"),
    ("nds_declaration", "is_active", "true"),
    ("nds_tax_rates", "is_active", "true"),
    ("notifications", "is_read", "false"),
    ("payments", "status", "'processing'"),
    ("payments", "fiscal_retry_count", "0"),
    ("purchase_orders", "status", "'reserved'"),
    ("purchase_orders", "paid_amount", "0"),
    ("purchase_orders", "remaining_amount", "0"),
    ("report_codes", "is_active", "true"),
    ("report_types", "is_active", "true"),
    ("shopping_cart", "quantity", "1"),
    ("shopping_cart", "is_selected", "true"),
    ("signature_requests", "status", "'pending'"),
    ("special_equipment_products", "condition", "'used'"),
    ("special_equipment_trims", "id", "gen_random_uuid()"),
    ("support_programs", "support_params", "'{}'"),
    ("support_programs", "show_to_leasing_company", "true"),
    ("support_programs", "show_to_client", "true"),
    ("users", "is_active", "true"),
    ("users", "email_verified", "false"),
    ("users", "phone_verified", "false"),
    ("users", "mfa_enabled", "false"),
)


def upgrade() -> None:
    for table, column, default in _SERVER_DEFAULTS:
        op.alter_column(table, column, server_default=sa.text(default))

    # Repair only the ambiguous legacy flag, preserving both explicit flags and
    # the read_at fact. Other historical NULL values are intentionally untouched.
    op.execute(sa.text(
        "UPDATE notifications SET is_read = (read_at IS NOT NULL) "
        "WHERE is_read IS NULL"
    ))


def downgrade() -> None:
    for table, column, _default in reversed(_SERVER_DEFAULTS):
        op.alter_column(table, column, server_default=None)
    # Read history is not reversible: never turn repaired flags back into NULL.
