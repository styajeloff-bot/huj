"""Real HTTP/DB regression: request-only fields cannot block their own LC assignment."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from acceptance import API, ROOT, guard, pdf, progress, require
from readiness_acceptance import require_no_delivery

SIGNATURE_FIELDS = ("authorized_person_signature", "company_seal")
REQUEST_ONLY_FIELDS = (
    "director_appointment_document",
    "state_defense_order",
    "licenses_or_sro_membership",
    "loans_credits_leasing",
    "third_party_guarantees",
    "additional_collateral_available",
    "director_snils",
    "open_bank_accounts",
    "transaction_beneficiary",
)
UNAVAILABLE_FIELDS = (*SIGNATURE_FIELDS, *REQUEST_ONLY_FIELDS)
REQUEST_ONLY_REASON = (
    "Сведения заполняются по дозапросу после назначения ЛК, "
    "поэтому их нельзя сделать обязательными до назначения."
)


async def verify():
    guard()
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import questionnaire_settings_repository as settings

    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    lc_id = state["companies"]["lc_a"]["leasing_company_id"]
    other_lc_id = state["companies"]["lc_b"]["leasing_company_id"]
    path = f"/api/v1/leasing/companies/{lc_id}/questionnaire-settings"

    async def raw_settings(identifier=lc_id):
        async with AsyncSessionLocal() as session:
            return await settings.get_fields(session, UUID(identifier))

    async def write_settings(fields, identifier=lc_id):
        # The only non-HTTP setup is historical configuration that the new API rejects.
        async with AsyncSessionLocal() as session:
            await settings.replace_fields(session, UUID(identifier), fields)
            await session.commit()

    original = {identifier: await raw_settings(identifier) for identifier in (lc_id, other_lc_id)}
    legacy = {
        **{field: {"enabled": True, "required": True} for field in UNAVAILABLE_FIELDS},
        "company_phone": {"enabled": True, "required": True},
    }
    other_rules = {"director_snils": {"enabled": False, "required": False}}
    try:
        await write_settings(legacy)
        await write_settings(other_rules, other_lc_id)
        created = await api.request("client", "POST", "/api/v1/applications", expected=201,
            headers={"Idempotency-Key": str(uuid4())}, json={
                "company_id": state["companies"]["client"]["company_id"],
                "source_type": "platform", "name": "22286 request-only delivery gate",
                "vehicles": [{"modification_id": "questionnaire22286-model", "custom_price": "1000000", "is_model_order": True}],
            })
        app_id = created["application_id"]
        q_path = f"/api/v1/questionnaire/{app_id}"

        async def questionnaire(actor="client"):
            return (await api.request(actor, "GET", q_path))["questionnaire"]

        await api.request("client", "PUT", q_path, json={
            "full_company_name": "22286 unavailable field gate", "company_phone": None,
        })
        before = await questionnaire()
        require(all(before[field] is None for field in SIGNATURE_FIELDS), "Fixture signature fields are already filled")
        require(before["director_appointment_document"]["status"] == "missing", "Fixture already has an appointment document")
        require(before["director_snils"] is None, "Fixture already has SNILS")
        assign_path = f"/api/v1/admin/applications/{app_id}/assign-leasing-companies"
        assignment = {"leasing_company_ids": [lc_id, other_lc_id]}
        error = await api.request("admin", "PUT", assign_path, expected=422, json=assignment)
        require("Телефон организации" in error["detail"], "Normal required field no longer blocks delivery")
        await require_no_delivery(app_id)
        await api.request("client", "PUT", q_path, json={"company_phone": "+74951234567"})
        # This is the regression's RED boundary: all request-only fields are still
        # absent, but assignment must succeed so that an LC can request them.
        result = await api.request("admin", "PUT", assign_path, json=assignment)
        after = await questionnaire()
        require(result["new_links_count"] == 2 and after["questionnaire_completed_at"], "Request-only legacy requirements prevented delivery")
        require(after["id"] == before["id"], "Assignment replaced questionnaire")
        require(all(after[field] == before[field] for field in UNAVAILABLE_FIELDS), "Assignment fabricated request-only or signature data")
        require(await raw_settings() == legacy, "Assignment rewrote historical settings")
        completed = after["questionnaire_completed_at"]

        await api.request(None, "GET", path, expected=401)
        for actor in ("admin", "client"):
            response = await api.request(actor, "GET", path)
            fields = {item["field"]: item for item in response["fields"]}
            for field in UNAVAILABLE_FIELDS:
                item = fields[field]
                require(item["enabled"] and not item["required"], "Legacy required override remained effective")
                require(item["required_available"] is False and item["required_unavailable_reason"], "Unavailable field has no explanation")
                if field in REQUEST_ONLY_FIELDS:
                    require(item["required_unavailable_reason"] == REQUEST_ONLY_REASON, "Request-only field has an unrelated explanation")
            require(fields["company_phone"]["required"] and fields["company_phone"]["required_available"], "Normal required rule changed")
            require(fields["company_phone"]["required_unavailable_reason"] is None, "Normal field has unavailable reason")
            require(fields["main_counterparties"]["required_available"], "Pre-assignment bank-derived counterparties were excluded")
            require(fields["management_company_details"]["required_available"], "Company-source field was excluded")
        require(await raw_settings() == legacy, "Reading effective settings rewrote legacy data")

        for field in UNAVAILABLE_FIELDS:
            bad = {"fields": [{"field": field, "enabled": True, "required": True}]}
            error = await api.request("admin", "PUT", path, expected=422, json=bad)
            require("нельзя сделать обязательным" in error["detail"], "Unavailable requirement has unrelated error")
            require(await raw_settings() == legacy, "Rejected PUT modified settings")
            await api.request("client", "PUT", path, expected=403, json=bad)

        visible = await questionnaire("lc_a")
        require(all(field in visible for field in UNAVAILABLE_FIELDS), "Unavailable requirement disabled field visibility")
        await api.request("outsider", "GET", q_path, expected=(403, 404))
        await api.request("lc_a", "POST", f"/api/v1/leasing/applications/{app_id}/take-in-work")
        requested = await api.request("lc_a", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
            json={"requested_documents": [
                {"source": "catalog", "document_type": "appointment_docs", "display_name": "Решение о назначении руководителя"},
                {"source": "catalog", "document_type": "snils", "display_name": "СНИЛС руководителя"},
            ]})
        requests = {item["slug"]: item["id"] for item in requested["items"]}
        appointment_data = {
            "application_id": app_id, "document_request_id": requests["appointment_docs"],
            "user_titles": json.dumps(["Решение о назначении от 01.10.2026"], ensure_ascii=False),
        }
        await api.request("outsider", "POST", "/api/v1/documents", expected=403,
            data=appointment_data, files=[("files", ("appointment.pdf", pdf(), "application/pdf"))],
            headers={"Idempotency-Key": str(uuid4())})
        uploaded = await api.request("client", "POST", "/api/v1/documents", expected=201,
            data=appointment_data, files=[("files", ("appointment.pdf", pdf(), "application/pdf"))],
            headers={"Idempotency-Key": str(uuid4())})
        document_id = uploaded["documents"][0]["id"]
        await api.request("client", "POST", "/api/v1/documents", expected=201,
            data={"application_id": app_id, "document_request_id": requests["snils"],
                  "form_data": json.dumps({"number": "11223344595"})},
            files=[], headers={"Idempotency-Key": str(uuid4())})
        answered = await questionnaire()
        require(answered["id"] == before["id"] and answered["questionnaire_completed_at"] == completed, "A later answer changed questionnaire identity or delivery time")
        require(answered["director_appointment_document"]["status"] == "attached", "Appointment response did not populate questionnaire")
        require(answered["director_appointment_document"]["documents"] == [
            {"document_id": document_id, "user_title": "Решение о назначении от 01.10.2026"},
        ], "Appointment reference or user title was lost")
        require(answered["director_snils"] == "11223344595", "Typed response did not populate SNILS")
        lc_a = await questionnaire("lc_a")
        lc_b = await questionnaire("lc_b")
        require(lc_a["director_appointment_document"]["documents"][0]["document_id"] == document_id, "Requesting LC lost its document")
        require(lc_a["director_snils"] == "11223344595", "Visible SNILS missing from requesting LC")
        require("director_appointment_document" not in lc_b and "director_snils" not in lc_b, "Another LC received a private document or disabled field")
        for actor in ("client", "lc_a"):
            await api.request(actor, "GET", f"/api/v1/documents/{document_id}/content", raw=True)
        await api.request("lc_b", "GET", f"/api/v1/documents/{document_id}/content", expected=(403, 404), raw=True)
        require(await raw_settings() == legacy, "Document flow rewrote historical settings")
        require(await raw_settings(other_lc_id) == other_rules, "Document flow changed the other LC settings")

        effective = (await api.request("admin", "GET", path))["fields"]
        await api.request("admin", "PUT", path, json={"fields": [
            {key: (False if key == "enabled" and item["field"] in {"company_seal", "director_appointment_document", "director_snils"} else item[key])
             for key in ("field", "enabled", "required")}
            for item in effective
        ]})
        hidden = await questionnaire("lc_a")
        require("company_seal" not in hidden and "authorized_person_signature" in hidden, "Signature visibility became coupled to required availability")
        require("director_appointment_document" not in hidden and "director_snils" not in hidden, "Request-only visibility cannot be disabled")
        require(await questionnaire() == answered, "Visibility save changed questionnaire data")
        progress("unavailable_fields_required_gate_http_db_passed", application_id=app_id,
                 checked="legacy nine fields, ordinary gate, metadata, PUT 422, assign/request/file+form, LC isolation, visibility")
    finally:
        for identifier, fields in original.items():
            await write_settings(fields, identifier)


if __name__ == "__main__":
    asyncio.run(verify())
