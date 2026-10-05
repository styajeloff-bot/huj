"""Compensation repository — async, dict-only API."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingApplicationCalculation,
    LeasingApplicationVehicleCalculation,
)
from infrastructure.models.compensations import (
    CompensationModel,
    CompensationTemplateModel,
)
from infrastructure.models.exchange import ExchangeRequest
from infrastructure.models.fast_deals import FastDeal
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.support import (
    ApplicationAppliedSupport,
    SupportProgram,
    SupportProgramDistributor,
)
from infrastructure.repository_timing import timed_repository


def _visible_support_program_condition(
    visible_distributor_id: UUID | None,
    restrict_to_distributor: bool,
) -> Any:
    if not restrict_to_distributor:
        return True
    if visible_distributor_id is None:
        return False
    distributor_match = (
        select(SupportProgramDistributor.support_program_id)
        .where(
            SupportProgramDistributor.support_program_id == SupportProgram.id,
            SupportProgramDistributor.distributor_id == visible_distributor_id,
        )
        .exists()
    )
    return (
        select(ApplicationAppliedSupport.id)
        .join(SupportProgram, SupportProgram.id == ApplicationAppliedSupport.support_program_id)
        .where(
            ApplicationAppliedSupport.id == CompensationModel.applied_support_id,
            or_(
                SupportProgram.distributor_id == visible_distributor_id,
                distributor_match,
            ),
        )
        .exists()
    )


@timed_repository
async def create_compensation(session: AsyncSession, data: dict[str, Any]) -> dict:
    model = CompensationModel(
        applied_support_id=data["applied_support_id"],
        application_id=data.get("application_id"),
        exchange_request_id=data.get("exchange_request_id"),
        fast_deal_id=data.get("fast_deal_id"),
        source=data.get("source", "platform"),
        vehicle_id=data.get("vehicle_id"),
        payer=data["payer"],
        recipient=data["recipient"],
        calculation_base=data["calculation_base"],
        calculation_base_amount=data["calculation_base_amount"],
        value_type=data["value_type"],
        value=data["value"],
        min_amount=data.get("min_amount"),
        max_amount=data.get("max_amount"),
        min_percent=data.get("min_percent"),
        max_percent=data.get("max_percent"),
        amount=data["amount"],
        status=data.get("status", "under_review"),
        payment_schedule_type=data.get("payment_schedule_type", "days_count"),
        payment_schedule_period=data.get("payment_schedule_period"),
        payment_schedule_value=data.get("payment_schedule_value"),
        due_date=data.get("due_date"),
        paid_at=data.get("paid_at"),
        documents=data.get("documents", []),
        comment=data.get("comment", ""),
        created_by=data.get("created_by"),
    )
    session.add(model)
    await session.flush()
    return _to_dict(model)

@timed_repository
async def replace_compensation_templates(
    session: AsyncSession,
    support_program_id: UUID,
    templates: list[dict[str, Any]],
    *,
    created_by: UUID | None = None,
) -> None:
    await session.execute(
        delete(CompensationTemplateModel).where(
            CompensationTemplateModel.support_program_id == support_program_id
        )
    )
    for template in templates:
        session.add(
            CompensationTemplateModel(
                support_program_id=support_program_id,
                payer=template["payer"],
                recipient=template["recipient"],
                calculation_base=template["calculation_base"],
                value_type=template["value_type"],
                value=template["value"],
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
                created_by=created_by,
            )
        )
    await session.flush()

@timed_repository
async def list_compensation_templates(
    session: AsyncSession, support_program_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(CompensationTemplateModel)
            .where(CompensationTemplateModel.support_program_id == support_program_id)
            .order_by(
                CompensationTemplateModel.created_at.asc(),
                CompensationTemplateModel.id.asc(),
            )
        )
    ).scalars().all()
    return [_template_to_dict(row) for row in rows]

@timed_repository
async def create_applied_support(
    session: AsyncSession, data: dict[str, Any]
) -> dict[str, Any]:
    row = ApplicationAppliedSupport(
        application_id=data.get("application_id"),
        exchange_request_id=data.get("exchange_request_id"),
        fast_deal_id=data.get("fast_deal_id"),
        fast_deal_vehicle_id=data.get("fast_deal_vehicle_id"),
        vehicle_id=data.get("vehicle_id"),
        support_program_id=data.get("support_program_id"),
        dealer_company_id=data.get("dealer_company_id"),
        distributor_company_id=data.get("distributor_company_id"),
        name=data["name"],
        support_type=data["support_type"],
        support_params=data.get("support_params") or {},
        comment=data.get("comment"),
        starts_at=data.get("starts_at"),
        ends_at=data.get("ends_at"),
        main_payer=data.get("main_payer"),
        base_amount=data.get("base_amount", 0),
        support_amount=data.get("support_amount", 0),
    )
    session.add(row)
    await session.flush()
    return _applied_support_to_dict(row)

@timed_repository
async def count_applied_supports_for_application(
    session: AsyncSession, application_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count(ApplicationAppliedSupport.id)).where(
            ApplicationAppliedSupport.application_id == application_id
        )
    )
    return int(result.scalar() or 0)


@timed_repository
async def count_applied_supports_for_exchange_request(
    session: AsyncSession, exchange_request_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count(ApplicationAppliedSupport.id)).where(
            ApplicationAppliedSupport.exchange_request_id
            == exchange_request_id
        )
    )
    return int(result.scalar() or 0)


@timed_repository
async def list_applied_supports_for_exchange_requests(
    session: AsyncSession,
    exchange_request_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    if not exchange_request_ids:
        return {}
    rows = (
        await session.execute(
            select(ApplicationAppliedSupport)
            .where(
                ApplicationAppliedSupport.exchange_request_id.in_(
                    exchange_request_ids
                )
            )
            .order_by(
                ApplicationAppliedSupport.created_at.asc(),
                ApplicationAppliedSupport.id.asc(),
            )
        )
    ).scalars().all()
    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        if row.exchange_request_id is None:
            continue
        result.setdefault(row.exchange_request_id, []).append(
            _applied_support_to_dict(row)
        )
    return result

@timed_repository
async def get_applied_support_by_id(
    session: AsyncSession, applied_support_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(ApplicationAppliedSupport, applied_support_id)
    return _applied_support_to_dict(row) if row else None

@timed_repository
async def get_compensation_by_id(
    session: AsyncSession,
    compensation_id: UUID,
    *,
    visible_distributor_id: UUID | None = None,
    restrict_to_distributor: bool = False,
) -> dict | None:
    result = await session.execute(
        select(
            CompensationModel,
            LeasingApplication.display_number,
            ExchangeRequest.batch_number,
            ExchangeRequest.batch_index,
            ApplicationAppliedSupport.name,
            ApplicationAppliedSupport.support_program_id,
            FastDeal.display_number,
        )
        .outerjoin(
            LeasingApplication,
            LeasingApplication.id == CompensationModel.application_id,
        )
        .outerjoin(
            ExchangeRequest,
            ExchangeRequest.id == CompensationModel.exchange_request_id,
        )
        .outerjoin(
            ApplicationAppliedSupport,
            ApplicationAppliedSupport.id == CompensationModel.applied_support_id,
        )
        .outerjoin(FastDeal, FastDeal.id == CompensationModel.fast_deal_id)
        .where(
            CompensationModel.id == compensation_id,
            _visible_support_program_condition(
                visible_distributor_id, restrict_to_distributor
            ),
        )
    )
    row = result.one_or_none()
    if not row:
        return None
    (
        compensation,
        display_number,
        exchange_batch_number,
        exchange_batch_index,
        applied_support_name,
        support_program_id,
        fast_deal_display_number,
    ) = row
    return _to_dict(
        compensation,
        application_display_number=display_number,
        exchange_batch_number=exchange_batch_number,
        exchange_batch_index=exchange_batch_index,
        applied_support_name=applied_support_name,
        support_program_id=support_program_id,
        fast_deal_display_number=fast_deal_display_number,
    )

@timed_repository
async def list_compensations(
    session: AsyncSession,
    *,
    application_id: uuid.UUID | None = None,
    application_query: str | None = None,
    applied_support_id: UUID | None = None,
    support_query: str | None = None,
    status: str | None = None,
    payer: str | None = None,
    recipient: str | None = None,
    source: str | None = None,
    due_date_from: date | None = None,
    due_date_to: date | None = None,
    participant_role: str | None = None,
    participant_scope: Literal["payer", "recipient", "either"] | None = None,
    visible_distributor_id: UUID | None = None,
    restrict_to_distributor: bool = False,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict], int]:
    query = (
        select(
            CompensationModel,
            LeasingApplication.display_number,
            ExchangeRequest.batch_number,
            ExchangeRequest.batch_index,
            ApplicationAppliedSupport.name,
            ApplicationAppliedSupport.support_program_id,
            FastDeal.display_number,
        )
        .outerjoin(
            LeasingApplication,
            LeasingApplication.id == CompensationModel.application_id,
        )
        .outerjoin(
            ExchangeRequest,
            ExchangeRequest.id == CompensationModel.exchange_request_id,
        )
        .outerjoin(
            ApplicationAppliedSupport,
            ApplicationAppliedSupport.id == CompensationModel.applied_support_id,
        )
        .outerjoin(FastDeal, FastDeal.id == CompensationModel.fast_deal_id)
    )
    count_query = (
        select(func.count(CompensationModel.id))
        .select_from(CompensationModel)
        .outerjoin(
            LeasingApplication,
            LeasingApplication.id == CompensationModel.application_id,
        )
        .outerjoin(
            ApplicationAppliedSupport,
            ApplicationAppliedSupport.id == CompensationModel.applied_support_id,
        )
        .outerjoin(FastDeal, FastDeal.id == CompensationModel.fast_deal_id)
    )

    conditions: list[Any] = [
        _visible_support_program_condition(
            visible_distributor_id, restrict_to_distributor
        )
    ]
    _add_application_filters(conditions, application_id, application_query)
    _add_support_filters(conditions, applied_support_id, support_query)
    if status:
        conditions.append(CompensationModel.status == status)
    if payer:
        conditions.append(CompensationModel.payer == payer)
    if recipient:
        conditions.append(CompensationModel.recipient == recipient)
    if source:
        conditions.append(CompensationModel.source == source)
    if due_date_from:
        conditions.append(CompensationModel.due_date >= due_date_from)
    if due_date_to:
        conditions.append(CompensationModel.due_date <= due_date_to)
    _add_participant_filter(conditions, participant_role, participant_scope)

    if conditions:
        where_clause = and_(*conditions)
        query = query.where(where_clause)
        count_query = count_query.where(where_clause)

    total = (await session.execute(count_query)).scalar() or 0

    query = query.order_by(CompensationModel.created_at.desc())
    query = query.offset((page - 1) * limit).limit(limit)

    rows = (await session.execute(query)).all()
    return [
        _to_dict(
            comp,
            application_display_number=display_number,
            exchange_batch_number=exchange_batch_number,
            exchange_batch_index=exchange_batch_index,
            applied_support_name=applied_support_name,
            support_program_id=support_program_id,
            fast_deal_display_number=fast_deal_display_number,
        )
        for (
            comp,
            display_number,
            exchange_batch_number,
            exchange_batch_index,
            applied_support_name,
            support_program_id,
            fast_deal_display_number,
        ) in rows
    ], total

@timed_repository
async def get_compensations_for_support(
    session: AsyncSession,
    applied_support_id: UUID,
    *,
    visible_distributor_id: UUID | None = None,
    restrict_to_distributor: bool = False,
) -> list[dict]:
    rows = (
        await session.execute(
            select(
                CompensationModel,
                LeasingApplication.display_number,
                ExchangeRequest.batch_number,
                ExchangeRequest.batch_index,
                ApplicationAppliedSupport.name,
                ApplicationAppliedSupport.support_program_id,
                FastDeal.display_number,
            )
            .outerjoin(
                LeasingApplication,
                LeasingApplication.id == CompensationModel.application_id,
            )
            .outerjoin(
                ExchangeRequest,
                ExchangeRequest.id == CompensationModel.exchange_request_id,
            )
            .outerjoin(
                ApplicationAppliedSupport,
                ApplicationAppliedSupport.id == CompensationModel.applied_support_id,
            )
            .outerjoin(FastDeal, FastDeal.id == CompensationModel.fast_deal_id)
            .where(
                CompensationModel.applied_support_id == applied_support_id,
                _visible_support_program_condition(
                    visible_distributor_id, restrict_to_distributor
                ),
            )
            .order_by(CompensationModel.created_at.asc(), CompensationModel.id.asc())
        )
    ).all()
    return [
        _to_dict(
            comp,
            application_display_number=display_number,
            exchange_batch_number=exchange_batch_number,
            exchange_batch_index=exchange_batch_index,
            applied_support_name=applied_support_name,
            support_program_id=support_program_id,
            fast_deal_display_number=fast_deal_display_number,
        )
        for (
            comp,
            display_number,
            exchange_batch_number,
            exchange_batch_index,
            applied_support_name,
            support_program_id,
            fast_deal_display_number,
        ) in rows
    ]

@timed_repository
async def count_compensations_for_support(
    session: AsyncSession, applied_support_id: UUID
) -> int:
    result = await session.execute(
        select(func.count(CompensationModel.id)).where(
            CompensationModel.applied_support_id == applied_support_id
        )
    )
    return result.scalar() or 0

@timed_repository
async def update_compensation(
    session: AsyncSession,
    compensation_id: UUID,
    data: dict[str, Any],
) -> dict | None:
    result = await session.execute(
        select(CompensationModel).where(CompensationModel.id == compensation_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        return None

    for key, value in data.items():
        if hasattr(model, key):
            setattr(model, key, value)
    cast("Any", model).updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(model)

@timed_repository
async def mark_overdue_compensations(session: AsyncSession) -> int:
    """Transition all accepted compensations past their due_date to overdue."""
    today = datetime.now(UTC).date()
    count = (
        await session.execute(
            select(func.count(CompensationModel.id)).where(
                and_(
                    CompensationModel.status == "accepted",
                    CompensationModel.due_date <= today,
                    CompensationModel.due_date.isnot(None),
                )
            )
        )
    ).scalar() or 0
    stmt = (
        update(CompensationModel)
        .where(
            and_(
                CompensationModel.status == "accepted",
                CompensationModel.due_date <= today,
                CompensationModel.due_date.isnot(None),
            )
        )
        .values(status="overdue", updated_at=datetime.now(UTC))
    )
    await session.execute(stmt)
    return int(count)

@timed_repository
async def cancel_compensations_for_support(
    session: AsyncSession, applied_support_id: UUID
) -> tuple[int, list[dict]]:
    """Cancel open compensations. Returns (cancelled_count, already_paid_list)."""
    rows = (
        await session.execute(
            select(CompensationModel).where(
                CompensationModel.applied_support_id == applied_support_id
            )
        )
    ).scalars().all()

    cancelled = 0
    already_paid = []

    for row in rows:
        if row.status in ("under_review", "accepted", "overdue"):
            row.status = "cancelled"
            cast("Any", row).updated_at = datetime.now(UTC)
            cancelled += 1
        elif row.status == "paid":
            already_paid.append(_to_dict(row))

    await session.flush()
    return cancelled, already_paid

@timed_repository
async def list_application_bound_support_ids_for_auto_recalculation(
    session: AsyncSession,
) -> list[UUID]:
    """Return support ids that should be auto-recalculated from live deal data."""
    del session
    return []

@timed_repository
async def list_inactive_support_ids_with_open_compensations(
    session: AsyncSession,
) -> list[UUID]:
    """Return inactive support ids that still have open compensations."""
    rows = (
        await session.execute(
            select(ApplicationAppliedSupport.id)
            .select_from(CompensationModel)
            .join(
                ApplicationAppliedSupport,
                ApplicationAppliedSupport.id == CompensationModel.applied_support_id,
            )
            .join(
                SupportProgram,
                SupportProgram.id == ApplicationAppliedSupport.support_program_id,
            )
            .where(
                and_(
                    SupportProgram.is_active.is_(False),
                    CompensationModel.status.in_(("under_review", "accepted", "overdue")),
                )
            )
            .distinct()
        )
    ).scalars().all()
    return [row for row in rows if row is not None]

@timed_repository
async def get_compensations_coverage(
    session: AsyncSession, applied_support_id: UUID, support_amount: Decimal
) -> dict:
    """Return coverage summary for a support's compensations."""
    result = await session.execute(
        select(func.sum(CompensationModel.amount)).where(
            and_(
                CompensationModel.applied_support_id == applied_support_id,
                CompensationModel.status != "cancelled",
            )
        )
    )
    total_compensations = result.scalar() or Decimal(0)
    return {
        "support_amount": float(support_amount),
        "total_compensations": float(total_compensations),
        "is_fully_covered": total_compensations >= support_amount,
    }

