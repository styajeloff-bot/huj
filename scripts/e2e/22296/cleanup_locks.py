"""Cleanup regression against an isolated PostgreSQL, replacing only external S3.

Run cleanup_locks.sh; never point this harness at the application database.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from infrastructure.repositories.document_registry_cleanup_repository import lock_file_key
from infrastructure.services import document_registry_cleanup as cleanup


def key(number: int) -> str:
    return f"document-registry/{UUID(int=1)}/{UUID(int=2)}/{UUID(int=number)}"


class S3Listing:
    """Controlled external listing; all reference queries and locks are real SQL."""

    def __init__(self, numbers: range, observe, *, fail_delete: bool = False):
        self.keys = [key(number) for number in numbers]
        self.observe = observe
        self.fail_delete = fail_delete
        self.deleted: list[str] = []
        self.old = datetime.now(UTC) - timedelta(days=2)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    async def paginate(self, **kwargs):
        assert kwargs["Prefix"] == "document-registry/"
        for offset in range(0, len(self.keys), 100):
            await self.observe()
            yield {"Contents": [{"Key": item, "LastModified": self.old, "ETag": "fixture"} for item in self.keys[offset:offset + 100]]}

    async def head_object(self, **kwargs):
        await self.observe()
        return {"LastModified": self.old, "ETag": "fixture"}

    async def delete_object(self, **kwargs):
        if self.fail_delete:
            raise RuntimeError("isolated fixture S3 deletion failure")
        self.deleted.append(kwargs["Key"])


class S3Factory:
    def __init__(self, client):
        self.client_instance = client

    def client(self, service, **_):
        assert service == "s3"
        return self.client_instance


async def main():
    engine = create_async_engine("postgresql+asyncpg://cleanup_regression@cleanup-pg:5432/cleanup_regression", pool_size=3, max_overflow=0)
    sessions = async_sessionmaker(engine)
    original_aws = cleanup.aioboto3.Session
    try:
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT current_database()")) == "cleanup_regression"
            assert await connection.scalar(text("SHOW max_locks_per_transaction")) == "10"
            await connection.execute(text("CREATE TABLE reference_document_files (id uuid PRIMARY KEY, s3_key text NOT NULL UNIQUE)"))
            await connection.execute(text("INSERT INTO reference_document_files(id, s3_key) VALUES (:id, :s3_key)"), [{"id": UUID(int=n), "s3_key": key(n)} for n in range(1, 4001)])
        async with engine.connect() as observer, sessions() as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            maximum = 0

            async def lock_count():
                return int(await observer.scalar(text("SELECT count(*) FROM pg_locks WHERE pid=:pid AND locktype='advisory'"), {"pid": pid}))

            async def observe():
                nonlocal maximum
                current = await lock_count()
                maximum = max(maximum, current)
                assert current <= 1, f"Cleanup accumulated {current} advisory locks"

            async def run(label, numbers, expected, *, failure=False):
                nonlocal maximum, pid
                maximum = 0
                pid = await session.scalar(text('SELECT pg_backend_pid()'))
                listing = S3Listing(numbers, observe, fail_delete=failure)
                cleanup.aioboto3.Session = lambda: S3Factory(listing)
                if failure:
                    try:
                        await cleanup.cleanup_orphaned_registry_files(session)
                    except RuntimeError as exc:
                        assert str(exc) == "isolated fixture S3 deletion failure"
                    else:
                        raise AssertionError("Expected external deletion failure")
                else:
                    actual = await cleanup.cleanup_orphaned_registry_files(session)
                    assert actual == expected, (label, actual, expected)
                held = await lock_count()
                assert held == 0, f"{label}: cleanup retained {held} locks until caller transaction ends"
                print(json.dumps({"stage": label, "max_advisory_locks": maximum, "locks_after_call": held, "deleted": len(listing.deleted)}), flush=True)
                await session.rollback()
                return listing

            await run("referenced_files_release_locks", range(1, 101), {"scanned": 100, "deleted": 0, "retained": 100})
            await run("4000_referenced_files_bounded", range(1, 4001), {"scanned": 4000, "deleted": 0, "retained": 4000})
            await run("1200_orphans_bounded", range(5001, 6201), {"scanned": 1200, "deleted": 1200, "retained": 0})
            async with sessions() as uploader:
                await lock_file_key(uploader, key(7001))
                kept = await run("concurrent_upload_kept", range(7001, 7002), {"scanned": 1, "deleted": 0, "retained": 1})
                assert not kept.deleted
                await uploader.rollback()
            await run("uncommitted_upload_reclaimed", range(7001, 7002), {"scanned": 1, "deleted": 1, "retained": 0})
            await run("external_failure_releases_lock", range(8001, 8002), {}, failure=True)
            assert await observer.scalar(text("SELECT count(*) FROM reference_document_files")) == 4000
        print(json.dumps({"stage": "cleanup_lock_regressions_passed", "postgres_limits": "max_connections=10,max_locks_per_transaction=10", "production_threshold_claimed": False}), flush=True)
    finally:
        cleanup.aioboto3.Session = original_aws
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
