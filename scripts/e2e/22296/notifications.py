"""Isolated real Kafka/outbox/inbox expiry workflow for task 22296."""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

READY = Path("/runtime/documentregistry22296-notifications-ready")


def healthy() -> bool:
    try:
        return time.time() - READY.stat().st_mtime < 30
    except FileNotFoundError:
        return False


def _registry_link_matches(action_url: str | None, document_id: UUID) -> bool:
    if not action_url:
        return False
    url = urlsplit(action_url)
    query = parse_qs(url.query)
    if (url.path != "/workspace/document-registry" or url.netloc or url.scheme
        or query.get("document") != [str(document_id)]
        or not set(query) <= {"document", "notification_company_id"}):
        return False
    context = query.get("notification_company_id")
    if context:
        return len(context) == 1 and str(UUID(context[0])) == context[0]
    return True


async def verify_notifications(
    document_id: UUID, expected_user_ids: set[UUID], *,
    version_id: UUID | None = None, wait_seconds: float = 40,
) -> UUID:
    from runtime import guard, require

    guard()
    from sqlalchemy import select

    from application.notifications.document_registry_expiry import (
        scan_document_registry_expiries,
    )
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.misc import Notification
    from infrastructure.models.notification_delivery import (
        NotificationEmailDelivery,
        NotificationEventOutbox,
        NotificationEventReceipt,
    )

    # Drive the same scheduled use case twice. The separately running process
    # publishes and consumes Kafka; this helper never materializes inbox rows.
    async with AsyncSessionLocal() as session:
        await scan_document_registry_expiries(session, datetime.now(UTC))
        await session.commit()
        await scan_document_registry_expiries(session, datetime.now(UTC))
        await session.commit()
    deadline = time.monotonic() + wait_seconds
    event_id = None
    while time.monotonic() < deadline:
        async with AsyncSessionLocal() as session:
            statement = select(NotificationEventOutbox).where(
                NotificationEventOutbox.entity_id == document_id,
                NotificationEventOutbox.event_type == "document_registry.expiring",
            )
            if version_id is not None:
                statement = statement.where(
                    NotificationEventOutbox.payload["payload"]["version_id"].astext == str(version_id),
                )
            events = list((await session.scalars(statement)).all())
            require(len(events) <= 1, "Duplicate expiry outbox occurrences")
            if events:
                event_id = events[0].event_id
                rows = list((await session.scalars(select(Notification).where(
                    Notification.event_id == event_id,
                ))).all())
                receipt = await session.get(NotificationEventReceipt, event_id)
                if receipt:
                    require({row.user_id for row in rows} == expected_user_ids,
                        "Expiry recipients differ from current document ACL")
                    require(len(rows) == len(expected_user_ids), "Duplicate personal expiry notification")
                    require(events[0].published_at is not None, "Outbox event was not published")
                    require(all(row.application_id is None for row in rows), "Document expiry linked to an application")
                    require(all(_registry_link_matches(row.action_url, document_id) for row in rows),
                        "Incorrect registry deep link")
                    email = await session.scalar(select(NotificationEmailDelivery.id).where(
                        NotificationEmailDelivery.event_id == event_id,
                    ).limit(1))
                    require(email is None, "In-app expiry unexpectedly created email deliveries")
                    return event_id
        await asyncio.sleep(0.25)
    raise AssertionError(f"Expiry did not reach inbox before timeout: {document_id}, {event_id}")


