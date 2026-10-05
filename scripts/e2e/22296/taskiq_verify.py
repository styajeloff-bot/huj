"""Isolated production Taskiq expiry E2E; launched only by taskiq_run.py."""
# ruff: noqa: E402
# Bootstrap must validate fixture resources before production imports.

import asyncio
import json
import time
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
import taskiq_bootstrap
from runtime import ROOT, guard, pdf, require, progress

settings = guard()
CONFIG = taskiq_bootstrap.CONFIG
PREFIX = "22296-audit-taskiq"
state = json.loads((ROOT / "state.secret.json").read_text())
require(state["database"] == CONFIG["db"], "Wrong isolated fixture state")


async def http(role, method, path, expected=200, **kwargs):
    import httpx

    actor = state["users"][role]
    async with httpx.AsyncClient(
        base_url="http://localhost:3002",
        trust_env=False,
        timeout=30,
        cookies={"accessToken": actor["access_token"], "csrfToken": actor["csrf"]},
        headers={"Origin": "http://localhost:18296", "X-CSRF-Token": actor["csrf"]},
    ) as client:
        response = await client.request(method, path, **kwargs)
    require(
        response.status_code == expected,
        f"{method} {path}: HTTP{response.status_code} {response.text[:200]}",
    )
    return response.json() if response.content else None


async def schedules():
    import application.tasks  # noqa: F401 - register the actual decorated tasks
    from infrastructure.taskiq_scheduler import scheduler
    from taskiq.schedule_sources import LabelScheduleSource

    source = next(
        item for item in scheduler.sources if isinstance(item, LabelScheduleSource)
    )
    await source.startup()
    matches = [
        task
        for task in await source.get_schedules()
        if task.task_name == "notifications.scan_document_registry_expiries"
    ]
    require(
        len(matches) == 1, "Expiry task missing or duplicated in LabelScheduleSource"
    )
    require(matches[0].cron == "0 * * * *", "Wrong expiry cron")
    progress(
        "taskiq_schedule_registered",
        source=type(source).__name__,
        task=matches[0].task_name,
        cron=matches[0].cron,
        matching_schedules=len(matches),
        wall_clock_trigger_tested=False,
    )
    await source.shutdown()


async def add_colleague():
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.users import User, UserCompany

    identifier = uuid4()
    company = UUID(state["companies"]["dealer"]["company_id"])
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        existing = await session.scalar(
            select(User.id).where(User.name == PREFIX + " colleague")
        )
        if existing:
            return existing
        session.add(
            User(
                id=identifier,
                name=PREFIX + " colleague",
                phone="+70002229699",
                email="audit-colleague@documentregistry22296.test",
                role="dealer",
                company_id=company,
                is_active=True,
                phone_verified=True,
                email_verified=True,
            )
        )
        await session.flush()
        session.add(
            UserCompany(
                user_id=identifier,
                company_id=company,
                sub_role="employee",
                can_view_applications=False,
                can_create_applications=False,
            )
        )
        await session.commit()
    return identifier


async def counts(document_id):
    from sqlalchemy import select, func
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.misc import Notification
    from infrastructure.models.notification_delivery import (
        NotificationEventOutbox,
        NotificationEventReceipt,
        NotificationEmailDelivery,
    )

    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(NotificationEventOutbox).where(
                        NotificationEventOutbox.entity_id == UUID(document_id),
                        NotificationEventOutbox.event_type
                        == "document_registry.expiring",
                    )
                )
            ).all()
        )
        event_ids = [event.event_id for event in events]
        inbox = (
            list(
                (
                    await session.scalars(
                        select(Notification).where(Notification.event_id.in_(event_ids))
                    )
                ).all()
            )
            if event_ids
            else []
        )
        receipts = (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(NotificationEventReceipt)
                    .where(NotificationEventReceipt.event_id.in_(event_ids))
                )
            )
            if event_ids
            else 0
        )
        emails = (
            int(
                await session.scalar(
                    select(func.count())
                    .select_from(NotificationEmailDelivery)
                    .where(NotificationEmailDelivery.event_id.in_(event_ids))
                )
            )
            if event_ids
            else 0
        )
        return {
            "events": events,
            "inbox": inbox,
            "receipts": receipts,
            "emails": emails,
        }


