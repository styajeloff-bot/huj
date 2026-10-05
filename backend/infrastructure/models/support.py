"""SQLAlchemy ORM models for support-related tables."""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from infrastructure.models import Base
from infrastructure.models.enums import support_type_enum


class DealerGroup(Base):
    """ORM model for the dealer_groups table."""

    __tablename__ = "dealer_groups"
    __table_args__ = (
        sa.Index("idx_dealer_groups_distributor", "distributor_company_id"),
        sa.Index("idx_dealer_groups_active", "is_active"),
        sa.Index(
            "uq_dealer_groups_distributor_name_active",
            "distributor_company_id",
            sa.text("lower(name)"),
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distributor_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class DealerGroupMember(Base):
    """ORM model for dealer company membership in a distributor group."""

    __tablename__ = "dealer_group_members"
    __table_args__ = (
        sa.UniqueConstraint(
            "dealer_group_id",
            "dealer_company_id",
            name="uq_dealer_group_members_group_dealer_company",
        ),
        sa.Index("idx_dealer_group_members_group", "dealer_group_id"),
        sa.Index("idx_dealer_group_members_dealer_company", "dealer_company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    dealer_group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class SupportProgram(Base):
    """ORM model for the support_programs table."""

    __tablename__ = "support_programs"
    __table_args__ = (
        sa.Index("idx_support_programs_distributor", "distributor_id"),
        sa.Index("idx_support_programs_mark", "mark_id"),
        sa.Index("idx_support_programs_model", "model_id"),
        sa.Index("idx_support_programs_vin", "vin"),
        sa.Index("idx_support_programs_vins_gin", "vins", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
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
    model_ids: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    complectation_ids: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    vin: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    vins: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text), nullable=True)
    dealer_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    distributor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    support_type: Mapped[str] = mapped_column(support_type_enum, nullable=False)
    support_params: Mapped[dict] = mapped_column(
        JSONB, server_default=sa.text("'{}'"), nullable=False
    )
    production_year_from: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    production_year_to: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    production_date_from: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    production_date_to: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    delivery_date_from: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    delivery_date_to: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    starts_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    is_compatible: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    show_to_leasing_company: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True,
        comment="Показывать программу лизинговой компании в админке",
    )
    show_to_client: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.true(), nullable=True,
        comment="Показывать программу клиенту (калькулятор, корзина)",
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class SupportProgramCompatibility(Base):
    """Canonical undirected compatibility pair between support programs."""

    __tablename__ = "support_program_compatibilities"
    __table_args__ = (
        sa.CheckConstraint(
            "support_program_id < compatible_support_program_id",
            name="ck_support_program_compatibilities_canonical_order",
        ),
        sa.UniqueConstraint(
            "support_program_id",
            "compatible_support_program_id",
            name="uq_support_program_compatibilities_pair",
        ),
        sa.Index(
            "idx_support_program_compatibilities_compatible_program",
            "compatible_support_program_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    compatible_support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __init__(
        self,
        *,
        support_program_id: uuid.UUID,
        compatible_support_program_id: uuid.UUID,
    ) -> None:
        self.support_program_id = support_program_id
        self.compatible_support_program_id = compatible_support_program_id


class SupportProgramLeasingCompany(Base):
    """ORM model for the support_program_leasing_companies join table (composite primary key)."""

    __tablename__ = "support_program_leasing_companies"
    __table_args__ = (sa.PrimaryKeyConstraint("support_program_id", "leasing_company_id"),)

    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
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


class SupportProgramMark(Base):
    """ORM model for support_program_marks join table."""

    __tablename__ = "support_program_marks"
    __table_args__ = (
        sa.PrimaryKeyConstraint("support_program_id", "mark_id"),
        sa.Index("idx_support_program_marks_mark", "mark_id"),
        sa.Index("idx_support_program_marks_program", "support_program_id"),
    )

    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_marks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class SupportProgramDistributor(Base):
    """ORM model for support_program_distributors join table."""

    __tablename__ = "support_program_distributors"
    __table_args__ = (
        sa.PrimaryKeyConstraint("support_program_id", "distributor_id"),
        sa.Index("idx_support_program_distributors_distributor", "distributor_id"),
        sa.Index("idx_support_program_distributors_program", "support_program_id"),
    )

    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    distributor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class ApplicationAppliedSupport(Base):
    """Immutable support snapshot fixed at application submission time."""

    __tablename__ = "application_applied_supports"
    __table_args__ = (
        sa.Index("idx_application_applied_supports_application", "application_id"),
        sa.Index(
            "idx_application_applied_supports_exchange_request",
            "exchange_request_id",
        ),
        sa.Index("idx_application_applied_supports_program", "support_program_id"),
        sa.Index("idx_application_applied_supports_product", "product_id"),
        sa.UniqueConstraint(
            "exchange_request_id",
            "support_program_id",
            name="uq_application_applied_supports_exchange_program",
        ),
        sa.Index(
            "idx_application_applied_supports_fast_deal",
            "fast_deal_id",
            postgresql_where=sa.text("fast_deal_id IS NOT NULL"),
        ),
        sa.Index(
            "uq_application_applied_supports_fast_deal_position_program",
            "fast_deal_vehicle_id",
            "support_program_id",
            unique=True,
            postgresql_where=sa.text("fast_deal_vehicle_id IS NOT NULL"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(application_id, exchange_request_id, fast_deal_id) = 1",
            name="ck_application_applied_supports_exactly_one_source",
        ),
        sa.CheckConstraint(
            "fast_deal_vehicle_id IS NULL OR fast_deal_id IS NOT NULL",
            name="ck_application_applied_supports_fast_deal_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    exchange_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Fast-deal origin: never cascaded, a confirmed deal keeps its support history.
    fast_deal_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    fast_deal_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("fast_deal_vehicles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    vehicle_id = synonym("product_id")
    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    distributor_company_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    support_program_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    support_type: Mapped[str] = mapped_column(support_type_enum, nullable=False)
    support_params: Mapped[dict] = mapped_column(
        JSONB, server_default=sa.text("'{}'"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    starts_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    main_payer: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    base_amount: Mapped[sa.Numeric] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )
    support_amount: Mapped[sa.Numeric] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class SupportBillOfLading(Base):
    """ORM model for the support_bill_of_ladings table."""

    __tablename__ = "support_bill_of_ladings"
    __table_args__ = (
        sa.Index("idx_support_bill_of_ladings_support_program_id", "support_program_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    bill_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    file_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class SupportProgramDealerGroup(Base):
    """ORM model for the support_program_dealer_groups join table (composite primary key)."""

    __tablename__ = "support_program_dealer_groups"
    __table_args__ = (
        sa.PrimaryKeyConstraint("support_program_id", "dealer_group_id"),
        sa.Index("idx_support_program_dealer_groups_group", "dealer_group_id"),
        sa.Index("idx_support_program_dealer_groups_program", "support_program_id"),
    )

    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dealer_group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("dealer_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
