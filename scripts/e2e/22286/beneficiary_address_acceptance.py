"""Prepare independent browser fixtures for beneficiary OCR address refresh.

DBrain responses are synthetic cache entries; recognition and confirmation use
real HTTP endpoints, and the browser confirms the second recognition itself.
"""
from __future__ import annotations

import asyncio
import io
import json
from uuid import UUID, uuid4

from acceptance import API, ROOT, guard, progress, require
from core_acceptance import projection_application


async def run():
    guard()
    from PIL import Image
    from application.services.passport_profile_fields import PASSPORT_MAIN_TYPE, PASSPORT_REGISTRATION_TYPE
    from application.services.sopd_passport import map_dbrain
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import passport_recognition_repository as cache
    from infrastructure.services.document_recognition import calculate_file_hash

    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    old_address = "Москва, Старый автоматический адрес, 1"
    new_address = "Казань, Новый адрес из паспорта, 2"
    fixtures = {}
    raw_main = {"items": [{"fields": {
        "surname": "Тестова", "first_name": "Анна", "other_names": "Ивановна",
        "nationality": "Российская Федерация", "sex": "female", "date_of_birth": "1990-01-01",
        "place_of_birth": "Москва", "series_and_number": "1234 987654", "date_of_issue": "2020-01-01",
        "subdivision_code": "123-456", "issuing_authority": "УМВД России",
    }}]}

    async def recognize(passport_url, address):
        buffer = io.BytesIO()
        Image.new("RGB", (36, 36), tuple(uuid4().bytes[:3])).save(buffer, format="PNG")
        content = buffer.getvalue()
        raw_registration = {"items": [{"fields": {"registration_address": {"text": address, "confidence": 0.96}}}]}
        async with AsyncSessionLocal() as session:
            for kind, raw in ((PASSPORT_MAIN_TYPE, raw_main), (PASSPORT_REGISTRATION_TYPE, raw_registration)):
                mapped, confidence = map_dbrain(raw)
                await cache.save(session, user_id=UUID(state["users"]["client"]["id"]),
                    file_hash=calculate_file_hash(content), passport_type=kind,
                    raw_data=raw, mapped_data=mapped, confidence_data=confidence, recognition_task_id=None)
            await session.commit()
        return await api.request("client", "POST", passport_url.replace("/passport", "/passport-recognition"),
            files={"passport_main": ("main.png", content, "image/png"), "passport_registration": ("registration.png", content, "image/png")})

    for name in ("automatic", "manual", "manual_clear", "concurrent", "concurrent_share", "failed_refresh"):
        app_id = await projection_application(api, state)
        person_id = str(uuid4())
        q_url = f"/api/v1/questionnaire/{app_id}"
        await api.request("client", "PUT", q_url, json={"has_beneficiary": True, "beneficiaries": [
            {"id": person_id, "full_name": "Тестова Анна Ивановна", "share_percentage": 40},
        ]})
        passport_url = f"/api/v1/applications/{app_id}/sopd-signers/beneficiary%3A{person_id}/passport"
        first = await recognize(passport_url, old_address)
        await api.request("client", "PATCH", passport_url, json={"fields": first["fields"], "editedFields": []})
        person = (await api.request("client", "GET", q_url))["questionnaire"]["beneficiaries"][0]
        require(person["registration_address"] == old_address, "Initial automatic address did not reach the questionnaire")
        initial_address = old_address
        if name in {"manual", "manual_clear"}:
            initial_address = "Минск, Адрес введён вручную, 3" if name == "manual" else None
            await api.request("client", "PUT", q_url, json={"beneficiaries": [{**person, "registration_address": initial_address}]})
        await recognize(passport_url, new_address)
        current = (await api.request("client", "GET", q_url))["questionnaire"]["beneficiaries"][0]
        require(current["registration_address"] == initial_address, "Unconfirmed OCR changed the questionnaire")
        await api.request(None, "GET", q_url, expected=401)
        await api.request("outsider", "GET", q_url, expected=(403, 404))
        await api.request("outsider", "PATCH", passport_url, expected=(403, 404), json={"fields": first["fields"], "editedFields": []})
        fixtures[name] = {"application_id": app_id, "person_id": person_id,
            "initial_address": initial_address, "recognized_address": new_address}
    (ROOT / "beneficiary-address-fixture.json").write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
    progress("beneficiary_address_browser_fixtures_ready", scenarios=list(fixtures))


if __name__ == "__main__":
    asyncio.run(run())