async def enqueue(stage):
    from application.tasks.notifications import scan_document_registry_expiries

    task = await scan_document_registry_expiries.kiq()
    result = await task.wait_result(timeout=30)
    require(not result.is_err, "Real Taskiq worker failed " + stage)
    progress(
        "taskiq_task_completed",
        phase=stage,
        task_id=task.task_id,
        is_error=result.is_err,
        execution_seconds=result.execution_time,
        transport="private real Redis + production CLI worker",
    )
    return task.task_id


async def kafka_evidence(event_id):
    from aiokafka import AIOKafkaConsumer
    from aiokafka.admin import AIOKafkaAdminClient
    from infrastructure.messaging.topics import NOTIFICATION_EVENTS

    consumer = AIOKafkaConsumer(
        NOTIFICATION_EVENTS,
        bootstrap_servers=settings.kafka_brokers,
        group_id=None,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_brokers)
    await consumer.start()
    await admin.start()
    deadline = time.monotonic() + 20
    found = None
    try:
        while found is None and time.monotonic() < deadline:
            for partition, messages in (
                await consumer.getmany(timeout_ms=200, max_records=30)
            ).items():
                for message in messages:
                    if json.loads(message.value).get("event_id") == str(event_id):
                        found = (partition, message.offset)
                        break
        require(found is not None, "Event absent from real private Kafka topic")
        partition, offset = found
        committed = -1
        while time.monotonic() < deadline:
            offsets = await admin.list_consumer_group_offsets(
                settings.kafka_notification_consumer_group, partitions=[partition]
            )
            if partition in offsets:
                committed = offsets[partition].offset
            if committed > offset:
                break
            await asyncio.sleep(0.1)
        require(
            committed > offset, "Production consumer did not acknowledge Kafka event"
        )
        return {
            "topic": NOTIFICATION_EVENTS,
            "partition": partition.partition,
            "event_offset": offset,
            "consumer_committed_offset": committed,
        }
    finally:
        await consumer.stop()
        await admin.close()


