"""One database snapshot for document ACL and every part of its projection."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from presentation.dependencies.notification_database import get_db


async def get_read_snapshot(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncSession:
    # Acquire the connection before actor resolution performs its first query.
    # Pool return resets these transaction options; writes keep normal isolation.
    await session.connection(execution_options={
        "isolation_level": "REPEATABLE READ", "postgresql_readonly": True,
    })
    return session
