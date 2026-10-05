"""Calculator repository — leasing rates, history, support-program lookups.

Returns plain dicts/lists. ORM models live only inside this file.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import CalculationHistory
from infrastructure.models.companies import (
    Company,
    LeasingCompany,
)
from infrastructure.models.misc import LeasingRate
from infrastructure.models.special_equipment import (
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.support import (
    DealerGroup,
    DealerGroupMember,
    SupportBillOfLading,
    SupportProgram,
    SupportProgramDealerGroup,
    SupportProgramLeasingCompany,
    SupportProgramMark,
)
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Leasing rates
# ---------------------------------------------------------------------------

@timed_repository
async def get_leasing_rates(session: AsyncSession) -> dict[str, Any] | None:
    rate = await get_effective_leasing_rate(session)
    if not rate:
        return None
    return {
        "key_rate": rate["key_rate"],
        "surcharge": rate["surcharge"],
        "vat_rate": rate["vat_rate"],
        "profit_tax_rate": rate["profit_tax_rate"],
    }


def _rate_ordering() -> tuple[Any, ...]:
    return (
        sa.case((LeasingRate.date_to.is_(None), 0), else_=1).asc(),
        LeasingRate.date_from.desc(),
        LeasingRate.id.desc(),
    )


def _leasing_rate_to_dict(rate: LeasingRate) -> dict[str, Any]:
    return {
        "id": rate.id,
        "date_from": rate.date_from,
        "date_to": rate.date_to,
        "is_current": rate.date_to is None,
        "key_rate": float(rate.key_rate),
        "surcharge": float(rate.surcharge),
        "vat_rate": float(rate.vat_rate),
        "profit_tax_rate": float(rate.profit_tax_rate),
    }


@timed_repository
async def get_effective_leasing_rate(session: AsyncSession) -> dict[str, Any] | None:
    stmt = select(LeasingRate).order_by(*_rate_ordering()).limit(1)
    rate = (await session.execute(stmt)).scalars().first()
    return _leasing_rate_to_dict(rate) if rate else None


@timed_repository
async def list_leasing_rate_rows(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(LeasingRate).order_by(*_rate_ordering())
    rates = (await session.execute(stmt)).scalars().all()
    return [_leasing_rate_to_dict(rate) for rate in rates]


@timed_repository
async def get_leasing_rate_row(
    session: AsyncSession, rate_id: UUID
) -> dict[str, Any] | None:
    rate = await session.get(LeasingRate, rate_id)
    return _leasing_rate_to_dict(rate) if rate else None


@timed_repository
async def has_current_leasing_rate(
    session: AsyncSession, *, exclude_id: UUID | None = None
) -> bool:
    stmt = select(LeasingRate.id).where(LeasingRate.date_to.is_(None))
    if exclude_id is not None:
        stmt = stmt.where(LeasingRate.id != exclude_id)
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


@timed_repository
async def has_overlapping_leasing_rate_period(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date | None,
    exclude_id: UUID | None = None,
) -> bool:
    conditions: list[Any] = [
        sa.or_(LeasingRate.date_to.is_(None), LeasingRate.date_to > date_from)
    ]
    if date_to is not None:
        conditions.append(LeasingRate.date_from < date_to)
    if exclude_id is not None:
        conditions.append(LeasingRate.id != exclude_id)

    stmt = select(LeasingRate.id).where(*conditions).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


@timed_repository
async def create_leasing_rate_row(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date | None,
    key_rate: float,
    surcharge: float,
    vat_rate: float,
    profit_tax_rate: float,
) -> dict[str, Any]:
    rate = LeasingRate(
        date_from=date_from,
        date_to=date_to,
        key_rate=key_rate,
        surcharge=surcharge,
        vat_rate=vat_rate,
        profit_tax_rate=profit_tax_rate,
    )
    session.add(rate)
    await session.flush()
    await session.refresh(rate)
    return _leasing_rate_to_dict(rate)


@timed_repository
async def update_leasing_rate_row(
    session: AsyncSession,
    rate_id: UUID,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    rate = await session.get(LeasingRate, rate_id)
    if rate is None:
        return None
    for key, value in values.items():
        setattr(rate, key, value)
    await session.flush()
    await session.refresh(rate)
    return _leasing_rate_to_dict(rate)

# ---------------------------------------------------------------------------
# Leasing companies
# ---------------------------------------------------------------------------

@timed_repository
async def get_active_leasing_companies(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingCompany.id,
            Company.name,
            LeasingCompany.average_down_payment_percent,
            LeasingCompany.average_lease_term_months,
            LeasingCompany.average_markup_percent,
            LeasingCompany.min_down_payment_percent,
            LeasingCompany.max_lease_term_months,
        )
        .join(Company, Company.id == LeasingCompany.company_id)
        .where(LeasingCompany.is_active.is_(True), Company.is_active.is_(True))
        .order_by(Company.name.asc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "average_down_payment_percent": row["average_down_payment_percent"],
            "average_lease_term_months": row["average_lease_term_months"],
            "average_markup_percent": (
                float(row["average_markup_percent"])
                if row["average_markup_percent"] is not None
                else None
            ),
            "min_down_payment_percent": row["min_down_payment_percent"],
            "max_lease_term_months": row["max_lease_term_months"],
        }
        for row in rows
    ]

@timed_repository
async def get_leasing_company_id_by_company_id(
    session: AsyncSession, company_id: UUID | None
) -> UUID | None:
    if company_id is None:
        return None
    stmt = select(LeasingCompany.id).where(LeasingCompany.company_id == company_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row if row is not None else None

# ---------------------------------------------------------------------------
# Optional auth helper
# ---------------------------------------------------------------------------

@timed_repository
async def find_active_user_for_calculator(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    stmt = select(User.id, User.role, User.company_id).where(
        User.id == user_id, User.is_active.is_(True)
    )
    row = (await session.execute(stmt)).mappings().first()
    if not row:
        return None
    return {"id": row["id"], "role": row["role"], "company_id": row["company_id"]}

# ---------------------------------------------------------------------------
# Vehicles effective prices
# ---------------------------------------------------------------------------

@timed_repository
async def get_vehicles_effective_prices(
    session: AsyncSession, vehicle_ids: list[UUID]
) -> list[dict[str, Any]]:
    """Return the same authoritative unit price exposed by the public catalog."""

    if not vehicle_ids:
        return []
    effective_price = sa.func.coalesce(
        SpecialEquipmentProduct.special_price,
        SpecialEquipmentProduct.price,
        0,
    )
    stmt = select(
        SpecialEquipmentProduct.id.label("vehicle_id"),
        effective_price.label("effective_price"),
    ).where(SpecialEquipmentProduct.id.in_(vehicle_ids))
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "vehicle_id": r["vehicle_id"],
            "effective_price": float(r["effective_price"] or 0),
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Vehicles with applicable support programs
# ---------------------------------------------------------------------------

def _support_program_join_conditions() -> list[sa.ColumnElement[bool]]:
    """SQL filters that decide whether a support_program applies to a vehicle/product."""
    sp = SupportProgram
    v = SpecialEquipmentProduct
    v_model_id = (
        select(SpecialEquipmentModification.model_id)
        .where(SpecialEquipmentModification.id == v.modification_id)
        .correlate(v)
        .scalar_subquery()
    )
    v_mark_id = (
        select(SpecialEquipmentModel.mark_id)
        .where(SpecialEquipmentModel.id == v_model_id)
        .correlate(v)
        .scalar_subquery()
    )
    today = sa.func.current_date()
    mark_match = (
        select(SupportProgramMark.mark_id)
        .where(
            SupportProgramMark.support_program_id == sp.id,
            SupportProgramMark.mark_id == v_mark_id,
        )
        .exists()
    )
    return [
        sp.is_active.is_(True),
        sa.or_(sp.starts_at.is_(None), sp.starts_at <= today),
        sa.or_(sp.ends_at.is_(None), sp.ends_at >= today),
        sa.or_(sp.mark_id.is_(None), sp.mark_id == v_mark_id, mark_match),
        sa.or_(
            sa.and_(
                sp.vin.is_(None),
                sa.or_(
                    sp.vins.is_(None),
                    sa.func.cardinality(sp.vins) == 0,
                ),
            ),
            sa.and_(sp.vin.is_not(None), v.vin == sp.vin),
            sa.and_(sp.vins.is_not(None), v.vin == sa.func.any(sp.vins)),
        ),
        sa.or_(
            sa.and_(
                sp.model_id.is_(None),
                sa.or_(
                    sp.model_ids.is_(None),
                    sa.func.cardinality(sp.model_ids) == 0,
                ),
            ),
            sa.and_(sp.model_id.is_not(None), sp.model_id == v_model_id),
            sa.and_(
                sp.model_ids.is_not(None),
                sa.cast(v_model_id, sa.Text) == sa.func.any(sp.model_ids),
            ),
        ),
        sa.or_(
            sp.production_year_from.is_(None),
            v.manufacture_year >= sp.production_year_from,
        ),
        sa.or_(
            sp.production_year_to.is_(None),
            v.manufacture_year <= sp.production_year_to,
        ),
    ]


def _vehicle_dealer_company_id_expr() -> sa.ColumnElement[Any]:
    warehouse_dealer_company_id = (
        select(sa.func.coalesce(Warehouse.company_id, Warehouse.dealer_id))
        .where(Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .limit(1)
        .correlate(SpecialEquipmentProduct)
        .scalar_subquery()
    )
    return sa.func.coalesce(warehouse_dealer_company_id, SpecialEquipmentProduct.seller_company_id)


def _support_dealer_group_condition() -> sa.ColumnElement[bool]:
    dealer_company_id = _vehicle_dealer_company_id_expr()
    has_group_restriction = (
        select(SupportProgramDealerGroup.dealer_group_id)
        .where(SupportProgramDealerGroup.support_program_id == SupportProgram.id)
        .correlate(SupportProgram)
        .exists()
    )
    group_match = (
        select(DealerGroupMember.id)
        .select_from(DealerGroupMember)
        .join(DealerGroup, DealerGroup.id == DealerGroupMember.dealer_group_id)
        .join(
            SupportProgramDealerGroup,
            sa.and_(
                SupportProgramDealerGroup.dealer_group_id == DealerGroup.id,
                SupportProgramDealerGroup.support_program_id == SupportProgram.id,
            ),
        )
        .where(
            DealerGroup.is_active.is_(True),
            DealerGroup.distributor_company_id == SupportProgram.distributor_id,
            DealerGroupMember.dealer_company_id == dealer_company_id,
        )
        .correlate(SupportProgram, SpecialEquipmentProduct)
        .exists()
    )
    return sa.or_(sa.not_(has_group_restriction), group_match)

@timed_repository
async def get_vehicles_with_support_info(
    session: AsyncSession,
    vehicle_ids: list[UUID],
    *,
    leasing_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Return one row per (vehicle, applicable support_program)."""
    if not vehicle_ids:
        return []
    join_conds = _support_program_join_conditions()

    if leasing_company_id is not None:
        join_conds.append(
            SupportProgram.show_to_leasing_company.is_not(False)
        )
        # Either no LC restriction on the program, or the restriction matches.
        no_lc_restriction = sa.not_(
            select(SupportProgramLeasingCompany.leasing_company_id)
            .where(
                SupportProgramLeasingCompany.support_program_id == SupportProgram.id
            )
            .exists()
        )
        lc_match = (
            select(SupportProgramLeasingCompany.leasing_company_id)
            .where(
                SupportProgramLeasingCompany.support_program_id == SupportProgram.id,
                SupportProgramLeasingCompany.leasing_company_id == leasing_company_id,
            )
            .exists()
        )
        join_conds.append(sa.or_(no_lc_restriction, lc_match))
    else:
        join_conds.append(SupportProgram.show_to_client.is_not(False))
    join_conds.append(_support_dealer_group_condition())

    stmt = (
        select(
            SpecialEquipmentProduct.id.label("vehicle_id"),
            sa.func.coalesce(SpecialEquipmentProduct.price, 0).label("base_price"),
            SupportProgram.id.label("support_program_id"),
            SupportProgram.support_type.label("support_type"),
            SupportProgram.support_params.label("support_params"),
        )
        .join(SupportProgram, sa.and_(*join_conds))
        .where(SpecialEquipmentProduct.id.in_(vehicle_ids))
        .order_by(SpecialEquipmentProduct.id.asc(), SupportProgram.id.asc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "vehicle_id": r["vehicle_id"],
            "base_price": float(r["base_price"] or 0),
            "support_program_id": (
                r["support_program_id"] if r["support_program_id"] is not None else None
            ),
            "support_type": r["support_type"],
            "support_params": r["support_params"],
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Support program details
# ---------------------------------------------------------------------------

@timed_repository
async def get_support_program_details_by_ids(
    session: AsyncSession, program_ids: list[UUID]
) -> list[dict[str, Any]]:
    if not program_ids:
        return []
    unique_ids = sorted({pid for pid in program_ids if pid is not None})
    if not unique_ids:
        return []

    stmt = select(
        SupportProgram.id,
        SupportProgram.name,
        SupportProgram.support_type,
        SupportProgram.support_params,
        SupportProgram.comment,
        SupportProgram.starts_at,
        SupportProgram.ends_at,
        SupportProgram.is_compatible,
    ).where(SupportProgram.id.in_(unique_ids))
    program_rows = (await session.execute(stmt)).mappings().all()

    from infrastructure.repositories import support_repository

    compatibility_by_program_id = (
        await support_repository.get_compatibility_by_program_ids(
            session,
            unique_ids,
        )
    )

    bol_stmt = select(
        SupportBillOfLading.support_program_id,
        SupportBillOfLading.id,
        SupportBillOfLading.bill_date,
        SupportBillOfLading.file_name,
        SupportBillOfLading.file_path,
        SupportBillOfLading.file_size,
        SupportBillOfLading.comment,
        SupportBillOfLading.created_at,
    ).where(SupportBillOfLading.support_program_id.in_(unique_ids)).order_by(
        SupportBillOfLading.support_program_id.asc(),
        SupportBillOfLading.created_at.asc(),
    )
    bol_rows = (await session.execute(bol_stmt)).mappings().all()

    bol_by_program: dict[UUID, dict[str, Any]] = {}
    for row in bol_rows:
        pid = row["support_program_id"]
        bucket = bol_by_program.setdefault(pid, {"comment": None, "files": []})
        if row["comment"]:
            bucket["comment"] = row["comment"]
        bucket["files"].append(
            {
                "id": row["id"],
                "bill_date": _date_iso(row["bill_date"]),
                "file_name": row["file_name"],
                "file_path": row["file_path"],
                "file_size": row["file_size"],
            }
        )

    out: list[dict[str, Any]] = []
    for row in program_rows:
        pid = row["id"]
        bol = bol_by_program.get(pid)
        out.append(
            {
                "id": pid,
                "name": row["name"],
                "support_type": row["support_type"],
                "support_params": row["support_params"] or {},
                "comment": row["comment"],
                "starts_at": _date_iso(row["starts_at"]),
                "ends_at": _date_iso(row["ends_at"]),
                "is_compatible": bool(row["is_compatible"]),
                "compatible_support_ids": sorted(
                    compatibility_by_program_id.get(pid, set())
                ),
                "bill_of_lading": (
                    bol if bol and bol["files"] else None
                ),
            }
        )
    return out

def _date_iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@timed_repository
async def list_history_by_user(
    session: AsyncSession, user_id: UUID, *, limit: int, offset: int
) -> list[dict[str, Any]]:
    stmt = (
        select(
            CalculationHistory.id,
            CalculationHistory.vehicle_ids,
            CalculationHistory.total_amount,
            CalculationHistory.down_payment,
            CalculationHistory.down_payment_percent,
            CalculationHistory.lease_term_months,
            CalculationHistory.monthly_payment,
            CalculationHistory.total_cost,
            CalculationHistory.markup,
            CalculationHistory.calculation_type,
            CalculationHistory.created_at,
        )
        .where(CalculationHistory.user_id == user_id)
        .order_by(CalculationHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "id": r["id"],
            "vehicle_ids": list(r["vehicle_ids"] or []),
            "total_amount": _num(r["total_amount"]),
            "down_payment": _num(r["down_payment"]),
            "down_payment_percent": _num(r["down_payment_percent"]),
            "lease_term_months": r["lease_term_months"],
            "monthly_payment": _num(r["monthly_payment"]),
            "total_cost": _num(r["total_cost"]),
            "markup": _num(r["markup"]),
            "calculation_type": r["calculation_type"],
            "created_at": (
                r["created_at"].isoformat() if r["created_at"] is not None else None
            ),
        }
        for r in rows
    ]

@timed_repository
async def count_history_by_user(session: AsyncSession, user_id: UUID) -> int:
    stmt = select(func.count(CalculationHistory.id)).where(
        CalculationHistory.user_id == user_id
    )
    return int((await session.execute(stmt)).scalar() or 0)

@timed_repository
async def save_history(session: AsyncSession, data: dict[str, Any]) -> UUID:
    row = CalculationHistory(
        user_id=data["user_id"],
        vehicle_ids=data.get("vehicle_ids") or [],
        total_amount=data.get("total_amount"),
        down_payment=data.get("down_payment"),
        down_payment_percent=data.get("down_payment_percent"),
        lease_term_months=data.get("lease_term_months"),
        monthly_payment=data.get("monthly_payment"),
        total_cost=data.get("total_cost"),
        markup=data.get("markup"),
        calculation_type=data.get("calculation_type", "standard"),
        rate=data.get("rate"),
        total_interest=data.get("total_interest"),
        buyout_amount=data.get("buyout_amount", 0),
        vat_refund=data.get("vat_refund"),
        profit_tax_savings=data.get("profit_tax_savings"),
        total_savings=data.get("total_savings"),
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row.id

def _num(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
