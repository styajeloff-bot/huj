"""Active administrative directories for the warehouse form."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import warehouse_repository as repo


def _result(
    key: str, rows: list[dict[str, Any]], total: int, page: int, limit: int
) -> dict[str, Any]:
    return {
        key: rows,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
        },
    }


async def handle_list_warehouse_form_marks(
    session: AsyncSession, *, search: str | None, page: int, limit: int
) -> dict[str, Any]:
    rows, total = await repo.list_form_marks(
        session, search=search, page=page, limit=limit
    )
    return _result("marks", rows, total, page, limit)


async def handle_list_warehouse_form_categories(
    session: AsyncSession,
    *,
    brand_ids: list[UUID],
    search: str | None,
    page: int,
    limit: int,
) -> dict[str, Any]:
    rows, total = await repo.list_form_categories(
        session, brand_ids=brand_ids, search=search, page=page, limit=limit
    )
    return _result("categories", rows, total, page, limit)
