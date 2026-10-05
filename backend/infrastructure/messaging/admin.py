"""Idempotent topic provisioning for the catalog ingestion pipeline.

Called once on worker startup. Uses ``aiokafka`` (already pulled in by
``faststream[kafka]``) so we don't add a new dependency. Creating a topic
that already exists is treated as success — Redpanda returns
``TOPIC_ALREADY_EXISTS`` and we swallow it.
"""
from __future__ import annotations

import logging

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from infrastructure.messaging.topics import TOPIC_PARTITIONS
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


async def ensure_topics() -> None:
    """Create all catalog topics with their configured partition counts.

    Idempotent: lists existing topics first, then creates only the missing
    ones. This avoids the batch-create partial-failure trap where aiokafka
    raises a generic ``KafkaError`` when *some* topics already exist, which
    caused missing topics to never be created (``UnknownTopicOrPartitionError``
    on consumer start).
    """
    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_brokers,
        client_id="carcraft-topic-admin",
    )
    await admin.start()
    try:
        existing: set[str] = set()
        try:
            existing = set(await admin.list_topics())
        except Exception as exc:
            logger.warning("kafka_list_topics_failed err=%s", exc)

        missing = {
            name: partitions
            for name, partitions in TOPIC_PARTITIONS.items()
            if name not in existing
        }

        if not missing:
            logger.info("kafka_topics_all_exist count=%s", len(TOPIC_PARTITIONS))
            return

        new_topics = [
            NewTopic(
                name=name,
                num_partitions=partitions,
                replication_factor=1,
            )
            for name, partitions in missing.items()
        ]

        try:
            await admin.create_topics(new_topics)
            logger.info(
                "kafka_topics_created topics=%s",
                ",".join(missing.keys()),
            )
        except TopicAlreadyExistsError:
            logger.info("kafka_topics_already_exist")
        except Exception as exc:
            # Some brokers raise per-topic errors as a generic exception
            # when at least one topic already exists. Log loudly so we don't
            # silently skip creation again.
            logger.error("kafka_topics_create_failed err=%s", exc)
            raise
    finally:
        await admin.close()