@timed_repository
async def get_support_amount_for_applied_support(
    session: AsyncSession, applied_support_id: UUID
) -> Decimal:
    rows = await get_compensations_for_support(session, applied_support_id)
    if not rows:
        return Decimal("0")

    application_id = rows[0].get("application_id")
    if application_id is not None:
        return await get_support_amount_snapshot(session, application_id)
    return await get_support_amount_snapshot_from_program(session, applied_support_id)

@timed_repository
async def get_support_amount_snapshot(
    session: AsyncSession, application_id: uuid.UUID
) -> Decimal:
    calc = await session.get(LeasingApplicationCalculation, application_id)
    return _as_decimal(calc.down_payment_support if calc else None) or Decimal("0")

@timed_repository
async def get_support_amount_snapshot_from_program(
    session: AsyncSession, support_program_id: UUID
) -> Decimal:
    program = await session.get(SupportProgram, support_program_id)
    if not program:
        return Decimal("0")
    params = program.support_params or {}
    return _as_decimal(params.get("value")) or Decimal("0")

@timed_repository
async def get_calculation_context(
    session: AsyncSession,
    *,
    applied_support_id: UUID,
    application_id: uuid.UUID | None,
    vehicle_id: UUID | None,
) -> dict[str, Decimal | None]:
    vehicle = await session.get(SpecialEquipmentProduct, vehicle_id) if vehicle_id is not None else None

    application = (
        await session.get(LeasingApplication, application_id)
        if application_id is not None
        else None
    )
    app_vehicle = None
    vehicle_calc = None
    app_calc = None

    if application_id is not None and vehicle_id is not None:
        app_vehicle = (
            await session.execute(
                select(ApplicationVehicle).where(
                    and_(
                        ApplicationVehicle.application_id == application_id,
                        ApplicationVehicle.product_id == vehicle_id,
                    )
                )
            )
        ).scalar_one_or_none()
        vehicle_calc = (
            await session.execute(
                select(LeasingApplicationVehicleCalculation).where(
                    and_(
                        LeasingApplicationVehicleCalculation.leasing_application_id
                        == application_id,
                        LeasingApplicationVehicleCalculation.vehicle_id == vehicle_id,
                    )
                )
            )
        ).scalar_one_or_none()

    if application_id is not None:
        app_calc = await session.get(LeasingApplicationCalculation, application_id)

    application_price = None
    if app_vehicle and app_vehicle.unit_price is not None:
        application_price = app_vehicle.unit_price
    elif vehicle_calc and vehicle_calc.unit_price is not None:
        application_price = vehicle_calc.unit_price

    down_payment = None
    if vehicle_calc and vehicle_calc.down_payment is not None:
        down_payment = vehicle_calc.down_payment
    elif application and application.down_payment is not None:
        down_payment = application.down_payment

    support_amount = _as_decimal(app_calc.down_payment_support if app_calc else None)
    if support_amount is None:
        support_amount = await get_support_amount_snapshot_from_program(
            session, applied_support_id
        )

    return {
        "base_price": _as_decimal(getattr(vehicle, "price", None) if vehicle else None),
        "special_price": _as_decimal(getattr(vehicle, "special_price", None) if vehicle else None),
        "dealer_cost": _as_decimal(getattr(vehicle, "dealer_cost", None) if vehicle else None),
        "application_price": _as_decimal(application_price),
        "down_payment": _as_decimal(down_payment),
        "support_amount": support_amount,
    }

