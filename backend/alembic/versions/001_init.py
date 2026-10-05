"""Squashed init migration with UUID PK.

Revision ID: 001
Revises:
Create Date: 2026-05-20
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID, insert as pg_insert


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables from pre-generated DDL extracted from ORM models."""
    connection = op.get_bind()
    connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    op.create_table(
        'balance_sheet',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_inn', sa.String(12), nullable=False),
    sa.Column('company_kpp', sa.String(9), nullable=True),
    sa.Column('company_name', sa.String(255), nullable=True),
    sa.Column('report_year', sa.Integer(), nullable=False),
    sa.Column('period_code', sa.SmallInteger(), nullable=False, default=34),
    sa.Column('period_name', sa.String(20), nullable=True),
    sa.Column('load_date', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('line_code', sa.String(10), nullable=False),
    sa.Column('line_name', sa.String(255), nullable=True),
    sa.Column('okei_code', sa.String(3), nullable=True),
    sa.Column('amount', sa.Numeric(20, 2), nullable=True),
    sa.Column('amount_prev', sa.Numeric(20, 2), nullable=True),
    sa.Column('amount_before_prev', sa.Numeric(20, 2), nullable=True),
    sa.Column('source_type', sa.String(20), nullable=False, default='api_fns'),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('xml_raw', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['superseded_by'], ['balance_sheet.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'capital_changes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_inn', sa.String(12), nullable=False),
    sa.Column('company_kpp', sa.String(9), nullable=True),
    sa.Column('company_name', sa.String(255), nullable=True),
    sa.Column('report_year', sa.Integer(), nullable=False),
    sa.Column('period_code', sa.SmallInteger(), nullable=False, default=34),
    sa.Column('period_name', sa.String(20), nullable=True),
    sa.Column('load_date', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('line_code', sa.String(10), nullable=False),
    sa.Column('line_name', sa.String(255), nullable=True),
    sa.Column('component_code', sa.String(20), nullable=True),
    sa.Column('component_name', sa.String(255), nullable=True),
    sa.Column('okei_code', sa.String(3), nullable=True),
    sa.Column('amount', sa.Numeric(20, 2), nullable=True),
    sa.Column('amount_prev', sa.Numeric(20, 2), nullable=True),
    sa.Column('source_type', sa.String(20), nullable=False, default='api_fns'),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('xml_raw', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['superseded_by'], ['capital_changes.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'cash_flow',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_inn', sa.String(12), nullable=False),
    sa.Column('company_kpp', sa.String(9), nullable=True),
    sa.Column('company_name', sa.String(255), nullable=True),
    sa.Column('report_year', sa.Integer(), nullable=False),
    sa.Column('period_code', sa.SmallInteger(), nullable=False, default=34),
    sa.Column('period_name', sa.String(20), nullable=True),
    sa.Column('load_date', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('line_code', sa.String(10), nullable=False),
    sa.Column('line_name', sa.String(255), nullable=True),
    sa.Column('okei_code', sa.String(3), nullable=True),
    sa.Column('amount', sa.Numeric(20, 2), nullable=True),
    sa.Column('amount_prev', sa.Numeric(20, 2), nullable=True),
    sa.Column('source_type', sa.String(20), nullable=False, default='api_fns'),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('xml_raw', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['superseded_by'], ['cash_flow.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'catalog_import_jobs',
    sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('GEN_RANDOM_UUID()')),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('s3_key', sa.String(500), nullable=False),
    sa.Column('filename', sa.String(500), nullable=True),
    sa.Column('status', sa.String(20), nullable=False, default='queued'),
    sa.Column('rows_total', sa.Integer(), nullable=False, default='0'),
    sa.Column('rows_done', sa.Integer(), nullable=False, default='0'),
    sa.Column('images_total', sa.Integer(), nullable=False, default='0'),
    sa.Column('images_done', sa.Integer(), nullable=False, default='0'),
    sa.Column('images_failed', sa.Integer(), nullable=False, default='0'),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'cities',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'companies',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(500), nullable=False),
    sa.Column('inn', sa.String(20), nullable=True),
    sa.Column('kpp', sa.String(20), nullable=True),
    sa.Column('ogrn', sa.String(20), nullable=True),
    sa.Column('company_type', sa.Enum("dealer", "leasing_company", "distributor", "other", name="company_type", create_type=True), nullable=False),
    sa.Column('address', sa.JSON(), nullable=True),
    sa.Column('contact_info', sa.JSON(), nullable=True),
    sa.Column('legal_address', sa.Text(), nullable=True),
    sa.Column('actual_address', sa.Text(), nullable=True),
    sa.Column('phone', sa.String(255), nullable=True),
    sa.Column('email', sa.String(255), nullable=True),
    sa.Column('website', sa.String(255), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('full_name', sa.Text(), nullable=True),
    sa.Column('short_name', sa.String(255), nullable=True),
    sa.Column('okpo', sa.String(10), nullable=True),
    sa.Column('okato', sa.String(20), nullable=True),
    sa.Column('legal_form', sa.String(255), nullable=True),
    sa.Column('region', sa.String(100), nullable=True),
    sa.Column('city', sa.String(255), nullable=True),
    sa.Column('legal_address_details', sa.JSON(), nullable=True),
    sa.Column('registration_date', sa.Date(), nullable=True),
    sa.Column('registration_department', sa.Text(), nullable=True),
    sa.Column('employees_count', sa.Integer(), nullable=True),
    sa.Column('main_okved_code', sa.String(20), nullable=True),
    sa.Column('main_okved_description', sa.Text(), nullable=True),
    sa.Column('additional_okved_code', sa.String(20), nullable=True),
    sa.Column('additional_okved_description', sa.Text(), nullable=True),
    sa.Column('additional_okved_list', sa.JSON(), nullable=True),
    sa.Column('director_full_name', sa.String(255), nullable=True),
    sa.Column('director_position', sa.String(255), nullable=True),
    sa.Column('director_inn', sa.String(12), nullable=True),
    sa.Column('founders', sa.JSON(), nullable=True),
    sa.Column('bank_bik', sa.String(9), nullable=True),
    sa.Column('bank_name', sa.String(255), nullable=True),
    sa.Column('bank_account_number', sa.String(20), nullable=True),
    sa.Column('authorized_capital', sa.BigInteger(), nullable=True),
    sa.Column('net_profit', sa.BigInteger(), nullable=True),
    sa.Column('reporting_year', sa.Integer(), nullable=True),
    sa.Column('tax_system', sa.String(50), nullable=True),
    sa.Column('enrichment_status', sa.String(20), nullable=True),
    sa.Column('enrichment_attempts', sa.Integer(), nullable=True, default=0),
    sa.Column('enrichment_last_error', sa.Text(), nullable=True),
    sa.Column('enrichment_last_fetch_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'dealer_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'dealer_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False, default='0'),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'document_types',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('type_code', sa.String(100), nullable=True),
    sa.Column('display_name', sa.String(255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_required_for_all', sa.Boolean(), nullable=True, default=False),
    sa.Column('file_types', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('max_file_size_mb', sa.Integer(), nullable=True, default=10),
    sa.Column('validation_rules', sa.JSON(), nullable=True),
    sa.Column('auto_approve', sa.Boolean(), nullable=True, default=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'financial_result',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_inn', sa.String(12), nullable=False),
    sa.Column('company_kpp', sa.String(9), nullable=True),
    sa.Column('company_name', sa.String(255), nullable=True),
    sa.Column('report_year', sa.Integer(), nullable=False),
    sa.Column('period_code', sa.SmallInteger(), nullable=False, default=34),
    sa.Column('period_name', sa.String(20), nullable=True),
    sa.Column('load_date', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('line_code', sa.String(10), nullable=False),
    sa.Column('line_name', sa.String(255), nullable=True),
    sa.Column('okei_code', sa.String(3), nullable=True),
    sa.Column('amount', sa.Numeric(20, 2), nullable=True),
    sa.Column('amount_prev', sa.Numeric(20, 2), nullable=True),
    sa.Column('source_type', sa.String(20), nullable=False, default='api_fns'),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('xml_raw', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['superseded_by'], ['financial_result.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'leasing_rates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('key_rate', sa.Float(), nullable=False),
    sa.Column('surcharge', sa.Float(), nullable=False),
    sa.Column('vat_rate', sa.Float(), nullable=False),
    sa.Column('profit_tax_rate', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'mark',
    sa.Column('id', sa.String(50), nullable=False),
    sa.Column('name', sa.String(50), nullable=True),
    sa.Column('cyrillic_name', sa.String(50), nullable=True),
    sa.Column('popular', sa.SmallInteger(), nullable=True),
    sa.Column('country', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'nds_tax_rates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('xml_tag', sa.String(50), nullable=False),
    sa.Column('tax_base_description', sa.String(255), nullable=False),
    sa.Column('tax_amount_description', sa.String(255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'report_codes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('okud', sa.String(20), nullable=False),
    sa.Column('code', sa.String(10), nullable=False),
    sa.Column('xml_tag', sa.String(50), nullable=True),
    sa.Column('name', sa.String(500), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'report_types',
    sa.Column('knd', sa.String(20), nullable=False),
    sa.Column('okud', sa.String(20), nullable=True),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('knd'),
    )

    op.create_table(
        'sopd_rendered_pdfs',
    sa.Column('template_hash', sa.String(64), nullable=False),
    sa.Column('context_hash', sa.String(64), nullable=False),
    sa.Column('s3_key', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('template_hash', 'context_hash'),
    )

    op.create_table(
        'users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(255), nullable=True),
    sa.Column('password_hash', sa.String(255), nullable=True),
    sa.Column('name', sa.String(255), nullable=True),
    sa.Column('role', sa.Enum("carcraft_employee", "dealer", "client", "leasing_company", "distributor", "external_api", name="user_role", create_type=True), nullable=True, server_default='client'),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('phone', sa.String(20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('email_verified', sa.Boolean(), nullable=True, default=False),
    sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('phone_verified', sa.Boolean(), nullable=True, default=False),
    sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mfa_enabled', sa.Boolean(), nullable=False, default=False),
    sa.Column('mfa_secret', sa.String(64), nullable=True),
    sa.Column('mfa_pending_secret', sa.String(64), nullable=True),
    sa.Column('mfa_backup_codes', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'verification_codes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(255), nullable=True),
    sa.Column('phone', sa.String(20), nullable=True),
    sa.Column('code', sa.String(6), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'accounting_metadata',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('inn', sa.String(12), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('provider_name', sa.String(40), nullable=False),
    sa.Column('period_years', sa.JSON(), nullable=True),
    sa.Column('organization', sa.JSON(), nullable=True),
    sa.Column('audit_report', sa.JSON(), nullable=True),
    sa.Column('clarification_url', sa.Text(), nullable=True),
    sa.Column('year_files', sa.JSON(), nullable=True),
    sa.Column('computed_ratios', sa.JSON(), nullable=True),
    sa.Column('fetch_status', sa.String(20), nullable=False, default='pending'),
    sa.Column('fetch_attempts', sa.Integer(), nullable=False, default=0),
    sa.Column('last_fetch_error', sa.Text(), nullable=True),
    sa.Column('last_fetch_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['superseded_by'], ['accounting_metadata.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'accounting_reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('inn', sa.String(12), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('provider_name', sa.String(40), nullable=False),
    sa.Column('period_years', sa.JSON(), nullable=True),
    sa.Column('organization', sa.JSON(), nullable=True),
    sa.Column('balance_sheet', sa.JSON(), nullable=True),
    sa.Column('financial_result', sa.JSON(), nullable=True),
    sa.Column('cash_flow', sa.JSON(), nullable=True),
    sa.Column('capital_change', sa.JSON(), nullable=True),
    sa.Column('audit_report', sa.JSON(), nullable=True),
    sa.Column('clarification_url', sa.Text(), nullable=True),
    sa.Column('year_files', sa.JSON(), nullable=True),
    sa.Column('computed_ratios', sa.JSON(), nullable=True),
    sa.Column('fetch_status', sa.String(20), nullable=False, default='pending'),
    sa.Column('fetch_attempts', sa.Integer(), nullable=False, default=0),
    sa.Column('last_fetch_error', sa.Text(), nullable=True),
    sa.Column('last_fetch_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'calculation_history',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('vehicle_ids', sa.ARRAY(sa.UUID()), nullable=True),
    sa.Column('total_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment_percent', sa.Numeric(5, 2), nullable=True),
    sa.Column('lease_term_months', sa.Integer(), nullable=True),
    sa.Column('monthly_payment', sa.Numeric(12, 2), nullable=True),
    sa.Column('total_cost', sa.Numeric(15, 2), nullable=True),
    sa.Column('markup', sa.Numeric(15, 2), nullable=True),
    sa.Column('rate', sa.Numeric(5, 2), nullable=True),
    sa.Column('total_interest', sa.Numeric(15, 2), nullable=True),
    sa.Column('buyout_amount', sa.Numeric(15, 2), nullable=True, default=0),
    sa.Column('vat_refund', sa.Numeric(15, 2), nullable=True),
    sa.Column('profit_tax_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('calculation_type', sa.String(50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )

    op.create_table(
        'client_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('client_type', sa.String(50), nullable=True),
    sa.Column('passport_series', sa.String(20), nullable=True),
    sa.Column('passport_issued_date', sa.Date(), nullable=True),
    sa.Column('passport_issued_by', sa.Text(), nullable=True),
    sa.Column('company_name', sa.String(500), nullable=True),
    sa.Column('inn', sa.String(20), nullable=True),
    sa.Column('kpp', sa.String(20), nullable=True),
    sa.Column('ogrn', sa.String(20), nullable=True),
    sa.Column('legal_address', sa.Text(), nullable=True),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('notification_settings', sa.JSON(), nullable=True, default='{}'),
    sa.Column('two_factor_enabled', sa.Boolean(), nullable=True, default=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'company_select_history',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'dealer_group_members',
    sa.Column('dealer_group_id', sa.UUID(), nullable=False),
    sa.Column('dealer_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('dealer_group_id', 'dealer_id'),
        sa.ForeignKeyConstraint(['dealer_group_id'], ['dealer_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'distributors',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('regions', sa.JSON(), nullable=True),
    sa.Column('brands', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
    )

    op.create_table(
        'email_preferences',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('application_status_emails', sa.Boolean(), nullable=False, default=True),
    sa.Column('document_request_emails', sa.Boolean(), nullable=False, default=True),
    sa.Column('document_status_emails', sa.Boolean(), nullable=False, default=True),
    sa.Column('leasing_approval_emails', sa.Boolean(), nullable=False, default=True),
    sa.Column('system_emails', sa.Boolean(), nullable=False, default=True),
    sa.Column('weekly_digest', sa.Boolean(), nullable=False, default=True),
    sa.Column('marketing_emails', sa.Boolean(), nullable=False, default=False),
    sa.Column('email_frequency', sa.String(16), nullable=False, default='immediate'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'leasing_applications',
    sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('GEN_RANDOM_UUID()')),
    sa.Column('display_number', sa.String(64), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('dealer_company_id', sa.UUID(), nullable=True),
    sa.Column('vehicle_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(255), nullable=True),
    sa.Column('email', sa.String(255), nullable=True),
    sa.Column('status', sa.Enum("active", "rejected", "issued", name="application_status", create_type=True), nullable=True, default='active'),
    sa.Column('total_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment_percent', sa.Numeric(5, 2), nullable=True),
    sa.Column('lease_term_months', sa.Integer(), nullable=True),
    sa.Column('monthly_payment', sa.Numeric(12, 2), nullable=True),
    sa.Column('total_cost', sa.Numeric(15, 2), nullable=True),
    sa.Column('markup', sa.Numeric(15, 2), nullable=True),
    sa.Column('rate', sa.Numeric(5, 2), nullable=True),
    sa.Column('total_interest', sa.Numeric(15, 2), nullable=True),
    sa.Column('buyout_amount', sa.Numeric(15, 2), nullable=True, default=0),
    sa.Column('vat_refund', sa.Numeric(15, 2), nullable=True),
    sa.Column('profit_tax_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('selected_leasing_companies', sa.ARRAY(sa.UUID()), nullable=True),
    sa.Column('leasing_company_comments', sa.Text(), nullable=True),
    sa.Column('requested_documents', sa.JSON(), nullable=True),
    sa.Column('comments_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('documents_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('client_visible_comment', sa.Text(), nullable=True),
    sa.Column('client_comment_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('questionnaire_completed', sa.Boolean(), nullable=True, default=False),
    sa.Column('questionnaire_progress', sa.Integer(), nullable=True, default=0),
    sa.Column('current_stage', sa.String(50), nullable=True, default='leasing_companies'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('group_id', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['dealer_company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['group_id'], ['leasing_applications.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'leasing_calculations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('calculation', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'leasing_companies',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('average_down_payment_percent', sa.Integer(), nullable=True, default=30),
    sa.Column('average_lease_term_months', sa.Integer(), nullable=True, default=72),
    sa.Column('average_markup_percent', sa.Numeric(5, 2), nullable=True, default=10.0),
    sa.Column('min_down_payment_percent', sa.Integer(), nullable=True, default=10),
    sa.Column('max_lease_term_months', sa.Integer(), nullable=True, default=84),
    sa.Column('special_offers', sa.JSON(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
    )

    op.create_table(
        'magic_links',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('token', sa.String(64), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.String(32), nullable=False, default='activation'),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'model',
    sa.Column('id', sa.String(50), nullable=False),
    sa.Column('name', sa.String(50), nullable=True),
    sa.Column('cyrillic_name', sa.String(50), nullable=True),
    sa.Column('class', sa.String(5), nullable=True),
    sa.Column('year_from', sa.SmallInteger(), nullable=True),
    sa.Column('year_to', sa.SmallInteger(), nullable=True),
    sa.Column('mark_id', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'nds_declaration',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_inn', sa.String(12), nullable=False),
    sa.Column('company_kpp', sa.String(9), nullable=True),
    sa.Column('company_name', sa.String(255), nullable=True),
    sa.Column('report_year', sa.Integer(), nullable=False),
    sa.Column('period_code', sa.SmallInteger(), nullable=False, default=34),
    sa.Column('period_name', sa.String(20), nullable=True),
    sa.Column('load_date', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('tax_rate_id', sa.UUID(), nullable=False),
    sa.Column('tax_base', sa.Numeric(20, 2), nullable=True),
    sa.Column('tax_amount', sa.Numeric(20, 2), nullable=True),
    sa.Column('total_tax_payable', sa.Numeric(20, 2), nullable=False, default=0),
    sa.Column('total_deductions', sa.Numeric(20, 2), nullable=False, default=0),
    sa.Column('total_recovered', sa.Numeric(20, 2), nullable=True),
    sa.Column('source_type', sa.String(10), nullable=False, default='xml_file'),
    sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
    sa.Column('superseded_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tax_rate_id'], ['nds_tax_rates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['superseded_by'], ['nds_declaration.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'shopping_cart',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('modification_id', sa.String(100), nullable=True),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False, default=1),
    sa.Column('is_selected', sa.Boolean(), nullable=True, default=True),
    sa.Column('custom_price', sa.Numeric(15, 2), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'user_companies',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('user_id', 'company_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'user_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('refresh_token_hash', sa.String(255), nullable=False),
    sa.Column('ip_address', sa.String(45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('country_code', sa.String(2), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'vehicles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vin', sa.String(20), nullable=True),
    sa.Column('dealer_id', sa.UUID(), nullable=True),
    sa.Column('mark_id', sa.String(50), nullable=True),
    sa.Column('model_id', sa.String(50), nullable=True),
    sa.Column('generation_id', sa.String(50), nullable=True),
    sa.Column('configuration_id', sa.String(50), nullable=True),
    sa.Column('complectation_id', sa.String(50), nullable=True),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('base_price', sa.Numeric(12, 2), nullable=True),
    sa.Column('special_price', sa.Numeric(12, 2), nullable=True),
    sa.Column('dealer_cost', sa.Numeric(12, 2), nullable=True),
    sa.Column('discount_price', sa.Numeric(12, 2), nullable=True),
    sa.Column('color', sa.String(100), nullable=True),
    sa.Column('color_inter', sa.String(100), nullable=True),
    sa.Column('images', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(50), nullable=True, default='available'),
    sa.Column('is_available', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['dealer_id'], ['companies.id']),
    )

    op.create_table(
        'warehouses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('address', sa.String(500), nullable=False),
    sa.Column('brand', sa.String(100), nullable=False),
    sa.Column('city_id', sa.UUID(), nullable=True),
    sa.Column('dealer_id', sa.UUID(), nullable=True),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(20), nullable=True, default='active'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['city_id'], ['cities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dealer_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'application_document_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('leasing_company_id', sa.UUID(), nullable=False),
    sa.Column('document_type', sa.String(100), nullable=False),
    sa.Column('status', sa.String(50), nullable=True, default='requested'),
    sa.Column('is_required', sa.Boolean(), nullable=True, default=True),
    sa.Column('request_message', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('provided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
    )

    op.create_table(
        'application_questionnaires',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('full_company_name', sa.String(500), nullable=True),
    sa.Column('short_company_name', sa.String(255), nullable=True),
    sa.Column('inn', sa.String(20), nullable=True),
    sa.Column('ogrn', sa.String(20), nullable=True),
    sa.Column('kpp', sa.String(20), nullable=True),
    sa.Column('okpo', sa.String(20), nullable=True),
    sa.Column('okato', sa.String(20), nullable=True),
    sa.Column('okved_main', sa.String(500), nullable=True),
    sa.Column('okved_additional', sa.Text(), nullable=True),
    sa.Column('tax_system', sa.String(50), nullable=True),
    sa.Column('legal_form', sa.String(100), nullable=True),
    sa.Column('legal_address', sa.Text(), nullable=True),
    sa.Column('legal_address_matches_registration', sa.Boolean(), nullable=True, default=True),
    sa.Column('actual_address', sa.Text(), nullable=True),
    sa.Column('actual_address_details', sa.Text(), nullable=True),
    sa.Column('postal_address', sa.Text(), nullable=True),
    sa.Column('phone', sa.String(50), nullable=True),
    sa.Column('fax', sa.String(50), nullable=True),
    sa.Column('email', sa.String(255), nullable=True),
    sa.Column('website', sa.String(255), nullable=True),
    sa.Column('bank_name', sa.String(255), nullable=True),
    sa.Column('bik', sa.String(20), nullable=True),
    sa.Column('settlement_account', sa.String(50), nullable=True),
    sa.Column('director_full_name', sa.String(255), nullable=True),
    sa.Column('director_position', sa.String(100), nullable=True),
    sa.Column('director_passport_series', sa.String(10), nullable=True),
    sa.Column('director_passport_number', sa.String(20), nullable=True),
    sa.Column('director_passport_issued_by', sa.Text(), nullable=True),
    sa.Column('director_passport_issue_date', sa.Date(), nullable=True),
    sa.Column('director_passport_department_code', sa.String(10), nullable=True),
    sa.Column('director_birth_date', sa.Date(), nullable=True),
    sa.Column('director_birth_place', sa.Text(), nullable=True),
    sa.Column('director_citizenship', sa.String(100), nullable=True),
    sa.Column('director_registration_address', sa.Text(), nullable=True),
    sa.Column('director_actual_address', sa.Text(), nullable=True),
    sa.Column('director_phone', sa.String(50), nullable=True),
    sa.Column('director_email', sa.String(255), nullable=True),
    sa.Column('director_surname', sa.String(100), nullable=True),
    sa.Column('director_first_name', sa.String(100), nullable=True),
    sa.Column('director_patronymic', sa.String(100), nullable=True),
    sa.Column('director_sex', sa.String(20), nullable=True),
    sa.Column('director_birth_country', sa.String(100), nullable=True),
    sa.Column('director_registration_country', sa.String(100), nullable=True),
    sa.Column('director_registration_postal_code', sa.String(10), nullable=True),
    sa.Column('director_registration_house', sa.String(50), nullable=True),
    sa.Column('director_registration_apartment', sa.String(50), nullable=True),
    sa.Column('director_registration_date', sa.Date(), nullable=True),
    sa.Column('director_actual_country', sa.String(100), nullable=True),
    sa.Column('director_actual_postal_code', sa.String(10), nullable=True),
    sa.Column('director_actual_house', sa.String(50), nullable=True),
    sa.Column('director_actual_apartment', sa.String(50), nullable=True),
    sa.Column('director_actual_same_as_registration', sa.Boolean(), nullable=True, default=False),
    sa.Column('founders', sa.JSON(), nullable=True, default='[]'),
    sa.Column('beneficiaries', sa.JSON(), nullable=True, default='[]'),
    sa.Column('has_beneficiary', sa.Boolean(), nullable=True, default=False),
    sa.Column('other_representatives', sa.JSON(), nullable=True, default='[]'),
    sa.Column('beneficiary_info', sa.Text(), nullable=True),
    sa.Column('management_bodies', sa.JSON(), nullable=True, default='[]'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'application_vehicles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=True),
    sa.Column('modification_id', sa.String(100), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=True, default=1),
    sa.Column('unit_price', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_price', sa.Numeric(15, 2), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('vin', sa.String(50), nullable=True),
    sa.Column('vin_assigned_by', sa.UUID(), nullable=True),
    sa.Column('vin_assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_model_order', sa.Boolean(), nullable=True, default=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
    )

    op.create_table(
        'compensations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('applied_support_id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('vehicle_id', sa.UUID(), nullable=True),
    sa.Column('payer', sa.Enum("distributor", "dealer", "carcraft", "minpromtorg", "client", name="payer_type", create_type=True), nullable=False),
    sa.Column('recipient', sa.Enum("leasing_company", "dealer", "carcraft", name="recipient_type", create_type=True), nullable=False),
    sa.Column('calculation_base', sa.Enum("base_price", "special_price", "dealer_cost", "application_price", "down_payment", "support_amount", name="calculation_base", create_type=True), nullable=False),
    sa.Column('calculation_base_amount', sa.Numeric(15, 2), nullable=False, default=0),
    sa.Column('value_type', sa.Enum("percent", "sum", name="compensation_value_type", create_type=True), nullable=False),
    sa.Column('value', sa.Numeric(15, 2), nullable=False),
    sa.Column('min_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('max_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('min_percent', sa.Numeric(10, 4), nullable=True),
    sa.Column('max_percent', sa.Numeric(10, 4), nullable=True),
    sa.Column('amount', sa.Numeric(15, 2), nullable=False, default=0),
    sa.Column('status', sa.Enum("pending", "paid", "overdue", "cancelled", name="compensation_status", create_type=True), nullable=False, default='pending'),
    sa.Column('payment_schedule_type', sa.Enum("fixed_date", "days_count", "monthly", "weekly", "quarterly", name="payment_schedule_type", create_type=True), nullable=False, default='days_count'),
    sa.Column('payment_schedule_value', sa.String(50), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('documents', sa.JSON(), nullable=True, default='[]'),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('document_type', sa.String(100), nullable=False),
    sa.Column('file_path', sa.String(500), nullable=True),
    sa.Column('file_name', sa.String(255), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('s3_key', sa.String(500), nullable=True),
    sa.Column('period_label', sa.String(32), nullable=True),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('is_required', sa.Boolean(), nullable=True, default=False),
    sa.Column('status', sa.Enum("not_uploaded", "uploaded", "under_review", "verified", "requested", name="document_status", create_type=True), nullable=True, default='not_uploaded'),
    sa.Column('version', sa.Integer(), nullable=True, default=1),
    sa.Column('parent_document_id', sa.UUID(), nullable=True),
    sa.Column('is_current_version', sa.Boolean(), nullable=True, default=True),
    sa.Column('related_application_id', sa.UUID(), nullable=True),
    sa.Column('approved_by_leasing_company', sa.UUID(), nullable=True),
    sa.Column('leasing_company_status', sa.String(50), nullable=True, default='pending'),
    sa.Column('leasing_company_comments', sa.Text(), nullable=True),
    sa.Column('leasing_company_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('extracted_data', sa.JSON(), nullable=True),
    sa.Column('recognition_status', sa.String(50), nullable=True),
    sa.Column('recognition_error', sa.Text(), nullable=True),
    sa.Column('dbrain_task_id', sa.String(100), nullable=True),
    sa.Column('recognized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['parent_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['related_application_id'], ['leasing_applications.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by_leasing_company'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id']),
    )

    op.create_table(
        'exchange_cart_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False, default='1'),
    sa.Column('expiration_date', sa.Date(), nullable=True),
    sa.Column('discount_type', sa.String(20), nullable=True),
    sa.Column('discount_value', sa.Numeric(15, 2), nullable=True),
    sa.Column('file_url', sa.String(1000), nullable=True),
    sa.Column('file_name', sa.String(500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('lc_user_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('distributor_id', sa.UUID(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False, default='1'),
    sa.Column('expiration_date', sa.Date(), nullable=True),
    sa.Column('discount_type', sa.String(20), nullable=True),
    sa.Column('discount_value', sa.Numeric(15, 2), nullable=True),
    sa.Column('file_url', sa.String(1000), nullable=True),
    sa.Column('file_name', sa.String(500), nullable=True),
    sa.Column('status', sa.String(20), nullable=False, default='open'),
    sa.Column('accepted_bid_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('batch_number', sa.Integer(), nullable=True),
    sa.Column('batch_index', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['lc_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['distributor_id'], ['companies.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'featured_vehicles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('model_id', sa.String(50), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False, default='0'),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['model_id'], ['model.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'generation',
    sa.Column('id', sa.String(50), nullable=False),
    sa.Column('name', sa.String(50), nullable=True),
    sa.Column('year_start', sa.SmallInteger(), nullable=True),
    sa.Column('year_stop', sa.SmallInteger(), nullable=True),
    sa.Column('is_restyle', sa.SmallInteger(), nullable=True),
    sa.Column('model_id', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'leasing_application_calculations',
    sa.Column('leasing_application_id', sa.UUID(), nullable=False),
    sa.Column('monthly_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('rate', sa.Numeric(10, 4), nullable=True),
    sa.Column('total_cost', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_interest', sa.Numeric(15, 2), nullable=True),
    sa.Column('buyout_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('vat_refund', sa.Numeric(15, 2), nullable=True),
    sa.Column('profit_tax_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('base_total', sa.Numeric(15, 2), nullable=True),
    sa.Column('vehicle_discount_support', sa.Numeric(15, 2), nullable=True),
    sa.Column('dealer_commission_support', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment_support', sa.Numeric(15, 2), nullable=True),
    sa.Column('interest_support', sa.Numeric(15, 2), nullable=True),
    sa.Column('effective_total', sa.Numeric(15, 2), nullable=True),
    sa.Column('effective_down_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('leasing_application_id'),
        sa.ForeignKeyConstraint(['leasing_application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'leasing_application_comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('leasing_application_id', sa.UUID(), nullable=True),
    sa.Column('comment_type', sa.String(50), nullable=False),
    sa.Column('comment_text', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['leasing_application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )

    op.create_table(
        'leasing_application_vehicle_calculations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('leasing_application_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=True),
    sa.Column('modification_id', sa.String(100), nullable=True),
    sa.Column('color', sa.String(100), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False, default=1),
    sa.Column('unit_price', sa.Numeric(15, 2), nullable=False),
    sa.Column('total_amount', sa.Numeric(15, 2), nullable=False),
    sa.Column('down_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment_percent', sa.Numeric(5, 2), nullable=True),
    sa.Column('lease_term_months', sa.Integer(), nullable=True),
    sa.Column('buyout_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('monthly_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('rate', sa.Numeric(10, 4), nullable=True),
    sa.Column('total_cost', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_interest', sa.Numeric(15, 2), nullable=True),
    sa.Column('vat_refund', sa.Numeric(15, 2), nullable=True),
    sa.Column('profit_tax_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False, default=0),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['leasing_application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'leasing_company_applications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('leasing_company_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum("draft", "submitted", "under_review", "approved_scoring", "approved_scoring_another_cond", "rejected_prescoring", "documents_required", "approved_final", "approved_final_another_cond", "rejected_approved", "selected_lc", "deal", "closed", "prescoring", "issued", name="leasing_company_application_status", create_type=True), nullable=True, default='under_review'),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('decision_comment', sa.Text(), nullable=True),
    sa.Column('response_pdf_s3_key', sa.Text(), nullable=True),
    sa.Column('response_pdf_file_name', sa.String(255), nullable=True),
    sa.Column('response_pdf_size', sa.Integer(), nullable=True),
    sa.Column('response_pdf_uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id']),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id']),
    )

    op.create_table(
        'leasing_company_document_requirements',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('leasing_company_id', sa.UUID(), nullable=False),
    sa.Column('document_type_id', sa.UUID(), nullable=False),
    sa.Column('is_required', sa.Boolean(), nullable=True, default=True),
    sa.Column('is_mandatory', sa.Boolean(), nullable=True, default=False),
    sa.Column('sort_order', sa.Integer(), nullable=True, default=0),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_type_id'], ['document_types.id']),
    )

    op.create_table(
        'leasing_company_users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('leasing_company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'notifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('type', sa.Enum("application_status", "document_request", "approval", "general", "document_status", "leasing_approval", "system", "exchange_new_request", "exchange_new_bid", "exchange_bid_updated", "exchange_bid_accepted", name="notification_type", create_type=True), nullable=False),
    sa.Column('title', sa.String(500), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=True, default=False),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('action_url', sa.String(1000), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id']),
    )

    op.create_table(
        'purchase_orders',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('purchase_type', sa.Enum("reservation", "full_purchase", name="purchase_type", create_type=True), nullable=False),
    sa.Column('status', sa.Enum("reserved", "purchased", "leasing_pending", "leasing_active", "cancelled", "cancellation_requested", name="purchase_status", create_type=True), nullable=False, default='reserved'),
    sa.Column('total_price', sa.Numeric(15, 2), nullable=False),
    sa.Column('paid_amount', sa.Numeric(15, 2), nullable=False, default=0),
    sa.Column('remaining_amount', sa.Numeric(15, 2), nullable=False, default=0),
    sa.Column('leasing_application_id', sa.UUID(), nullable=True),
    sa.Column('cancellation_reason', sa.Text(), nullable=True),
    sa.Column('cancellation_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.ForeignKeyConstraint(['leasing_application_id'], ['leasing_applications.id']),
    )

    op.create_table(
        'signature_requests',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('invited_by_user_id', sa.UUID(), nullable=True),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('document_type', sa.String(100), nullable=False),
    sa.Column('status', sa.String(32), nullable=False, default='pending'),
    sa.Column('signature_method', sa.String(16), nullable=True),
    sa.Column('subject_snapshot', sa.JSON(), nullable=False),
    sa.Column('signed_pdf_s3_key', sa.Text(), nullable=True),
    sa.Column('signing_ip', sa.String(45), nullable=True),
    sa.Column('signing_user_agent', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'support_programs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('mark_id', sa.String(50), nullable=True),
    sa.Column('model_id', sa.String(50), nullable=True),
    sa.Column('model_ids', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('complectation_ids', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('vin', sa.String(50), nullable=True),
    sa.Column('vins', sa.ARRAY(sa.Text()), nullable=True),
    sa.Column('dealer_group_id', sa.UUID(), nullable=True),
    sa.Column('distributor_id', sa.UUID(), nullable=True),
    sa.Column('support_type', sa.Enum("down_payment_compensation", "vehicle_discount_dealer_compensation", "vehicle_discount_dealer_invoice", "leasing_interest_compensation", name="support_type", create_type=True), nullable=False),
    sa.Column('support_params', sa.JSON(), nullable=False, default='{}'),
    sa.Column('production_year_from', sa.Integer(), nullable=True),
    sa.Column('production_year_to', sa.Integer(), nullable=True),
    sa.Column('starts_at', sa.Date(), nullable=True),
    sa.Column('ends_at', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('show_to_leasing_company', sa.Boolean(), nullable=True, default=True),
    sa.Column('show_to_client', sa.Boolean(), nullable=True, default=True),
    sa.Column('comment', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['mark_id'], ['mark.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['model_id'], ['model.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dealer_group_id'], ['dealer_groups.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['distributor_id'], ['distributors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'user_favorites',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'vehicle_warehouses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('warehouse_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'application_documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('document_request_id', sa.UUID(), nullable=True),
    sa.Column('leasing_company_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(50), nullable=True, default='submitted'),
    sa.Column('reviewer_comments', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revision_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('auto_approved', sa.Boolean(), nullable=True, default=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_request_id'], ['application_document_requests.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
    )

    op.create_table(
        'configuration',
    sa.Column('id', sa.String(50), nullable=False),
    sa.Column('doors_count', sa.SmallInteger(), nullable=True),
    sa.Column('body_type', sa.String(50), nullable=True),
    sa.Column('configuration_name', sa.String(50), nullable=True),
    sa.Column('generation_id', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'director_doc_signing_invitations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('document_type', sa.String(100), nullable=False),
    sa.Column('period_label', sa.String(32), nullable=True),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('signature_request_id', sa.UUID(), nullable=True),
    sa.Column('director_user_id', sa.UUID(), nullable=True),
    sa.Column('director_phone', sa.String(20), nullable=True),
    sa.Column('sms_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sms_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['signature_request_id'], ['signature_requests.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['director_user_id'], ['users.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'document_applications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['application_id'], ['leasing_applications.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'document_leasing_company_approvals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('leasing_company_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(50), nullable=True, default='pending'),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
    )

    op.create_table(
        'exchange_bids',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('dealer_id', sa.UUID(), nullable=False),
    sa.Column('distributor_id', sa.UUID(), nullable=True),
    sa.Column('price', sa.Numeric(15, 2), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('is_accepted', sa.Boolean(), nullable=False, default=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('kp_file_url', sa.String(1000), nullable=True),
    sa.Column('kp_file_name', sa.String(500), nullable=True),
    sa.Column('kp_status', sa.String(20), nullable=False, default='none'),
    sa.Column('kp_dealer_comment', sa.Text(), nullable=True),
    sa.Column('kp_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('kp_responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False, default='1'),
    sa.Column('bid_file_url', sa.String(1000), nullable=True),
    sa.Column('bid_file_name', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['exchange_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['distributor_id'], ['companies.id'], ondelete='SET NULL'),
    )

    op.create_table(
        'exchange_cart_item_dealer_comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cart_item_id', sa.UUID(), nullable=False),
    sa.Column('dealer_id', sa.UUID(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cart_item_id'], ['exchange_cart_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_cart_item_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cart_item_id', sa.UUID(), nullable=False),
    sa.Column('dealer_option_id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cart_item_id'], ['exchange_cart_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_option_id'], ['dealer_options.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_cart_item_warehouses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('cart_item_id', sa.UUID(), nullable=False),
    sa.Column('warehouse_id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cart_item_id'], ['exchange_cart_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_request_dealer_comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('dealer_id', sa.UUID(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['exchange_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_request_files',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('dealer_id', sa.UUID(), nullable=True),
    sa.Column('file_url', sa.String(1000), nullable=False),
    sa.Column('file_name', sa.String(500), nullable=False),
    sa.Column('file_type', sa.String(50), nullable=False, default='kp'),
    sa.Column('uploaded_by', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['exchange_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
    )

    op.create_table(
        'exchange_request_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('dealer_option_id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['exchange_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_option_id'], ['dealer_options.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_request_warehouses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('warehouse_id', sa.UUID(), nullable=False),
    sa.Column('dealer_id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['request_id'], ['exchange_requests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_id'], ['users.id']),
    )

    op.create_table(
        'leasing_proposals',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('leasing_company_application_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.Enum("preliminary", "final", name="leasing_proposal_kind", create_type=True), nullable=False, default='preliminary'),
    sa.Column('position', sa.Integer(), nullable=False, default=1),
    sa.Column('total_amount', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment', sa.Numeric(15, 2), nullable=True),
    sa.Column('down_payment_percent', sa.Numeric(5, 2), nullable=True),
    sa.Column('lease_term_months', sa.Integer(), nullable=True),
    sa.Column('monthly_payment', sa.Numeric(12, 2), nullable=True),
    sa.Column('total_cost', sa.Numeric(15, 2), nullable=True),
    sa.Column('markup', sa.Numeric(15, 2), nullable=True),
    sa.Column('rate', sa.Numeric(5, 2), nullable=True),
    sa.Column('total_interest', sa.Numeric(15, 2), nullable=True),
    sa.Column('buyout_amount', sa.Numeric(15, 2), nullable=True, default=0),
    sa.Column('vat_refund', sa.Numeric(15, 2), nullable=True),
    sa.Column('profit_tax_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('total_savings', sa.Numeric(15, 2), nullable=True),
    sa.Column('client_decision_action', sa.String(16), nullable=True),
    sa.Column('client_decision_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('client_decision_comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['leasing_company_application_id'], ['leasing_company_applications.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'passport_recognition_data',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('file_hash', sa.String(64), nullable=False),
    sa.Column('passport_type', sa.String(50), nullable=False),
    sa.Column('raw_data', sa.JSON(), nullable=False),
    sa.Column('mapped_data', sa.JSON(), nullable=False),
    sa.Column('confidence_data', sa.JSON(), nullable=False),
    sa.Column('dbrain_task_id', sa.String(100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'payments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('purchase_order_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('payment_type', sa.Enum("reservation", "remaining_balance", "full_purchase", "leasing_monthly", name="payment_type", create_type=True), nullable=False),
    sa.Column('amount', sa.Numeric(15, 2), nullable=False),
    sa.Column('status', sa.Enum("processing", "completed", "error", "pending_payment", "failed", name="payment_status", create_type=True), nullable=False, default='processing'),
    sa.Column('gateway_transaction_id', sa.String(255), nullable=True),
    sa.Column('gateway_response', sa.JSON(), nullable=True),
    sa.Column('receipt_url', sa.String(500), nullable=True),
    sa.Column('receipt_s3_key', sa.String(500), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
    sa.Column('payment_method', sa.String(20), nullable=True),
    sa.Column('fiscal_status', sa.String(30), nullable=True),
    sa.Column('fiscal_receipt_id', sa.String(255), nullable=True),
    sa.Column('fiscal_response', sa.JSON(), nullable=True),
    sa.Column('fiscal_retry_count', sa.Integer(), nullable=True, default=0),
    sa.Column('fiscal_error_message', sa.Text(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )

    op.create_table(
        'support_bill_of_ladings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('support_program_id', sa.UUID(), nullable=False),
    sa.Column('bill_date', sa.Date(), nullable=True),
    sa.Column('file_name', sa.String(255), nullable=True),
    sa.Column('file_path', sa.Text(), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['support_program_id'], ['support_programs.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'support_program_dealer_groups',
    sa.Column('support_program_id', sa.UUID(), nullable=False),
    sa.Column('dealer_group_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('support_program_id', 'dealer_group_id'),
        sa.ForeignKeyConstraint(['support_program_id'], ['support_programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_group_id'], ['dealer_groups.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'support_program_leasing_companies',
    sa.Column('support_program_id', sa.UUID(), nullable=False),
    sa.Column('leasing_company_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('support_program_id', 'leasing_company_id'),
        sa.ForeignKeyConstraint(['support_program_id'], ['support_programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['leasing_company_id'], ['leasing_companies.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_bid_comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('bid_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bid_id'], ['exchange_bids.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'exchange_bid_options',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('bid_id', sa.UUID(), nullable=False),
    sa.Column('dealer_option_id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['bid_id'], ['exchange_bids.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dealer_option_id'], ['dealer_options.id'], ondelete='CASCADE'),
    )

    op.create_table(
        'leasing_payment_schedule',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('purchase_order_id', sa.UUID(), nullable=False),
    sa.Column('payment_number', sa.Integer(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(15, 2), nullable=False),
    sa.Column('principal', sa.Numeric(15, 2), nullable=True),
    sa.Column('interest', sa.Numeric(15, 2), nullable=True),
    sa.Column('payment_id', sa.UUID(), nullable=True),
    sa.Column('is_paid', sa.Boolean(), nullable=True, default=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
    )

    op.create_table(
        'modification',
    sa.Column('complectation_id', sa.String(50), nullable=False),
    sa.Column('offers_price_from', sa.Numeric(12, 2), nullable=True),
    sa.Column('offers_price_to', sa.Numeric(12, 2), nullable=True),
    sa.Column('group_name', sa.String(100), nullable=True),
    sa.Column('configuration_id', sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint('complectation_id'),
    )

    op.create_table(
        'options',
    sa.Column('complectation_id', sa.String(50), nullable=False),
    sa.Column('alcantara', sa.String(100), nullable=True),
    sa.Column('black_roof', sa.String(100), nullable=True),
    sa.Column('combo_interior', sa.String(100), nullable=True),
    sa.Column('decorative_interior_lighting', sa.String(100), nullable=True),
    sa.Column('door_sill_panel', sa.String(100), nullable=True),
    sa.Column('driver_seat_electric', sa.String(100), nullable=True),
    sa.Column('driver_seat_memory', sa.String(100), nullable=True),
    sa.Column('driver_seat_support', sa.String(100), nullable=True),
    sa.Column('driver_seat_updown', sa.String(100), nullable=True),
    sa.Column('eco_leather', sa.String(100), nullable=True),
    sa.Column('electro_rear_seat', sa.String(100), nullable=True),
    sa.Column('fabric_seats', sa.String(100), nullable=True),
    sa.Column('folding_front_passenger_seat', sa.String(100), nullable=True),
    sa.Column('folding_tables_rear', sa.String(100), nullable=True),
    sa.Column('front_centre_armrest', sa.String(100), nullable=True),
    sa.Column('front_seat_support', sa.String(100), nullable=True),
    sa.Column('front_seats_heat', sa.String(100), nullable=True),
    sa.Column('front_seats_heat_vent', sa.String(100), nullable=True),
    sa.Column('hatch', sa.String(100), nullable=True),
    sa.Column('leather', sa.String(100), nullable=True),
    sa.Column('leather_gear_stick', sa.String(100), nullable=True),
    sa.Column('massage_seats', sa.String(100), nullable=True),
    sa.Column('panorama_roof', sa.String(100), nullable=True),
    sa.Column('passenger_seat_electric', sa.String(100), nullable=True),
    sa.Column('passenger_seat_updown', sa.String(100), nullable=True),
    sa.Column('rear_seat_heat_vent', sa.String(100), nullable=True),
    sa.Column('rear_seat_memory', sa.String(100), nullable=True),
    sa.Column('rear_seats_heat', sa.String(100), nullable=True),
    sa.Column('roller_blind_for_rear_window', sa.String(100), nullable=True),
    sa.Column('roller_blinds_for_rear_side_windows', sa.String(100), nullable=True),
    sa.Column('seat_memory', sa.String(100), nullable=True),
    sa.Column('seat_transformation', sa.String(100), nullable=True),
    sa.Column('sport_pedals', sa.String(100), nullable=True),
    sa.Column('sport_seats', sa.String(100), nullable=True),
    sa.Column('third_rear_headrest', sa.String(100), nullable=True),
    sa.Column('third_row_seats', sa.String(100), nullable=True),
    sa.Column('tinted_glass', sa.String(100), nullable=True),
    sa.Column('wheel_heat', sa.String(100), nullable=True),
    sa.Column('wheel_leather', sa.String(100), nullable=True),
    sa.Column('camera_360', sa.String(100), nullable=True),
    sa.Column('adj_pedals', sa.String(100), nullable=True),
    sa.Column('auto_cruise', sa.String(100), nullable=True),
    sa.Column('auto_mirrors', sa.String(100), nullable=True),
    sa.Column('auto_park', sa.String(100), nullable=True),
    sa.Column('climate_control_1', sa.String(100), nullable=True),
    sa.Column('climate_control_2', sa.String(100), nullable=True),
    sa.Column('computer', sa.String(100), nullable=True),
    sa.Column('condition', sa.String(100), nullable=True),
    sa.Column('cruise_control', sa.String(100), nullable=True),
    sa.Column('drive_mode_sys', sa.String(100), nullable=True),
    sa.Column('e_adjustment_wheel', sa.String(100), nullable=True),
    sa.Column('easy_trunk_opening', sa.String(100), nullable=True),
    sa.Column('electro_mirrors', sa.String(100), nullable=True),
    sa.Column('electro_trunk', sa.String(100), nullable=True),
    sa.Column('electro_window_back', sa.String(100), nullable=True),
    sa.Column('electro_window_front', sa.String(100), nullable=True),
    sa.Column('electronic_gage_panel', sa.String(100), nullable=True),
    sa.Column('front_camera', sa.String(100), nullable=True),
    sa.Column('keyless_entry', sa.String(100), nullable=True),
    sa.Column('multi_wheel', sa.String(100), nullable=True),
    sa.Column('multizone_climate_control', sa.String(100), nullable=True),
    sa.Column('park_assist_f', sa.String(100), nullable=True),
    sa.Column('park_assist_r', sa.String(100), nullable=True),
    sa.Column('power_latching_doors', sa.String(100), nullable=True),
    sa.Column('programmed_block_heater', sa.String(100), nullable=True),
    sa.Column('projection_display', sa.String(100), nullable=True),
    sa.Column('rear_camera', sa.String(100), nullable=True),
    sa.Column('remote_engine_start', sa.String(100), nullable=True),
    sa.Column('servo', sa.String(100), nullable=True),
    sa.Column('start_button', sa.String(100), nullable=True),
    sa.Column('start_stop_function', sa.String(100), nullable=True),
    sa.Column('steering_wheel_gear_shift_paddles', sa.String(100), nullable=True),
    sa.Column('wheel_configuration1', sa.String(100), nullable=True),
    sa.Column('wheel_configuration2', sa.String(100), nullable=True),
    sa.Column('wheel_memory', sa.String(100), nullable=True),
    sa.Column('wheel_power', sa.String(100), nullable=True),
    sa.Column('adaptive_light', sa.String(100), nullable=True),
    sa.Column('automatic_lighting_control', sa.String(100), nullable=True),
    sa.Column('drl', sa.String(100), nullable=True),
    sa.Column('heated_wash_system', sa.String(100), nullable=True),
    sa.Column('high_beam_assist', sa.String(100), nullable=True),
    sa.Column('laser_lights', sa.String(100), nullable=True),
    sa.Column('led_lights', sa.String(100), nullable=True),
    sa.Column('light_cleaner', sa.String(100), nullable=True),
    sa.Column('light_sensor', sa.String(100), nullable=True),
    sa.Column('mirrors_heat', sa.String(100), nullable=True),
    sa.Column('ptf', sa.String(100), nullable=True),
    sa.Column('rain_sensor', sa.String(100), nullable=True),
    sa.Column('windcleaner_heat', sa.String(100), nullable=True),
    sa.Column('windscreen_heat', sa.String(100), nullable=True),
    sa.Column('xenon', sa.String(100), nullable=True),
    sa.Column('abs', sa.String(100), nullable=True),
    sa.Column('airbag_curtain', sa.String(100), nullable=True),
    sa.Column('airbag_driver', sa.String(100), nullable=True),
    sa.Column('airbag_passenger', sa.String(100), nullable=True),
    sa.Column('airbag_rear_side', sa.String(100), nullable=True),
    sa.Column('airbag_side', sa.String(100), nullable=True),
    sa.Column('asr', sa.String(100), nullable=True),
    sa.Column('bas', sa.String(100), nullable=True),
    sa.Column('blind_spot', sa.String(100), nullable=True),
    sa.Column('collision_prevention_assist', sa.String(100), nullable=True),
    sa.Column('dha', sa.String(100), nullable=True),
    sa.Column('drowsy_driver_alert_system', sa.String(100), nullable=True),
    sa.Column('esp', sa.String(100), nullable=True),
    sa.Column('feedback_alarm', sa.String(100), nullable=True),
    sa.Column('glonass', sa.String(100), nullable=True),
    sa.Column('hcc', sa.String(100), nullable=True),
    sa.Column('isofix', sa.String(100), nullable=True),
    sa.Column('isofix_front', sa.String(100), nullable=True),
    sa.Column('knee_airbag', sa.String(100), nullable=True),
    sa.Column('laminated_safety_glass', sa.String(100), nullable=True),
    sa.Column('lane_keeping_assist', sa.String(100), nullable=True),
    sa.Column('night_vision', sa.String(100), nullable=True),
    sa.Column('power_child_locks_rear_doors', sa.String(100), nullable=True),
    sa.Column('traffic_sign_recognition', sa.String(100), nullable=True),
    sa.Column('tyre_pressure', sa.String(100), nullable=True),
    sa.Column('vsm', sa.String(100), nullable=True),
    sa.Column('alarm', sa.String(100), nullable=True),
    sa.Column('immo', sa.String(100), nullable=True),
    sa.Column('lock_system', sa.String(100), nullable=True),
    sa.Column('volume_sensor', sa.String(100), nullable=True),
    sa.Column('socket_12v', sa.String(100), nullable=True),
    sa.Column('socket_220v', sa.String(100), nullable=True),
    sa.Column('android_auto', sa.String(100), nullable=True),
    sa.Column('apple_carplay', sa.String(100), nullable=True),
    sa.Column('audiopreparation', sa.String(100), nullable=True),
    sa.Column('audiosystem_cd', sa.String(100), nullable=True),
    sa.Column('audiosystem_tv', sa.String(100), nullable=True),
    sa.Column('aux', sa.String(100), nullable=True),
    sa.Column('bluetooth', sa.String(100), nullable=True),
    sa.Column('entertainment_system_for_rear_seat_passengers', sa.String(100), nullable=True),
    sa.Column('music_super', sa.String(100), nullable=True),
    sa.Column('navigation', sa.String(100), nullable=True),
    sa.Column('usb', sa.String(100), nullable=True),
    sa.Column('voice_recognition', sa.String(100), nullable=True),
    sa.Column('wireless_charger', sa.String(100), nullable=True),
    sa.Column('ya_auto', sa.String(100), nullable=True),
    sa.Column('activ_suspension', sa.String(100), nullable=True),
    sa.Column('air_suspension', sa.String(100), nullable=True),
    sa.Column('reduce_spare_wheel', sa.String(100), nullable=True),
    sa.Column('spare_wheel', sa.String(100), nullable=True),
    sa.Column('sport_suspension', sa.String(100), nullable=True),
    sa.Column('wheels_14_inch', sa.String(100), nullable=True),
    sa.Column('wheels_15_inch', sa.String(100), nullable=True),
    sa.Column('wheels_16_inch', sa.String(100), nullable=True),
    sa.Column('wheels_17_inch', sa.String(100), nullable=True),
    sa.Column('wheels_18_inch', sa.String(100), nullable=True),
    sa.Column('wheels_19_inch', sa.String(100), nullable=True),
    sa.Column('wheels_20_inch', sa.String(100), nullable=True),
    sa.Column('wheels_21_inch', sa.String(100), nullable=True),
    sa.Column('wheels_22_inch', sa.String(100), nullable=True),
    sa.Column('body_kit', sa.String(100), nullable=True),
    sa.Column('body_mouldings', sa.String(100), nullable=True),
    sa.Column('duo_body_color', sa.String(100), nullable=True),
    sa.Column('paint_metallic', sa.String(100), nullable=True),
    sa.Column('roof_rails', sa.String(100), nullable=True),
    sa.Column('steel_wheels', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('complectation_id'),
    )

    op.create_table(
        'specifications',
    sa.Column('complectation_id', sa.String(50), nullable=False),
    sa.Column('back_brake', sa.String(100), nullable=True),
    sa.Column('feeding', sa.String(100), nullable=True),
    sa.Column('horse_power', sa.String(100), nullable=True),
    sa.Column('kvt_power', sa.String(100), nullable=True),
    sa.Column('rpm_power', sa.String(100), nullable=True),
    sa.Column('engine_type', sa.String(100), nullable=True),
    sa.Column('transmission', sa.String(100), nullable=True),
    sa.Column('drive', sa.String(100), nullable=True),
    sa.Column('volume', sa.String(100), nullable=True),
    sa.Column('time_to_100', sa.String(100), nullable=True),
    sa.Column('cylinders_order', sa.String(100), nullable=True),
    sa.Column('max_speed', sa.String(100), nullable=True),
    sa.Column('compression', sa.String(100), nullable=True),
    sa.Column('cylinders_value', sa.String(100), nullable=True),
    sa.Column('diametr', sa.String(100), nullable=True),
    sa.Column('piston_stroke', sa.String(100), nullable=True),
    sa.Column('engine_feeding', sa.String(100), nullable=True),
    sa.Column('engine_order', sa.String(100), nullable=True),
    sa.Column('gear_value', sa.String(100), nullable=True),
    sa.Column('moment', sa.String(100), nullable=True),
    sa.Column('petrol_type', sa.String(100), nullable=True),
    sa.Column('valves', sa.String(100), nullable=True),
    sa.Column('weight', sa.String(100), nullable=True),
    sa.Column('wheel_size', sa.String(100), nullable=True),
    sa.Column('wheel_base', sa.String(100), nullable=True),
    sa.Column('front_wheel_base', sa.String(100), nullable=True),
    sa.Column('back_wheel_base', sa.String(100), nullable=True),
    sa.Column('front_brake', sa.String(100), nullable=True),
    sa.Column('front_suspension', sa.String(100), nullable=True),
    sa.Column('back_suspension', sa.String(100), nullable=True),
    sa.Column('height', sa.String(100), nullable=True),
    sa.Column('width', sa.String(100), nullable=True),
    sa.Column('fuel_tank_capacity', sa.String(100), nullable=True),
    sa.Column('seats', sa.String(100), nullable=True),
    sa.Column('length', sa.String(100), nullable=True),
    sa.Column('emission_euro_class', sa.String(100), nullable=True),
    sa.Column('volume_litres', sa.String(100), nullable=True),
    sa.Column('consumption_mixed', sa.String(100), nullable=True),
    sa.Column('clearance', sa.String(100), nullable=True),
    sa.Column('trunks_min_capacity', sa.String(100), nullable=True),
    sa.Column('trunks_max_capacity', sa.String(100), nullable=True),
    sa.Column('consumption_hiway', sa.String(100), nullable=True),
    sa.Column('consumption_city', sa.String(100), nullable=True),
    sa.Column('moment_rpm', sa.String(100), nullable=True),
    sa.Column('full_weight', sa.String(100), nullable=True),
    sa.Column('range_distance', sa.String(100), nullable=True),
    sa.Column('battery_capacity', sa.String(100), nullable=True),
    sa.Column('fuel_emission', sa.String(100), nullable=True),
    sa.Column('electric_range', sa.String(100), nullable=True),
    sa.Column('charge_time', sa.String(100), nullable=True),
    sa.Column('safety_rating', sa.String(100), nullable=True),
    sa.Column('safety_grade', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('complectation_id'),
    )

    # ── Unique constraints from original 001_init.py missing in 009 DDL ──
    op.create_unique_constraint('uq_companies_inn', 'companies', ['inn'])
    op.create_unique_constraint('uq_dealer_groups_name', 'dealer_groups', ['name'])
    op.create_unique_constraint('dealer_options_name_unique', 'dealer_options', ['name'])
    op.create_unique_constraint('uq_users_phone', 'users', ['phone'])
    op.create_unique_constraint('uq_accounting_reports_inn', 'accounting_reports', ['inn'])
    op.create_unique_constraint('uq_client_profiles_user_id', 'client_profiles', ['user_id'])
    op.create_unique_constraint('shopping_cart_user_vehicle_unique', 'shopping_cart', ['user_id', 'vehicle_id'])
    op.create_unique_constraint('uq_application_document_requests', 'application_document_requests', ['application_id', 'leasing_company_id', 'document_type'])
    op.create_unique_constraint('uq_application_vehicles', 'application_vehicles', ['application_id', 'vehicle_id'])
    op.create_unique_constraint('exchange_cart_items_user_vehicle_unique', 'exchange_cart_items', ['user_id', 'vehicle_id'])
    op.create_unique_constraint('featured_vehicles_model_unique', 'featured_vehicles', ['model_id'])
    op.create_unique_constraint('uq_leasing_company_users', 'leasing_company_users', ['user_id', 'leasing_company_id'])
    op.create_unique_constraint('user_favorites_user_id_vehicle_id_key', 'user_favorites', ['user_id', 'vehicle_id'])
    op.create_unique_constraint('vehicle_warehouses_vehicle_unique', 'vehicle_warehouses', ['vehicle_id'])
    op.create_unique_constraint('uq_application_documents', 'application_documents', ['application_id', 'document_id', 'leasing_company_id'])
    op.create_unique_constraint('uq_document_applications', 'document_applications', ['document_id', 'application_id'])
    op.create_unique_constraint('uq_document_leasing_company_approvals', 'document_leasing_company_approvals', ['document_id', 'leasing_company_id'])
    op.create_unique_constraint('exchange_bids_request_dealer_unique', 'exchange_bids', ['request_id', 'dealer_id'])
    op.create_unique_constraint('exchange_cart_item_dealer_comments_unique', 'exchange_cart_item_dealer_comments', ['cart_item_id', 'dealer_id'])
    op.create_unique_constraint('exchange_cart_item_options_unique', 'exchange_cart_item_options', ['cart_item_id', 'dealer_option_id'])
    op.create_unique_constraint('exchange_cart_item_warehouses_unique', 'exchange_cart_item_warehouses', ['cart_item_id', 'warehouse_id'])
    op.create_unique_constraint('exchange_request_dealer_comments_unique', 'exchange_request_dealer_comments', ['request_id', 'dealer_id'])
    op.create_unique_constraint('exchange_request_options_unique', 'exchange_request_options', ['request_id', 'dealer_option_id'])
    op.create_unique_constraint('exchange_request_warehouses_unique', 'exchange_request_warehouses', ['request_id', 'warehouse_id'])
    op.create_unique_constraint('uq_passport_recognition_data', 'passport_recognition_data', ['user_id', 'file_hash', 'passport_type'])
    op.create_unique_constraint('exchange_bid_options_unique', 'exchange_bid_options', ['bid_id', 'dealer_option_id'])
    op.create_unique_constraint('uq_accounting_metadata_inn', 'accounting_metadata', ['inn'])
    op.create_unique_constraint('uq_nds_declaration_line', 'nds_declaration', ['company_inn', 'report_year', 'period_code', 'tax_rate_id', 'source_type'])

    op.create_index('idx_bs_active', 'balance_sheet', ['company_inn', 'is_active'])

    op.create_index('idx_bs_period', 'balance_sheet', ['company_inn', 'period_code', 'report_year'])

    op.create_index('idx_bs_lookup', 'balance_sheet', ['company_inn', 'report_year', 'line_code', 'source_type'])

    op.create_index('idx_cc_lookup', 'capital_changes', ['company_inn', 'report_year', 'line_code', 'component_code', 'source_type'])

    op.create_index('idx_cc_active', 'capital_changes', ['company_inn', 'is_active'])

    op.create_index('idx_cc_period', 'capital_changes', ['company_inn', 'period_code', 'report_year'])

    op.create_index('idx_cf_period', 'cash_flow', ['company_inn', 'period_code', 'report_year'])

    op.create_index('idx_cf_active', 'cash_flow', ['company_inn', 'is_active'])

    op.create_index('idx_cf_lookup', 'cash_flow', ['company_inn', 'report_year', 'line_code', 'source_type'])

    op.create_index('idx_catalog_import_jobs_status', 'catalog_import_jobs', ['status'])

    op.create_index('idx_catalog_import_jobs_user_id', 'catalog_import_jobs', ['user_id'])

    op.create_index('idx_cities_name', 'cities', ['name'])

    op.create_index('idx_companies_inn', 'companies', ['inn'])

    op.create_index('idx_companies_type', 'companies', ['company_type'])

    op.create_index('idx_companies_enrichment_status', 'companies', ['enrichment_status'])

    op.create_index('idx_document_types_type_code', 'document_types', ['type_code'], unique=True)

    op.create_index('idx_fr_active', 'financial_result', ['company_inn', 'is_active'])

    op.create_index('idx_fr_period', 'financial_result', ['company_inn', 'period_code', 'report_year'])

    op.create_index('idx_fr_lookup', 'financial_result', ['company_inn', 'report_year', 'line_code', 'source_type'])

    op.create_index('idx_leasing_rates_id', 'leasing_rates', ['id'])

    op.create_index('idx_mark_popular', 'mark', ['popular'])

    op.create_index('idx_report_codes_xml_tag', 'report_codes', ['xml_tag'])

    op.create_index('idx_report_codes_okud', 'report_codes', ['okud'])

    op.create_index('idx_report_types_knd', 'report_types', ['knd'])

    op.create_index('idx_report_types_okud', 'report_types', ['okud'])

    op.create_index('idx_users_email', 'users', ['email'])

    op.create_index('idx_users_role', 'users', ['role'])

    op.create_index('idx_users_deleted_at', 'users', ['deleted_at'])

    op.create_index('idx_users_phone', 'users', ['phone'])

    op.create_index('idx_users_last_login_at', 'users', ['last_login_at'])

    op.create_index('idx_users_company_id', 'users', ['company_id'])

    op.create_index('idx_verification_codes_email', 'verification_codes', ['email'])

    op.create_index('idx_verification_codes_phone', 'verification_codes', ['phone'])

    op.create_index('idx_accounting_metadata_company_id', 'accounting_metadata', ['company_id'])

    op.create_index('idx_accounting_metadata_fetch_status', 'accounting_metadata', ['fetch_status'])

    op.create_index('idx_accounting_metadata_last_fetch', 'accounting_metadata', ['last_fetch_at'])

    op.create_index('idx_accounting_metadata_active', 'accounting_metadata', ['is_active'])

    op.create_index('idx_accounting_reports_company_id', 'accounting_reports', ['company_id'])

    op.create_index('idx_accounting_reports_fetch_status', 'accounting_reports', ['fetch_status'])

    op.create_index('idx_calculation_history_created_at', 'calculation_history', ['created_at'])

    op.create_index('idx_calculation_history_user_id', 'calculation_history', ['user_id'])

    op.create_index('idx_client_profiles_user_id', 'client_profiles', ['user_id'])

    op.create_index('idx_company_select_history_company_id', 'company_select_history', ['company_id'])

    op.create_index('idx_leasing_applications_email', 'leasing_applications', ['email'])

    op.create_index('idx_leasing_applications_selected_companies', 'leasing_applications', ['selected_leasing_companies'])

    op.create_index('idx_leasing_applications_vehicle_id', 'leasing_applications', ['vehicle_id'])

    op.create_index('idx_applications_status', 'leasing_applications', ['status'])

    op.create_index('idx_leasing_applications_company_id', 'leasing_applications', ['company_id'])

    op.create_index('idx_leasing_applications_group_id', 'leasing_applications', ['group_id'])

    op.create_index('idx_applications_current_stage', 'leasing_applications', ['current_stage'])

    op.create_index('idx_leasing_applications_dealer_company_id', 'leasing_applications', ['dealer_company_id'])

    op.create_index('idx_applications_questionnaire_progress', 'leasing_applications', ['questionnaire_progress'])

    op.create_index('idx_leasing_applications_display_number', 'leasing_applications', ['display_number'])

    op.create_index('idx_leasing_calculations_user_id', 'leasing_calculations', ['user_id'])

    op.create_index('idx_magic_links_user_id', 'magic_links', ['user_id'])

    op.create_index('idx_magic_links_token', 'magic_links', ['token'], unique=True)

    op.create_index('idx_model_mark_id', 'model', ['mark_id'])

    op.create_index('idx_nds_active', 'nds_declaration', ['company_inn', 'is_active'])

    op.create_index('idx_nds_period', 'nds_declaration', ['company_inn', 'period_code', 'report_year'])

    op.create_index('idx_nds_lookup', 'nds_declaration', ['company_inn', 'report_year', 'tax_rate_id', 'source_type'])

    op.create_index('idx_shopping_cart_user', 'shopping_cart', ['user_id'])

    op.create_index('idx_shopping_cart_vehicle_id', 'shopping_cart', ['vehicle_id'])

    op.create_index('idx_shopping_cart_modification', 'shopping_cart', ['modification_id'])

    op.create_index('idx_user_companies_user_id', 'user_companies', ['user_id'])

    op.create_index('idx_user_companies_company_id', 'user_companies', ['company_id'])

    op.create_index('idx_user_sessions_user_id_last_used_at_desc', 'user_sessions', ['user_id', 'last_used_at'])

    op.create_index('vehicles_vin_unique', 'vehicles', ['vin'], unique=True, postgresql_where=sa.text('NOT vin IS NULL'))

    op.create_index('idx_vehicles_unique_combo', 'vehicles', ['mark_id', 'model_id', 'generation_id', 'complectation_id', 'color', 'color_inter'], postgresql_where=sa.text("is_available = TRUE AND status = 'available'"))

    op.create_index('idx_vehicles_year', 'vehicles', ['year'])

    op.create_index('idx_vehicles_complectation', 'vehicles', ['complectation_id'])

    op.create_index('idx_vehicles_price', 'vehicles', [sa.text('COALESCE(discount_price, base_price)')], postgresql_where=sa.text("is_available = TRUE AND status = 'available'"))

    op.create_index('idx_vehicles_color_inter', 'vehicles', ['color_inter'])

    op.create_index('idx_vehicles_main_filter', 'vehicles', ['is_available', 'status', 'mark_id', 'model_id', 'generation_id'], postgresql_where=sa.text("is_available = TRUE AND status = 'available'"))

    op.create_index('idx_vehicles_configuration', 'vehicles', ['configuration_id'])

    op.create_index('idx_vehicles_dealer_id', 'vehicles', ['dealer_id'])

    op.create_index('idx_vehicles_color', 'vehicles', ['color'])

    op.create_index('idx_vehicles_vin_available', 'vehicles', ['vin'], postgresql_where=sa.text("is_available = TRUE AND status = 'available' AND NOT vin IS NULL AND vin <> ''"))

    op.create_index('idx_vehicles_available', 'vehicles', ['id'], postgresql_where=sa.text("is_available = TRUE AND status = 'available'"))

    op.create_index('idx_warehouses_brand', 'warehouses', ['brand'])

    op.create_index('idx_warehouses_company_id', 'warehouses', ['company_id'])

    op.create_index('idx_warehouses_city_id', 'warehouses', ['city_id'])

    op.create_index('idx_warehouses_dealer_id', 'warehouses', ['dealer_id'])

    op.create_index('idx_warehouses_address', 'warehouses', ['address'])

    op.create_index('idx_questionnaires_application_id', 'application_questionnaires', ['application_id'])

    op.create_index('idx_application_vehicles_is_model_order', 'application_vehicles', ['is_model_order'])

    op.create_index('idx_application_vehicles_application_id', 'application_vehicles', ['application_id'])

    op.create_index('idx_application_vehicles_modification_id', 'application_vehicles', ['modification_id'])

    op.create_index('idx_application_vehicles_vehicle_id', 'application_vehicles', ['vehicle_id'])

    op.create_index('idx_compensations_status', 'compensations', ['status'])

    op.create_index('idx_compensations_payer', 'compensations', ['payer'])

    op.create_index('idx_compensations_recipient', 'compensations', ['recipient'])

    op.create_index('idx_compensations_applied_support', 'compensations', ['applied_support_id'])

    op.create_index('idx_compensations_due_date', 'compensations', ['due_date'])

    op.create_index('idx_compensations_application_id', 'compensations', ['application_id'])

    op.create_index('idx_documents_dbrain_task_id', 'documents', ['dbrain_task_id'])

    op.create_index('idx_documents_recognition_status', 'documents', ['recognition_status'])

    op.create_index('idx_documents_version', 'documents', ['version'])

    op.create_index('idx_documents_is_current_version', 'documents', ['is_current_version'])

    op.create_index('idx_documents_s3_key', 'documents', ['s3_key'])

    op.create_index('idx_documents_related_application_id', 'documents', ['related_application_id'])

    op.create_index('idx_documents_company_id', 'documents', ['company_id'])

    op.create_index('idx_documents_parent_document_id', 'documents', ['parent_document_id'])

    op.create_index('idx_documents_leasing_company_status', 'documents', ['leasing_company_status'])

    op.create_index('idx_exchange_cart_items_user', 'exchange_cart_items', ['user_id'])

    op.create_index('idx_exchange_requests_status', 'exchange_requests', ['status'])

    op.create_index('idx_exchange_requests_lc_user', 'exchange_requests', ['lc_user_id'])

    op.create_index('idx_exchange_requests_batch', 'exchange_requests', ['batch_number', 'batch_index'])

    op.create_index('idx_exchange_requests_distributor_id', 'exchange_requests', ['distributor_id'])

    op.create_index('idx_exchange_requests_vehicle', 'exchange_requests', ['vehicle_id'])

    op.create_index('idx_featured_vehicles_model_id', 'featured_vehicles', ['model_id'])

    op.create_index('idx_featured_vehicles_position', 'featured_vehicles', ['position'])

    op.create_index('idx_featured_vehicles_is_active', 'featured_vehicles', ['is_active'])

    op.create_index('idx_generation_year_start', 'generation', ['year_start'])

    op.create_index('idx_generation_model_id', 'generation', ['model_id'])

    op.create_index('idx_leasing_application_comments_created_at', 'leasing_application_comments', ['created_at'])

    op.create_index('idx_leasing_application_comments_type', 'leasing_application_comments', ['comment_type'])

    op.create_index('idx_leasing_application_comments_app_id', 'leasing_application_comments', ['leasing_application_id'])

    op.create_index('idx_lavc_leasing_application_id', 'leasing_application_vehicle_calculations', ['leasing_application_id'])

    op.create_index('idx_lca_submitted_at', 'leasing_company_applications', ['submitted_at'])

    op.create_index('idx_leasing_doc_req_unique', 'leasing_company_document_requirements', ['leasing_company_id', 'document_type_id'], unique=True)

    op.create_index('idx_notifications_user', 'notifications', ['user_id'])

    op.create_index('idx_purchase_orders_status', 'purchase_orders', ['status'])

    op.create_index('idx_purchase_orders_vehicle_id', 'purchase_orders', ['vehicle_id'])

    op.create_index('idx_purchase_orders_user_id', 'purchase_orders', ['user_id'])

    op.create_index('idx_signature_requests_status', 'signature_requests', ['status'])

    op.create_index('idx_signature_requests_user_id', 'signature_requests', ['user_id'])

    op.create_index('idx_signature_requests_invited_by_user_id', 'signature_requests', ['invited_by_user_id'])

    op.create_index('idx_signature_requests_application_id', 'signature_requests', ['application_id'])

    op.create_index('idx_support_programs_vin', 'support_programs', ['vin'])

    op.create_index('idx_support_programs_distributor', 'support_programs', ['distributor_id'])

    op.create_index('idx_support_programs_vins_gin', 'support_programs', ['vins'], postgresql_using='gin')

    op.create_index('idx_support_programs_mark', 'support_programs', ['mark_id'])

    op.create_index('idx_support_programs_model', 'support_programs', ['model_id'])

    op.create_index('idx_user_favorites_vehicle_id', 'user_favorites', ['vehicle_id'])

    op.create_index('idx_user_favorites_user_id', 'user_favorites', ['user_id'])

    op.create_index('idx_vehicle_warehouses_vehicle_id', 'vehicle_warehouses', ['vehicle_id'])

    op.create_index('idx_vehicle_warehouses_warehouse_id', 'vehicle_warehouses', ['warehouse_id'])

    op.create_index('idx_configuration_generation_id', 'configuration', ['generation_id'])

    op.create_index('idx_configuration_body_type', 'configuration', ['body_type'])

    op.create_index('idx_dirinv_application_id', 'director_doc_signing_invitations', ['application_id'])

    op.create_index('uq_dirinv_app_type_period', 'director_doc_signing_invitations', ['application_id', 'document_type', sa.text("COALESCE(period_label, '')")], unique=True)

    op.create_index('idx_document_applications_application_id', 'document_applications', ['application_id'])

    op.create_index('idx_document_applications_document_id', 'document_applications', ['document_id'])

    op.create_index('idx_document_leasing_company_approvals_document_id', 'document_leasing_company_approvals', ['document_id'])

    op.create_index('idx_document_leasing_company_approvals_leasing_company_id', 'document_leasing_company_approvals', ['leasing_company_id'])

    op.create_index('idx_exchange_bids_kp_status', 'exchange_bids', ['kp_status'])

    op.create_index('idx_exchange_bids_request', 'exchange_bids', ['request_id'])

    op.create_index('idx_exchange_bids_distributor_id', 'exchange_bids', ['distributor_id'])

    op.create_index('idx_exchange_bids_dealer', 'exchange_bids', ['dealer_id'])

    op.create_index('idx_exchange_request_files_request', 'exchange_request_files', ['request_id'])

    op.create_index('idx_exchange_request_warehouses_dealer', 'exchange_request_warehouses', ['dealer_id'])

    op.create_index('idx_leasing_proposals_lca_id', 'leasing_proposals', ['leasing_company_application_id'])

    op.create_index('idx_passport_recognition_user_id', 'passport_recognition_data', ['user_id'])

    op.create_index('idx_passport_recognition_file_hash', 'passport_recognition_data', ['file_hash'])

    op.create_index('idx_passport_recognition_passport_type', 'passport_recognition_data', ['passport_type'])

    op.create_index('idx_passport_recognition_document_id', 'passport_recognition_data', ['document_id'])

    op.create_index('idx_payments_purchase_order_id', 'payments', ['purchase_order_id'])

    op.create_index('idx_payments_expires_at', 'payments', ['expires_at'])

    op.create_index('idx_payments_user_id', 'payments', ['user_id'])

    op.create_index('idx_payments_fiscal_status', 'payments', ['fiscal_status'])

    op.create_index('idx_payments_status', 'payments', ['status'])

    op.create_index('idx_payments_gateway_transaction_id', 'payments', ['gateway_transaction_id'])

    op.create_index('idx_support_bill_of_ladings_support_program_id', 'support_bill_of_ladings', ['support_program_id'])

    op.create_index('idx_support_program_dealer_groups_group', 'support_program_dealer_groups', ['dealer_group_id'])

    op.create_index('idx_support_program_dealer_groups_program', 'support_program_dealer_groups', ['support_program_id'])

    op.create_index('idx_exchange_bid_comments_bid', 'exchange_bid_comments', ['bid_id'])

    op.create_index('idx_leasing_schedule_order_id', 'leasing_payment_schedule', ['purchase_order_id'])

    op.create_index('idx_leasing_schedule_due_date', 'leasing_payment_schedule', ['due_date'])

    op.create_index('idx_modification_configuration_id', 'modification', ['configuration_id'])

    op.create_index('idx_modification_price', 'modification', ['offers_price_from', 'offers_price_to'])

    op.create_index('idx_modification_config_group', 'modification', ['configuration_id', 'group_name'])

    op.create_index('idx_options_complectation_id', 'options', ['complectation_id'])

    op.create_index('idx_specifications_transmission', 'specifications', ['complectation_id', 'transmission'], postgresql_where=sa.text("NOT transmission IS NULL AND transmission <> ''"))

    op.create_index('idx_specifications_horse_power', 'specifications', ['complectation_id', 'horse_power'], postgresql_where=sa.text("NOT horse_power IS NULL AND horse_power <> ''"))

    op.create_index('idx_specifications_complectation_id', 'specifications', ['complectation_id'])


    # ── Schema changes from 002–009 not covered by 009 DDL ──
    op.add_column('companies', sa.Column('distributor_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_companies_distributor_id', 'companies', ['distributor_id'], unique=False)

    op.add_column('leasing_applications', sa.Column('distributor_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_leasing_applications_distributor_id', 'leasing_applications', ['distributor_id'], unique=False)

    op.create_unique_constraint('uq_balance_sheet_line', 'balance_sheet', ['company_inn', 'report_year', 'period_code', 'line_code', 'source_type'])
    op.create_unique_constraint('uq_financial_result_line', 'financial_result', ['company_inn', 'report_year', 'period_code', 'line_code', 'source_type'])
    op.create_unique_constraint('uq_cash_flow_line', 'cash_flow', ['company_inn', 'report_year', 'period_code', 'line_code', 'source_type'])
    op.create_unique_constraint('uq_capital_changes_line', 'capital_changes', ['company_inn', 'report_year', 'period_code', 'line_code', 'component_code', 'source_type'])

    op.create_foreign_key('fk_exchange_requests_accepted_bid', 'exchange_requests', 'exchange_bids', ['accepted_bid_id'], ['id'], ondelete='SET NULL', use_alter=True)
    op.create_unique_constraint('uq_leasing_proposals_lca_kind', 'leasing_proposals', ['leasing_company_application_id', 'kind'])

    # ── Seed data ──
    _seed_data()


def _seed_data() -> None:
    import random

    pw_hash = '$2a$10$AdpAfaOCsYmxblpSBGnVyuRKBxRNbKZcAUTdL18CGtoOGh5DIz.my'

    # 1. Leasing rates
    lr_id = uuid.uuid4()
    # nosemgrep: bandit.B608 -- UUID is generated within this seed migration, not user input.
    op.execute(sa.text(f"INSERT INTO leasing_rates (id, key_rate, surcharge, vat_rate, profit_tax_rate) VALUES ('{lr_id}', 15, 6, 20, 25) ON CONFLICT DO NOTHING"))

    # 2. Demo companies
    c_demo = uuid.uuid4()
    c_reso = uuid.uuid4()
    c_alfa = uuid.uuid4()
    c_dist1 = uuid.uuid4()
    c_dist2 = uuid.uuid4()
    c_carcraft = uuid.uuid4()

    op.execute(sa.text(f"""
        INSERT INTO companies (id, name, inn, kpp, ogrn, company_type, legal_address, actual_address, phone, email, website, is_active)
        VALUES
            ('{c_demo}', 'Демо Автосалон "Премиум Авто"', '7701234567', '770101001', '1027701234567', 'dealer',
             'г. Москва, ул. Автомобильная, д. 1', 'г. Москва, ул. Автомобильная, д. 1',
             '+7 (495) 123-45-67', 'dealer@demo.ru', 'https://demo-dealer.ru', true),
            ('{c_reso}', 'ООО "РЕСО-Лизинг"', '7709431786', '772601001', '1037709061015', 'leasing_company',
             'г Москва, Нагорный проезд, д 6 стр 8', 'г Москва, Нагорный проезд, д 6 стр 8',
             '+7 (495) 980–08–83', 'leasing@resoleasing.com', 'https://www.resoleasing.com', true),
            ('{c_alfa}', 'ООО "Альфамобиль"', '7702390587', '770201001', '1157746875373', 'leasing_company',
             '129110, город Москва, Большая Переяславская ул., д. 46 стр. 2, эт. 4,пом.I к.16,17', '129110, город Москва, Большая Переяславская ул., д. 46 стр. 2, эт. 4,пом.I к.16,17',
             '+7 (495) 126-24-70', 'cs@alfaleasing.ru', 'https://alfaleasing.ru/', true),
            ('{c_dist1}', 'Демо Дистрибьютор "Авто Импорт"', '7701234570', '770101004', '1027701234570', 'distributor',
             'г. Москва, ул. Дистрибьюторская, д. 5', 'г. Москва, ул. Дистрибьюторская, д. 5',
             '+7 (495) 456-78-90', 'distributor1@demo.ru', 'https://demo-distributor1.ru', true),
            ('{c_dist2}', 'Демо Дистрибьютор "Европа Авто"', '7701234571', '770101005', '1027701234571', 'distributor',
             'г. Екатеринбург, ул. Европейская, д. 15', 'г. Екатеринбург, ул. Европейская, д. 15',
             '+7 (343) 567-89-01', 'distributor2@demo.ru', 'https://demo-distributor2.ru', true),
            ('{c_carcraft}', 'ООО "КАРКРАФТ"', '9718036458', '771801001', '1177746758498', 'other',
             'г. Москва, ул. Тестовая, д. 1', 'г. Москва, ул. Тестовая, д. 1',
             '+7 (495) 999-12-34', 'client@demo.ru', NULL, true)
        ON CONFLICT DO NOTHING
    """))

    op.execute(sa.text(f"""
        INSERT INTO leasing_companies (id, company_id, is_active, created_at, updated_at)
        VALUES
            ('{c_reso}', '{c_reso}', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            ('{c_alfa}', '{c_alfa}', true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
    """))

    # 3. Document types
    doc_types_table = sa.table(
        'document_types',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('type_code', sa.String),
        sa.column('display_name', sa.String),
        sa.column('description', sa.Text),
        sa.column('file_types', sa.ARRAY(sa.Text)),
        sa.column('max_file_size_mb', sa.Integer),
        sa.column('auto_approve', sa.Boolean),
    )
    doc_types = [
        {'id': uuid.uuid4(), 'name': 'Бухгалтерская отчётность', 'type_code': 'accounting_report_xml', 'display_name': 'Бухгалтерская отчётность', 'description': 'Отчётность нарастающим итогом в формате XML по стандарту 1С Бухгалтерия (только ОСН).', 'file_types': ['.xml'], 'max_file_size_mb': 25, 'auto_approve': False},
        {'id': uuid.uuid4(), 'name': 'Декларация по налогу на прибыль', 'type_code': 'profit_tax_declaration_xml', 'display_name': 'Декларация по налогу на прибыль', 'description': 'Отчётность нарастающим итогом в формате XML по стандарту 1С Бухгалтерия (только ОСН).', 'file_types': ['.xml'], 'max_file_size_mb': 25, 'auto_approve': False},
        {'id': uuid.uuid4(), 'name': 'Декларация по НДС', 'type_code': 'vat_declaration_xml', 'display_name': 'Декларация по НДС', 'description': 'Ежеквартальная отчётность в формате XML по стандарту 1С Бухгалтерия. Один файл на квартал.', 'file_types': ['.xml'], 'max_file_size_mb': 25, 'auto_approve': False},
        {'id': uuid.uuid4(), 'name': 'Декларация по УСН', 'type_code': 'usn_declaration_xml', 'display_name': 'Декларация по УСН', 'description': 'Годовая отчётность в формате XML по стандарту 1С Бухгалтерия (только УСН).', 'file_types': ['.xml'], 'max_file_size_mb': 25, 'auto_approve': False},
        {'id': uuid.uuid4(), 'name': 'Бухгалтерская отчётность (XML)', 'type_code': 'accounting_xml', 'display_name': 'Бухгалтерская отчётность (XML)', 'description': 'Экспорт бухгалтерской отчётности из 1С Бухгалтерия в формате XML', 'file_types': ['.xml'], 'max_file_size_mb': 25, 'auto_approve': True},
    ]
    op.bulk_insert(doc_types_table, doc_types)

    # 4. Dealer options
    dealer_options_table = sa.table(
        'dealer_options',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
    )
    dealer_options_rows = [
        {'id': uuid.uuid4(), 'name': name, 'sort_order': idx, 'is_active': True}
        for idx, name in enumerate(
            ['Доставка', 'Шиномонтаж', 'Установка телематики', 'Коврики', 'Постановка на учет в ГИБДД', 'Сигнализация', 'Зимняя резина', 'Оклейка частичная', 'Оклейка полная'],
            start=1,
        )
    ]
    stmt = pg_insert(dealer_options_table).values(dealer_options_rows).on_conflict_do_nothing(index_elements=['name'])
    op.execute(stmt)

    # 5. Cities
    city_rows = [
        (uuid.uuid4(), 'Москва'),
        (uuid.uuid4(), 'Санкт-Петербург'),
        (uuid.uuid4(), 'Нижний Новгород'),
        (uuid.uuid4(), 'Краснодар'),
        (uuid.uuid4(), 'Екатеринбург'),
    ]
    city_values = [f"('{cid}', '{name}')" for cid, name in city_rows]
    # nosemgrep: bandit.B608 -- UUIDs and city names are fixed seed data, not user input.
    op.execute(sa.text(f"INSERT INTO cities (id, name) VALUES {','.join(city_values)} ON CONFLICT DO NOTHING"))

    # 6. Report types
    op.execute(sa.text("""
        INSERT INTO report_types (knd, okud, name, description, is_active)
        VALUES
            ('0710001', '0710001', 'Бухгалтерский баланс',
             'Форма №1. Бухгалтерский баланс организации (ОКУД 0710001)', true),
            ('0710002', '0710002', 'Отчет о финансовых результатах',
             'Форма №2. Отчет о финансовых результатах (ОКУД 0710002)', true),
            ('0710004', '0710004', 'Отчет об изменениях капитала',
             'Форма №3. Отчет об изменениях капитала (ОКУД 0710004)', true),
            ('0710005', '0710005', 'Отчет о движении денежных средств',
             'Форма №4. Отчет о движении денежных средств (ОКУД 0710005)', true),
            ('1151001', NULL, 'Налоговая декларация по НДС', NULL, true),
            ('1152017', NULL, 'Налоговая декларация по УСН', NULL, true),
            ('1151006', NULL, 'Налоговая декларация по налогу на прибыль', NULL, true),
            ('0710099', NULL, 'Пояснения к бухгалтерской отчетности', NULL, true)
        ON CONFLICT DO NOTHING
    """))

    # 7. Report codes
    report_codes_table = sa.table(
        'report_codes',
        sa.column('id', UUID(as_uuid=True)),
        sa.column('okud', sa.String),
        sa.column('code', sa.String),
        sa.column('xml_tag', sa.String),
        sa.column('name', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    report_codes_rows = [
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1110', 'xml_tag': 'ВнеоборотАктив', 'name': 'Внеоборотные активы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1150', 'xml_tag': 'ОсновнСредств', 'name': 'Основные средства', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1160', 'xml_tag': 'НематАктив', 'name': 'Нематериальные, финансовые и другие внеоборотные активы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1170', 'xml_tag': 'ФинВлож', 'name': 'Финансовые вложения', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1210', 'xml_tag': 'Запасы', 'name': 'Запасы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1230', 'xml_tag': 'ДебиторЗадолж', 'name': 'Дебиторская задолженность', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1250', 'xml_tag': 'ДенежнСред', 'name': 'Денежные средства и денежные эквиваленты', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1600', 'xml_tag': 'Баланс', 'name': 'БАЛАНС (актив)', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1310', 'xml_tag': 'УставнКапитал', 'name': 'Уставный капитал (складочный капитал, уставный фонд, вклады товарищей)', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1410', 'xml_tag': 'КредитЗадолж', 'name': 'Кредиты и займы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1450', 'xml_tag': 'КредитЗадолжКратк', 'name': 'Кредиторская задолженность', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1500', 'xml_tag': 'КраткосрочнОбяз', 'name': 'Краткосрочные обязательства', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710001', 'code': '1700', 'xml_tag': 'БалансПасс', 'name': 'БАЛАНС (пассив)', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2110', 'xml_tag': 'Выручка', 'name': 'Выручка', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2120', 'xml_tag': 'СебестПрод', 'name': 'Себестоимость продаж', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2200', 'xml_tag': 'ПродажПрибыль', 'name': 'Прибыль (убыток) от продаж', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2210', 'xml_tag': 'КомерРасход', 'name': 'Коммерческие расходы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2220', 'xml_tag': 'УправлРасход', 'name': 'Управленческие расходы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2300', 'xml_tag': 'ПрибыльДоНал', 'name': 'Прибыль (убыток) до налогообложения', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2340', 'xml_tag': 'ПрочДоходы', 'name': 'Прочие доходы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2350', 'xml_tag': 'ПрочРасход', 'name': 'Прочие расходы', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710002', 'code': '2400', 'xml_tag': 'ЧистПрибыль', 'name': 'Чистая прибыль (убыток)', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3100', 'xml_tag': 'КапУст', 'name': 'Уставный капитал', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3200', 'xml_tag': 'КапСобАкц', 'name': 'Собственные выкупленные акции', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3300', 'xml_tag': 'КапДоб', 'name': 'Добавочный капитал', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3400', 'xml_tag': 'КапРез', 'name': 'Резервный капитал', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3500', 'xml_tag': 'КапНерПр', 'name': 'Нераспределенная прибыль (непокрытый убыток)', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3600', 'xml_tag': 'КапНакДооц', 'name': 'Накопленные дооценки', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710004', 'code': '3700', 'xml_tag': 'КапИтог', 'name': 'Итого', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4110', 'xml_tag': 'ДенежнСредНач', 'name': 'Денежные средства на начало периода', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4111', 'xml_tag': 'ПоступПрод', 'name': 'Поступления от продаж товаров, выполнения работ, оказания услуг', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4121', 'xml_tag': 'ПлатПост', 'name': 'Платежи поставщикам', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4122', 'xml_tag': 'ПлатПерс', 'name': 'Платежи персоналу', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4123', 'xml_tag': 'ПлатПроч', 'name': 'Прочие платежи', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4100', 'xml_tag': 'СальдоТек', 'name': 'Сальдо денежных средств (текущая деятельность)', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4210', 'xml_tag': 'ПоступИнв', 'name': 'Поступления по инвестиционной деятельности', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4220', 'xml_tag': 'ПлатИнв', 'name': 'Платежи по инвестиционной деятельности', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4200', 'xml_tag': 'СальдоИнв', 'name': 'Сальдо инвестиционной деятельности', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4310', 'xml_tag': 'ПоступФин', 'name': 'Поступления по финансовой деятельности', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4320', 'xml_tag': 'ПлатФин', 'name': 'Платежи по финансовой деятельности', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4300', 'xml_tag': 'СальдоФин', 'name': 'Сальдо финансовой деятельности', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4400', 'xml_tag': 'СальдоПер', 'name': 'Сальдо за отчетный период', 'is_active': True},
        {'id': uuid.uuid4(), 'okud': '0710005', 'code': '4500', 'xml_tag': 'ДенежнСредКон', 'name': 'Денежные средства на конец периода', 'is_active': True},
    ]
    op.bulk_insert(report_codes_table, report_codes_rows)

    # 8. NDS tax rates
    nds_rows = [
        {'xml_tag': 'РеалТов20', 'tax_base_description': 'Налоговая база по ставке 20%', 'tax_amount_description': 'Сумма налога по ставке 20%', 'is_active': True},
        {'xml_tag': 'РеалТов10', 'tax_base_description': 'Налоговая база по ставке 10%', 'tax_amount_description': 'Сумма налога по ставке 10%', 'is_active': True},
        {'xml_tag': 'РеалТов7', 'tax_base_description': 'Налоговая база по ставке 7%', 'tax_amount_description': 'Сумма налога по ставке 7%', 'is_active': True},
        {'xml_tag': 'РеалТов5', 'tax_base_description': 'Налоговая база по ставке 5%', 'tax_amount_description': 'Сумма налога по ставке 5%', 'is_active': True},
        {'xml_tag': 'РеалТов120', 'tax_base_description': 'Налоговая база по ставке 20/120', 'tax_amount_description': 'Сумма налога по ставке 20/120', 'is_active': True},
        {'xml_tag': 'РеалТов110', 'tax_base_description': 'Налоговая база по ставке 10/110', 'tax_amount_description': 'Сумма налога по ставке 10/110', 'is_active': True},
        {'xml_tag': 'РеалТов107', 'tax_base_description': 'Налоговая база по ставке 7/107', 'tax_amount_description': 'Сумма налога по ставке 7/107', 'is_active': True},
        {'xml_tag': 'РеалТов105', 'tax_base_description': 'Налоговая база по ставке 5/105', 'tax_amount_description': 'Сумма налога по ставке 5/105', 'is_active': True},
        {'xml_tag': 'РеалТов18', 'tax_base_description': 'Налоговая база по ставке 18%', 'tax_amount_description': 'Сумма налога по ставке 18%', 'is_active': True},
        {'xml_tag': 'РеалТов118', 'tax_base_description': 'Налоговая база по ставке 18/118', 'tax_amount_description': 'Сумма налога по ставке 18/118', 'is_active': True},
        {'xml_tag': 'РеалТов16.67', 'tax_base_description': 'Налоговая база по ставке 16.67%', 'tax_amount_description': 'Сумма налога по ставке 16.67%', 'is_active': True},
        {'xml_tag': 'РеалТов9.09', 'tax_base_description': 'Налоговая база по ставке 9.09%', 'tax_amount_description': 'Сумма налога по ставке 9.09%', 'is_active': True},
        {'xml_tag': 'ВыпСтрРаб', 'tax_base_description': 'Налоговая база по СМР', 'tax_amount_description': 'Сумма налога по СМР', 'is_active': True},
        {'xml_tag': 'ОплПредПост', 'tax_base_description': 'Налоговая база по предоплате', 'tax_amount_description': 'Сумма налога по предоплате', 'is_active': True},
        {'xml_tag': 'РеалТов0', 'tax_base_description': 'Налоговая база по ставке 0%', 'tax_amount_description': 'Сумма налога по ставке 0%', 'is_active': True},
        {'xml_tag': 'РеалТовНалЮЛ', 'tax_base_description': 'Налоговая база по ставке для налогоплательщика - нерезидента', 'tax_amount_description': 'Сумма налога по ставке для налогоплательщика - нерезидента', 'is_active': True},
    ]
    nds_table = sa.table('nds_tax_rates', sa.column('id', UUID(as_uuid=True)), sa.column('xml_tag', sa.String), sa.column('tax_base_description', sa.String), sa.column('tax_amount_description', sa.String), sa.column('is_active', sa.Boolean))
    nds_rows_with_id = [{'id': uuid.uuid4(), **row} for row in nds_rows]
    op.bulk_insert(nds_table, nds_rows_with_id)

    # 9. Leasing company document requirements
    op.execute(sa.text("""
        INSERT INTO leasing_company_document_requirements
            (id, leasing_company_id, document_type_id, is_required, is_active, sort_order)
        SELECT gen_random_uuid(),
               lc.id,
               dt.id,
               TRUE,
               TRUE,
               CASE dt.type_code
                   WHEN 'accounting_report_xml' THEN 10
                   WHEN 'profit_tax_declaration_xml' THEN 11
                   WHEN 'vat_declaration_xml' THEN 12
                   WHEN 'usn_declaration_xml' THEN 13
                   ELSE 100
               END
        FROM leasing_companies lc
        CROSS JOIN document_types dt
        WHERE lc.is_active = TRUE
          AND dt.type_code IN (
              'accounting_report_xml',
              'profit_tax_declaration_xml',
              'vat_declaration_xml',
              'usn_declaration_xml'
          )
        ON CONFLICT (leasing_company_id, document_type_id) DO UPDATE SET
            is_active = TRUE,
            is_required = TRUE,
            sort_order = EXCLUDED.sort_order,
            updated_at = NOW()
    """))

    # 10. Distributor test data
    company_ids_200 = [uuid.uuid4() for _ in range(5)]
    company_values = []
    used_inns = set()
    for i, cid in enumerate(company_ids_200, start=1):
        inn = f"{7700000000 + i:010d}"
        while inn in used_inns:
            # nosemgrep: bandit.B311 -- Non-cryptographic randomness is only used for demo seed data.
            inn = f"{7700000000 + random.randint(1, 999):010d}"
        used_inns.add(inn)
        kpp = f"{770100000 + i:09d}"
        ogrn = f"{1027700000000 + i:013d}"
        company_values.append(
            f"('{cid}', 'Дилерский Центр {i}', '{inn}', '{kpp}', '{ogrn}', 'dealer', "
            f"'г. Москва, ул. Дилерская, д. {i}', 'г. Москва, ул. Дилерская, д. {i}', "
            f"'+7 (495) 100-{i:02d}-00', 'dealer{i}@demo.ru', NULL, true)"
        )
    op.execute(sa.text(f"""
        INSERT INTO companies
            (id, name, inn, kpp, ogrn, company_type,
             legal_address, actual_address, phone, email, website, is_active)
        VALUES {','.join(company_values)}
        ON CONFLICT DO NOTHING
    """))

    user_ids_200 = [uuid.uuid4() for _ in range(10)]
    user_values = []
    for i, uid in enumerate(user_ids_200, start=3):
        cid = company_ids_200[(i - 1) % 5]
        user_values.append(
            f"('{uid}', 'dealer{i}@demo.ru', '{pw_hash}', 'Сотрудник ДЦ {i}', 'dealer', '{cid}', "
            f"'+76660{i:06d}', true, true, true, NOW())"
        )
    op.execute(sa.text(f"""
        INSERT INTO users
            (id, email, password_hash, name, role, company_id,
             phone, is_active, email_verified, phone_verified, mfa_enabled, created_at)
        VALUES {','.join(v.replace('NOW())', 'false, NOW())') for v in user_values)}
        ON CONFLICT DO NOTHING
    """))

    # Warehouses for test data
    city_map = {name: cid for cid, name in city_rows}
    warehouse_data = [
        ('Москва', 'BMW', 'ул. Ленина, д. 1'),
        ('Санкт-Петербург', 'Mercedes-Benz', 'пр. Невский, д. 10'),
        ('Нижний Новгород', 'Audi', 'ул. Большая Покровская, д. 5'),
        ('Краснодар', 'Toyota', 'ул. Красная, д. 20'),
        ('Екатеринбург', 'Volkswagen', 'пр. Ленина, д. 30'),
    ]
    wh_values = []
    for i, (city_name, brand, address) in enumerate(warehouse_data):
        wh_id = uuid.uuid4()
        city_id = city_map.get(city_name)
        company_id = company_ids_200[i % len(company_ids_200)]
        dealer_id = company_id
        wh_values.append(
            f"('{wh_id}', '{address}', '{brand}', '{city_id}', '{dealer_id}', '{company_id}', "
            f"NOW(), NOW(), 'active')"
        )
    op.execute(sa.text(f"""
        INSERT INTO warehouses
            (id, address, brand, city_id, dealer_id, company_id, created_at, updated_at, status)
        VALUES {','.join(wh_values)}
        ON CONFLICT DO NOTHING
    """))

    # 11. Carcraft admins
    admin_emails = ['admin1@carcraft.ru', 'admin2@carcraft.ru']
    admin_names = ['Админ 1', 'Админ 2']
    admin_phones = ['+76660000001', '+76660000002']
    admin_rows = []
    for i in range(len(admin_emails)):
        admin_rows.append(
            f"('{uuid.uuid4()}', '{admin_emails[i]}', '{pw_hash}', '{admin_names[i]}', 'carcraft_employee', NULL, "
            f"'{admin_phones[i]}', true, true, true, false, NOW())"
        )
    op.execute(sa.text(f"""
        INSERT INTO users
            (id, email, password_hash, name, role, company_id,
             phone, is_active, email_verified, phone_verified, mfa_enabled, created_at)
        VALUES {','.join(admin_rows)}
        ON CONFLICT (phone) DO UPDATE SET
            role = EXCLUDED.role,
            name = EXCLUDED.name,
            email = COALESCE(EXCLUDED.email, users.email),
            password_hash = EXCLUDED.password_hash,
            is_active = EXCLUDED.is_active,
            email_verified = EXCLUDED.email_verified,
            phone_verified = EXCLUDED.phone_verified,
            mfa_enabled = EXCLUDED.mfa_enabled,
            updated_at = NOW()
    """))


def downgrade() -> None:
    raise NotImplementedError("Squashed migration downgrade is not supported.")
