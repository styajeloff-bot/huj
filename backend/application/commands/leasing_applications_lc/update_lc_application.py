
"""Partial update of a leasing application from the LC cabinet.

Enforces two invariants via the Phase 3 aggregate:

1. Ownership — caller must own the application per ``ensure_owned_by``
   (LC is considered owner when the LC id is in
   ``selected_leasing_companies``).
2. Editability — only ``draft`` applications may be edited. Mirrors
   Express ``LeasingService.updateApplication`` behaviour.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.permissions import ensure_application_owned_by
from domain.errors import (
    ApplicationNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_leasing_application_changed
from infrastructure.repositories import application_repository as repo

# Fields the LC cabinet is allowed to write on a draft.
_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "email",
        "total_amount",
        "down_payment",
        "down_payment_percent",
        "lease_term_months",
        "monthly_payment",
        "total_cost",
        "markup",
        "rate",
        "total_interest",
        "buyout_amount",
        "vat_refund",
        "profit_tax_savings",
        "total_savings",
        "selected_leasing_companies",
        "current_stage",
    }
)


@dataclass
class UpdateLcApplicationCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None
    fields_set: set[str] = field(default_factory=set)
    name: str | None = None
    email: str | None = None
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
    selected_leasing_companies: list[UUID] | None = None
    current_stage: str | None = None


async def handle_update_lc_application(
    cmd: UpdateLcApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.application_id)
    if existing is None:
        raise ApplicationNotFoundError(cmd.application_id)
    entity = await ensure_application_owned_by(
        session,
        application=existing,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        actor_leasing_company_id=cmd.actor_leasing_company_id,
    )
    has_lc_children = await repo.has_lc_children(session, cmd.application_id)
    entity.ensure_editable(has_lc_children=has_lc_children)

    updates: dict[str, Any] = {}
    for name in _EDITABLE_FIELDS:
        if name in cmd.fields_set:
            updates[name] = getattr(cmd, name)

    if updates:
        await repo.update_application_fields(
            session, cmd.application_id, fields=updates
        )
    saved = await repo.get_by_id(session, cmd.application_id)
    assert saved is not None
    emit_leasing_application_changed({
        "application_id": str(saved["id"]),
        "display_number": saved.get("display_number"),
        "company_id": saved.get("company_id"),
        "dealer_company_id": saved.get("dealer_company_id"),
        "vehicle_id": saved.get("vehicle_id"),
        "name": saved.get("name"),
        "email": saved.get("email"),
        "status": saved.get("status"),
        "total_amount": saved.get("total_amount"),
        "down_payment": saved.get("down_payment"),
        "down_payment_percent": saved.get("down_payment_percent"),
        "lease_term_months": saved.get("lease_term_months"),
        "monthly_payment": saved.get("monthly_payment"),
        "total_cost": saved.get("total_cost"),
        "markup": saved.get("markup"),
        "rate": saved.get("rate"),
        "total_interest": saved.get("total_interest"),
        "buyout_amount": saved.get("buyout_amount"),
        "vat_refund": saved.get("vat_refund"),
        "profit_tax_savings": saved.get("profit_tax_savings"),
        "total_savings": saved.get("total_savings"),
        "selected_leasing_companies": saved.get("selected_leasing_companies"),
        "leasing_company_comments": saved.get("leasing_company_comments"),
        "requested_documents": saved.get("requested_documents"),
        "questionnaire_completed": saved.get("questionnaire_completed"),
        "questionnaire_progress": saved.get("questionnaire_progress"),
        "current_stage": saved.get("current_stage"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return {
        "message": "Заявка успешно обновлена",
        "application": saved,
    }