def _to_dict(
    model: CompensationModel,
    *,
    application_display_number: str | None = None,
    exchange_batch_number: int | None = None,
    exchange_batch_index: int | None = None,
    applied_support_name: str | None = None,
    support_program_id: UUID | None = None,
    fast_deal_display_number: str | None = None,
) -> dict:
    return {
        "id": model.id,
        "compensation_id": model.id,
        "applied_support_id": model.applied_support_id,
        "applied_support_name": applied_support_name,
        "support_program_id": support_program_id,
        "application_id": model.application_id,
        "application_display_number": application_display_number,
        "exchange_request_id": model.exchange_request_id,
        "exchange_request_display_number": _exchange_display_number(
            exchange_batch_number,
            exchange_batch_index,
        ),
        "fast_deal_id": model.fast_deal_id,
        "fast_deal_display_number": fast_deal_display_number,
        "source": model.source,
        "product_id": model.product_id,
        "vehicle_id": model.product_id,
        "payer": model.payer,
        "recipient": model.recipient,
        "calculation_base": model.calculation_base,
        "calculation_base_amount": _as_float(model.calculation_base_amount),
        "value_type": model.value_type,
        "value": _as_float(model.value),
        "min_amount": _as_float(model.min_amount),
        "max_amount": _as_float(model.max_amount),
        "min_percent": _as_float(model.min_percent),
        "max_percent": _as_float(model.max_percent),
        "amount": _as_float(model.amount),
        "status": model.status,
        "payment_schedule_type": model.payment_schedule_type,
        "payment_schedule_period": model.payment_schedule_period,
        "payment_schedule_value": model.payment_schedule_value,
        "due_date": _iso_date(model.due_date),
        "paid_at": _iso_datetime(model.paid_at),
        "documents": model.documents or [],
        "acceptance_comment": model.acceptance_comment,
        "rejection_comment": model.rejection_comment,
        "comment": model.comment or "",
        "created_by": model.created_by,
        "created_at": _iso_datetime(model.created_at),
        "updated_at": _iso_datetime(model.updated_at),
    }