async def main():
    from infrastructure.taskiq_broker import broker
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.document_registry import (
        reference_documents,
        reference_document_versions,
    )
    from sqlalchemy import select, update

    await schedules()
    colleague = await add_colleague()
    day = datetime.now(ZoneInfo("Europe/Moscow")).date()
    tag = uuid4().hex[:8]
    metadata = {
        "document_type": "contract",
        "contract_number": PREFIX + "-" + tag,
        "name": PREFIX + " production expiry " + tag,
        "valid_from": str(day),
        "valid_to": str(day + timedelta(days=31)),
        "participants": {
            "platform_ml": True,
            "leasing_company_ids": [
                state["companies"]["leasing"]["leasing_company_id"]
            ],
            "dealer_company_ids": [state["companies"]["dealer"]["company_id"]],
        },
        "related_companies": {
            "platform_ml": False,
            "dealer_company_ids": [state["companies"]["dealer2"]["company_id"]],
            "distributor_company_ids": [
                state["companies"]["distributor"]["company_id"]
            ],
        },
    }
    doc = await http(
        "admin",
        "POST",
        "/api/v1/document-registry/documents",
        expected=201,
        data={"metadata": json.dumps(metadata)},
        files=[("files", (PREFIX + ".pdf", pdf(), "application/pdf"))],
    )
    document_id = doc["id"]
    version_id = doc["current_version"]["id"]
    from infrastructure.models.users import User

    async with AsyncSessionLocal() as session:
        employees = set(
            (
                await session.scalars(
                    select(User.id).where(
                        User.role == "carcraft_employee",
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                    )
                )
            ).all()
        )
    expected = (
        {
            UUID(state["users"][alias]["id"])
            for alias in ("dealer", "leasing", "distributor", "outsider")
        }
        | {colleague}
        | employees
    )
    require(len(expected) == 9, "Isolated fixture must provide exactly nine recipients")
    await broker.startup()
    try:
        initial = await counts(document_id)
        require(not initial["events"], "Unexpected expiry event at +31 on creation")
        tasks = [await enqueue("end_plus_31")]
        outside = await counts(document_id)
        require(not outside["events"], "Production scan notified one day too early")
        progress(
            "taskiq_plus31_no_event",
            document_id=document_id,
            outbox_count=0,
            inbox_count=0,
        )
        # Controlled date transition affects only this isolated fixture version.
        async with AsyncSessionLocal() as session:
            number = await session.scalar(
                select(reference_documents.c.contract_number).where(
                    reference_documents.c.id == UUID(document_id)
                )
            )
            require(
                number == metadata["contract_number"] and number.startswith(PREFIX),
                "Refusing another fixture",
            )
            result = await session.execute(
                update(reference_document_versions)
                .where(
                    reference_document_versions.c.id == UUID(version_id),
                    reference_document_versions.c.document_id == UUID(document_id),
                )
                .values(valid_to=day + timedelta(days=30))
            )
            require(
                result.rowcount == 1,
                "Date advance did not affect exactly one owned version",
            )
            await session.commit()
        no_scanner = await counts(document_id)
        require(not no_scanner["events"], "Another scanner raced the isolated task")
        progress(
            "taskiq_controlled_fixture_date_transition",
            from_end_days=31,
            to_end_days=30,
            rows_updated=1,
            outbox_before_enqueue=0,
            production_clock_mocked=False,
        )
        tasks.append(await enqueue("end_plus_30"))
        deadline = time.monotonic() + 25
        observed = None
        while time.monotonic() < deadline:
            observed = await counts(document_id)
            if observed["receipts"] and len(observed["inbox"]) == len(expected):
                break
            await asyncio.sleep(0.1)
        require(
            observed is not None and len(observed["events"]) == 1,
            "Expected one expiry outbox occurrence",
        )
        event = observed["events"][0]
        require(event.published_at is not None, "Task failed to publish outbox")
        require(observed["receipts"] == 1, "Expected real Kafka consumer receipt")
        require(
            {row.user_id for row in observed["inbox"]} == expected,
            "Recipient set mismatch",
        )
        require(
            len(observed["inbox"]) == len(expected),
            "Duplicate or missing personal inbox row",
        )
        require(observed["emails"] == 0, "In-app event created email intent")
        require(
            all(
                str(document_id) in (row.action_url or "") for row in observed["inbox"]
            ),
            "Wrong inbox document links",
        )
        first_inbox_ids = {row.id for row in observed["inbox"]}
        kafka = await kafka_evidence(event.event_id)
        progress(
            "taskiq_kafka_inbox_verified",
            document_id=document_id,
            event_id=event.event_id,
            outbox_count=1,
            outbox_published=True,
            receipt_count=1,
            inbox_count=len(expected),
            expected_recipients=len(expected),
            same_company_second_user_received=any(
                row.user_id == colleague for row in observed["inbox"]
            ),
            second_user_can_view_applications=False,
            platform_admin_recipients=len(employees),
            email_delivery_count=0,
            **kafka,
        )
        tasks.append(await enqueue("repeat_same_occurrence"))
        repeated = await counts(document_id)
        require(
            len(repeated["events"]) == 1
            and repeated["events"][0].event_id == event.event_id,
            "Repeated scan duplicated outbox",
        )
        require(repeated["receipts"] == 1, "Repeated scan duplicated receipt")
        require(repeated["emails"] == 0, "Repeated scan created email intent")
        require(
            {row.id for row in repeated["inbox"]} == first_inbox_ids,
            "Repeated scan duplicated/replaced inbox rows",
        )
        progress(
            "taskiq_repeat_idempotent",
            outbox_count=1,
            receipt_count=1,
            inbox_count=len(expected),
            inbox_ids_unchanged=True,
            task_ids=tasks,
        )
        progress(
            "taskiq_audit_complete",
            database=CONFIG["db"],
            bucket=CONFIG["bucket"],
            worker_startup="production original callbacks",
            notification_handler="application.notification_events.consume_notification_event",
            hourly_wall_clock_trigger_tested=False,
            manual_enqueue=True,
        )
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
