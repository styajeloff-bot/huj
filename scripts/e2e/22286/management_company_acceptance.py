"""Management requisites + document evidence: real HTTP/DB/S3, synthetic DaData."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, pdf, private_json, progress, require

FIELD = "management_company_details"


async def verify():
    guard()
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import questionnaire_settings_repository as settings
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    lc_ids = [state["companies"][role]["leasing_company_id"] for role in ("lc_a", "lc_b")]
    originals = {}
    for lc_id in lc_ids:
        async with AsyncSessionLocal() as session:
            originals[lc_id] = await settings.get_fields(session, UUID(lc_id))
    source_mode = ROOT / "management-source-mode.json"
    original_mode = source_mode.read_bytes() if source_mode.exists() else None
    try:
        source_mode.write_text(json.dumps("off"))
        for lc_id in lc_ids:
            await api.request("admin", "PUT", f"/api/v1/leasing/companies/{lc_id}/questionnaire-settings", json={"fields": [
                {"field": FIELD, "enabled": True, "required": True},
            ]})
        created = await api.request("client", "POST", "/api/v1/applications", expected=201,
            headers={"Idempotency-Key": str(uuid4())}, json={
                "company_id": state["companies"]["client"]["company_id"], "source_type": "platform",
                "name": "22286 management company v3", "vehicles": [{
                    "modification_id": "questionnaire22286-model", "custom_price": "1000000", "is_model_order": True,
                }],
            })
        app_id = created["application_id"]
        q_path = f"/api/v1/questionnaire/{app_id}"
        async def questionnaire(actor="client"):
            return (await api.request(actor, "GET", q_path))["questionnaire"]
        empty = await questionnaire()
        require(empty[FIELD] == {"requisites": [], "status": "not_provided", "file_name": None, "documents": []}, "Missing management defaults")
        assign = f"/api/v1/admin/applications/{app_id}/assign-leasing-companies"
        await api.request("admin", "PUT", assign, expected=422, json={"leasing_company_ids": lc_ids})
        source_mode.write_text(json.dumps("first"))
        first = await api.request("client", "POST", q_path + "/refresh")
        require(first["sources"]["dadata"] == "updated", "Synthetic DaData source did not run")
        require(first["questionnaire"][FIELD]["requisites"][0]["name"] == "УК Источник 1", "DaData did not populate nested requisites")
        # Requisites satisfy the unchanged rule; no LC-requested file is required.
        await api.request("admin", "PUT", assign, json={"leasing_company_ids": lc_ids})
        before = await questionnaire()
        await api.request("lc_a", "POST", f"/api/v1/leasing/applications/{app_id}/take-in-work")
        async def request_document():
            response = await api.request("lc_a", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents", json={
                "requestedDocuments": [{"source": "catalog", "document_type": "management_company", "display_name": "Сведения об управляющей компании"}],
            })
            return response["items"][0]["id"]
        async def answer(request_id, *, title=None, actor="client", key=None, expected=201):
            data = {"application_id": app_id, "document_request_id": request_id}
            files = []
            if title:
                data["user_titles"] = json.dumps([title], ensure_ascii=False)
                files = [("files", ("management.pdf", pdf(), "application/pdf"))]
            return await api.request(actor, "POST", "/api/v1/documents", expected=expected,
                data=data, files=files, headers={"Idempotency-Key": key or str(uuid4())})
        request_id = await request_document()
        await answer(request_id, actor="outsider", expected=403)
        await answer(request_id)
        no_file = (await questionnaire())[FIELD]
        require(no_file == before[FIELD], "No-file answer changed requisites or fabricated a file")
        request_id = await request_document()
        title = "Реквизиты управляющей компании — версия 3"
        key = str(uuid4())
        uploaded = await answer(request_id, title=title, key=key)
        document_id = uploaded["documents"][0]["id"]
        replay = await answer(request_id, title=title, key=key)
        require(replay["documents"][0]["id"] == document_id, "Replay duplicated the management file")
        attached = (await questionnaire())[FIELD]
        require(attached["status"] == "file_attached" and attached["file_name"] == title, "Wrong §3.30 file status/title")
        require(attached["requisites"] == before[FIELD]["requisites"], "File answer erased requisites")
        require(attached["documents"] == [{"document_id": document_id, "user_title": title}], "Missing persisted file reference")
        source_mode.write_text(json.dumps("second"))
        refreshed = await api.request("admin", "POST", q_path + "/refresh")
        value = refreshed["questionnaire"][FIELD]
        require(value["requisites"][0]["name"] == "УК Источник 2", "Automatic requisites did not refresh")
        require({k: value[k] for k in ("status", "file_name", "documents")} == {k: attached[k] for k in ("status", "file_name", "documents")}, "Refresh erased document evidence")
        # Legacy array API now edits requisites only; explicit null also retains files.
        for manual in ([{"name": "УК Ручные реквизиты", "inn": "7709876543", "ogrn": "1027700000999"}], None):
            await api.request("admin", "PUT", q_path, json={FIELD: manual})
            refreshed = await api.request("admin", "POST", q_path + "/refresh")
            value = refreshed["questionnaire"][FIELD]
            require(value["requisites"] == manual and value["documents"] == attached["documents"], "Manual requisites/null or file were overwritten")
        requisites = [{"name": "УК Сохранённые реквизиты", "inn": "7709876543", "ogrn": "1027700000999"}]
        await api.request("admin", "PUT", q_path, json={FIELD: {"requisites": requisites}})
        current = (await questionnaire())[FIELD]
        await api.request("admin", "PUT", q_path, json={FIELD: current})
        for forged in (
            {**current, "documents": [{"document_id": str(uuid4()), "user_title": "Подмена"}]},
            {**current, "status": "not_provided"}, {**current, "file_name": "Подмена"},
        ):
            await api.request("admin", "PUT", q_path, expected=422, json={FIELD: forged})
        await api.request(None, "GET", q_path, expected=401)
        await api.request("outsider", "GET", q_path, expected=(403, 404))
        lc_a = (await questionnaire("lc_a"))[FIELD]
        lc_b = (await questionnaire("lc_b"))[FIELD]
        require(lc_a == current, "Requesting LC lost file or requisites")
        require(lc_b == {"requisites": requisites, "status": "not_provided", "file_name": None, "documents": []}, "Other LC received private filename or lost common requisites")
        for actor in ("client", "lc_a"):
            for disposition in ("inline", "attachment"):
                response = await api.request(actor, "GET", f"/api/v1/documents/{document_id}/content?disposition={disposition}", raw=True)
                require(response.content.startswith(b"%PDF-") and response.headers.get("content-disposition", "").startswith(disposition), "Open/download returned wrong content")
        await api.request("lc_b", "GET", f"/api/v1/documents/{document_id}/content", expected=(403, 404), raw=True)
        # A new no-file answer clears only the document part of the same row.
        await answer(await request_document())
        cleared = (await questionnaire())[FIELD]
        require(cleared == {"requisites": requisites, "status": "not_provided", "file_name": None, "documents": []}, "Repeated empty answer lost requisites")
        final_upload = await answer(await request_document(), title=title)
        document_id = final_upload["documents"][0]["id"]
        after = await questionnaire()
        require(after["id"] == before["id"] and after["questionnaire_completed_at"] == before["questionnaire_completed_at"], "Answer replaced questionnaire identity or delivery time")
        stored = await db_questionnaire(app_id)
        require(stored["field_sources"][FIELD + ".requisites"] == "manual", "Manual provenance lost")
        require(stored["field_sources"][FIELD + ".documents"] == "document_request", "Document provenance lost")
        manifest_path = ROOT / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["management_company"] = {"application_id": app_id, "requisites_name": requisites[0]["name"], "document_title": title, "document_id": document_id, "empty_pending_request_id": await request_document()}
        private_json(manifest_path, manifest)
        progress("management_company_http_db_s3_passed", application_id=app_id,
                 checked="defaults, requisites-only gate, source/manual/null precedence, no-file/file/replay/repeat, UUID/date, forged references, two-LC privacy, downloads")
    finally:
        if original_mode is None:
            source_mode.write_text(json.dumps("off"))
        else:
            source_mode.write_bytes(original_mode)
        for lc_id, original in originals.items():
            async with AsyncSessionLocal() as session:
                await settings.replace_fields(session, UUID(lc_id), original)
                await session.commit()


if __name__ == "__main__":
    asyncio.run(verify())
