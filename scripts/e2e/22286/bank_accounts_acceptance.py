"""Real HTTP/DB acceptance of saved v1 and new v2 bank-account request forms."""
from __future__ import annotations

import asyncio
import copy
import json
import runpy
from uuid import UUID, uuid4

from acceptance import API, ROOT, guard, private_json, progress, require

V1_FORM = {"accounts": [{
    "bank": {"name": "Банк исторического ответа", "bik": "044525225"},
    "acc_number": "40702810000000000001",
}]}
V2_FORM = {"accounts": [
    {"bank": "Банк новой формы", "bik": "044525225", "acc_number": "40702810000000000002", "correspondent_account": "30101810400000000225"},
    {"bank": "Второй банк новой формы", "bik": "044525974", "acc_number": "40702810000000000003", "correspondent_account": "30101810145250000974"},
]}


async def verify():
    guard()
    from sqlalchemy import select, update

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.documents import ApplicationDocumentRequest, DocumentType
    from infrastructure.repositories import questionnaire_settings_repository as settings

    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    lc_id = state["companies"]["lc_a"]["leasing_company_id"]
    async with AsyncSessionLocal() as session:
        catalog = await session.scalar(select(DocumentType).where(DocumentType.type_code == "open_bank_accounts"))
        require(catalog is not None, "Bank-account type missing")
        original_schema = copy.deepcopy(catalog.form_schema)
        original_rules = await settings.get_fields(session, UUID(lc_id))
    require(original_schema["schema_version"] == 2, "Run migration157 before bank acceptance")
    # Historical snapshots come from the published v1 catalog definition, not
    # from a guessed fallback payload. Only this isolated fixture changes catalog data.
    v1_schema = runpy.run_path("/source/alembic/versions/129_typed_document_requests.py")["SCHEMAS"]["open_bank_accounts"]

    async def catalog_schema(schema):
        async with AsyncSessionLocal() as session:
            await session.execute(update(DocumentType).where(DocumentType.type_code == "open_bank_accounts").values(form_schema=schema))
            await session.commit()

    async def snapshot(request_id):
        async with AsyncSessionLocal() as session:
            row = await session.get(ApplicationDocumentRequest, UUID(request_id))
            require(row is not None, "Request snapshot disappeared")
            return {column.key: copy.deepcopy(getattr(row, column.key)) for column in ApplicationDocumentRequest.__table__.columns}

    async def create_application(name):
        created = await api.request("client", "POST", "/api/v1/applications", expected=201,
            headers={"Idempotency-Key": str(uuid4())}, json={
                "company_id": state["companies"]["client"]["company_id"],
                "source_type": "platform", "name": name,
                "vehicles": [{"modification_id": "questionnaire22286-model", "custom_price": "1000000", "is_model_order": True}],
            })
        app_id = created["application_id"]
        await api.request("client", "PUT", f"/api/v1/questionnaire/{app_id}", json={"company_phone": "+74951234567"})
        await api.request("admin", "PUT", f"/api/v1/admin/applications/{app_id}/assign-leasing-companies", json={"leasing_company_ids": [lc_id]})
        await api.request("lc_a", "POST", f"/api/v1/leasing/applications/{app_id}/take-in-work")
        return app_id

    async def request_accounts(app_id):
        result = await api.request("lc_a", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
            json={"requested_documents": [{"source": "catalog", "document_type": "open_bank_accounts", "display_name": "Расчётные счета"}]})
        return result["items"][0]["id"]

    async def answer(app_id, request_id, form, *, actor="client", expected=201, key=None):
        return await api.request(actor, "POST", "/api/v1/documents", expected=expected,
            data={"application_id": app_id, "document_request_id": request_id, "form_data": json.dumps(form, ensure_ascii=False)},
            files=[], headers={"Idempotency-Key": key or str(uuid4())})

    async def questionnaire(app_id, actor="client"):
        return (await api.request(actor, "GET", f"/api/v1/questionnaire/{app_id}"))["questionnaire"]

    async def history(app_id):
        result = await api.request("client", "GET", f"/api/v1/applications/{app_id}/document-requests")
        return {item["id"]: item for batch in result["batches"] for item in batch["items"]}

    try:
        async with AsyncSessionLocal() as session:
            await settings.replace_fields(session, UUID(lc_id), {})
            await session.commit()
        old_app = await create_application("22286 bank v1 snapshots")
        await catalog_schema(v1_schema)
        old_provided = await request_accounts(old_app)
        await answer(old_app, old_provided, V1_FORM)
        old_pending = await request_accounts(old_app)
        before_provided = await snapshot(old_provided)
        before_pending = await snapshot(old_pending)
        private_json(ROOT / "bank-accounts-v1-before.json", {"provided": before_provided, "pending": before_pending})
        await catalog_schema(original_schema)
        require(await snapshot(old_provided) == before_provided, "Catalog update rewrote a provided v1 snapshot")
        require(await snapshot(old_pending) == before_pending, "Catalog update rewrote a pending v1 snapshot")
        private_json(ROOT / "bank-accounts-v1-after.json", {"provided": await snapshot(old_provided), "pending": await snapshot(old_pending)})
        await answer(old_app, old_pending, V2_FORM, expected=422)
        await answer(old_app, old_pending, V1_FORM)
        require((await questionnaire(old_app))["open_bank_accounts"] == V1_FORM["accounts"], "Pending v1 request no longer accepts its saved contract")
        historical = await history(old_app)
        require(historical[old_provided]["form_schema"]["schema_version"] == 1 and historical[old_provided]["form_data"] == V1_FORM, "Provided v1 history was converted or lost")
        # Leave a genuine v1 request pending for the browser, then restore the
        # current catalog before creating the v2 browser request.
        await catalog_schema(v1_schema)
        browser_v1_request = await request_accounts(old_app)
        await catalog_schema(original_schema)

        new_app = await create_application("22286 bank v2 form")
        baseline = await questionnaire(new_app)
        new_request = await request_accounts(new_app)
        require((await snapshot(new_request))["form_schema"]["schema_version"] == 2, "New request did not snapshot v2")
        await answer(new_app, new_request, V2_FORM, actor=None, expected=401)
        await answer(new_app, new_request, V2_FORM, actor="outsider", expected=403)
        await api.request("lc_b", "GET", f"/api/v1/applications/{new_app}/document-requests", expected=(403, 404))
        incomplete = copy.deepcopy(V2_FORM)
        del incomplete["accounts"][0]["correspondent_account"]
        invalid_bik = copy.deepcopy(V2_FORM)
        invalid_bik["accounts"][0]["bik"] = "123"
        invalid_account = copy.deepcopy(V2_FORM)
        invalid_account["accounts"][0]["acc_number"] = "123"
        invalid_correspondent = copy.deepcopy(V2_FORM)
        invalid_correspondent["accounts"][0]["correspondent_account"] = "x" * 20
        empty_bank = copy.deepcopy(V2_FORM)
        empty_bank["accounts"][0]["bank"] = "  "
        extra = copy.deepcopy(V2_FORM)
        extra["accounts"][0]["unexpected"] = "ignored?"
        invalid_second = copy.deepcopy(V2_FORM)
        invalid_second["accounts"][1]["correspondent_account"] = "123"
        for form in (V1_FORM, incomplete, invalid_bik, invalid_account, invalid_correspondent, empty_bank, extra, invalid_second, {"accounts": [None]}, {"accounts": []}, {"accounts": V2_FORM["accounts"] * 6}):
            await answer(new_app, new_request, form, expected=422)
            saved_request = await snapshot(new_request)
            require(saved_request["form_data"] is None and saved_request["status"] == "requested", "Rejected form changed the request")
            require((await questionnaire(new_app))["open_bank_accounts"] == baseline["open_bank_accounts"], "Rejected form changed questionnaire")
        key = str(uuid4())
        first = await answer(new_app, new_request, V2_FORM, key=key)
        replay = await answer(new_app, new_request, V2_FORM, key=key)
        require(first == replay and first["documents"] == [], "No-file replay created documents or changed response")
        await answer(new_app, new_request, V2_FORM, expected=409)
        saved = await questionnaire(new_app)
        require(saved["open_bank_accounts"] == V2_FORM["accounts"], "Not all v2 rows/fields reached questionnaire")
        require(saved["id"] == baseline["id"] and saved["questionnaire_completed_at"] == baseline["questionnaire_completed_at"], "Bank response changed identity or delivery date")
        require(all(saved[field] == baseline[field] for field in ("bank_name", "bik", "settlement_account", "correspondent_account")), "Bank response overwrote separate scalar fields")
        require((await questionnaire(new_app, "lc_a"))["open_bank_accounts"] == V2_FORM["accounts"], "Assigned LC lost bank data")
        second_request = await request_accounts(new_app)
        replacement = {"accounts": [V2_FORM["accounts"][1]]}
        await answer(new_app, second_request, replacement)
        require((await questionnaire(new_app))["open_bank_accounts"] == replacement["accounts"], "Repeated answer did not replace the same questionnaire list")
        require((await history(new_app))[new_request]["form_data"] == V2_FORM, "New answer overwrote historical response data")

        future_app = await create_application("22286 unsupported bank form version")
        future_schema = {**original_schema, "schema_version": 99}
        await catalog_schema(future_schema)
        future_request = await request_accounts(future_app)
        await catalog_schema(original_schema)
        error = await answer(future_app, future_request, V2_FORM, expected=422)
        require("Неподдерживаемая версия" in error["detail"], "Unknown form version was accepted or misclassified")
        require((await snapshot(future_request))["form_data"] is None, "Unknown version wrote form_data")
        browser_v2_request = await request_accounts(new_app)
        manifest = json.loads((ROOT / "manifest.json").read_text())
        manifest["bank_accounts"] = {
            "v1": {"application_id": old_app, "request_id": browser_v1_request, "provided_request_id": old_provided, "provided_form": V1_FORM},
            "v2": {"application_id": new_app, "request_id": browser_v2_request, "provided_request_id": new_request, "provided_form": V2_FORM},
        }
        private_json(ROOT / "manifest.json", manifest)
        progress("bank_accounts_v1_v2_http_db_passed", checked="saved snapshots, no-file responses, validation, permissions, replay, history, stable questionnaire, browser fixtures")
    finally:
        await catalog_schema(original_schema)
        async with AsyncSessionLocal() as session:
            await settings.replace_fields(session, UUID(lc_id), original_rules)
            await session.commit()


if __name__ == "__main__":
    asyncio.run(verify())
