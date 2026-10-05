"""SQLAlchemy ORM models for company-related tables."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base
from infrastructure.models.enums import company_type_enum


class Company(Base):
    """ORM model for the companies table."""

    __tablename__ = "companies"
    __table_args__ = (
        sa.Index("idx_companies_inn", "inn"),
        sa.Index("idx_companies_type", "company_type"),
        sa.Index("idx_companies_enrichment_status", "enrichment_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    inn: Mapped[str | None] = mapped_column(sa.String(20), unique=True, nullable=True)
    kpp: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    company_type: Mapped[str] = mapped_column(company_type_enum, nullable=False)
    address: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    contact_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    legal_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    actual_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    is_active: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )

    # Enrichment fields, previously in company_1c_data (retired in 010).
    full_name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    short_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    okpo: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    okato: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    legal_form: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    legal_address_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    registration_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    registration_department: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    employees_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    main_okved_code: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    main_okved_description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    additional_okved_code: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    additional_okved_description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    additional_okved_list: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    director_full_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    director_position: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    director_inn: Mapped[str | None] = mapped_column(sa.String(12), nullable=True)
    founders: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bank_bik: Mapped[str | None] = mapped_column(sa.String(9), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    authorized_capital: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    net_profit: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    reporting_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    tax_system: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    enrichment_status: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    enrichment_attempts: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=True
    )
    enrichment_last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    enrichment_last_fetch_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class LeasingCompany(Base):
    """ORM model for the leasing_companies table."""

    __tablename__ = "leasing_companies"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id"),
        nullable=True,
    )
    average_down_payment_percent: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("30"), nullable=True
    )
    average_lease_term_months: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("72"), nullable=True
    )
    average_markup_percent: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 2), server_default=sa.text("10.0"), nullable=True
    )
    min_down_payment_percent: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("10"), nullable=True
    )
    max_lease_term_months: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("84"), nullable=True
    )
    special_offers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class Distributor(Base):
    """ORM model for the distributors table."""

    __tablename__ = "distributors"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id"),
        nullable=True,
    )
    regions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    brands: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    can_manage_dealer_groups: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class DistributorBrand(Base):
    """A soft-deactivatable vehicle brand assigned to a distributor company."""

    __tablename__ = "distributor_brands"
    __table_args__ = (
        sa.Index(
            "uq_distributor_brands_active_company_brand",
            "distributor_company_id",
            "brand_id",
            unique=True,
            postgresql_where=sa.text("is_active"),
        ),
        sa.Index(
            "idx_distributor_brands_active_company",
            "distributor_company_id",
            postgresql_where=sa.text("is_active"),
        ),
        sa.Index("idx_distributor_brands_brand_id", "brand_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    distributor_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "companies.id",
            name="fk_distributor_brands_company",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "special_equipment_marks.id",
            name="fk_distributor_brands_brand",
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        default=True,
        server_default=sa.true(),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    )


class DistributorDealerLink(Base):
    """ORM model for the distributor_dealer_links table.

    Links a distributor company to its dealer companies.
    One distributor → many dealers; one dealer → exactly one distributor.
    """

    __tablename__ = "distributor_dealer_links"
    __table_args__ = (
        sa.PrimaryKeyConstraint("distributor_company_id", "dealer_company_id"),
        sa.UniqueConstraint("dealer_company_id"),
    )

    distributor_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class LeasingCompanyUser(Base):
    """ORM model for the leasing_company_users table."""

    __tablename__ = "leasing_company_users"
    __table_args__ = (sa.UniqueConstraint("user_id", "leasing_company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
