"""SQLAlchemy ORM models for the self-contained "fast deal" registration process.

A fast deal records a deal already agreed outside the platform between a dealer
and a leasing company (DD: dealer → leasing, DL: leasing → dealer). It is its own
aggregate, never a disguised ordinary leasing application.

Historical rows are never removed by cascade: sent deals keep their audit trail,
offers and files. Only a never-sent draft is deleted, by an explicit use case that
removes its children first.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column

from infrastructure.models import Base

DEAL_STATUSES = (
    "draft",
    "pending_lc_confirmation",
    "pending_lc_final_confirmation",
    "pending_dealer_confirmation",
    "pending_lc_changes_confirmation",
    "confirmed",
    "rejected",
    "cancelled",
)
LC_APPLICATION_STATUSES = (
    "pending_review",
    "offer_sent",
    "selected_by_dealer",
    "confirmed",
    "rejected",
    "closed_not_selected",
)
FILE_KINDS = ("deal_main", "deal_additional", "lc_offer_pdf", "vehicle_offer")
SUPPORT_REQUEST_STATUSES = ("requested", "pre_approved", "approved", "cancelled")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _uuid_pk() -> MappedColumn[uuid.UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts_now() -> MappedColumn[datetime]:
    return mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class FastDeal(Base):
    """Root aggregate: parties, requested/final terms, version and review cycle."""

    __tablename__ = "fast_deals"
    __table_args__ = (
        sa.UniqueConstraint("display_number", name="uq_fast_deals_display_number"),
        sa.CheckConstraint(
            "source_type IN ('dealer_to_leasing', 'leasing_to_dealer')",
            name="ck_fast_deals_source_type",
        ),
        sa.CheckConstraint(
            _in_list("status", DEAL_STATUSES), name="ck_fast_deals_status"
        ),
        sa.CheckConstraint(
            "down_payment_mode IS NULL OR down_payment_mode IN ('amount', 'percent')",
            name="ck_fast_deals_down_payment_mode",
        ),
        sa.CheckConstraint(
            "lease_term_months IS NULL OR lease_term_months BETWEEN 12 AND 84",
            name="ck_fast_deals_lease_term",
        ),
        sa.CheckConstraint(
            "final_lease_term_months IS NULL OR final_lease_term_months BETWEEN 12 AND 84",
            name="ck_fast_deals_final_lease_term",
        ),
        sa.CheckConstraint(
            "(down_payment IS NULL OR down_payment >= 0) "
            "AND (monthly_payment IS NULL OR monthly_payment >= 0) "
            "AND (buyout_amount IS NULL OR buyout_amount >= 0) "
            "AND (calculated_monthly_payment IS NULL OR calculated_monthly_payment >= 0) "
            "AND vehicles_total >= 0 "
            "AND (confirmed_amount IS NULL OR confirmed_amount >= 0)",
            name="ck_fast_deals_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "(final_total_amount IS NULL OR final_total_amount >= 0) "
            "AND (final_down_payment IS NULL OR final_down_payment >= 0) "
            "AND (final_monthly_payment IS NULL OR final_monthly_payment >= 0) "
            "AND (final_total_cost IS NULL OR final_total_cost >= 0) "
            "AND (final_buyout_amount IS NULL OR final_buyout_amount >= 0)",
            name="ck_fast_deals_final_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "down_payment_percent IS NULL OR "
            "(down_payment_percent >= 0 AND down_payment_percent <= 100)",
            name="ck_fast_deals_down_payment_percent",
        ),
        sa.CheckConstraint(
            "client_phone ~ '^\\+7[0-9]{10}$'", name="ck_fast_deals_client_phone"
        ),
        sa.CheckConstraint(
            "version >= 1 AND review_cycle >= 1", name="ck_fast_deals_counters"
        ),
        sa.CheckConstraint(
            "source_type <> 'dealer_to_leasing' "
            "OR dealer_company_id = initiator_company_id",
            name="ck_fast_deals_dd_dealer_is_initiator",
        ),
        sa.CheckConstraint(
            "source_type <> 'leasing_to_dealer' "
            "OR leasing_company_id = initiator_company_id",
            name="ck_fast_deals_dl_leasing_is_initiator",
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR "
            "(confirmed_amount IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_fast_deals_confirmed_snapshot",
        ),
        sa.Index(
            "idx_fast_deals_initiator_created",
            "initiator_company_id",
            sa.desc("created_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_fast_deals_dealer_created",
            "dealer_company_id",
            sa.desc("created_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_fast_deals_leasing_created",
            "leasing_company_id",
            sa.desc("created_at"),
            sa.desc("id"),
        ),
        sa.Index(
            "idx_fast_deals_client_created",
            "client_company_id",
            sa.desc("created_at"),
            sa.desc("id"),
        ),
        sa.Index("idx_fast_deals_status_source", "status", "source_type"),
        sa.Index(
            "idx_fast_deals_group",
            "group_id",
            postgresql_where=sa.text("group_id IS NOT NULL"),
        ),
        sa.Index("idx_fast_deals_created_by", "created_by"),
        sa.Index("idx_fast_deals_created_at", sa.desc("created_at"), sa.desc("id")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    display_number: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(40), nullable=False, server_default=sa.text("'draft'")
    )
    # DL split group: the original deal id. A logical key, deliberately no FK.
    group_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    client_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_phone: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    initiator_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    leasing_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    final_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "fast_deal_offers.id",
            ondelete="RESTRICT",
            name="fk_fast_deals_final_offer",
            use_alter=True,
        ),
        nullable=True,
    )

    # Requested terms (DD: dealer's request; DL: terms set by the leasing company).
    down_payment_mode: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    down_payment: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    down_payment_percent: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    lease_term_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    monthly_payment: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    monthly_payment_is_manual: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    calculated_monthly_payment: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    buyout_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    calc_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    vehicles_total: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )

    # Final terms are copied from the chosen offer (DD) or the accepted terms (DL).
    final_total_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    final_down_payment: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    final_down_payment_percent: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    final_lease_term_months: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    final_monthly_payment: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    final_total_cost: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    final_buyout_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)

    has_pending_changes: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    # DL: state sent to the dealer, the "before" side of dealer changes.
    sent_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confirmed_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    review_cycle: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()


class FastDealVehicle(Base):
    """One physical unit (no quantity) with price, options and a catalog snapshot."""

    __tablename__ = "fast_deal_vehicles"
    __table_args__ = (
        sa.CheckConstraint(
            "vehicle_source_type IN ('product', 'manual')",
            name="ck_fast_deal_vehicles_source_type",
        ),
        sa.CheckConstraint(
            "item_status IN ('active', 'removed', 'replaced')",
            name="ck_fast_deal_vehicles_item_status",
        ),
        sa.CheckConstraint(
            "base_price >= 0 AND final_price >= 0 AND support_amount >= 0 "
            "AND options_amount >= 0",
            name="ck_fast_deal_vehicles_amounts",
        ),
        sa.CheckConstraint(
            "(adjustment_type IS NULL AND adjustment_amount IS NULL) OR "
            "(adjustment_type IN ('discount', 'markup') "
            "AND adjustment_amount IS NOT NULL AND adjustment_amount > 0)",
            name="ck_fast_deal_vehicles_adjustment",
        ),
        sa.CheckConstraint(
            "replaced_by_id IS NULL OR item_status = 'replaced'",
            name="ck_fast_deal_vehicles_replaced_by",
        ),
        sa.CheckConstraint(
            "NOT is_reservable OR (vehicle_source_type = 'product' "
            "AND product_id IS NOT NULL AND NOT vin_entered_manually)",
            name="ck_fast_deal_vehicles_reservable",
        ),
        sa.Index(
            "uq_fast_deal_vehicles_active_vin",
            "fast_deal_id",
            "vin",
            unique=True,
            postgresql_where=sa.text("item_status = 'active'"),
        ),
        sa.Index(
            "uq_fast_deal_vehicles_active_product",
            "fast_deal_id",
            "product_id",
            unique=True,
            postgresql_where=sa.text("item_status = 'active' AND product_id IS NOT NULL"),
        ),
        sa.Index("idx_fast_deal_vehicles_deal", "fast_deal_id", "position"),
        sa.Index(
            "idx_fast_deal_vehicles_product",
            "product_id",
            postgresql_where=sa.text("product_id IS NOT NULL"),
        ),
        sa.Index("idx_fast_deal_vehicles_dealer", "dealer_company_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fast_deal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    vehicle_source_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    mark_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_marks.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_models.id", ondelete="SET NULL"),
        nullable=True,
    )
    modification_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_modifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    trim_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_trims.id", ondelete="SET NULL"),
        nullable=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    body_color_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_colors.id", ondelete="SET NULL"),
        nullable=True,
    )
    body_color_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    mark_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    modification_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    trim_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    category_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    vin: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    vin_entered_manually: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    is_reservable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
    )
    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    base_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    adjustment_type: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    adjustment_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    equipments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    services: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    purposes: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    regions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    support_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )
    options_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )
    final_price: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    item_status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'active'")
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_vehicles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    catalog_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()


class FastDealLcApplication(Base):
    """A leasing company's invitation record (DD) in one review cycle."""

    __tablename__ = "fast_deal_lc_applications"
    __table_args__ = (
        sa.CheckConstraint(
            _in_list("status", LC_APPLICATION_STATUSES),
            name="ck_fast_deal_lc_applications_status",
        ),
        sa.CheckConstraint(
            "review_cycle >= 1", name="ck_fast_deal_lc_applications_cycle"
        ),
        sa.Index(
            "uq_fast_deal_lc_applications_active",
            "fast_deal_id",
            "leasing_company_id",
            unique=True,
            postgresql_where=sa.text("archived_at IS NULL AND status <> 'rejected'"),
        ),
        sa.Index("idx_fast_deal_lc_applications_deal", "fast_deal_id", "review_cycle"),
        sa.Index(
            "idx_fast_deal_lc_applications_company",
            "leasing_company_id",
            "status",
            sa.desc("created_at"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fast_deal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default=sa.text("'pending_review'")
    )
    current_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey(
            "fast_deal_offers.id",
            ondelete="RESTRICT",
            name="fk_fast_deal_lc_applications_current_offer",
            use_alter=True,
        ),
        nullable=True,
    )
    review_cycle: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    selected_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()


class FastDealOffer(Base):
    """Immutable commercial proposal (КП) of one leasing company invitation."""

    __tablename__ = "fast_deal_offers"
    __table_args__ = (
        sa.CheckConstraint(
            "lease_term_months BETWEEN 12 AND 84",
            name="ck_fast_deal_offers_lease_term",
        ),
        sa.CheckConstraint(
            "total_amount >= 0 AND down_payment >= 0 AND monthly_payment >= 0 "
            "AND total_cost >= 0 AND buyout_amount >= 0",
            name="ck_fast_deal_offers_amounts",
        ),
        sa.Index("idx_fast_deal_offers_lc_application", "lc_application_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    lc_application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_lc_applications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_cycle: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    total_amount: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    down_payment: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    down_payment_percent: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    lease_term_months: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    buyout_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )
    rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    markup: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    total_interest: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    vat_refund: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    profit_tax_savings: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(15, 2), nullable=True
    )
    total_savings: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    optional_financial_terms: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    pdf_file_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_files.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = _ts_now()
    superseded_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class FastDealStatusHistory(Base):
    """Append-only audit: actor, transition, reason and changed business fields."""

    __tablename__ = "fast_deal_status_history"
    __table_args__ = (
        sa.Index("idx_fast_deal_history_deal", "fast_deal_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fast_deal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lc_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_lc_applications.id", ondelete="RESTRICT"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(sa.String(48), nullable=False)
    from_status: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    deal_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    review_cycle: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    created_at: Mapped[datetime] = _ts_now()


class FastDealSupportRequest(Base):
    """Dealer's request for additional support, decided by their distributor."""

    __tablename__ = "fast_deal_support_requests"
    __table_args__ = (
        sa.CheckConstraint(
            _in_list("status", SUPPORT_REQUEST_STATUSES),
            name="ck_fast_deal_support_requests_status",
        ),
        sa.CheckConstraint(
            "requested_amount > 0", name="ck_fast_deal_support_requests_requested"
        ),
        sa.CheckConstraint(
            "decided_amount IS NULL OR decided_amount > 0",
            name="ck_fast_deal_support_requests_decided",
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR decided_amount IS NOT NULL",
            name="ck_fast_deal_support_requests_approved_amount",
        ),
        sa.CheckConstraint(
            "accounted_amount >= 0", name="ck_fast_deal_support_requests_accounted"
        ),
        sa.Index(
            "uq_fast_deal_support_requests_open",
            "fast_deal_vehicle_id",
            unique=True,
            postgresql_where=sa.text("status IN ('requested', 'pre_approved')"),
        ),
        sa.Index(
            "idx_fast_deal_support_requests_distributor",
            "distributor_company_id",
            "status",
            sa.desc("created_at"),
        ),
        sa.Index("idx_fast_deal_support_requests_deal", "fast_deal_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fast_deal_vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_vehicles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fast_deal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    distributor_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_amount: Mapped[Decimal] = mapped_column(sa.Numeric(15, 2), nullable=False)
    decided_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    # Part of the decided amount already subtracted from the vehicle price.
    accounted_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )
    status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'requested'")
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()


class FastDealFile(Base):
    """Private object metadata; one row per addressee, shared storage object."""

    __tablename__ = "fast_deal_files"
    __table_args__ = (
        sa.CheckConstraint(
            _in_list("kind", FILE_KINDS), name="ck_fast_deal_files_kind"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_fast_deal_files_size"),
        sa.CheckConstraint(
            "(kind = 'vehicle_offer') = (fast_deal_vehicle_id IS NOT NULL)",
            name="ck_fast_deal_files_vehicle_link",
        ),
        sa.CheckConstraint(
            "kind <> 'deal_main' OR addressee_company_id IS NULL",
            name="ck_fast_deal_files_main_unaddressed",
        ),
        sa.CheckConstraint(
            "kind <> 'deal_additional' OR addressee_company_id IS NOT NULL",
            name="ck_fast_deal_files_additional_addressed",
        ),
        sa.CheckConstraint(
            "kind NOT IN ('lc_offer_pdf', 'vehicle_offer') OR lc_application_id IS NOT NULL",
            name="ck_fast_deal_files_lc_link",
        ),
        sa.Index("idx_fast_deal_files_deal", "fast_deal_id", "kind"),
        sa.Index(
            "idx_fast_deal_files_addressee",
            "addressee_company_id",
            postgresql_where=sa.text("addressee_company_id IS NOT NULL"),
        ),
        sa.Index("idx_fast_deal_files_storage_key", "storage_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fast_deal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fast_deal_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_vehicles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    lc_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_lc_applications.id", ondelete="RESTRICT"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(sa.String(24), nullable=False)
    addressee_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    storage_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    filename: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_by_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = _ts_now()


class FastDealAssignee(Base):
    """Responsible employee of one party: one primary and at most one additional."""

    __tablename__ = "fast_deal_assignees"
    __table_args__ = (
        sa.CheckConstraint(
            "role IN ('primary', 'additional')", name="ck_fast_deal_assignees_role"
        ),
        sa.UniqueConstraint(
            "fast_deal_id", "company_id", "role", name="uq_fast_deal_assignees_role"
        ),
        sa.UniqueConstraint(
            "fast_deal_id", "company_id", "user_id", name="uq_fast_deal_assignees_user"
        ),
        sa.Index("idx_fast_deal_assignees_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fast_deal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
