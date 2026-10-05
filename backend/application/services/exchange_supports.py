"""Support-program selection shared by exchange cart and requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.support_programs import build_applicable_support_programs
from domain.entities.leasing_calculator import SUPPORT_TYPE_VEHICLE_DISCOUNT
from infrastructure.repositories import (
    calculator_repository,
    leasing_company_application_repository,
    support_repository,
)


@dataclass(frozen=True)
class ExchangeSupportSelection:
    selected_ids: list[UUID]
    eligible_rows: list[dict[str, Any]]
    program_details: list[dict[str, Any]]


def selected_support_price_summary(
    programs: list[dict[str, Any]],
    selected_ids: list[UUID],
    *,
    fallback_base_price: float = 0,
) -> dict[str, int]:
    selected = {
        program["id"]: program
        for program in programs
        if program.get("id") in set(selected_ids)
    }
    base_price = round(
        next(
            (
                float(program.get("base_price") or 0)
                for program in selected.values()
                if program.get("base_price") is not None
            ),
            fallback_base_price,
        )
    )
    support_amount = min(
        base_price,
        sum(
            max(0, round(float(program.get("support_amount") or 0)))
            for program in selected.values()
            if program.get("support_type") in SUPPORT_TYPE_VEHICLE_DISCOUNT
        ),
    )
    return {
        "support_price_base": max(0, base_price),
        "support_price_display": max(0, base_price - support_amount),
        "support_price_amount": max(0, support_amount),
    }


async def resolve_exchange_support_selection(
    session: AsyncSession,
    *,
    user_id: UUID,
    vehicle_id: UUID,
    requested_ids: list[UUID],
    select_default: bool,
) -> ExchangeSupportSelection:
    """Validate an LC-owned support set and return its display projection."""

    leasing_company_id = (
        await leasing_company_application_repository.resolve_lc_id_for_user(
            session, user_id
        )
    )
    if leasing_company_id is None:
        if requested_ids:
            raise ServiceError(
                "Для пользователя не настроена лизинговая компания", 400
            )
        return ExchangeSupportSelection(
            selected_ids=[],
            eligible_rows=[],
            program_details=[],
        )

    eligible_rows = await calculator_repository.get_vehicles_with_support_info(
        session,
        [vehicle_id],
        leasing_company_id=leasing_company_id,
    )
    applicable_ids = {
        row["support_program_id"]
        for row in eligible_rows
        if row.get("support_program_id") is not None
    }
    # The shared applicability query already applies the LC rule: an empty
    # program relation is universal, while a non-empty relation must contain
    # the current leasing company. Re-filtering by explicit relations here
    # would incorrectly discard universal programs.
    eligible_ids = applicable_ids
    selected_ids = sorted(set(requested_ids))
    if not selected_ids and select_default and eligible_ids:
        selected_ids = [min(eligible_ids)]

    unavailable = [program_id for program_id in selected_ids if program_id not in eligible_ids]
    if unavailable:
        raise ServiceError(
            "Выбранная программа поддержки недоступна для этого ТС и лизинговой компании",
            400,
        )

    await _ensure_pairwise_compatible(session, selected_ids)
    details = await calculator_repository.get_support_program_details_by_ids(
        session, sorted(eligible_ids)
    )
    program_details = build_applicable_support_programs(
        eligible_rows,
        details,
    ).get(vehicle_id, [])
    return ExchangeSupportSelection(
        selected_ids=selected_ids,
        eligible_rows=eligible_rows,
        program_details=program_details,
    )


async def _ensure_pairwise_compatible(
    session: AsyncSession, selected_ids: list[UUID]
) -> None:
    if len(selected_ids) < 2:
        return
    flags = await support_repository.get_program_compatibility_flags(
        session, selected_ids
    )
    graph = await support_repository.get_compatibility_by_program_ids(
        session, selected_ids
    )
    if any(not flags.get(program_id, False) for program_id in selected_ids):
        raise ServiceError(
            "Выбранные программы поддержки несовместимы", 400
        )
    for index, left_id in enumerate(selected_ids):
        neighbours = graph.get(left_id, set())
        if any(right_id not in neighbours for right_id in selected_ids[index + 1 :]):
            raise ServiceError(
                "Все выбранные программы должны быть совместимы друг с другом",
                400,
            )
