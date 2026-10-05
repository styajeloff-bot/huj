"""Immutable financial snapshots, owned exclusively by monetization.

External participant/source identifiers are snapshots without cascading foreign keys.
Removing a source record cannot erase a financial agreement or its audit history.
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from infrastructure.models import Base


def _id() -> sa.Column[Any]:
    return sa.Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )


def _uuid(
    name: str, *, nullable: bool = True, target: str | None = None
) -> sa.Column[Any]:
    if target:
        return sa.Column(
            name,
            UUID(as_uuid=True),
            sa.ForeignKey(target, ondelete="RESTRICT"),
            nullable=nullable,
        )
    return sa.Column(name, UUID(as_uuid=True), nullable=nullable)


def _created() -> sa.Column[Any]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def _money(name: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, sa.Numeric(24, 8), nullable=nullable)


def build_tables(metadata: sa.MetaData) -> tuple[sa.Table, ...]:
    programs = sa.Table(
        "monetization_programs",
        metadata,
        _id(),
        sa.Column("name", sa.String(255), nullable=False),
        _uuid("leasing_company_id", nullable=False, target="leasing_companies.id"),
        _uuid("dealer_company_id"),
        _uuid("distributor_company_id"),
        _uuid("support_program_id"),
        sa.Column("brand", sa.String(100)),
        sa.Column("model", sa.String(100)),
        sa.Column("modification", sa.String(255)),
        sa.Column("trim", sa.String(255)),
        sa.Column("vin", sa.String(50)),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("rules_version", sa.Integer, nullable=False, server_default="2"),
        sa.Column("vehicle_filter_version", sa.Integer, nullable=False, server_default="2"),
        _uuid("created_by", nullable=False),
        _created(),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_monetization_program_status"
        ),
        sa.CheckConstraint(
            "period_end IS NULL OR period_end >= period_start",
            name="ck_monetization_program_period",
        ),
        sa.CheckConstraint(
            "rules_version IN (1, 2)", name="ck_monetization_program_rules_version"
        ),
        sa.CheckConstraint(
            "vehicle_filter_version IN (1, 2)",
            name="ck_monetization_program_vehicle_filter_version",
        ),
        sa.Index("idx_monetization_program_leasing", "leasing_company_id"),
    )
    sources = sa.Table(
        "monetization_program_sources",
        metadata,
        _id(),
        _uuid("program_id", nullable=False, target="monetization_programs.id"),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "source_type IN ('platform','dealer_account','exchange','dealer_site','distributor_site')",
            name="ck_monetization_source_type",
        ),
        sa.UniqueConstraint(
            "program_id", "position", name="uq_monetization_source_position"
        ),
    )
    participants = sa.Table(
        "monetization_program_source_participants",
        metadata,
        _id(),
        _uuid(
            "program_source_id",
            nullable=False,
            target="monetization_program_sources.id",
        ),
        sa.Column("local_id", sa.String(100), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("participant_type", sa.String(20), nullable=False),
        sa.Column("base_type", sa.String(20), nullable=False),
        sa.Column("calc_type", sa.String(10), nullable=False),
        _money("value"),
        _money("min", nullable=True),
        _money("max", nullable=True),
        sa.Column(
            "vat_excluded", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("expense_ref", sa.String(100)),
        sa.Column("position", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "side IN ('expense','income')", name="ck_monetization_participant_side"
        ),
        sa.CheckConstraint(
            "participant_type IN ('leasing','dealer','distributor','platform')",
            name="ck_monetization_participant_type",
        ),
        sa.CheckConstraint(
            "calc_type IN ('percent','amount')", name="ck_monetization_calc_type"
        ),
        sa.CheckConstraint(
            "base_type IN ('none','property_value','expense_amount')",
            name="ck_monetization_base_type",
        ),
        sa.CheckConstraint(
            "value > 0 AND (min IS NULL OR min >= 0) AND (max IS NULL OR max >= 0) AND (min IS NULL OR max IS NULL OR min <= max)",
            name="ck_monetization_participant_values",
        ),
        sa.CheckConstraint(
            "(base_type <> 'none' OR calc_type = 'amount') AND (side <> 'expense' OR base_type <> 'expense_amount')",
            name="ck_monetization_participant_base",
        ),
        sa.UniqueConstraint(
            "program_source_id", "local_id", name="uq_monetization_participant_local_id"
        ),
    )
    contracts = sa.Table(
        "monetization_program_contracts",
        metadata,
        _id(),
        _uuid("program_id", nullable=False, target="monetization_programs.id"),
        sa.Column("object_key", sa.Text, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        _uuid("created_by", nullable=False),
        _created(),
    )
    deals = sa.Table(
        "monetization_deals",
        metadata,
        _id(),
        _uuid("program_id", nullable=False, target="monetization_programs.id"),
        _uuid("application_id"),
        _uuid("leasing_company_application_id"),
        _uuid("exchange_request_id"),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("application_number", sa.String(100)),
        _uuid("leasing_company_id", nullable=False),
        _uuid("dealer_company_id", nullable=False),
        _uuid("distributor_company_id"),
        _uuid("client_company_id"),
        _uuid("dealer_group_id"),
        _money("base_amount"),
        sa.Column(
            "vehicles", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "participant_snapshot",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="pending_approval"
        ),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "confirmations",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("consumed_vin", sa.String(50), unique=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column(
            "source_snapshot",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        _created(),
        sa.CheckConstraint(
            "(exchange_request_id IS NOT NULL AND application_id IS NULL AND leasing_company_application_id IS NULL AND source_type = 'exchange') OR (exchange_request_id IS NULL AND application_id IS NOT NULL AND leasing_company_application_id IS NOT NULL AND source_type IN ('platform','dealer_account','dealer_site','distributor_site'))",
            name="ck_monetization_deal_origin",
        ),
        sa.CheckConstraint(
            "status IN ('pending_approval','paid')", name="ck_monetization_deal_status"
        ),
        sa.CheckConstraint(
            "base_amount > 0 AND revision > 0", name="ck_monetization_deal_values"
        ),
        sa.UniqueConstraint(
            "leasing_company_application_id", name="uq_monetization_deal_lca"
        ),
        sa.UniqueConstraint(
            "exchange_request_id", name="uq_monetization_deal_exchange"
        ),
        sa.Index("idx_monetization_deal_dealer", "dealer_company_id"),
        sa.Index("idx_monetization_deal_leasing", "leasing_company_id"),
    )
    amounts = sa.Table(
        "monetization_deal_participant_amounts",
        metadata,
        _id(),
        _uuid("deal_id", nullable=False, target="monetization_deals.id"),
        _uuid("program_source_id", target="monetization_program_sources.id"),
        _uuid(
            "source_participant_id",
            target="monetization_program_source_participants.id",
        ),
        _uuid("participant_company_id"),
        sa.Column("local_id", sa.String(100)),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("participant_type", sa.String(20), nullable=False),
        _uuid(
            "expense_ref_amount_id", target="monetization_deal_participant_amounts.id"
        ),
        sa.Column("raw_amount", sa.Numeric(), nullable=False),
        _money("amount"),
        sa.Column("percent", sa.Numeric(38, 8)),
        sa.Column("input_mode", sa.String(10)),
        sa.CheckConstraint(
            "percent IS NULL OR percent >= 0",
            name="ck_monetization_amount_percent",
        ),
        sa.CheckConstraint(
            "input_mode IS NULL OR input_mode IN ('percent','amount')",
            name="ck_monetization_amount_input_mode",
        ),
        sa.CheckConstraint(
            "input_mode IS DISTINCT FROM 'percent' OR (percent IS NOT NULL AND percent > 0)",
            name="ck_monetization_amount_percent_input",
        ),
        sa.Column("clip", sa.String(10), nullable=False, server_default="none"),
        sa.Column(
            "vat_excluded", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "side IN ('expense','income') AND participant_type IN ('leasing','dealer','distributor','platform')",
            name="ck_monetization_amount_participant",
        ),
        sa.CheckConstraint(
            "raw_amount >= 0 AND amount >= 0", name="ck_monetization_amount_values"
        ),
        sa.UniqueConstraint(
            "deal_id", "position", name="uq_monetization_amount_position"
        ),
    )
    documents = sa.Table(
        "monetization_deal_documents",
        metadata,
        _id(),
        _uuid("deal_id", nullable=False, target="monetization_deals.id"),
        sa.Column("participant_type", sa.String(30), nullable=False),
        _uuid("participant_company_id"),
        sa.Column("object_key", sa.Text, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        _uuid("created_by", nullable=False),
        _created(),
    )
    adjustments = sa.Table(
        "monetization_deal_adjustments",
        metadata,
        _id(),
        _uuid("deal_id", nullable=False, target="monetization_deals.id"),
        _uuid(
            "amount_id",
            nullable=False,
            target="monetization_deal_participant_amounts.id",
        ),
        _money("old_value"),
        _money("new_value"),
        sa.Column("old_percent", sa.Numeric(38, 8)),
        sa.Column("new_percent", sa.Numeric(38, 8)),
        sa.Column("old_input_mode", sa.String(10)),
        sa.Column("new_input_mode", sa.String(10)),
        sa.CheckConstraint(
            "(old_percent IS NULL OR old_percent >= 0) AND (new_percent IS NULL OR new_percent >= 0)",
            name="ck_monetization_adjustment_percent",
        ),
        sa.CheckConstraint(
            "(old_input_mode IS NULL OR old_input_mode IN ('percent','amount')) AND (new_input_mode IS NULL OR new_input_mode IN ('percent','amount'))",
            name="ck_monetization_adjustment_input_mode",
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        _uuid("created_by", nullable=False),
        _created(),
        sa.CheckConstraint("new_value > 0", name="ck_monetization_adjustment_positive"),
    )
    requests = sa.Table(
        "monetization_condition_requests",
        metadata,
        _id(),
        _uuid("application_id", nullable=False),
        _uuid("dealer_company_id", nullable=False),
        _uuid("leasing_company_id", nullable=False, target="leasing_companies.id"),
        sa.Column("requested_calc_type", sa.String(10), nullable=False),
        _money("requested_value"),
        sa.Column("comment", sa.Text),
        sa.Column("response_comment", sa.Text),
        sa.Column("counter_calc_type", sa.String(10)),
        _money("counter_value", nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="sent"),
        _uuid("responded_by"),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        _uuid("decided_by"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        _uuid("created_by", nullable=False),
        _created(),
        sa.CheckConstraint(
            "status IN ('sent','accepted','rejected','countered')",
            name="ck_monetization_request_status",
        ),
        sa.CheckConstraint(
            "requested_calc_type IN ('percent','amount') AND requested_value > 0 AND (counter_value IS NULL OR counter_value > 0)",
            name="ck_monetization_request_value",
        ),
        sa.Index("idx_monetization_request_application", "application_id"),
    )
    return (
        programs,
        sources,
        participants,
        contracts,
        deals,
        amounts,
        documents,
        adjustments,
        requests,
    )


(
    programs,
    sources,
    participants,
    contracts,
    deals,
    amounts,
    documents,
    adjustments,
    condition_requests,
) = build_tables(Base.metadata)


class MonetizationProgram(Base):
    __table__ = programs


class MonetizationProgramSource(Base):
    __table__ = sources


class MonetizationProgramSourceParticipant(Base):
    __table__ = participants


class MonetizationProgramContract(Base):
    __table__ = contracts


class MonetizationDeal(Base):
    __table__ = deals


class MonetizationDealParticipantAmount(Base):
    __table__ = amounts


class MonetizationDealDocument(Base):
    __table__ = documents


class MonetizationDealAdjustment(Base):
    __table__ = adjustments


class MonetizationConditionRequest(Base):
    __table__ = condition_requests
