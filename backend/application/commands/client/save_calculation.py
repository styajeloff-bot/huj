
"""Save a leasing calculation row owned by the current user."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class SaveCalculationCommand:
    user_id: UUID
    name: str
    params: dict[str, Any]
    calculation: dict[str, Any]


@dataclass(frozen=True)
class SaveCalculationResult:
    saved: dict[str, Any]


async def handle_save_calculation(
    cmd: SaveCalculationCommand, session: AsyncSession
) -> SaveCalculationResult:
    saved = await repo.save_calculation(
        session,
        cmd.user_id,
        name=cmd.name,
        params=dict(cmd.params),
        calculation=dict(cmd.calculation),
    )
    from infrastructure.messaging.dwh_events import emit_calculation_created
    calc = saved.get("calculation", {})
    emit_calculation_created({
        "calc_id": saved["id"],
        "user_id": saved["user_id"],
        "vehicle_ids": saved.get("params", {}).get("vehicle_ids"),
        "total_amount": str(calc.get("total_amount")) if calc.get("total_amount") else None,
        "down_payment": str(calc.get("down_payment")) if calc.get("down_payment") else None,
        "down_payment_percent": calc.get("down_payment_percent"),
        "lease_term_months": calc.get("lease_term_months"),
        "monthly_payment": str(calc.get("monthly_payment")) if calc.get("monthly_payment") else None,
        "total_cost": str(calc.get("total_cost")) if calc.get("total_cost") else None,
        "markup": str(calc.get("markup")) if calc.get("markup") else None,
        "rate": str(calc.get("rate")) if calc.get("rate") else None,
        "total_interest": str(calc.get("total_interest")) if calc.get("total_interest") else None,
        "buyout_amount": str(calc.get("buyout_amount")) if calc.get("buyout_amount") else None,
        "vat_refund": str(calc.get("vat_refund")) if calc.get("vat_refund") else None,
        "profit_tax_savings": str(calc.get("profit_tax_savings")) if calc.get("profit_tax_savings") else None,
        "total_savings": str(calc.get("total_savings")) if calc.get("total_savings") else None,
        "calculation_type": saved.get("params", {}).get("calculation_type"),
        "created_at": _isoformat(saved.get("created_at")),
    })
    return SaveCalculationResult(saved=saved)
