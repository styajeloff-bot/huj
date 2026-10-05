"""Remove only aged, unreferenced uploads from the dedicated registry prefix."""

from datetime import UTC, datetime, timedelta
from typing import Any

import aioboto3
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import document_registry_cleanup_repository as repo
from infrastructure.settings import settings


async def cleanup_orphaned_registry_files(
    session: AsyncSession, *, before: datetime | None = None,
) -> dict[str, int]:
    """Inspect immutable keys without retaining locks across the bucket scan."""
    before = before or datetime.now(UTC) - timedelta(hours=24)
    if before.utcoffset() is None:
        raise ValueError("Timezone-aware cleanup cutoff required")
    counts = {"scanned": 0, "deleted": 0, "retained": 0}
    async with aioboto3.Session().client(
        "s3", endpoint_url=settings.s3_endpoint or None, region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    ) as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix="document-registry/"):
            for item in page.get("Contents", []):
                counts["scanned"] += 1
                if await _delete_orphan(session, s3, item, before):
                    counts["deleted"] += 1
                else:
                    counts["retained"] += 1
    return counts


async def _delete_orphan(
    session: AsyncSession, s3: Any, item: dict[str, Any], before: datetime,
) -> bool:
    key = item["Key"]
    if (not repo.registry_file_key(key) or item["LastModified"] >= before
        or await repo.is_referenced(session, key)):
        return False
    # A committed reference is permanent, including historical and deleted docs.
    # For a possible orphan, acquire the uploader's transaction lock in a
    # savepoint and recheck the reference after taking the lock. Rolling back
    # this read-only savepoint releases its lock immediately, including on an
    # S3 error, without committing or rolling back the caller's transaction.
    savepoint = await session.begin_nested()
    try:
        if not await repo.try_lock_file_key(session, key) or await repo.is_referenced(session, key):
            return False
        current = await s3.head_object(Bucket=settings.s3_bucket, Key=key)
        if current["LastModified"] >= before or current.get("ETag") != item.get("ETag"):
            return False
        await s3.delete_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
            return False
        raise
    finally:
        await savepoint.rollback()