def _exchange_display_number(
    batch_number: int | None,
    batch_index: int | None,
) -> str | None:
    if batch_number is None:
        return None
    if batch_index is None:
        return str(batch_number)
    return f"{batch_number}.{batch_index}"

def _template_to_dict(model: CompensationTemplateModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "support_program_id": model.support_program_id,
        "payer": model.payer,
        "recipient": model.recipient,
        "calculation_base": model.calculation_base,
        "value_type": model.value_type,
        "value": _as_float(model.value),
        "min_amount": _as_float(model.min_amount),
        "max_amount": _as_float(model.max_amount),
        "min_percent": _as_float(model.min_percent),
        "max_percent": _as_float(model.max_percent),
        "payment_schedule_type": model.payment_schedule_type,
        "payment_schedule_period": model.payment_schedule_period,
        "payment_schedule_value": model.payment_schedule_value,
        "comment": model.comment or "",
        "created_by": model.created_by,
        "created_at": _iso_datetime(model.created_at),
        "updated_at": _iso_datetime(model.updated_at),
    }

def _applied_support_to_dict(model: ApplicationAppliedSupport) -> dict[str, Any]:
    return {
        "id": model.id,
        "application_id": model.application_id,
        "exchange_request_id": model.exchange_request_id,
        "fast_deal_id": model.fast_deal_id,
        "fast_deal_vehicle_id": model.fast_deal_vehicle_id,
        "product_id": model.product_id,
        "vehicle_id": model.product_id,
        "support_program_id": model.support_program_id,
        "dealer_company_id": model.dealer_company_id,
        "distributor_company_id": model.distributor_company_id,
        "name": model.name,
        "support_type": model.support_type,
        "support_params": dict(model.support_params or {}),
        "comment": model.comment,
        "starts_at": _iso_date(model.starts_at),
        "ends_at": _iso_date(model.ends_at),
        "main_payer": model.main_payer,
        "base_amount": _as_float(model.base_amount),
        "support_amount": _as_float(model.support_amount),
        "created_at": _iso_datetime(model.created_at),
    }

