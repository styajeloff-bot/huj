"""LC creates a leasing application on behalf of a client.

Thin wrapper around Phase 3's ``CreateApplicationCommand``. The difference
is that the caller is an LC — the created application's
``selected_leasing_companies`` defaults to the acting LC (so the LC can see
and work the application right away) and ``create_draft`` is True (so the
status lands on ``draft`` instead of ``submitted``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.applications import (
    ApplicationVehiclePayload,
    CreateApplicationCommand,
    handle_create_application,
)
from domain.errors import LeasingCompanyBindingNotConfiguredError


@dataclass
class CreateLcApplicationCommand:
    actor_id: UUID
    actor_role: str
    source_type: str
    actor_leasing_company_id: UUID | None
    company_id: UUID
    name: str = ""
    email: str = ""
    vehicles: list[ApplicationVehiclePayload] = field(default_factory=list)
    selected_leasing_companies: list[UUID] = field(default_factory=list)
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: float | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    current_stage: str = "leasing_companies"
    questionnaire: dict[str, Any] | None = None
    vehicle_calculations: list[dict[str, Any]] | None = None


async def handle_create_lc_application(
    cmd: CreateLcApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    selected = list(cmd.selected_leasing_companies)
    if cmd.actor_role == "leasing_company":
        if cmd.actor_leasing_company_id is None:
            raise LeasingCompanyBindingNotConfiguredError()
        if cmd.actor_leasing_company_id not in selected:
            selected.append(cmd.actor_leasing_company_id)

    return await handle_create_application(
        CreateApplicationCommand(
            source_type=cmd.source_type,
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            company_id=cmd.company_id,
            name=cmd.name,
            email=cmd.email,
            vehicles=list(cmd.vehicles),
            selected_leasing_companies=selected,
            total_amount=cmd.total_amount,
            down_payment=cmd.down_payment,
            down_payment_percent=cmd.down_payment_percent,
            lease_term_months=cmd.lease_term_months,
            monthly_payment=cmd.monthly_payment,
            total_cost=cmd.total_cost,
            markup=cmd.markup,
            rate=cmd.rate,
            total_interest=cmd.total_interest,
            buyout_amount=cmd.buyout_amount,
            vat_refund=cmd.vat_refund,
            profit_tax_savings=cmd.profit_tax_savings,
            total_savings=cmd.total_savings,
            current_stage=cmd.current_stage,
            # LC pre-applications always start as drafts so the LC can
            # iterate on the data before handing to the client.
            create_draft=True,
            questionnaire=cmd.questionnaire,
            vehicle_calculations=cmd.vehicle_calculations,
        ),
        session,
    )
