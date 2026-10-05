#!/usr/bin/env python3
"""22242 real scheduled-worker acceptance. Mount beside runtime.py in /runtime.

Healthy: seed, rollback (optional), delete, check, replay, check.
Outage: seed --scenario s3|kafka while healthy; coordinator stops the chosen
service; delete; expect-failure --kind file|event; coordinator restores service;
retry; check. Every command that does I/O requires --execute.
No Docker, direct worker invocation, Kafka publishing, or ClickHouse writes.
Only dedicated UUID5 vehicles, object keys and their delivery rows are mutated.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import runtime as rt

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4aUAAAAASUVORK5CYII=")
TABLES = {"file": ("object_storage_deletion_jobs", "entity_id"),
          "event": ("vehicle_deletion_outbox", "vehicle_id")}


def fixture(scenario: str) -> dict:
    name = f"api/delivery/{scenario}"
    return {"marker": rt.MARKER, "scenario": scenario, "name": name,
            "vehicle": str(rt.identifier(f"vehicle/{name}")),
            "keeper": str(rt.identifier(f"delivery/{scenario}/keeper")),
            "warehouse": str(rt.identifier(f"delivery/{scenario}/warehouse")),
            "keys": {kind: f"vehicles/task22242-delivery-{scenario}-{rt.identifier(f'delivery/{scenario}/{kind}')}.png"
                     for kind in ("owned", "shared", "missing", "sentinel")}}


def path_for(scenario: str) -> Path:
    return Path(f"/runtime/delivery-{scenario}.json")


def save(state: dict, *, create: bool = False) -> None:
    fd = os.open(path_for(state["scenario"]), os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW |
                 (os.O_EXCL if create else os.O_TRUNC), 0o600)
    with os.fdopen(fd, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(state, output, indent=2, default=str)


def load(scenario: str) -> dict:
    fd = os.open(path_for(scenario), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        state = json.load(source)
    rt.require(all(state.get(key) == value for key, value in fixture(scenario).items()), "Wrong delivery fixture identity")
    rt.require(state.get("ready") is True, "Incomplete delivery seed; inspect isolated state")
    return state


async def rows(state: dict) -> dict:
    from sqlalchemy import column, literal_column, select, table as sql_table, text

    from infrastructure.database import AsyncSessionLocal

    result = {}
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        for kind, (table, key) in TABLES.items():
            query = (select(literal_column("*")).select_from(sql_table(table))
                     .where(column(key) == UUID(state["vehicle"])).order_by(column("id")))
            result[kind] = [dict(row) for row in (await session.execute(query)).mappings()]
        result["vehicles"] = [dict(row) for row in (await session.execute(text(
            "SELECT id, images FROM vehicles WHERE id IN (:target, :keeper) ORDER BY id"),
            {"target": UUID(state["vehicle"]), "keeper": UUID(state["keeper"])})).mappings()]
    return result


def receipts(state: dict, current: dict) -> None:
    rt.require({str(row["id"]) for row in current["vehicles"]} == {state["keeper"]}, "Deleted vehicle restored or keeper lost")
    rt.require(len(current["file"]) == 3 and {row["object_key"] for row in current["file"]}
               == {state["keys"][key] for key in ("owned", "shared", "missing")}, "Wrong atomic file job set")
    rt.require(len(current["event"]) == 1, "Missing/duplicate durable deletion event")
    payload = current["event"][0]["payload"]
    rt.require(payload["vehicle_id"] == state["vehicle"] and payload["_deleted"] is True, "Wrong durable tombstone")
    if "payload" in state:
        rt.require(payload == state["payload"], "Retry changed the original event payload/version")
        rt.require({str(row["id"]) for kind in TABLES for row in current[kind]} == set(state["job_ids"]),
                   "Delivery job identities changed")


async def objects(state: dict, *, deleted: bool) -> None:
    from infrastructure.services.object_storage import get_object_storage

    storage = get_object_storage()
    for kind, key in state["keys"].items():
        value = await asyncio.wait_for(storage.get(key), timeout=15)
        absent = kind == "missing" or (kind == "owned" and deleted)
        rt.require((value is None) if absent else (value is not None and value.data == PNG),
                   f"Unexpected S3 object bytes/existence: {kind}")


async def seed(scenario: str) -> None:
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.vehicles import Vehicle, VehicleWarehouse, Warehouse
    from infrastructure.services.object_storage import get_object_storage

    state = fixture(scenario)
    save(state, create=True)  # Never overwrite another run or partial seed.
    storage = get_object_storage()
    for key in state["keys"].values():
        rt.require(not await asyncio.wait_for(storage.exists(key), timeout=15), "Delivery object already exists")
    for kind in ("owned", "shared", "sentinel"):
        await asyncio.wait_for(storage.put(state["keys"][kind], PNG, "image/png"), timeout=15)
    shared = {"filename": state["keys"]["shared"].removeprefix("vehicles/"),
              "url": storage.public_url(state["keys"]["shared"])}
    async with AsyncSessionLocal() as session, session.begin():
        await rt.insert(session, Warehouse, id=UUID(state["warehouse"]), brand="22242 delivery",
                        address=f"22242 delivery {scenario}", company_id=rt.identifier("company/dealer"),
                        dealer_id=rt.identifier("company/dealer"), status="active")
        for key in ("vehicle", "keeper"):
            vehicle_id = UUID(state[key])
            images = ([{"filename": state["keys"]["owned"].removeprefix("vehicles/"),
                        "url": storage.public_url(state["keys"]["owned"])},
                       state["keys"]["shared"], state["keys"]["missing"]] if key == "vehicle" else [shared])
            await rt.insert(session, Vehicle, id=vehicle_id, vin="D22242" + vehicle_id.hex[:11].upper(),
                            dealer_id=rt.identifier("company/dealer"), mark_id=str(rt.identifier("mark")),
                            model_id=str(rt.identifier("model")), year=2026, base_price=rt.PRICE,
                            images=images, is_available=True, status="available")
            await rt.insert(session, VehicleWarehouse, id=rt.identifier(f"delivery/{scenario}/binding/{key}"),
                            vehicle_id=vehicle_id, warehouse_id=UUID(state["warehouse"]))
    await objects(state, deleted=False)
    state["ready"] = True
    save(state)
    rt.check(f"delivery {scenario}: dedicated vehicle/keeper; owned/shared/sentinel PNG uploaded; missing key absent")


async def http_delete(state: dict, auth: dict, expected: int = 200) -> None:
    import httpx

    auth["vehicles"][state["name"]] = {"id": state["vehicle"]}
    rt.require(auth["users"][rt.ADMIN]["access_token_expires"] > time.time() + 90, "Run runtime.py auth --execute")
    async with httpx.AsyncClient(base_url=rt.API_URL, timeout=60, trust_env=False, follow_redirects=False) as client:
        api = rt.API(client, auth)
        result = await api.request("DELETE", api.vehicle(state["name"]), expected, body={"confirmation": "УДАЛИТЬ"})
        if expected == 200:
            rt.require(result["deleted"] is True and result["vehicle_id"] == state["vehicle"], "Wrong HTTP deletion result")


async def delete(state: dict, auth: dict) -> None:
    before = await rows(state)
    rt.require(not before["file"] and not before["event"] and len(before["vehicles"]) == 2,
               "Expected untouched delivery fixture before DELETE")
    await http_delete(state, auth)
    current = await rows(state)
    receipts(state, current)
    state.update(payload=current["event"][0]["payload"],
                 job_ids=[str(row["id"]) for kind in TABLES for row in current[kind]])
    save(state)
    rt.check("HTTP committed: vehicle absent + exactly three file jobs and one durable event; keeper present")


async def rollback(state: dict, auth: dict) -> None:
    from sqlalchemy import text

    from infrastructure.database import AsyncSessionLocal

    before = await rows(state)
    rt.require(not before["file"] and not before["event"] and len(before["vehicles"]) == 2, "Rollback needs fresh seed")
    function = "task22242_delivery_rollback_" + state["scenario"]
    # Deferred commit failure exercises the real router and queue insertion.
    async with AsyncSessionLocal() as session, session.begin():
        await session.execute(text(f"""
            CREATE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.id = '{UUID(state['vehicle'])}'::uuid THEN
                RAISE EXCEPTION 'task22242 delivery rollback' USING ERRCODE = 'P0001';
              END IF;
              RETURN OLD;
            END $$
        """))
        await session.execute(text(f"""
            CREATE CONSTRAINT TRIGGER {function} AFTER DELETE ON public.vehicles
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.{function}()
        """))
    try:
        await http_delete(state, auth, expected=500)
        rt.require(await rows(state) == before, "Rollback leaked DB changes/delivery receipts")
        await objects(state, deleted=False)
        rt.check("real HTTP commit failure rolled back jobs/event/vehicle; actual S3 files preserved")
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(text(f"DROP TRIGGER {function} ON public.vehicles"))
            await session.execute(text(f"DROP FUNCTION public.{function}()"))


async def kafka_receipt(state: dict, settings) -> dict | None:
    """Read the real topic with NO consumer group/offset commits or publish calls."""
    from aiokafka import AIOKafkaConsumer

    from infrastructure.messaging.topics import VEHICLE_CHANGED

    # Subscribe before start: topics() returns a separate metadata snapshot and
    # does not populate an unsubscribed consumer's partitions_for_topic cache.
    consumer = AIOKafkaConsumer(VEHICLE_CHANGED, bootstrap_servers=settings.kafka_brokers, group_id=None,
                               enable_auto_commit=False, request_timeout_ms=10000,
                               consumer_timeout_ms=1000, auto_offset_reset="earliest")
    try:
        await asyncio.wait_for(consumer.start(), timeout=15)
        targets = sorted(consumer.assignment(), key=lambda partition: partition.partition)
        if not targets:
            print("WAIT Kafka: subscribed topic has no assigned partitions", flush=True)
            return None
        await consumer.seek_to_beginning(*targets)
        ends = await consumer.end_offsets(targets)
        print("PHASE Kafka: scanning " + json.dumps({str(partition.partition): end for partition, end in ends.items()}), flush=True)
        found = None
        scanned = 0
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            batches = await consumer.getmany(timeout_ms=1000, max_records=500)
            for partition, batch in batches.items():
                for message in batch:
                    scanned += 1
                    try:
                        payload = json.loads(message.value)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(payload, dict) or payload.get("vehicle_id") != state["vehicle"]:
                        continue
                    rt.require(payload == state["payload"] and message.key == state["vehicle"].encode(),
                               "Kafka tombstone payload/key differs from outbox")
                    previous = state.get("kafka")
                    if previous and state.get("replaying") and partition.partition == previous["partition"]:
                        if message.offset <= previous["offset"]:
                            continue
                    found = {"topic": VEHICLE_CHANGED, "partition": partition.partition, "offset": message.offset}
            if all([await consumer.position(partition) >= ends[partition] for partition in targets]):
                print(f"{'FOUND' if found else 'WAIT'} Kafka: scanned={scanned}, "
                      + (f"partition={found['partition']} offset={found['offset']}" if found else "target tombstone absent in captured offsets"), flush=True)
                return found
        print(f"{'FOUND' if found else 'WAIT'} Kafka: scan deadline reached after {scanned} records", flush=True)
        return found
    finally:
        await asyncio.wait_for(consumer.stop(), timeout=10)


async def clickhouse_receipt(state: dict, settings) -> bool:
    # Use bounded async HTTP SELECT; no synchronous client/thread can outlive
    # the timeout and no credentials or DSNs are printed.
    import httpx

    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.post("http://clickhouse:8123/", auth=(settings.clickhouse_user, settings.clickhouse_password),
                                     # readonly=1 disallows changing settings. Keep
                                     # the request bounded by httpx, not an extra
                                     # per-query max_execution_time override.
                                     params={"database": settings.clickhouse_db, "readonly": "1",
                                             "param_id": state["vehicle"]}, content="""
            SELECT toString(vehicle_id) AS id, _deleted,
                   toUnixTimestamp64Milli(updated_at) AS version
            FROM dwh_vehicles FINAL WHERE vehicle_id = {id:UUID} FORMAT JSONEachRow
        """)
        if response.is_error:
            body = response.text
            for secret in (settings.clickhouse_password, settings.db_password, settings.s3_secret_access_key):
                if secret:
                    body = body.replace(secret, "[redacted]")
            body = re.sub(r"(?i)(password|token|secret|authorization)\s*[:=]\s*[^\s,;]+",
                          r"\1=[redacted]", body)
            body = " ".join(body.split())[:480]
            print(f"WAIT ClickHouse HTTP {response.status_code}: {body}", flush=True)
        response.raise_for_status()
        values = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    if not values:
        return False
    expected = int(datetime.fromisoformat(state["payload"]["updated_at"]).timestamp() * 1000)
    rt.require(len(values) == 1 and values[0]["id"] == state["vehicle"]
               and values[0]["_deleted"] == 1 and int(values[0]["version"]) == expected,
               "ClickHouse FINAL tombstone/version mismatch")
    return True


async def wait_for_delivery(state: dict, settings, timeout: int, *, failure_kind: str | None = None) -> None:
    deadline = time.monotonic() + timeout
    previous = None
    kafka = None
    while time.monotonic() < deadline:
        current = await rows(state)
        receipts(state, current)
        brief = {kind: [(str(row["id"]), row["status"], row["attempts"]) for row in current[kind]] for kind in TABLES}
        if brief != previous:
            print(json.dumps({"queues": brief}), flush=True)
            previous = brief
        if failure_kind:
            targets = [row for row in current[failure_kind] if failure_kind == "event"
                       or row["object_key"] == state["keys"]["owned"]]
            if targets and all(row["status"] == "failed" and row["attempts"] > 0 and row["last_error"]
                               and row["scheduled_at"] is not None for row in targets):
                state["failed"] = {str(row["id"]): row["attempts"] for row in targets}
                save(state)
                rt.check(f"real {failure_kind} worker failure persisted with diagnostics/retry schedule; vehicle remains deleted")
                return
        elif all(row["status"] == "completed" and row["attempts"] > 0 for kind in TABLES for row in current[kind]):
            for row in [*current["file"], *current["event"]]:
                minimum = state.get("attempts_before", {}).get(str(row["id"]), 0)
                rt.require(row["attempts"] > minimum, "Scheduled worker did not perform the requested retry/replay")
                rt.require(row["processed_at"] is not None and row["last_error"] is None, "Invalid completed job state")
            print("PHASE S3: checking owned/missing/shared/sentinel", flush=True)
            await objects(state, deleted=True)
            print("FOUND S3: owned/missing absent; shared/sentinel exact bytes retained", flush=True)
            try:
                print("PHASE Kafka: looking for exact outbox payload/key" if not kafka else "FOUND Kafka: receipt already observed", flush=True)
                kafka = kafka or await kafka_receipt(state, settings)
                print("PHASE ClickHouse: SELECT FINAL tombstone/version", flush=True)
                ch = await clickhouse_receipt(state, settings)
                print("FOUND ClickHouse: _deleted=1 and exact version" if ch else "WAIT ClickHouse: target UUID not present yet", flush=True)
            except rt.AcceptanceFailure:
                raise
            except Exception as exc:
                print(f"WAIT analytical delivery: {type(exc).__name__}", flush=True)
                ch = False
            if kafka and ch:
                state.update(kafka=kafka, checked_at=datetime.now(UTC).isoformat(), replaying=False)
                save(state)
                rt.check("cron delivery completed: owned/missing absent, shared/sentinel exact bytes retained")
                rt.check(f"Kafka {kafka['topic']} partition={kafka['partition']} offset={kafka['offset']} -> event-worker -> dwh_vehicles FINAL _deleted=1")
                return
        await asyncio.sleep(3)
    raise rt.AcceptanceFailure("Bounded delivery wait expired; inspect task worker/scheduler/event-worker logs; rerun check safely")


async def reschedule(state: dict, *, replay: bool) -> None:
    from sqlalchemy import text

    from infrastructure.database import AsyncSessionLocal

    current = await rows(state)
    receipts(state, current)
    selected = [row for kind in TABLES for row in current[kind]
                if row["status"] == ("completed" if replay else "failed")]
    rt.require(selected, "No eligible completed/failed fixture jobs")
    if replay:
        rt.require(state.get("checked_at") and len(selected) == 4, "Replay requires a successful full check first")
    else:
        rt.require(state.get("failed"), "Run expect-failure before retry")
    state["attempts_before"] = {str(row["id"]): row["attempts"] for row in selected}
    async with AsyncSessionLocal() as session, session.begin():
        for kind, (table, key) in TABLES.items():
            ids = [row["id"] for row in current[kind] if row in selected]
            if kind == "file":
                rt.require(all(row["attempts"] < 8 for row in current[kind] if row in selected), "File retry limit exhausted")
            changed = (await session.execute(text(f"""
                UPDATE {table} SET status = 'pending', scheduled_at = now(),
                    processed_at = NULL, processing_started_at = NULL, last_error = NULL
                WHERE {key} = :target AND id = ANY(CAST(:ids AS uuid[])) AND status = :previous
                RETURNING id
            """), {"target": UUID(state["vehicle"]), "ids": ids,
                    "previous": "completed" if replay else "failed"})).scalars().all()
            rt.require(set(changed) == set(ids), "Worker raced rescheduling; transaction rolled back, rerun check")
    state["replaying"] = replay
    save(state)
    rt.check(f"{'replay' if replay else 'retry'}: rescheduled only {len(selected)} exact fixture jobs, attempts/payload retained; cron worker will execute")


async def run(args) -> None:
    settings = rt.guard(args)
    auth = rt.load_state()
    rt.require(settings.clickhouse_host == "clickhouse" and settings.clickhouse_port == 8123,
               "ClickHouse must be the isolated clickhouse:8123 service")
    rt.require(all(urlsplit("//" + broker).hostname == "redpanda" for broker in settings.kafka_brokers.split(",")),
               "Kafka must be the isolated redpanda service")
    if args.mode == "seed":
        await seed(args.scenario)
        return
    state = load(args.scenario)
    if args.mode == "delete":
        await delete(state, auth)
    elif args.mode == "rollback":
        await rollback(state, auth)
    elif args.mode in {"retry", "replay"}:
        await reschedule(state, replay=args.mode == "replay")
    else:
        # Hard wall-clock bound covers DB, S3, Kafka, HTTP and polling together.
        async with asyncio.timeout(args.timeout):
            await wait_for_delivery(state, settings, args.timeout,
                                    failure_kind=args.kind if args.mode == "expect-failure" else None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "delete", "rollback", "check", "expect-failure", "retry", "replay"))
    parser.add_argument("--scenario", choices=("happy", "s3", "kafka"), default="happy")
    parser.add_argument("--kind", choices=("file", "event"), default="file")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--backend-path", default="/app")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        rt.require(1 <= args.timeout <= 600, "Timeout must be 1..600 seconds")
        asyncio.run(run(args))
    except rt.AcceptanceFailure as exc:
        print(f"FAIL {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}; isolated diagnostics only; secrets suppressed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
