"""Independent real-HTTP fixtures for passport confirmation/autosave races."""
from __future__ import annotations

import asyncio
import json
from urllib.parse import quote
from uuid import uuid4

from acceptance import API, ROOT, guard, progress, require
from core_acceptance import projection_application, projection_passport_fields


async def run():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    fixtures = {}
    full_name = "Тестова Анна Ивановна"
    for scenario, role in (
        ("founder_slow", "founder"),
        ("founder_quick", "founder"),
        ("representative_slow", "representative"),
        ("director_slow", "director_applicant"),
        ("founder_failed", "founder"),
        ("founder_prior_save", "founder"),
        ("founder_pending", "founder"),
        ("beneficiary_pending", "beneficiary"),
    ):
        app_id = await projection_application(api, state)
        person_id = str(uuid4())
        collection = {"founder": "founders", "beneficiary": "beneficiaries"}.get(role, "other_representatives")
        q_url = f"/api/v1/questionnaire/{app_id}"
        if role == "director_applicant":
            payload = {"director_full_name": full_name, "director_name_changed": False}
        elif role == "beneficiary":
            payload = {"has_beneficiary": True, collection: [{"id": person_id, "full_name": full_name,
                "registration_address": "Москва, Прежний адрес, 1", "name_changed": False}]}
        elif role == "founder":
            payload = {collection: [{"id": person_id, "name": full_name,
                "inn": "000000000099", "share": "40", "name_changed": False}]}
        else:
            payload = {collection: [{"id": person_id, "full_name": full_name, "name_changed": False}]}
        await api.request("client", "PUT", q_url, json=payload)
        candidates = (await api.request("client", "GET", f"/api/v1/applications/{app_id}/sopd-signer-candidates"))["candidates"]
        candidate = next(person for person in candidates if person["role"] == role)
        passport_url = f"/api/v1/applications/{app_id}/sopd-signers/{quote(candidate['key'], safe='')}/passport"
        fields = {**projection_passport_fields(), "passportNumber": "123456"}
        await api.request("client", "PATCH", passport_url, json={"fields": fields, "editedFields": list(fields)})
        q = (await api.request("client", "GET", q_url))["questionnaire"]
        saved = q["director_passport_number"] if role == "director_applicant" else next(person for person in q[collection] if person["id"] == person_id)["passport_number"]
        require(saved == "123456", "Initial passport was not projected into the questionnaire")
        await api.request(None, "GET", q_url, expected=401)
        await api.request("outsider", "GET", q_url, expected=(403, 404))
        await api.request("outsider", "PATCH", passport_url, expected=(403, 404), json={"fields": fields, "editedFields": list(fields)})
        fixtures[scenario] = {"application_id": app_id, "person_id": person_id, "role": role,
            "collection": collection, "full_name": full_name, "old_number": "123456", "new_number": "654321"}
    (ROOT / "passport-refresh-fixture.json").write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
    progress("passport_refresh_browser_fixtures_ready", scenarios=list(fixtures))


if __name__ == "__main__":
    asyncio.run(run())