async def _await_kafka_consumed(event_id: UUID, wait_seconds: float = 40) -> None:
    """Observe the actual committed production group offset without joining it."""
    from runtime import guard, require

    settings = guard()
    from aiokafka import AIOKafkaConsumer
    from aiokafka.admin import AIOKafkaAdminClient

    from infrastructure.messaging.topics import NOTIFICATION_EVENTS

    consumer = AIOKafkaConsumer(
        NOTIFICATION_EVENTS, bootstrap_servers=settings.kafka_brokers,
        group_id=None, enable_auto_commit=False, auto_offset_reset="earliest",
    )
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_brokers)
    await consumer.start()
    await admin.start()
    deadline = time.monotonic() + wait_seconds
    position = None
    try:
        while position is None and time.monotonic() < deadline:
            batches = await consumer.getmany(timeout_ms=500, max_records=100)
            for partition, messages in batches.items():
                for message in messages:
                    if json.loads(message.value).get("event_id") == str(event_id):
                        position = (partition, message.offset)
                        break
        require(position is not None, "Expiry event did not reach real Kafka")
        partition, offset = position
        while time.monotonic() < deadline:
            offsets = await admin.list_consumer_group_offsets(
                settings.kafka_notification_consumer_group, partitions=[partition],
            )
            if partition in offsets and offsets[partition].offset > offset:
                return
            await asyncio.sleep(0.25)
        raise AssertionError("Production notification consumer did not acknowledge expiry")
    finally:
        await consumer.stop()
        await admin.close()


async def verify_reactivation(
    api: Any, document_id: UUID, expected_user_ids: set[UUID],
) -> None:
    from runtime import guard, require

    guard()
    from sqlalchemy import func, select

    from application.notifications.events import record_notification_event
    from domain.reference_document_expiry import expiry_occurrence_key
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.misc import Notification
    from infrastructure.models.notification_delivery import NotificationEventReceipt
    from infrastructure.repositories.notification_document_registry_repository import (
        get_document_context,
    )

    # The API created a due but deactivated version. Record its queued historical
    # fact to model deactivation winning the race before the worker acquires it.
    async with AsyncSessionLocal() as session:
        record = await get_document_context(session, document_id)
        require(record is not None and record["deactivated_at"] is not None,
            "Reactivation fixture must be a deactivated due document")
        expiry = record["valid_to"]
        event_id = await record_notification_event(
            session, event_type="document_registry.expiring", entity_type="reference_document",
            entity_id=document_id, aggregate_id=document_id, request_number=record["contract_number"],
            payload={"version_id": record["version_id"], "valid_to": expiry.isoformat(),
                "document_type": record["document_type"], "document_name": record["name"]},
            occurrence_key=expiry_occurrence_key(document_id, record["version_id"], expiry),
        )
        require(event_id is not None, "Reactivation fixture already has an expiry event")
        await session.commit()
    await _await_kafka_consumed(event_id)
    async with AsyncSessionLocal() as session:
        require(await session.get(NotificationEventReceipt, event_id) is None,
            "Suppressed expiry incorrectly completed its receipt")
        require(not await session.scalar(select(func.count()).select_from(Notification).where(
            Notification.event_id == event_id)), "Deactivated document produced an inbox item")
    url = f"/api/v1/document-registry/documents/{document_id}/activation"
    await api.request("admin", "PATCH", url, json={"active": True})
    received_event_id = await verify_notifications(document_id, expected_user_ids)
    require(received_event_id == event_id, "Reactivation changed expiry occurrence identity")
    async with AsyncSessionLocal() as session:
        first_receipt = await session.get(NotificationEventReceipt, event_id)
        processed_at = first_receipt.processed_at
        first_ids = set((await session.scalars(select(Notification.id).where(
            Notification.event_id == event_id))).all())
    await api.request("admin", "PATCH", url, json={"active": False})
    await api.request("admin", "PATCH", url, json={"active": True})
    await verify_notifications(document_id, expected_user_ids)
    async with AsyncSessionLocal() as session:
        receipt = await session.get(NotificationEventReceipt, event_id)
        require(receipt is not None and receipt.processed_at == processed_at,
            "Reactivation replaced a successful receipt")
        require(set((await session.scalars(select(Notification.id).where(
            Notification.event_id == event_id))).all()) == first_ids,
            "Reactivation recreated delivered inbox rows")


async def _expiry_context(document_id: UUID) -> dict[str, Any]:
    from runtime import require

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories.notification_document_registry_repository import (
        get_document_context,
    )

    async with AsyncSessionLocal() as session:
        record = await get_document_context(session, document_id)
        require(record is not None and record["valid_to"] is not None,
            "Expiry fixture must have a current version with an end date")
        return record


