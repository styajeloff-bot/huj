"""Create immutable support snapshots when an Exchange request becomes a deal."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.compensations import (
    CreateCompensationCommand,
    handle_create_compensation,
)
from application.errors import ServiceError
from domain.entities.leasing_calculator import (
    SUPPORT_TYPE_DOWN_PAYMENT,
    LeasingCalculator,
)
from domain.monetization.sources import support_origin
from infrastructure.repositories import compensation_repository as comp_repo
from infrastructure.repositories import exchange_request_repository as req_repo
from infrastructure.repositories import support_repository


async def finalize_exchange_supports(
    session: AsyncSession,
    *,
    request_id: UUID,
    accepted_bid: dict[str, Any],
    actor_id: UUID | None,
) -> None:
    """Fix selected supports and create Exchange-sourced compensations once."""

    request = await req_repo.get_by_id(session, request_id)
    if request is None:
        return

    vehicle_id = request["vehicle_id"]
    unit_price = float(accepted_bid.get("price") or 0)
    if unit_price <= 0:
        return

    existing_snapshots = (
        await comp_repo.list_applied_supports_for_exchange_requests(
            session, [request_id]
        )
    ).get(request_id, [])
    existing_program_ids = {
        snapshot["support_program_id"]
        for snapshot in existing_snapshots
        if snapshot.get("support_program_id") is not None
    }
    for support_program_id in request.get("selected_support_ids") or []:
        if support_program_id in existing_program_ids:
            continue
        program = await support_repository.get_program_by_id(
            session, support_program_id
        )
        if program is None:
            continue
        support_amount = _exchange_support_amount(
            support_type=program["support_type"],
            support_params=program.get("support_params") or {},
            accepted_unit_price=unit_price,
        )
        if support_amount <= 0:
            continue

        templates = await comp_repo.list_compensation_templates(
            session, support_program_id
        )
        snapshot = await comp_repo.create_applied_support(
            session,
            {
                "application_id": None,
                "exchange_request_id": request_id,
                "vehicle_id": vehicle_id,
                "support_program_id": support_program_id,
                **support_origin(
                    program, accepted_bid.get("dealer_company_id"),
                    accepted_bid.get("distributor_id")),
                "name": program["name"],
                "support_type": program["support_type"],
                "support_params": program.get("support_params") or {},
                "comment": program.get("comment"),
                "starts_at": program.get("starts_at"),
                "ends_at": program.get("ends_at"),
                "main_payer": templates[0]["payer"] if templates else None,
                "base_amount": unit_price,
                "support_amount": support_amount,
            },
        )
        context = await comp_repo.get_calculation_context(
            session,
            applied_support_id=snapshot["id"],
            application_id=None,
            vehicle_id=vehicle_id,
        )
        for template in templates:
            await handle_create_compensation(
                CreateCompensationCommand(
                    applied_support_id=snapshot["id"],
                    application_id=None,
                    exchange_request_id=request_id,
                    source="exchange",
                    vehicle_id=vehicle_id,
                    payer=template["payer"],
                    recipient=template["recipient"],
                    calculation_base=template["calculation_base"],
                    calculation_base_amount=_exchange_base_amount(
                        template["calculation_base"],
                        context=context,
                        accepted_unit_price=unit_price,
                        support_amount=float(support_amount),
                    ),
                    value_type=template["value_type"],
                    value=float(template["value"]),
                    min_amount=template.get("min_amount"),
                    max_amount=template.get("max_amount"),
                    min_percent=template.get("min_percent"),
                    max_percent=template.get("max_percent"),
                    payment_schedule_type=template.get(
                        "payment_schedule_type", "days_count"
                    ),
                    payment_schedule_period=template.get(
                        "payment_schedule_period"
                    ),
                    payment_schedule_value=template.get(
                        "payment_schedule_value"
                    ),
                    comment=template.get("comment", ""),
                    created_by=actor_id,
                ),
                session,
            )


def _exchange_base_amount(
    calculation_base: str,
    *,
    context: dict[str, Any],
    accepted_unit_price: float,
    support_amount: float,
) -> float:
    if calculation_base == "support_amount":
        return support_amount
    if calculation_base == "application_price":
        return accepted_unit_price
    if calculation_base == "down_payment":
        raise ServiceError(
            "Для шаблона с базой down_payment в заявке Биржи "
            "нет подтверждённого размера первоначального взноса",
            400,
        )
    value = context.get(calculation_base)
    if value is not None:
        return float(value)
    return accepted_unit_price


def _exchange_support_amount(
    *,
    support_type: str,
    support_params: dict[str, Any],
    accepted_unit_price: float,
) -> int:
    if support_type == SUPPORT_TYPE_DOWN_PAYMENT and (
        support_params.get("value_type") == "percent"
        or support_params.get("min_percent") is not None
        or support_params.get("max_percent") is not None
    ):
        raise ServiceError(
            "Процентную поддержку первоначального взноса нельзя "
            "зафиксировать по заявке Биржи без размера взноса",
            400,
        )
    return LeasingCalculator.compute_support_from_params(
        support_params,
        accepted_unit_price,
    )
