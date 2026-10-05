"""Background task that polls Kafka consumer lag and updates Prometheus gauges.

Runs inside the event-worker process.  It inspects every registered
``@broker.subscriber`` consumer, reads partition positions and end-offsets,
and exports lag per (topic, partition, group).
"""

from __future__ import annotations

import asyncio
import logging

from infrastructure.messaging.broker import broker
from infrastructure.metrics import KAFKA_CONSUMER_LAG, KAFKA_CONSUMER_LAG_TOTAL

logger = logging.getLogger("carcraft-backend")

# Scrape interval — should align with Prometheus scrape interval (15 s).
LAG_POLL_INTERVAL_SECONDS = 15


async def _collect_lag() -> None:
    """Read high-water offsets and current positions for all consumers."""
    for subscriber in broker._subscribers:
        consumer = getattr(subscriber, "consumer", None)
        if consumer is None:
            continue

        group_id = getattr(subscriber, "group_id", "unknown") or "unknown"
        assignment = consumer.assignment()
        if not assignment:
            continue

        try:
            end_offsets = await consumer.end_offsets(assignment)
            total_lag = 0
            for tp in assignment:
                position = await consumer.position(tp)
                highwater = end_offsets.get(tp)
                if highwater is None:
                    continue
                lag = max(0, highwater - position)
                KAFKA_CONSUMER_LAG.labels(
                    topic=tp.topic,
                    partition=str(tp.partition),
                    group=group_id,
                ).set(lag)
                total_lag += lag

            KAFKA_CONSUMER_LAG_TOTAL.labels(group=group_id).set(total_lag)
        except Exception as exc:
            logger.warning(
                "lag_collection_failed group=%s err=%s",
                group_id,
                exc,
            )


async def run_lag_collector() -> None:
    """Infinite loop that updates lag metrics every *LAG_POLL_INTERVAL_SECONDS*."""
    while True:
        try:
            await _collect_lag()
        except Exception as exc:
            logger.warning("lag_collector_iteration_failed err=%s", exc)
        await asyncio.sleep(LAG_POLL_INTERVAL_SECONDS)
