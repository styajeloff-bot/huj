"""Read-only persistence operations for the citizenship reference."""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.citizenship import Citizenship


async def list_citizenships(session: AsyncSession) -> list[dict[str, Any]]:
    """Return a deterministic Unicode-alphabetical list of citizenships."""
    rows = (
        await session.execute(
            sa.select(Citizenship).order_by(
                sa.func.translate(Citizenship.citizenship_name, "Ёё", "Ее").collate("C"),
                Citizenship.citizenship_name.collate("C"),
                Citizenship.id,
            )
        )
    ).scalars()
    return [
        {
            "id": row.id,
            "code2": row.code2,
            "code3": row.code3,
            "citizenship_name": row.citizenship_name,
        }
        for row in rows
    ]