async def _queue_historical_expiry(record: dict[str, Any]) -> UUID:
    """Publish an authentic queued fact; delivery still goes through real Kafka."""
    from runtime import require

    from application.notifications.events import record_notification_event
    from domain.reference_document_expiry import expiry_occurrence_key
    from infrastructure.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        event_id = await record_notification_event(
            session, event_type="document_registry.expiring", entity_type="reference_document",
            entity_id=record["id"], aggregate_id=record["id"], request_number=record["contract_number"],
            payload={"version_id": record["version_id"], "valid_to": record["valid_to"].isoformat(),
                "document_type": record["document_type"], "document_name": record["name"]},
            occurrence_key=expiry_occurrence_key(record["id"], record["version_id"], record["valid_to"]),
        )
        require(event_id is not None, "Historical fixture already has an expiry event")
        await session.commit()
        return event_id


async def _event_state(event_id: UUID) -> dict[str, Any]:
    from runtime import require
    from sqlalchemy import select

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.misc import Notification
    from infrastructure.models.notification_delivery import (
        NotificationEmailDelivery,
        NotificationEventOutbox,
        NotificationEventReceipt,
    )

    async with AsyncSessionLocal() as session:
        event = await session.get(NotificationEventOutbox, event_id)
        require(event is not None, "Expiry outbox identity disappeared")
        receipt = await session.get(NotificationEventReceipt, event_id)
        rows = (await session.scalars(select(Notification).where(Notification.event_id == event_id))).all()
        emails = (await session.scalars(select(NotificationEmailDelivery.id).where(
            NotificationEmailDelivery.event_id == event_id))).all()
        require(not emails, "Version switch unexpectedly queued email")
        return {
            "published_at": event.published_at, "publish_attempts": event.publish_attempts,
            "processed_at": receipt.processed_at if receipt else None,
            "notifications": {row.id: (row.user_id, row.deleted_at) for row in rows},
        }


async def _require_suppressed(event_id: UUID) -> None:
    from runtime import require

    await _await_kafka_consumed(event_id)
    state = await _event_state(event_id)
    require(state["published_at"] is not None, "Suppression was not exercised through Kafka")
    require(state["processed_at"] is None and not state["notifications"],
        "Non-current or deactivated expiry completed delivery")


def _related_dealer(company_id: str) -> dict[str, Any]:
    return {"platform_ml": False, "leasing_company_ids": [],
        "dealer_company_ids": [company_id], "distributor_company_ids": []}


