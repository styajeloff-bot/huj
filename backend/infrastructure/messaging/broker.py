"""FastStream KafkaBroker singleton and lifecycle helpers."""

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from time import monotonic
from typing import Any
from uuid import uuid4

from faststream import BaseMiddleware
from faststream.kafka import KafkaBroker, KafkaPublishCommand
from faststream.message import StreamMessage

from infrastructure.logging import (
    LogLevel,
    bind_log_context,
    get_log_context_field,
    log_event,
    normalize_correlation_id,
)
from infrastructure.settings import settings


class _FastStreamWarningLogger:
    """Keep dependency warnings/errors while suppressing routine service chatter."""

    def log(
        self,
        level: int,
        msg: Any,
        /,
        *,
        exc_info: Any = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        if level < logging.WARNING:
            return

        fields: dict[str, Any] = {"component": "kafka"}
        if extra:
            for key in ("topic", "message_id"):
                value = extra.get(key)
                if value:
                    fields[key] = value
            if group_id := extra.get("group_id"):
                fields["consumer_group"] = group_id

        if level >= logging.CRITICAL:
            normalized_level: LogLevel = "critical"
        elif level >= logging.ERROR:
            normalized_level = "error"
        else:
            normalized_level = "warning"
        log_event(
            normalized_level,
            f"faststream.{normalized_level}",
            str(msg),
            error=exc_info if isinstance(exc_info, BaseException) else None,
            **fields,
        )


def _header_correlation_id(raw_message: Any) -> str | None:
    headers = getattr(raw_message, "headers", ()) or ()
    items: Iterable[tuple[Any, Any]]
    if isinstance(headers, Mapping):
        items = headers.items()
    else:
        items = headers
    for key, value in items:
        if str(key).lower() != "correlation_id":
            continue
        decoded = value.decode(errors="replace") if isinstance(value, bytes) else value
        return normalize_correlation_id(decoded)
    return None


def _consumer_group(context: Any) -> str | None:
    get_local = getattr(context, "get_local", None)
    if not callable(get_local):
        return None
    log_context = get_local("log_context", {})
    if not isinstance(log_context, Mapping):
        return None
    group_id = log_context.get("group_id")
    return str(group_id) if group_id else None


class KafkaLoggingMiddleware(BaseMiddleware[KafkaPublishCommand, Any]):
    """Propagate correlation and own one terminal event per consumed operation."""

    async def publish_scope(
        self,
        call_next: Callable[[KafkaPublishCommand], Awaitable[Any]],
        cmd: KafkaPublishCommand,
    ) -> Any:
        correlation_id = normalize_correlation_id(
            get_log_context_field("correlation_id")
        )
        if correlation_id is not None:
            cmd.correlation_id = correlation_id
            cmd.headers = {**cmd.headers, "correlation_id": correlation_id}
        return await call_next(cmd)

    async def consume_scope(
        self,
        call_next: Callable[[StreamMessage[Any]], Awaitable[Any]],
        msg: StreamMessage[Any],
    ) -> Any:
        raw_messages = (
            msg.raw_message
            if isinstance(msg.raw_message, tuple)
            else (msg.raw_message,)
        )
        first = raw_messages[0]
        topic = str(getattr(first, "topic", "unknown"))
        partition = getattr(first, "partition", None)
        offset = getattr(first, "offset", None)
        message_count = len(raw_messages)
        operation = "batch" if message_count > 1 else "message"
        started_at = monotonic()

        record_correlation_ids = [
            _header_correlation_id(raw_message) for raw_message in raw_messages
        ]
        source_correlation_ids = list(
            dict.fromkeys(
                correlation_id
                for correlation_id in record_correlation_ids
                if correlation_id is not None
            )
        )
        incomplete_batch = message_count > 1 and any(
            correlation_id is None for correlation_id in record_correlation_ids
        )
        aggregate_batch = message_count > 1 and (
            incomplete_batch or len(source_correlation_ids) != 1
        )
        if len(source_correlation_ids) == 1 and not incomplete_batch:
            correlation_id = source_correlation_ids[0]
        elif aggregate_batch:
            # A batch may combine several originating requests. Give the batch
            # its own ID and retain every source ID instead of attributing all
            # records to FastStream's first-message correlation.
            correlation_id = str(uuid4())
        else:
            correlation_id = normalize_correlation_id(msg.correlation_id) or str(uuid4())

        context_fields: dict[str, Any] = {
            "correlation_id": correlation_id,
            "topic": topic,
        }
        if aggregate_batch and source_correlation_ids:
            context_fields["source_correlation_ids"] = source_correlation_ids
        uncorrelated_message_count = sum(
            correlation_id is None for correlation_id in record_correlation_ids
        )
        if uncorrelated_message_count:
            context_fields["uncorrelated_message_count"] = uncorrelated_message_count
        if partition is not None:
            context_fields["partition"] = partition
        if offset is not None:
            context_fields["offset"] = offset
        if consumer_group := _consumer_group(self.context):
            context_fields["consumer_group"] = consumer_group

        terminal_fields: dict[str, Any] = {
            "component": "kafka",
            "message_count": message_count,
        }
        if aggregate_batch and source_correlation_ids:
            terminal_fields["source_correlation_ids"] = source_correlation_ids
        if uncorrelated_message_count:
            terminal_fields["uncorrelated_message_count"] = (
                uncorrelated_message_count
            )

        with bind_log_context(**context_fields):
            try:
                result = await call_next(msg)
            except Exception as exc:
                log_event(
                    "error",
                    f"kafka.{operation}.failed",
                    f"Kafka {operation} from {topic} failed",
                    error=exc,
                    duration_ms=round((monotonic() - started_at) * 1000, 2),
                    **terminal_fields,
                )
                raise

            log_event(
                "info",
                f"kafka.{operation}.completed",
                f"Consumed {message_count} Kafka {operation} from {topic}",
                duration_ms=round((monotonic() - started_at) * 1000, 2),
                **terminal_fields,
            )
            return result


broker: KafkaBroker = KafkaBroker(
    settings.kafka_brokers,
    logger=_FastStreamWarningLogger(),
    middlewares=(KafkaLoggingMiddleware,),
)


def get_broker() -> KafkaBroker:
    """Return the module-level KafkaBroker singleton."""
    return broker


async def start_broker() -> None:
    """Connect the broker and start any registered subscribers."""
    await broker.start()


async def stop_broker() -> None:
    """Gracefully close the broker."""
    await broker.stop()
