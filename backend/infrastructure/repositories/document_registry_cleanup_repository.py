"""Reference checks and upload/cleanup serialization for immutable file keys."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.document_registry import reference_document_files as files


def registry_file_key(key: str) -> bool:
    parts = key.split("/")
    if len(parts) != 4 or parts[0] != "document-registry":
        return False
    try:
        return all(str(UUID(part)) == part and UUID(part).int != 0 for part in parts[1:])
    except ValueError:
        return False


async def lock_file_key(session: AsyncSession, key: str) -> None:
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 22296))))


async def try_lock_file_key(session: AsyncSession, key: str) -> bool:
    return bool(await session.scalar(select(func.pg_try_advisory_xact_lock(func.hashtextextended(key, 22296)))))


async def is_referenced(session: AsyncSession, key: str) -> bool:
    # Include old versions and soft-deleted documents: these are retained files.
    return await session.scalar(select(files.c.id).where(files.c.s3_key == key).limit(1)) is not None
