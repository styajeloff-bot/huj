"""Vehicle support status — light-weight per-vehicle list of eligible programs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.support_programs import load_applicable_support_programs


@dataclass
class GetSupportStatusQuery:
    vehicle_ids: list[UUID] = field(default_factory=list)
    user: dict[str, Any] | None = None


async def handle_get_support_status(
    query: GetSupportStatusQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    if not query.vehicle_ids:
        return []
    # Always use the client view here: support-status is a discovery list,
    # leasing-company filters are applied only inside `calculate`.
    applicable_by_vehicle = await load_applicable_support_programs(
        session,
        query.vehicle_ids,
        leasing_company_id=None,
    )

    items: list[dict[str, Any]] = []
    for vid in query.vehicle_ids:
        applicable = applicable_by_vehicle.get(vid, [])
        program_ids = [item["id"] for item in applicable]
        if not program_ids:
            items.append(
                {
                    "vehicle_id": vid,
                    "has_support": False,
                    "support_type": None,
                    "support_params": None,
                    "eligible_program_ids": [],
                    "applicable_support_programs": [],
                }
            )
            continue
        chosen = applicable[0]
        items.append(
            {
                "vehicle_id": vid,
                "has_support": True,
                "support_type": chosen["support_type"],
                "support_params": chosen["support_params"],
                "eligible_program_ids": program_ids,
                "applicable_support_programs": applicable,
            }
        )
    return items
