from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

import aioboto3
import asyncpg
import redis.asyncio as redis
from aiokafka.admin import AIOKafkaAdminClient
from botocore.exceptions import ClientError

logger = logging.getLogger("carcraft-e2e")


async def _retry(
    label: str,
    operation: Callable[[], Awaitable[None]],
    *,
    attempts: int = 90,
) -> None:
    last_error: Exception | None = None
    for _attempt in range(attempts):
        try:
            await operation()
            logger.info("healthy: %s", label)
            return
        except Exception as error:
            last_error = error
            await asyncio.sleep(1)
    raise RuntimeError(f"Timed out waiting for {label}") from last_error


async def _postgres() -> None:
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    connection = await asyncpg.connect(dsn, timeout=3)
    try:
        await connection.fetchval("SELECT 1")
    finally:
        await connection.close()


async def _redis() -> None:
    client = redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=3)
    try:
        if not await client.ping():
            raise RuntimeError("Redis PING returned false")
    finally:
        await client.aclose()


async def _kafka() -> None:
    client = AIOKafkaAdminClient(
        bootstrap_servers=os.environ["KAFKA_BROKERS"],
        request_timeout_ms=3_000,
    )
    await client.start()
    await client.close()


async def _s3_and_bucket() -> None:
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        region_name=os.environ.get("S3_REGION", "ru-central1"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
    ) as client:
        bucket = os.environ["S3_BUCKET"]
        try:
            await client.head_bucket(Bucket=bucket)
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                raise RuntimeError(f"Bucket {bucket} not found") from error
            raise


async def main() -> None:
    await _retry("PostgreSQL", _postgres)
    await _retry("Redis", _redis)
    await _retry("Redpanda", _kafka)
    await _retry("S3 and bucket", _s3_and_bucket)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(main())
