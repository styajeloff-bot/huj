"""Real HTTP acceptance of immutable edits, retained files and version selection."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from runtime import pdf, progress, require

BASE = "/api/v1/document-registry"


def version_metadata(document, **changes):
    version = document["current_version"]
    related = document["related_companies"]
    result = {"expected_current_version_id": version["id"], "name": document["name"],
        "related_companies": {key: related[key] for key in ("platform_ml", "leasing_company_ids", "dealer_company_ids", "distributor_company_ids")},
        "valid_from": version["valid_from"], "valid_to": version["valid_to"],
        "retained_file_ids": [file["id"] for file in version["files"]]}
    return {**result, **changes}


async def verify_version_lifecycle(api, original, foreign, state):
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.document_registry import reference_document_files as files

    document_id = original["id"]
    path = BASE + f"/documents/{document_id}"
    initial = original["current_version"]
    initial_bytes = (await api.request("admin", "GET", initial["files"][0]["download_url"], raw=True)).content
    require(initial["name"] == original["name"] and initial["related_companies"] == original["related_companies"], "Initial metadata snapshot incomplete")
    require(initial["is_current"] and not initial["metadata_backfilled"], "New version marked backfilled or noncurrent")

    async def edit(document, *, expected=201, role="admin", attachments=None, **changes):
        return await api.request(role, "POST", path + "/versions", expected=expected,
            data={"metadata": json.dumps(version_metadata(document, **changes))}, files=attachments)

    async def activate(document, version_id, *, expected=200, role="admin", expected_id=None):
        return await api.request(role, "POST", path + f"/versions/{version_id}/activate", expected=expected,
            json={"expected_current_version_id": expected_id or document["current_version"]["id"]})

    await api.request("admin", "PATCH", path, expected=405, json={"name": "unversioned"})
    for role in ("dealer", "leasing", "distributor", "outsider", "client"):
        await edit(original, role=role, expected=403)
        await activate(original, initial["id"], role=role, expected=403)
    await edit(original, retained_file_ids=[], expected=422)
    await edit(original, retained_file_ids=[str(uuid4())], expected=422)
    await edit(original, retained_file_ids=[foreign["current_version"]["files"][0]["id"]], expected=422)
    await edit(original, retained_file_ids=[initial["files"][0]["id"]]*2, expected=422)
    await edit(original, name="   ", expected=422)
    await edit(original, attachments=[("files", (f"extra-{index}.pdf", pdf(), "application/pdf")) for index in range(9)], expected=422)
    await edit(original, contract_number="immutable", expected=422)
    await edit(original, document_type="act", expected=422)
    await edit(original, group_id=foreign["group_id"], expected=422)
    await activate(original, foreign["current_version"]["id"], expected=404)
    unknown_related = {**version_metadata(original)["related_companies"], "dealer_company_ids": [str(uuid4())]}
    await edit(original, related_companies=unknown_related, expected=422)
    await api.request("admin", "POST", path + "/versions", expected=422, data={"metadata": json.dumps({"valid_from": initial["valid_from"]})})

    async with AsyncSessionLocal() as session:
        original_keys = set((await session.scalars(select(files.c.s3_key).where(files.c.version_id == UUID(initial["id"])))).all())
    changed_related = {"platform_ml": True, "leasing_company_ids": [], "dealer_company_ids": [state["companies"]["dealer2"]["company_id"]], "distributor_company_ids": []}
    second = await edit(original, name=original["name"] + " edited", related_companies=changed_related,
        valid_from="2098-01-01", valid_to="2099-01-01", retained_file_ids=[file["id"] for file in reversed(initial["files"])])
    require(second["status"] == "pending" and second["current_version"]["version_number"] == 2, "Metadata-only edit did not create version2")
    require(second["related_companies"]["platform_ml"] is True, "Platform relationship snapshot lost")
    require([file["name"] for file in second["current_version"]["files"]] == [file["name"] for file in reversed(initial["files"])], "Retained file order changed")
    async with AsyncSessionLocal() as session:
        new_keys = set((await session.scalars(select(files.c.s3_key).where(files.c.version_id == UUID(second["current_version"]["id"])))).all())
    require(original_keys == new_keys, "Metadata edit reuploaded retained files")
    for file in second["current_version"]["files"]:
        await api.request("outsider", "GET", file["download_url"], raw=True)
    await api.request("dealer", "GET", path, expected=404)
    await api.request("dealer", "GET", initial["files"][0]["download_url"], expected=404)
    await api.request("outsider", "GET", path)
    history = await api.request("outsider", "GET", path + "/versions")
    old = next(version for version in history["items"] if version["id"] == initial["id"])
    require({key: old[key] for key in old if key != "is_current"} == {key: initial[key] for key in initial if key != "is_current"}, "Edit mutated historical snapshot")
    require(not old["is_current"] and sum(version["is_current"] for version in history["items"]) == 1, "Multiple current versions")
    await edit(original, expected=409)
    await edit(second, retained_file_ids=[initial["files"][0]["id"]], expected=422)
    await activate(second, initial["id"], expected_id=initial["id"], expected=409)

    replacement_bytes = pdf("Distinct replacement version " + document_id)
    require(replacement_bytes != initial_bytes, "Version fixtures must contain different bytes")
    third = await edit(second, name=second["name"] + " third", retained_file_ids=[second["current_version"]["files"][0]["id"]], attachments=[("files", ("replacement.pdf", replacement_bytes, "application/pdf"))])
    require([file["name"] for file in third["current_version"]["files"]] == [second["current_version"]["files"][0]["name"], "replacement.pdf"], "Retained and uploaded file composition incorrect")
    await api.request("admin", "PATCH", path + "/activation", json={"active": False})
    restored = await activate(third, initial["id"])
    require(restored["version_count"] == 3 and restored["current_version"]["version_number"] == 1, "Selection copied a version")
    require(restored["status"] == "deactivated" and not restored["active"], "Version selection changed manual deactivation")
    for field in ("name", "related_companies", "contract_number", "document_type", "group_id"):
        require(restored[field] == original[field], "Selection did not restore " + field)
    require(restored["current_version"] == initial, "Selection did not restore dates/files/author exactly")
    old_download = await api.request("dealer", "GET", initial["files"][0]["download_url"], raw=True)
    new_download = await api.request("dealer", "GET", third["current_version"]["files"][1]["download_url"], raw=True)
    require(old_download.content == initial_bytes and new_download.content == replacement_bytes, "Restore changed historical file content")
    await api.request("dealer", "GET", path)
    await api.request("outsider", "GET", path, expected=404)
    await api.request("outsider", "GET", second["current_version"]["files"][0]["download_url"], expected=404)
    idempotent = await activate(restored, initial["id"], expected_id=third["current_version"]["id"])
    require(idempotent == restored, "Selecting current version is not idempotent")
    fourth = await edit(restored, name=original["name"] + " fourth")
    require(fourth["current_version"]["version_number"] == 4 and fourth["version_count"] == 4, "Version number reused after restore")
    require(not fourth["active"], "Edit changed manual deactivation")
    await api.request("admin", "PATCH", path + "/activation", json={"active": True})
    current = await api.request("admin", "GET", path)
    payload = version_metadata(current, name=current["name"] + " concurrent")
    async def race():
        return await api.request("admin", "POST", path + "/versions", expected=(201,409), raw=True, data={"metadata": json.dumps(payload)})
    results = await asyncio.gather(race(), race())
    require(sorted(response.status_code for response in results) == [201,409], "Concurrent stale edit was not rejected")
    final = await api.request("admin", "GET", path)
    require(final["version_count"] == 5 and final["current_version"]["version_number"] == 5, "Conflict created partial version")
    progress("registry_version_lifecycle_passed", document_id=document_id, version_count=final["version_count"])
    return final


async def verify_inactive_relationships(api, state):
    from sqlalchemy import update
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company, LeasingCompany
    from runtime import guard, pdf

    guard()
    dealer_id, company_id, leasing_id = uuid4(), uuid4(), uuid4()
    async with AsyncSessionLocal() as session:
        session.add_all([Company(id=dealer_id, name="22296 historical dealer", company_type="dealer", is_active=True),
            Company(id=company_id, name="22296 historical leasing", company_type="leasing_company", is_active=True)])
        await session.flush()
        session.add(LeasingCompany(id=leasing_id, company_id=company_id, is_active=True))
        await session.commit()
    payload = {"document_type": "contract", "contract_number": "22296-inactive-" + uuid4().hex,
        "name": "22296 historical relationships", "valid_from": "2098-01-01", "valid_to": None,
        "participants": {"leasing_company_ids": [state["companies"]["leasing"]["leasing_company_id"]]},
        "related_companies": {"dealer_company_ids": [str(dealer_id)], "leasing_company_ids": [str(leasing_id)]}}
    original = await api.request("admin", "POST", BASE + "/documents", expected=201, data={"metadata": json.dumps(payload)}, files=[("files", ("historical.pdf", pdf(), "application/pdf"))])
    path = BASE + f"/documents/{original['id']}"
    async with AsyncSessionLocal() as session:
        await session.execute(update(Company).where(Company.id.in_([dealer_id, company_id])).values(is_active=False))
        await session.execute(update(LeasingCompany).where(LeasingCompany.id == leasing_id).values(is_active=False))
        await session.commit()
    edited = await api.request("admin", "POST", path + "/versions", expected=201,
        data={"metadata": json.dumps(version_metadata(original, name=original["name"] + " edited"))})
    require(edited["related_companies"] == original["related_companies"], "Metadata edit dropped inactive historical assignment")
    cleared = await api.request("admin", "POST", path + "/versions", expected=201,
        data={"metadata": json.dumps(version_metadata(edited, related_companies={"platform_ml": False, "leasing_company_ids": [], "dealer_company_ids": [], "distributor_company_ids": []}))})
    await api.request("admin", "POST", path + "/versions", expected=422,
        data={"metadata": json.dumps(version_metadata(cleared, related_companies=version_metadata(original)["related_companies"]))})
    restored = await api.request("admin", "POST", path + f"/versions/{original['current_version']['id']}/activate",
        json={"expected_current_version_id": cleared["current_version"]["id"]})
    require(restored["related_companies"] == original["related_companies"], "Restore revalidated immutable historical assignment")
    progress("registry_inactive_relationships_passed", document_id=original["id"])


async def verify_standalone():
    from runtime import API, ROOT, guard
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    payload = {"document_type": "contract", "name": "22296 standalone version flow", "valid_from": "2026-01-01", "valid_to": "2099-01-01",
        "participants": {"leasing_company_ids": [state["companies"]["leasing"]["leasing_company_id"]]},
        "related_companies": {"dealer_company_ids": [state["companies"]["dealer"]["company_id"]]}}
    documents = []
    for index in range(2):
        documents.append(await api.request("admin", "POST", BASE + "/documents", expected=201,
            data={"metadata": json.dumps({**payload, "contract_number": "22296-standalone-" + uuid4().hex})},
            files=[("files", (name, pdf(), "application/pdf")) for name in ("first.pdf", "second.pdf")]))
    await verify_version_lifecycle(api, documents[0], documents[1], state)
    await verify_inactive_relationships(api, state)


if __name__ == "__main__":
    asyncio.run(verify_standalone())
