"""Disposable failure injection in guarded E2E infrastructure only."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from runtime import API, ROOT, guard, pdf, private_json, progress, require
from versioning import version_metadata


async def verify_faults(api: API, document: dict):
    import aioboto3
    from sqlalchemy import select, text
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.document_registry import reference_document_versions

    settings = guard()
    document_id = document["id"]
    prefix = f"document-registry/{document_id}/"
    original = await api.request("admin", "GET", f"/api/v1/document-registry/documents/{document_id}")
    day = datetime.now(ZoneInfo("Europe/Moscow")).date()
    metadata = json.dumps(version_metadata(original, valid_from=str(day), valid_to=str(day + timedelta(days=100))))
    async with aioboto3.Session().client("s3", endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region, aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key) as s3:
        before = await s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix)
        keys_before = {item["Key"] for item in before.get("Contents", [])}
        async with AsyncSessionLocal() as session:
            await session.execute(text("""CREATE FUNCTION e2e22296_reject_file() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.file_name = 'registry-force-db-failure.pdf' THEN
                    RAISE EXCEPTION 'E2E 22296 intentional isolated DB failure';
                END IF;
                RETURN NEW;
            END;
            $$"""))
            await session.execute(text("CREATE TRIGGER e2e22296_reject_file BEFORE INSERT ON reference_document_files FOR EACH ROW EXECUTE FUNCTION e2e22296_reject_file()"))
            await session.commit()
        try:
            await api.request("admin", "POST", f"/api/v1/document-registry/documents/{document_id}/versions", expected=500,
                data={"metadata": metadata}, files=[("files", ("registry-force-db-failure.pdf", pdf(), "application/pdf"))])
        finally:
            async with AsyncSessionLocal() as session:
                await session.execute(text("DROP TRIGGER IF EXISTS e2e22296_reject_file ON reference_document_files"))
                await session.execute(text("DROP FUNCTION IF EXISTS e2e22296_reject_file()"))
                await session.commit()
        after = await api.request("admin", "GET", f"/api/v1/document-registry/documents/{document_id}")
        require(after["current_version"]["id"] == original["current_version"]["id"] and after["version_count"] == original["version_count"], "DB failure published partial version")
        await api.request("admin", "GET", original["current_version"]["files"][0]["download_url"], raw=True)
        require(after["name"] == original["name"] and after["related_companies"] == original["related_companies"], "DB failure changed current metadata projection")
        objects = await s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix)
        require({item["Key"] for item in objects.get("Contents", [])} == keys_before, "DB rollback did not clean uploaded S3 object")
        async with AsyncSessionLocal() as session:
            current_count = len((await session.scalars(select(reference_document_versions.c.id).where(reference_document_versions.c.document_id == UUID(document_id), reference_document_versions.c.is_current.is_(True)))).all())
            require(current_count == 1, "DB rollback lost current version")
        private_json(ROOT / "storage-failure.secret.json", {"document": original, "keys": sorted(keys_before)})


async def storage_failure():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    snapshot = json.loads((ROOT / "storage-failure.secret.json").read_text())
    original = snapshot["document"]
    api = API(state)
    day = datetime.now(ZoneInfo("Europe/Moscow")).date()
    await api.request("admin", "POST", f"/api/v1/document-registry/documents/{original['id']}/versions", expected=500,
        data={"metadata": json.dumps(version_metadata(original, valid_from=str(day), valid_to=str(day + timedelta(days=100))))},
        files=[("files", ("registry-force-s3-failure.pdf", pdf(), "application/pdf"))])
    after = await api.request("admin", "GET", f"/api/v1/document-registry/documents/{original['id']}")
    require(after["current_version"]["id"] == original["current_version"]["id"] and after["version_count"] == original["version_count"], "Unavailable S3 published partial version")
    progress("registry_unavailable_s3_rollback_passed")


async def storage_recovered():
    import aioboto3
    settings = guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    snapshot = json.loads((ROOT / "storage-failure.secret.json").read_text())
    original = snapshot["document"]
    api = API(state)
    await api.request("dealer", "GET", original["current_version"]["files"][0]["download_url"], raw=True)
    async with aioboto3.Session().client("s3", endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region, aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key) as s3:
        objects = await s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=f"document-registry/{original['id']}/")
        require(sorted(item["Key"] for item in objects.get("Contents", [])) == snapshot["keys"], "S3 failure left partial objects")
    progress("registry_s3_recovered_existing_file_readable")


if __name__ == "__main__":
    import asyncio
    import sys
    asyncio.run(storage_failure() if sys.argv[1] == "unavailable" else storage_recovered())
