"""SQLAlchemy ORM models for leasing application-related tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.models import Base
from infrastructure.models.enums import (
    application_status_enum,
    leasing_company_application_status_enum,
)


class LeasingApplication(Base):
    """ORM model for the leasing_applications table."""

    __tablename__ = "leasing_applications"
    __table_args__ = (
        sa.Index("idx_applications_current_stage", "current_stage"),
        sa.Index("idx_applications_questionnaire_progress", "questionnaire_progress"),
        sa.Index("idx_applications_status", "status"),
        sa.Index("idx_leasing_applications_company_id", "company_id"),
        sa.Index("idx_leasing_applications_dealer_company_id", "dealer_company_id"),
        sa.Index(
            "idx_leasing_applications_assigned_dealer_group_id",
            "assigned_dealer_group_id",
        ),
        sa.Index(
            "idx_leasing_applications_dealer_assigned_by",
            "dealer_assigned_by",
        ),
        sa.Index(
            "idx_leasing_applications_primary_employee_id",
            "primary_employee_id",
        ),
        sa.Index(
            "idx_leasing_applications_additional_employee_id",
            "additional_employee_id",
        ),
        sa.Index(
            "idx_leasing_applications_employees_assigned_by",
            "employees_assigned_by",
        ),
        sa.Index("idx_leasing_applications_display_number", "display_number"),
        sa.Index("idx_leasing_applications_source_type", "source_type"),
        sa.Index("idx_leasing_applications_email", "email"),
        sa.Index(
            "idx_leasing_applications_selected_companies", "selected_leasing_companies"
        ),
        sa.Index("idx_leasing_applications_vehicle_id", "vehicle_id"),
        sa.Index("idx_leasing_applications_group_id", "group_id"),
        sa.Index("idx_leasing_applications_storefront_id", "storefront_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    storefront_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefronts.id",
            name="fk_leasing_applications_storefront_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        default=lambda: DEFAULT_STOREFRONT_ID,
        server_default=sa.text("'00000000-0000-0000-0000-000000000001'::uuid"),
    )
    source_type: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    display_number: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id"),
        nullable=False,
    )
    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_dealer_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    dealer_assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dealer_assigned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    primary_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    additional_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    employees_assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    employees_assigned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(
        application_status_enum,
        server_default="active",
        nullable=True,
    )
    total_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment_percent: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    lease_term_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    monthly_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(12, 2), nullable=True
    )
    total_cost: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    markup: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    rate: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    total_interest: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    buyout_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=True
    )
    vat_refund: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    profit_tax_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    selected_leasing_companies: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=True
    )
    leasing_company_comments: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    requested_documents: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    comments_updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    documents_requested_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    client_visible_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    client_comment_updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    questionnaire_completed: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    questionnaire_progress: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=True
    )
    current_stage: Mapped[str | None] = mapped_column(
        sa.String(50), server_default=sa.text("'leasing_companies'"), nullable=True
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
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    deal_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    deal_documents: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )


class LeasingCompanyApplication(Base):
    """ORM model for the leasing_company_applications table."""

    __tablename__ = "leasing_company_applications"
    __table_args__ = (sa.Index("idx_lca_submitted_at", "submitted_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id"),
        nullable=True,
    )
    leasing_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id"),
        nullable=True,
    )
    status: Mapped[str | None] = mapped_column(
        leasing_company_application_status_enum,
        server_default="under_review",
        nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    response_pdf_s3_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    response_pdf_file_name: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )
    response_pdf_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    response_pdf_uploaded_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
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


class LeasingProposal(Base):
    """ORM model for the leasing_proposals table.

    Each row is one commercial proposal (КП) attached to a
    LeasingCompanyApplication. An LCA may have many proposals — the LC
    creates the first one with parameters pre-filled from the parent
    LeasingApplication, then optionally adds further КП variants
    (e.g. a longer term offering).
    """

    __tablename__ = "leasing_proposals"
    __table_args__ = (
        sa.Index("idx_leasing_proposals_lca_id", "leasing_company_application_id"),
        sa.UniqueConstraint(
            "leasing_company_application_id",
            "kind",
            name="uq_leasing_proposals_lca_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leasing_company_application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_company_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        sa.Enum(
            "preliminary",
            "final",
            name="leasing_proposal_kind",
            create_type=False,
        ),
        server_default="preliminary",
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("1"), nullable=False
    )
    total_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment_percent: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    lease_term_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    monthly_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(12, 2), nullable=True
    )
    total_cost: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    markup: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    rate: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    total_interest: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    buyout_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=True
    )
    vat_refund: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    profit_tax_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    client_decision_action: Mapped[str | None] = mapped_column(
        sa.String(16), nullable=True
    )
    client_decision_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    client_decision_comment: Mapped[str | None] = mapped_column(
        sa.Text(), nullable=True
    )
    pdf_s3_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    pdf_file_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    pdf_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    pdf_uploaded_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )


class ShoppingCart(Base):
    """ORM model for the shopping_cart table."""

    __tablename__ = "shopping_cart"
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "storefront_id",
            "product_id",
            name="shopping_cart_user_vehicle_unique",
        ),
        sa.Index("idx_shopping_cart_modification", "modification_id"),
        sa.Index("idx_shopping_cart_user", "user_id"),
        sa.Index("idx_shopping_cart_product_id", "product_id"),
        sa.Index("idx_shopping_cart_storefront_id", "storefront_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    storefront_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "catalog_storefronts.id",
            name="fk_shopping_cart_storefront_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        default=lambda: DEFAULT_STOREFRONT_ID,
        server_default=sa.text("'00000000-0000-0000-0000-000000000001'::uuid"),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    modification_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("1"), nullable=False
    )
    allow_overstock: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    is_selected: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    custom_price: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    equipments: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    services: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    added_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    vehicle_id = synonym("product_id")


class ApplicationVehicle(Base):
    """ORM model for the application_vehicles table."""

    __tablename__ = "application_vehicles"
    __table_args__ = (
        sa.CheckConstraint("requested_quantity IS NULL OR requested_quantity > 0", name="ck_application_requested_quantity"),
        sa.CheckConstraint("confirmed_quantity IS NULL OR confirmed_quantity > 0", name="ck_application_confirmed_quantity"),
        sa.Index("idx_application_vehicles_car_status", "car_status"),
        sa.UniqueConstraint("application_id", "product_id", name="uq_application_vehicles"),
        sa.Index("idx_application_vehicles_application_id", "application_id"),
        sa.Index("idx_application_vehicles_is_model_order", "is_model_order"),
        sa.Index("idx_application_vehicles_modification_id", "modification_id"),
        sa.Index("idx_application_vehicles_product_id", "product_id"),
        sa.Index(
            "idx_application_vehicles_reservation_due", "reserve_expires_at", "id",
            postgresql_where=sa.text("car_status = 'confirmed' AND reserve_expires_at IS NOT NULL"),
        ),
        sa.Index("idx_application_vehicles_dealer_company_id", "dealer_company_id"),
        sa.Index("idx_application_vehicles_dealer_assigned_by", "dealer_assigned_by"),
        sa.Index("idx_application_vehicles_primary_employee_id", "primary_employee_id"),
        sa.Index(
            "idx_application_vehicles_additional_employee_id", "additional_employee_id"
        ),
        sa.Index(
            "idx_application_vehicles_employees_assigned_by", "employees_assigned_by"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id"),
        nullable=True,
    )
    vehicle_id = synonym("product_id")
    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    dealer_assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dealer_assigned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    primary_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    additional_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    employees_assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    employees_assigned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    modification_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    quantity: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("1"), nullable=True
    )
    requested_quantity: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    confirmed_quantity: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    fulfillment_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    unit_price: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_price: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    equipments: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    services: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    leasing_purpose: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    leasing_purposes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    regions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    car_status: Mapped[str] = mapped_column(
        sa.String(50),
        sa.ForeignKey("cars_status.status_name", name="fk_application_vehicles_car_status"),
        nullable=False,
        server_default=sa.text("'active'"),
    )
    dealer_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reserve_expires_at: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    discount_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    discount_value: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    discount_show_catalog_price: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    markup_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    markup_value: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    markup_show_catalog_price: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    final_price: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    vin: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    vin_assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    vin_assigned_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    is_model_order: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class ApplicationDealerDistributionRequest(Base):
    """An atomic, idempotent assignment of quantities to a dealer."""

    __tablename__ = "application_dealer_distribution_requests"
    __table_args__ = (
        sa.UniqueConstraint(
            "application_id",
            "distributor_company_id",
            "client_request_id",
            name="uq_dealer_distribution_request",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    payload_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class ApplicationVehicleDealerDistribution(Base):
    """Quantity assignments without duplicating commercial application lines."""

    __tablename__ = "application_vehicle_dealer_distributions"
    __table_args__ = (
        sa.CheckConstraint("quantity > 0", name="ck_dealer_distribution_quantity"),
        sa.UniqueConstraint(
            "request_id",
            "application_vehicle_id",
            name="uq_dealer_distribution_request_line",
        ),
        sa.Index("idx_dealer_distribution_line", "application_vehicle_id"),
        sa.Index("idx_dealer_distribution_dealer", "dealer_company_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("application_vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "application_dealer_distribution_requests.id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class ApplicationVehicleDealerActionDocument(Base):
    """Files attached by dealer actions on application vehicles."""

    __tablename__ = "application_vehicle_dealer_action_documents"
    __table_args__ = (
        sa.Index(
            "idx_av_dealer_action_docs_application_vehicle_id",
            "application_vehicle_id",
        ),
        sa.Index("idx_av_dealer_action_docs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    application_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("application_vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    file_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    file_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class LeasingPurpose(Base):
    """Reference dictionary for vehicle leasing purposes."""

    __tablename__ = "leasing_purpose"

    purpose_name: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    purpose_display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)


class AdditionalEquipment(Base):
    """Reference dictionary for selectable additional equipment."""

    __tablename__ = "additional_equipments"

    equipment_code: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    equipment_display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )


class AdditionalService(Base):
    """Reference dictionary for selectable additional services."""

    __tablename__ = "additional_services"

    service_code: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    service_display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )


class LeasingRegion(Base):
    """Reference dictionary for selectable leasing regions."""

    __tablename__ = "leasing_region"
    __table_args__ = (
        sa.Index("idx_leasing_region_display_name", "region_display_name"),
        sa.Index("idx_leasing_region_number", "region_number"),
    )

    region_name: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    region_display_name: Mapped[str] = mapped_column(
        sa.String(255), nullable=False, unique=True
    )
    region_number: Mapped[str] = mapped_column(
        sa.String(2), nullable=False, unique=True
    )


class CarsStatus(Base):
    """Reference dictionary for dealer-facing application vehicle statuses."""

    __tablename__ = "cars_status"

    status_name: Mapped[str] = mapped_column(sa.String(50), primary_key=True)
    status_display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)


class LeasingApplicationComment(Base):
    """ORM model for the leasing_application_comments table."""

    __tablename__ = "leasing_application_comments"
    __table_args__ = (
        sa.Index("idx_leasing_application_comments_app_id", "leasing_application_id"),
        sa.Index("idx_leasing_application_comments_created_at", "created_at"),
        sa.Index("idx_leasing_application_comments_type", "comment_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leasing_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    comment_type: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    comment_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class ApplicationQuestionnaire(Base):
    """ORM model for the application_questionnaires table."""

    __tablename__ = "application_questionnaires"
    __table_args__ = (
        sa.UniqueConstraint("application_id"),
        sa.Index("idx_questionnaires_application_id", "application_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_company_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    short_company_name: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )
    inn: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    kpp: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    okpo: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    okato: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    okved_main: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    okved_additional: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    tax_system: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    legal_form: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    legal_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    legal_address_matches_registration: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    actual_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    actual_address_same_as_legal: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    actual_address_details: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    postal_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    fax: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    bik: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    settlement_account: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    director_full_name: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )
    director_position: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    director_passport_series: Mapped[str | None] = mapped_column(
        sa.String(30), nullable=True
    )
    director_passport_number: Mapped[str | None] = mapped_column(
        sa.String(30), nullable=True
    )
    director_passport_issued_by: Mapped[str | None] = mapped_column(
        sa.Text, nullable=True
    )
    director_passport_issue_date: Mapped[sa.Date | None] = mapped_column(
        sa.Date, nullable=True
    )
    director_passport_department_code: Mapped[str | None] = mapped_column(
        sa.String(30), nullable=True
    )
    director_birth_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    director_birth_place: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    director_citizenship: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    director_registration_address: Mapped[str | None] = mapped_column(
        sa.Text, nullable=True
    )
    director_actual_address: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    director_phone: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    director_email: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    director_surname: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    director_first_name: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    director_patronymic: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    director_sex: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    director_birth_country: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    director_registration_country: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    director_registration_postal_code: Mapped[str | None] = mapped_column(
        sa.String(10), nullable=True
    )
    director_registration_house: Mapped[str | None] = mapped_column(
        sa.String(50), nullable=True
    )
    director_registration_apartment: Mapped[str | None] = mapped_column(
        sa.String(50), nullable=True
    )
    director_registration_date: Mapped[sa.Date | None] = mapped_column(
        sa.Date, nullable=True
    )
    director_actual_country: Mapped[str | None] = mapped_column(
        sa.String(100), nullable=True
    )
    director_actual_postal_code: Mapped[str | None] = mapped_column(
        sa.String(10), nullable=True
    )
    director_actual_house: Mapped[str | None] = mapped_column(
        sa.String(50), nullable=True
    )
    director_actual_apartment: Mapped[str | None] = mapped_column(
        sa.String(50), nullable=True
    )
    director_actual_same_as_registration: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    founders: Mapped[dict | None] = mapped_column(
        JSONB, server_default=sa.text("'[]'"), nullable=True
    )
    beneficiaries: Mapped[dict | None] = mapped_column(
        JSONB, server_default=sa.text("'[]'"), nullable=True
    )
    has_beneficiary: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    other_representatives: Mapped[dict | None] = mapped_column(
        JSONB, server_default=sa.text("'[]'"), nullable=True
    )
    beneficiary_info: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    management_bodies: Mapped[dict | None] = mapped_column(
        JSONB, server_default=sa.text("'[]'"), nullable=True
    )
    registration_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    registration_authority_name: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    postal_address_matches_legal: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    company_phone: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    company_email: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    company_website: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    contact_person: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    correspondent_account: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    director_inn: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    director_snils: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    director_appointment_document: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    director_is_pdl: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    director_pdl_related_person: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    director_name_changed: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    employee_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    licenses_or_sro_membership: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    main_counterparties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    open_bank_accounts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    loans_credits_leasing: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    third_party_guarantees: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    additional_collateral_available: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    vehicle_purchase_purpose: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    management_company_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transaction_beneficiary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    electronic_document_management_systems: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    website_in_blocked_domains_registry: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    state_defense_order: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    personal_data_processing_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    legal_entity_credit_report_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    individual_credit_report_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    credit_bureau_data_transfer_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    marketing_communications_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    information_accuracy_declaration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    information_verification_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    permitted_data_recipients: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    telecom_data_transfer_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    federal_register_inclusion_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    affiliates_data_transfer_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    electronic_documents_equivalence_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    automated_marketing_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    biometric_data_processing_consent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    consent_validity_period: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    consent_revocation_procedure: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    questionnaire_completed_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    authorized_person_signature: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    company_seal: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    foreign_company_name: Mapped[str | None] = mapped_column(sa.String(), nullable=True)
    no_beneficial_owner_reason: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey("beneficial_owner_absence_reasons.id", ondelete="RESTRICT"), nullable=True)
    no_beneficial_owner_reason_details: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    field_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    people_identity_map: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
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


class LeasingApplicationCalculation(Base):
    """ORM model for the leasing_application_calculations table."""

    __tablename__ = "leasing_application_calculations"

    leasing_application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    monthly_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    rate: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    total_cost: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_interest: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    buyout_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    vat_refund: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    profit_tax_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    base_total: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    vehicle_discount_support: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    dealer_commission_support: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment_support: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    interest_support: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    effective_total: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    effective_down_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    selected_support: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    support_per_vehicle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    support_per_program: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    support_program_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    calculations_per_vehicle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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


class LeasingApplicationVehicleCalculation(Base):
    """ORM model for the leasing_application_vehicle_calculations table."""

    __tablename__ = "leasing_application_vehicle_calculations"
    __table_args__ = (
        sa.Index("idx_lavc_leasing_application_id", "leasing_application_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leasing_application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    modification_id: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    color: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("1"), nullable=False
    )
    unit_price: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)
    total_amount: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)
    down_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment_percent: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    lease_term_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    buyout_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    monthly_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    rate: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    total_cost: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_interest: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    vat_refund: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    profit_tax_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=False
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class CalculationHistory(Base):
    """ORM model for the calculation_history table."""

    __tablename__ = "calculation_history"
    __table_args__ = (
        sa.Index("idx_calculation_history_created_at", sa.text("created_at DESC")),
        sa.Index("idx_calculation_history_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    vehicle_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=True
    )
    total_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    down_payment_percent: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    lease_term_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    monthly_payment: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(12, 2), nullable=True
    )
    total_cost: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    markup: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    rate: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    total_interest: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    buyout_amount: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=True
    )
    vat_refund: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    profit_tax_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_savings: Mapped[sa.Numeric | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    calculation_type: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )


class LeasingCompanyDocumentRequirement(Base):
    """ORM model for the leasing_company_document_requirements table."""

    __tablename__ = "leasing_company_document_requirements"
    __table_args__ = (
        sa.Index(
            "idx_leasing_doc_req_unique",
            "leasing_company_id",
            "document_type_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("document_types.id"),
        nullable=False,
    )
    is_required: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    is_mandatory: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    sort_order: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=True
    )
    is_active: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )


class ApplicationVehicleAllocation(Base):
    """Physical units reserved for a commercial application line; never extra prices."""

    __tablename__ = "application_vehicle_allocations"
    __table_args__ = (
        sa.Index("uq_vehicle_active_allocation", "product_id", unique=True,
                 postgresql_where=sa.text("released_at IS NULL")),
        sa.Index("idx_allocation_line", "application_vehicle_id"),
        sa.Index("idx_allocation_fast_deal_vehicle", "fast_deal_vehicle_id",
                 postgresql_where=sa.text("fast_deal_vehicle_id IS NOT NULL")),
        sa.CheckConstraint(
            "(application_vehicle_id IS NULL) <> (fast_deal_vehicle_id IS NULL)",
            name="ck_allocation_exactly_one_source",
        ),
        sa.CheckConstraint(
            "reserved_until IS NOT NULL OR fast_deal_vehicle_id IS NOT NULL",
            name="ck_allocation_reserved_until_required",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Exactly one source claims the unit: an application line or a fast-deal position.
    application_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("application_vehicles.id", ondelete="RESTRICT"), nullable=True)
    fast_deal_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("fast_deal_vehicles.id", ondelete="RESTRICT"), nullable=True)
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("special_equipment_products.id", ondelete="RESTRICT"), nullable=False)
    vehicle_id = synonym("product_id")
    vin: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    # NULL only for a fast-deal claim, which never expires by itself.
    reserved_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    released_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    release_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class ApplicationVehicleFulfillmentHistory(Base):
    __tablename__ = "application_vehicle_fulfillment_history"
    __table_args__ = (sa.Index("idx_fulfillment_history_line", "application_vehicle_id"),)
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), sa.ForeignKey("application_vehicles.id", ondelete="RESTRICT"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    previous_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
