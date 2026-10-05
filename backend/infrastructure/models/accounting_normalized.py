"""SQLAlchemy ORM models for accounting / bookkeeping reports (normalized tables).

New normalized row-level tables for storing accounting reports by line items,
with versioning (is_active/superseded_by) and support for both API-FNS and XML-1C sources.
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class ReportType(Base):
    """Reference table for report types (OKUD/KND codes)."""

    __tablename__ = "report_types"
    __table_args__ = (
        sa.Index("idx_report_types_knd", "knd"),
        sa.Index("idx_report_types_okud", "okud"),
    )

    knd: Mapped[str] = mapped_column(sa.String(20), primary_key=True)
    okud: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class ReportCode(Base):
    """Reference table for report line codes (one row per OKUD+code+XML tag combo)."""

    __tablename__ = "report_codes"
    __table_args__ = (
        sa.Index("idx_report_codes_okud", "okud"),
        sa.Index("idx_report_codes_xml_tag", "xml_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    okud: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    xml_tag: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class BalanceSheet(Base):
    """Normalized balance sheet rows (form ОКУД 0710001)."""

    __tablename__ = "balance_sheet"
    __table_args__ = (
        sa.Index("idx_bs_lookup", "company_inn", "report_year", "line_code", "source_type"),
        sa.Index("idx_bs_active", "company_inn", "is_active"),
        sa.Index("idx_bs_period", "company_inn", "period_code", "report_year"),
        sa.UniqueConstraint(
            "company_inn", "report_year", "period_code", "line_code", "source_type",
            name="uq_balance_sheet_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    company_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    company_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    report_year: Mapped[int] = mapped_column( nullable=False)
    period_code: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("34")
    )
    period_name: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    load_date: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    line_code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    line_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    okei_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    amount: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    amount_prev: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    amount_before_prev: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'api_fns'")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("balance_sheet.id", ondelete="SET NULL"),
        nullable=True,
    )
    xml_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class FinancialResult(Base):
    """Normalized financial result rows (form ОКУД 0710002)."""

    __tablename__ = "financial_result"
    __table_args__ = (
        sa.Index("idx_fr_lookup", "company_inn", "report_year", "line_code", "source_type"),
        sa.Index("idx_fr_active", "company_inn", "is_active"),
        sa.Index("idx_fr_period", "company_inn", "period_code", "report_year"),
        sa.UniqueConstraint(
            "company_inn", "report_year", "period_code", "line_code", "source_type",
            name="uq_financial_result_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    company_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    company_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    report_year: Mapped[int] = mapped_column( nullable=False)
    period_code: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("34")
    )
    period_name: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    load_date: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    line_code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    line_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    okei_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    amount: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    amount_prev: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'api_fns'")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("financial_result.id", ondelete="SET NULL"),
        nullable=True,
    )
    xml_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class CashFlow(Base):
    """Normalized cash flow rows (form ОКУД 0710005)."""

    __tablename__ = "cash_flow"
    __table_args__ = (
        sa.Index("idx_cf_lookup", "company_inn", "report_year", "line_code", "source_type"),
        sa.Index("idx_cf_active", "company_inn", "is_active"),
        sa.Index("idx_cf_period", "company_inn", "period_code", "report_year"),
        sa.UniqueConstraint(
            "company_inn", "report_year", "period_code", "line_code", "source_type",
            name="uq_cash_flow_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    company_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    company_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    report_year: Mapped[int] = mapped_column( nullable=False)
    period_code: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("34")
    )
    period_name: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    load_date: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    line_code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    line_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    okei_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    amount: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    amount_prev: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'api_fns'")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("cash_flow.id", ondelete="SET NULL"),
        nullable=True,
    )
    xml_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class CapitalChanges(Base):
    """Normalized capital changes rows (form ОКУД 0710004).

    Each component (УстКапитал, СобВыкупАкц, etc.) produces a separate row.
    """

    __tablename__ = "capital_changes"
    __table_args__ = (
        sa.Index("idx_cc_lookup", "company_inn", "report_year", "line_code", "component_code", "source_type"),
        sa.Index("idx_cc_active", "company_inn", "is_active"),
        sa.Index("idx_cc_period", "company_inn", "period_code", "report_year"),
        sa.UniqueConstraint(
            "company_inn", "report_year", "period_code", "line_code", "component_code", "source_type",
            name="uq_capital_changes_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    company_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    company_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    report_year: Mapped[int] = mapped_column( nullable=False)
    period_code: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("34")
    )
    period_name: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    load_date: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    line_code: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    line_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    component_code: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    component_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    okei_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    amount: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    amount_prev: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'api_fns'")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("capital_changes.id", ondelete="SET NULL"),
        nullable=True,
    )
    xml_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class NDSTaxRate(Base):
    """Reference table for NDS (VAT) tax rate XML tags."""

    __tablename__ = "nds_tax_rates"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    xml_tag: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    tax_base_description: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    tax_amount_description: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class NDSDeclaration(Base):
    """Normalized NDS (VAT) declaration rows."""

    __tablename__ = "nds_declaration"
    __table_args__ = (
        sa.Index("idx_nds_lookup", "company_inn", "report_year", "tax_rate_id", "source_type"),
        sa.Index("idx_nds_active", "company_inn", "is_active"),
        sa.Index("idx_nds_period", "company_inn", "period_code", "report_year"),
        sa.UniqueConstraint(
            "company_inn", "report_year", "period_code", "tax_rate_id", "source_type",
            name="uq_nds_declaration_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    company_kpp: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    company_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    report_year: Mapped[int] = mapped_column( nullable=False)
    period_code: Mapped[int] = mapped_column(
        sa.SmallInteger, nullable=False, server_default=sa.text("34")
    )
    period_name: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    load_date: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    tax_rate_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("nds_tax_rates.id", ondelete="CASCADE"),
        nullable=False,
    )
    tax_base: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    tax_amount: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    total_tax_payable: Mapped[float] = mapped_column(
        sa.Numeric(20, 2), nullable=False, server_default=sa.text("0")
    )
    total_deductions: Mapped[float] = mapped_column(
        sa.Numeric(20, 2), nullable=False, server_default=sa.text("0")
    )
    total_recovered: Mapped[float | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    source_type: Mapped[str] = mapped_column(
        sa.String(10), nullable=False, server_default=sa.text("'xml_file'")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), nullable=False
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("nds_declaration.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )

