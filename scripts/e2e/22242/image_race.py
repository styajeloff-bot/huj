#!/usr/bin/env python3
"""Runtime-only PostgreSQL/S3 races; no HTTP admin/outbox/Taskiq acceptance.

Run beside runtime.py: python /e2e/image_race.py --execute --backend-path /app
Uses actual guards, S3 and CatalogRepository for races; actual import pipeline
for an already-deleted target. Pauses coordinate operations, never fake results.
"""
import argparse
import asyncio
import hashlib
import json
import signal
from io import BytesIO
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

from runtime import check, guard, require


async def run():
    from PIL import Image
    from sqlalchemy import delete, select, text

    from application.services.catalog_ingestion import process_vehicle_images
    from infrastructure.database import AsyncSessionLocal, engine
    from infrastructure.models.vehicles import Vehicle
    from infrastructure.repositories.catalog_repository import CatalogRepository
    from infrastructure.repositories.vehicle_deletion_jobs_repository import (
        image_is_referenced, lock_vehicle_image_write,
    )
    from infrastructure.services.object_storage import get_object_storage

    namespace = uuid5(NAMESPACE_URL, f"task22242/image-race/{uuid4()}")
    ids = {name: uuid5(namespace, name) for name in ("writer", "cleaner", "same", "missing")}
    keys = {name: f"vehicles/{value.hex}.png" for name, value in ids.items()}
    source = f"vehicles/{uuid5(namespace, 'source').hex}.png"
    storage = get_object_storage()
    digest = hashlib.sha256(storage.public_url(source).encode()).hexdigest()[:32]
    import_keys = {f"vehicles/{digest}{ext}" for ext in ("", ".png", ".jpg", ".webp")}
    calls = []
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
    body = buffer.getvalue()
    print(json.dumps({"run": str(namespace), "vehicle_ids": list(map(str, ids.values())),
                      "object_keys": [*keys.values(), source]}), flush=True)
    pids, observed = {}, {}

    async def pid(session, label):
        pids[label] = await session.scalar(text("SELECT pg_backend_pid()"))

    async def blocking(waiter, holder):
        async with asyncio.timeout(4), AsyncSessionLocal() as session:
            while True:
                if waiter in pids and holder in pids:
                    blockers = await session.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": pids[waiter]})
                    if pids[holder] in blockers:
                        print(json.dumps({"waiter": waiter, "pid": pids[waiter], "pg_blocking_pids": blockers}), flush=True)
                        return
                await asyncio.sleep(0.02)

    async def writer(name, reached=None, release=None):
        async with AsyncSessionLocal() as session, session.begin():
            await pid(session, f"{name}/writer")
            require(await lock_vehicle_image_write(session, ids[name]), "Synthetic target missing")
            observed[name] = await storage.exists(keys[name])
            if reached is not None:
                reached.set()
                await release.wait()
            if not observed[name]:
                await storage.put(keys[name], body, "image/png")
            await CatalogRepository.update_vehicle_images(session, ids[name], [keys[name].split("/")[-1]])

    async def cleaner(name, reached=None, release=None):
        async with AsyncSessionLocal() as session, session.begin():
            await pid(session, f"{name}/cleaner")
            referenced = await image_is_referenced(session, keys[name])
            if reached is not None:
                reached.set()
                await release.wait()
            if not referenced:
                await storage.delete(keys[name])
            return referenced

    async def verify_reference(name):
        async with AsyncSessionLocal() as session:
            images = await session.scalar(select(Vehicle.images).where(Vehicle.id == ids[name]))
        require(images == [keys[name].split("/")[-1]], "Committed image reference missing")
        require(await storage.exists(keys[name]), "Committed reference points to absent S3 object")

    async def remove_same():
        async with AsyncSessionLocal() as session, session.begin():
            await pid(session, "same/delete")
            images = await session.scalar(select(Vehicle.images).where(Vehicle.id == ids["same"]).with_for_update())
            require(images == [keys["same"].split("/")[-1]], "Deletion did not observe committed image")
            await session.execute(delete(Vehicle).where(Vehicle.id == ids["same"]))

    try:
        async with AsyncSessionLocal() as session, session.begin():
            for vehicle_id in ids.values():
                await session.execute(Vehicle.__table__.insert().values(id=vehicle_id, images=[]))
        for key in [keys["writer"], keys["cleaner"], source]:
            await storage.put(key, body, "image/png")
        reached, release = asyncio.Event(), asyncio.Event()
        async with asyncio.TaskGroup() as group:
            group.create_task(writer("writer", reached, release))
            await reached.wait()
            cleanup = group.create_task(cleaner("writer"))
            await blocking("writer/cleaner", "writer/writer")
            release.set()
        require(observed["writer"] and cleanup.result(), "Shared reuse was not retained")
        await verify_reference("writer")
        check("writer-first: actual S3 reuse; cleanup blocked, then retained committed reference")

        reached, release = asyncio.Event(), asyncio.Event()
        async with asyncio.TaskGroup() as group:
            cleanup = group.create_task(cleaner("cleaner", reached, release))
            await reached.wait()
            group.create_task(writer("cleaner"))
            await blocking("cleaner/writer", "cleaner/cleaner")
            release.set()
        require(not cleanup.result() and not observed["cleaner"], "Writer did not observe actual S3 deletion")
        await verify_reference("cleaner")
        check("cleanup-first: writer blocked, then detected absent object, reuploaded and committed")

        reached, release = asyncio.Event(), asyncio.Event()
        async with asyncio.TaskGroup() as group:
            group.create_task(writer("same", reached, release))
            await reached.wait()
            group.create_task(remove_same())
            await blocking("same/delete", "same/writer")
            release.set()
        async with AsyncSessionLocal() as session, session.begin():
            require(await session.get(Vehicle, ids["same"]) is None, "Physical deletion failed")
            await session.execute(delete(Vehicle).where(Vehicle.id == ids["missing"]))
        require(not observed["same"] and await storage.exists(keys["same"]), "Same-target S3 upload did not complete")
        check("same target: physical deletion waited for image-reference commit and observed new images")

        class CountedStorage:
            async def exists(self, key):
                require(key in import_keys, "Unexpected target S3 key")
                calls.append(("exists", key))
                return await storage.exists(key)

            async def put(self, key, data, content_type):
                require(key in import_keys, "Unexpected target S3 key")
                calls.append(("put", key))
                return await storage.put(key, data, content_type)

        async def fetch_source(url):
            require(url == storage.public_url(source), "Unexpected source URL")
            actual = await storage.get(source)
            require(actual is not None, "Actual S3 source missing")
            return SimpleNamespace(content=actual.data, content_type=actual.content_type)

        result = await process_vehicle_images(
            {"vehicle_id": ids["missing"], "urls": [storage.public_url(source)], "job_id": None},
            asyncio.Semaphore(1), CountedStorage(), SimpleNamespace(fetch=fetch_source),
        )
        require(result == (None, 0, 1) and not calls, "Deleted target performed S3 reuse/upload or lost counters")
        check("actual process_vehicle_images: deleted target skips S3 exists/put after real S3 download")
    finally:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(delete(Vehicle).where(Vehicle.id.in_(list(ids.values()))))
        for key in {*keys.values(), source, *(key for method, key in calls if method == "put")}:
            await storage.delete(key)
        await engine.dispose()


async def bounded():
    async with asyncio.timeout(55):
        await run()


if __name__ == "__main__":
    signal.alarm(60)  # Hard process deadline, including cancellation/cleanup.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backend-path", default="/app")
    guard(parser.parse_args())
    asyncio.run(bounded())
