
"""Submit a leasing application from the LC cabinet (no-op).

With the simplified 3-status model every application starts as ``active``,
so there is no longer a separate "submit" transition. This handler is kept
as a compatibility shim so existing imports and tests do not break.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import application_repository as repo


@dataclass
class SubmitLcApplicationCommand:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None


async def handle_submit_lc_application(
    cmd: SubmitLcApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.application_id)
    if existing is None:
        raise ApplicationNotFoundError(cmd.application_id)
    return {
        "message": "Заявка уже активна",
        "application": existing,
    }
