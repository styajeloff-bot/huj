"""Read-only queries for additional equipment and service catalogs."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as repo


async def handle_list_additional_equipments(
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    return {"items": await repo.list_additional_equipments(session)}


async def handle_list_additional_services(
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    return {"items": await repo.list_additional_services(session)}