def _try_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None

def _add_application_filters(
    conditions: list[Any],
    application_id: uuid.UUID | None,
    application_query: str | None,
) -> None:
    if application_id is not None:
        conditions.append(CompensationModel.application_id == application_id)

    if not application_query:
        return

    text = application_query.strip()
    match_conditions: list[Any] = [
        LeasingApplication.display_number.ilike(f"%{text}%"),
        FastDeal.display_number.ilike(f"%{text}%"),
    ]
    parsed_uuid = _try_uuid(text)
    if parsed_uuid is not None:
        match_conditions.extend(
            [
                CompensationModel.application_id == parsed_uuid,
                CompensationModel.fast_deal_id == parsed_uuid,
            ]
        )
    conditions.append(or_(*match_conditions))

def _add_support_filters(
    conditions: list[Any],
    applied_support_id: UUID | None,
    support_query: str | None,
) -> None:
    if applied_support_id is not None:
        conditions.append(CompensationModel.applied_support_id == applied_support_id)

    if not support_query:
        return

    text = support_query.strip()
    match_conditions: list[Any] = [ApplicationAppliedSupport.name.ilike(f"%{text}%")]
    parsed_uuid = _try_uuid(text)
    if parsed_uuid is not None:
        match_conditions.extend(
            [
                CompensationModel.applied_support_id == parsed_uuid,
                ApplicationAppliedSupport.support_program_id == parsed_uuid,
            ]
        )
    conditions.append(or_(*match_conditions))

def _add_participant_filter(
    conditions: list[Any],
    participant_role: str | None,
    participant_scope: Literal["payer", "recipient", "either"] | None,
) -> None:
    if not participant_role:
        return
    if participant_scope == "payer":
        conditions.append(CompensationModel.payer == participant_role)
    elif participant_scope == "recipient":
        conditions.append(CompensationModel.recipient == participant_role)
    elif participant_scope == "either":
        conditions.append(
            or_(
                CompensationModel.payer == participant_role,
                CompensationModel.recipient == participant_role,
            )
        )

def _as_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))

def _as_float(value: object | None) -> float | None:
    if value is None:
        return None
    return float(str(value))

def _iso_date(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)

def _iso_datetime(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
