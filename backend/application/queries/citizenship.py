"""Read use case for the controlled citizenship reference."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import citizenship_repository as repo


async def list_citizenships(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    return {"items": await repo.list_citizenships(session)}
