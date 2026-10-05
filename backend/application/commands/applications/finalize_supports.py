"""Fix applied supports and instantiate compensations on application submit."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.calculator.calculate import (
    CalculateCommand,
    handle_calculate,
)
from application.commands.compensations import (
    CreateCompensationCommand,
    handle_create_compensation,
)
from application.errors import ServiceError
from domain.monetization.sources import support_origin
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import compensation_repository as comp_repo
from infrastructure.repositories import support_repository


async def finalize_application_supports(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    actor_id: UUID | None,
) -> None:
    """Create immutable support snapshots and compensation instances.

    The operation is idempotent for an application: if snapshots already exist,
    a repeated submit/status call does not create duplicates.
    """
    if await comp_repo.count_applied_supports_for_application(session, application_id):
        return

    application = await app_repo.get_by_id(session, application_id)
    if application is None:
        return

    vehicle_rows = await app_repo.list_application_vehicles(session, application_id)
    vehicle_ids = [
        vehicle_id
        for row in vehicle_rows
        if (vehicle_id := _to_uuid(row.get("vehicle_id"))) is not None
    ]
    if not vehicle_ids:
        return

    calc = await app_repo.get_calculation(session, application_id) or {}
    result = await handle_calculate(
        CalculateCommand(
            total_amount=float(
                _decimal_or_default(
                    application.get("total_amount"),
                    _sum_vehicle_total(vehicle_rows),
                )
            ),
            down_payment=float(_decimal_or_default(application.get("down_payment"), 0)),
            down_payment_percent=float(application.get("down_payment_percent") or 0),
            lease_term_months=int(application.get("lease_term_months") or 12),
            buyout_amount=float(application.get("buyout_amount") or 0),
            vehicle_ids=vehicle_ids,
            selected_support=_normalize_selected_support(
                calc.get("selected_support")
            ),
        ),
        session,
    )

    support_rows = result.response.get("support_per_vehicle") or []
    for vehicle_support in support_rows:
        vehicle_id = _to_uuid(vehicle_support.get("vehicle_id"))
        if vehicle_id is None:
            continue
        base_amount = float(vehicle_support.get("base_price") or 0)
        for applied in vehicle_support.get("applied_supports") or []:
            support_program_id = _to_uuid(applied.get("support_program_id"))
            if support_program_id is None:
                continue
            support_amount = float(applied.get("amount") or 0)
            if support_amount <= 0:
                continue
            program = await support_repository.get_program_by_id(
                session, support_program_id
            )
            if program is None:
                continue
            templates = await comp_repo.list_compensation_templates(
                session, support_program_id
            )
            snapshot = await comp_repo.create_applied_support(
                session,
                {
                    "application_id": application_id,
                    "vehicle_id": vehicle_id,
                    "support_program_id": support_program_id,
                    **support_origin(program, application.get("dealer_company_id")),
                    "name": program["name"],
                    "support_type": program["support_type"],
                    "support_params": program.get("support_params") or {},
                    "comment": program.get("comment"),
                    "starts_at": program.get("starts_at"),
                    "ends_at": program.get("ends_at"),
                    "main_payer": templates[0]["payer"] if templates else None,
                    "base_amount": base_amount,
                    "support_amount": support_amount,
                },
            )
            await _create_compensation_instances(
                session,
                applied_support_id=snapshot["id"],
                application_id=application_id,
                vehicle_id=vehicle_id,
                templates=templates,
                actor_id=actor_id,
            )


async def _create_compensation_instances(
    session: AsyncSession,
    *,
    applied_support_id: UUID,
    application_id: uuid.UUID,
    vehicle_id: UUID,
    templates: list[dict[str, Any]],
    actor_id: UUID | None,
) -> None:
    for template in templates:
        try:
            await handle_create_compensation(
                CreateCompensationCommand(
                    applied_support_id=applied_support_id,
                    application_id=application_id,
                    vehicle_id=vehicle_id,
                    payer=template["payer"],
                    recipient=template["recipient"],
                    calculation_base=template["calculation_base"],
                    calculation_base_amount=None,
                    value_type=template["value_type"],
                    value=float(template["value"]),
                    min_amount=template.get("min_amount"),
                    max_amount=template.get("max_amount"),
                    min_percent=template.get("min_percent"),
                    max_percent=template.get("max_percent"),
                    payment_schedule_type=template.get(
                        "payment_schedule_type", "days_count"
                    ),
                    payment_schedule_period=template.get("payment_schedule_period"),
                    payment_schedule_value=template.get("payment_schedule_value"),
                    comment=template.get("comment", ""),
                    created_by=actor_id,
                ),
                session,
            )
        except ServiceError as exc:
            if template["calculation_base"] == "special_price":
                raise ServiceError(
                    "Для автомобиля не заполнена специальная цена, "
                    "а шаблон компенсации использует базу «Специальная цена».",
                    400,
                ) from exc
            raise


def _normalize_selected_support(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, raw_ids in value.items():
        vehicle_id = _to_uuid(key)
        if vehicle_id is None:
            continue
        if not isinstance(raw_ids, list):
            continue
        program_ids: list[str] = []
        for raw_id in raw_ids:
            program_id = _to_uuid(raw_id)
            if program_id is not None:
                program_ids.append(str(program_id))
        if program_ids:
            result[str(vehicle_id)] = program_ids
    return result


def _to_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _sum_vehicle_total(vehicle_rows: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for row in vehicle_rows:
        total += _decimal_or_default(row.get("total_price"), 0)
    return total


def _decimal_or_default(value: Any, default: Decimal | int | float) -> Decimal:
    if value is None:
        return Decimal(str(default))
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