async def _edit_snapshot(
    api: Any, document: dict[str, Any], *, end_days: int,
    related: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from domain.reference_document_expiry import business_date

    current = document["current_version"]
    fields = ("platform_ml", "leasing_company_ids", "dealer_company_ids", "distributor_company_ids")
    metadata = {
        "expected_current_version_id": current["id"], "name": document["name"] + " edited",
        "related_companies": related if related is not None else {
            field: document["related_companies"][field] for field in fields},
        "valid_from": current["valid_from"],
        "valid_to": str(business_date(datetime.now(UTC)) + timedelta(days=end_days)),
        "retained_file_ids": [file["id"] for file in current["files"]],
    }
    # A multipart metadata part without a filename is a regular form field.
    # No binary files are uploaded: the new snapshot retains its current PDF.
    return await api.request("admin", "POST",
        f"/api/v1/document-registry/documents/{document['id']}/versions", expected=201,
        files=[("metadata", (None, json.dumps(metadata), "application/json"))])


async def _switch_snapshot(
    api: Any, document: dict[str, Any], target_version_id: str,
) -> dict[str, Any]:
    from runtime import require

    switched = await api.request("admin", "POST",
        f"/api/v1/document-registry/documents/{document['id']}/versions/{target_version_id}/activate",
        json={"expected_current_version_id": document["current_version"]["id"]})
    require(switched["current_version"]["id"] == target_version_id,
        "Version switch created a copy instead of restoring the selected version")
    require(switched["active"] == document["active"], "Version switch changed manual activation")
    return switched


async def _verify_inactive_restore(
    api: Any, document: dict[str, Any], other_version_id: str,
) -> None:
    from runtime import require

    from application.notifications.document_registry_expiry import (
        scan_document_registry_expiries,
    )
    from infrastructure.database import AsyncSessionLocal

    inactive = await api.request("admin", "PATCH",
        f"/api/v1/document-registry/documents/{document['id']}/activation", json={"active": False})
    due = await _edit_snapshot(api, inactive, end_days=20)
    event_id = await _queue_historical_expiry(await _expiry_context(UUID(due["id"])))
    await _require_suppressed(event_id)
    before = await _event_state(event_id)
    away = await _switch_snapshot(api, due, other_version_id)
    restored = await _switch_snapshot(api, away, due["current_version"]["id"])
    require(not restored["active"] and restored["status"] == "deactivated",
        "Restoring a version activated a manually disabled document")
    async with AsyncSessionLocal() as session:
        await scan_document_registry_expiries(session, datetime.now(UTC))
        await session.commit()
    require(await _event_state(event_id) == before,
        "Inactive version restore or scan requeued a suppressed expiry")


async def verify_version_switches(api: Any, state: dict[str, Any]) -> None:
    """HTTP snapshots plus real Kafka prove restore and recipient lifecycle."""
    from runtime import guard, pdf, progress, require

    guard()
    from domain.reference_document_expiry import business_date

    today = business_date(datetime.now(UTC))
    prefix = "22296-version-expiry-" + uuid4().hex[:8]
    related = _related_dealer(state["companies"]["dealer"]["company_id"])
    document = await api.request("admin", "POST", "/api/v1/document-registry/documents", expected=201,
        data={"metadata": json.dumps({"document_type": "contract", "contract_number": prefix,
            "name": prefix, "valid_from": str(today - timedelta(days=10)),
            "valid_to": str(today + timedelta(days=90)),
            "participants": {"mark_id": state["catalog"]["mark_id"]}, "related_companies": related})},
        files=[("files", ("version-expiry.pdf", pdf(), "application/pdf"))])
    document_id = UUID(document["id"])
    activation_url = f"/api/v1/document-registry/documents/{document_id}/activation"
    inactive = await api.request("admin", "PATCH", activation_url, json={"active": False})
    due = await _edit_snapshot(api, inactive, end_days=10)
    historical = await _expiry_context(document_id)
    far = await _edit_snapshot(api, due, end_days=90)
    active = await api.request("admin", "PATCH", activation_url, json={"active": True})
    event_id = await _queue_historical_expiry(historical)
    await _require_suppressed(event_id)
    restored = await _switch_snapshot(api, active, due["current_version"]["id"])
    expected = {UUID(state["users"]["dealer"]["id"])}
    delivered = await verify_notifications(document_id, expected, version_id=UUID(due["current_version"]["id"]))
    require(delivered == event_id, "Restoring a suppressed version changed event identity")
    first_delivery = await _event_state(event_id)
    require(restored["name"] == due["name"] and restored["related_companies"] == due["related_companies"],
        "Restored reminder context differs from its historical snapshot")

    changed = await _edit_snapshot(api, restored, end_days=10,
        related=_related_dealer(state["companies"]["dealer2"]["company_id"]))
    changed_event = await verify_notifications(document_id, {UUID(state["users"]["outsider"]["id"])},
        version_id=UUID(changed["current_version"]["id"]))
    require(changed_event != event_id, "Metadata edit reused the prior version's reminder")
    await api.request("dealer", "GET", f"/api/v1/document-registry/documents/{document_id}", expected=404)
    await api.request("outsider", "GET", f"/api/v1/document-registry/documents/{document_id}")
    restored = await _switch_snapshot(api, changed, due["current_version"]["id"])
    await verify_notifications(document_id, expected, version_id=UUID(due["current_version"]["id"]))
    require(await _event_state(event_id) == first_delivery,
        "Restoring a delivered version republished its event or replaced its receipt/inbox")
    await api.request("outsider", "GET", f"/api/v1/document-registry/documents/{document_id}", expected=404)
    await api.request("dealer", "GET", f"/api/v1/document-registry/documents/{document_id}")
    await _verify_inactive_restore(api, restored, far["current_version"]["id"])
    progress("registry_version_notifications_passed", document_id=document_id,
        restored_event_id=event_id, changed_related_event_id=changed_event)


async def verify_versions_from_runtime() -> None:
    from runtime import API, ROOT, guard

    guard()
    state = json.loads(await asyncio.to_thread((ROOT / "state.secret.json").read_text))
    await verify_version_switches(API(state), state)


async def verify_cleanup(referenced_key: str) -> None:
    from runtime import guard, require

    settings = guard()
    import aioboto3

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories.document_registry_cleanup_repository import (
        lock_file_key,
    )
    from infrastructure.services.document_registry_cleanup import (
        cleanup_orphaned_registry_files,
    )

    orphan = f"document-registry/{uuid4()}/{uuid4()}/{uuid4()}"
    busy = f"document-registry/{uuid4()}/{uuid4()}/{uuid4()}"
    foreign = f"documents/{uuid4()}"
    malformed = f"document-registry/not-a-registry-key/{uuid4()}"
    async with aioboto3.Session().client(
        "s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    ) as s3:
        original = await s3.head_object(Bucket=settings.s3_bucket, Key=referenced_key)
        for key in (orphan, busy, foreign, malformed):
            await s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=b"e2e cleanup fixture")
        async with AsyncSessionLocal() as session:
            result = await cleanup_orphaned_registry_files(session)
            await session.commit()
            require(result["deleted"] == 0, "Cleanup removed a fresh upload")
        async with AsyncSessionLocal() as uploader:
            await lock_file_key(uploader, busy)
            async with AsyncSessionLocal() as session:
                result = await cleanup_orphaned_registry_files(session, before=datetime.now(UTC) + timedelta(seconds=10))
                await session.commit()
            require(result["deleted"] == 1, "Aged orphan was not removed or protected file was removed")
            await s3.head_object(Bucket=settings.s3_bucket, Key=busy)
            await uploader.commit()
        current = await s3.head_object(Bucket=settings.s3_bucket, Key=referenced_key)
        require(current["ETag"] == original["ETag"], "Cleanup changed a referenced registry object")
        for key in (foreign, malformed):
            await s3.head_object(Bucket=settings.s3_bucket, Key=key)
        async with AsyncSessionLocal() as session:
            result = await cleanup_orphaned_registry_files(session, before=datetime.now(UTC) + timedelta(seconds=10))
            await session.commit()
            require(result["deleted"] == 1, "Uncommitted upload lock was not released")
        for key in (foreign, malformed):
            await s3.delete_object(Bucket=settings.s3_bucket, Key=key)


async def run() -> None:
    from runtime import guard, require

    settings = guard()
    require(settings.kafka_brokers == "redpanda:9092", "Refusing non-fixture Kafka")
    require(settings.redis_url == "redis://redis:6379/0", "Refusing non-fixture Redis")
    require(settings.kafka_notification_consumer_group == "documentregistry22296-notifications",
        "Refusing non-fixture consumer group")

    import application.notification_events  # noqa: F401
    from application.notifications.document_registry_expiry import (
        scan_document_registry_expiries,
    )
    from application.notifications.publisher import publish_outbox_batch
    from infrastructure.database import AsyncSessionLocal, engine
    from infrastructure.logging import configure_logging, log_event
    from infrastructure.messaging.admin import ensure_topics
    from infrastructure.messaging.broker import start_broker, stop_broker

    configure_logging(service_name="carcraft-event-worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, stop.set)
    await asyncio.to_thread(READY.unlink, missing_ok=True)
    await ensure_topics()
    await start_broker()
    log_event("info", "document_registry.e2e.notifications.started",
        "Isolated document expiry scheduler, publisher and consumer started")
    try:
        while not stop.is_set():
            async with AsyncSessionLocal() as session:
                await scan_document_registry_expiries(session, datetime.now(UTC))
                await session.commit()
            await publish_outbox_batch()
            await asyncio.to_thread(READY.touch)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=0.5)
    finally:
        await asyncio.to_thread(READY.unlink, missing_ok=True)
        await stop_broker()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "healthcheck", "verify-versions"], default="run", nargs="?")
    args = parser.parse_args()
    if args.action == "healthcheck":
        raise SystemExit(0 if healthy() else 1)
    asyncio.run(verify_versions_from_runtime() if args.action == "verify-versions" else run())
