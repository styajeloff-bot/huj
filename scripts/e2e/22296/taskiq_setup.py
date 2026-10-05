"""Create and clean only the transport/storage resources named by the guard."""

import asyncio
import sys

import taskiq_bootstrap
from runtime import guard, keys, migrate, progress, seed


async def initialize():
    await seed()
    from infrastructure.messaging.admin import ensure_topics

    await ensure_topics()
    progress("taskiq_private_resources_initialized")


async def cleanup():
    import aioboto3
    from aiokafka.admin import AIOKafkaAdminClient

    settings = guard()
    config = taskiq_bootstrap.CONFIG
    async with aioboto3.Session().client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    ) as s3:
        buckets = await s3.list_buckets()
        if any(bucket["Name"] == config["bucket"] for bucket in buckets["Buckets"]):
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=config["bucket"]):
                keys_to_delete = [
                    {"Key": row["Key"]} for row in page.get("Contents", [])
                ]
                if keys_to_delete:
                    result = await s3.delete_objects(
                        Bucket=config["bucket"], Delete={"Objects": keys_to_delete}
                    )
                    if result.get("Errors"):
                        raise RuntimeError("Private S3 objects could not be removed")
            await s3.delete_bucket(Bucket=config["bucket"])
        buckets = await s3.list_buckets()
        if any(bucket["Name"] == config["bucket"] for bucket in buckets["Buckets"]):
            raise RuntimeError("Private bucket remains after cleanup")
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_brokers)
    await admin.start()
    try:
        existing = set(await admin.list_topics())
        private_topics = [
            topic for topic in (config["topic"], config["dlq"]) if topic in existing
        ]
        if private_topics:
            await admin.delete_topics(private_topics)
        for _ in range(30):
            remaining = set(await admin.list_topics()) & {
                config["topic"],
                config["dlq"],
            }
            if not remaining:
                break
            await asyncio.sleep(0.1)
        if remaining:
            raise RuntimeError("Private Kafka topics remain after cleanup")
    finally:
        await admin.close()
    progress(
        "taskiq_private_s3_kafka_removed",
        bucket=config["bucket"],
        topics=[config["topic"], config["dlq"]],
    )


if __name__ == "__main__":
    if sys.argv[1] == "init":
        keys()
        migrate()
        asyncio.run(initialize())
    elif sys.argv[1] == "cleanup":
        asyncio.run(cleanup())
    else:
        raise SystemExit("Expected init or cleanup")
