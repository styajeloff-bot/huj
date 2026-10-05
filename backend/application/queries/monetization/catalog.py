"""Hierarchy lookups for internal monetization program filters."""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import monetization_catalog_repository as repo


async def lookup_catalog(
    session: AsyncSession, field: Literal["marks", "models", "modifications", "trims"],
    mark_id: str | None = None, model_id: str | None = None,
    modification_id: UUID | None = None,
) -> dict[str, Any]:
    mark_ids = list(dict.fromkeys(part.strip() for part in (mark_id or "").split(",") if part.strip()))
    if field == "marks":
        return {"marks": await repo.list_marks(session)}
    if field == "models":
        return {"models": await repo.list_models(session, mark_ids)}
    if field == "modifications":
        return {"modifications": await repo.list_modifications(session, mark_ids, model_id)}
    return {"trims": await repo.list_trims(session, mark_ids, model_id, modification_id)}
