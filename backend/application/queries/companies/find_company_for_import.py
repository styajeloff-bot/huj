"""Find company by id or inn for CSV import upsert."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.company_repository import (
    find_company_id_by_inn as _find_company_id_by_inn,
)
from infrastructure.repositories.company_repository import (
    get_company_by_id,
)


async def find_company_by_id(
    session: AsyncSession, company_id: UUID
) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await get_company_by_id(session, company_id)
    return result


async def find_company_id_by_inn(
    session: AsyncSession, inn: str
) -> UUID | None:
    result: UUID | None = await _find_company_id_by_inn(session, inn)
    return result
