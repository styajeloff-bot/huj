"""Real HTTP/PostgreSQL checks for historical questionnaire default completion.

Run in the isolated #22286 stack: python /e2e/defaults_acceptance.py
All fixtures are newly created applications; no shared application is modified.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, new_application, progress, require

COMPLETED_AT = datetime(2026, 9, 20, 12, 30, tzinfo=UTC)


async def seed_legacy(app_id, *, values=None, sources=None):
    from sqlalchemy import null, update
    from domain.questionnaire import initial_values
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import ApplicationQuestionnaire
    async with AsyncSessionLocal() as session:
        await session.execute(update(ApplicationQuestionnaire).where(
            ApplicationQuestionnaire.application_id == UUID(app_id)
        ).values(**{
            **dict.fromkeys(initial_values().keys() - {"actual_address_same_as_legal"}, null()),
            **(values or {}),
            "field_sources": sources or {},
            "questionnaire_completed_at": COMPLETED_AT,
        }))
        await session.commit()


async def run():
    guard()
    from domain.questionnaire import initial_values
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    expected = initial_values()

    # Real creation route and an older application with no questionnaire both
    # enter the shared upsert and get the same persisted initial field values.
    created = await api.request("client", "POST", "/api/v1/applications", expected=201, json={
        "company_id": state["companies"]["client"]["company_id"],
        "source_type": "platform", "name": "Defaults 22286",
        "vehicles": [{"modification_id": "questionnaire22286-model", "custom_price": "1000000", "is_model_order": True}],
    }, headers={"Idempotency-Key": str(uuid4())})
    fresh = await db_questionnaire(created["application_id"])
    require(all(fresh[key] == value for key, value in expected.items()), "New application defaults missing")
    require(fresh["questionnaire_completed_at"] is None, "Creation marked questionnaire delivered")

    app_id = await new_application(state)
    url = f"/api/v1/questionnaire/{app_id}"
    await api.request("client", "PUT", url, json={"full_company_name": "Initial defaults fixture"})
    first = await db_questionnaire(app_id)
    require(all(first[key] == value for key, value in expected.items()), "First shared upsert has no defaults")
    qid = first["id"]

    await seed_legacy(app_id)
    before = await db_questionnaire(app_id)
    await api.request(None, "PUT", url, expected=401, json={"full_company_name": "Forbidden"})
    await api.request("outsider", "PUT", url, expected=(403, 404), json={"full_company_name": "Forbidden"})
    denied = await db_questionnaire(app_id)
    require(denied == before, "Denied request changed historical defaults")
    await api.request("client", "PUT", url, expected=422, json={"website_in_blocked_domains_registry": "false"})
    require(await db_questionnaire(app_id) == before, "Invalid request changed historical defaults")
    await api.request("client", "PUT", url, json={"full_company_name": "Restored legacy defaults"})
    restored = await db_questionnaire(app_id)
    require(all(restored[key] == value for key, value in expected.items()), "Historical defaults not restored")
    require(restored["id"] == qid and restored["questionnaire_completed_at"] == COMPLETED_AT, "Historical identity or delivery date changed")
    for key, value in expected.items():
        if key == "actual_address_same_as_legal":
            continue  # Added with a persisted NOT NULL default in revision 155.
        # A null filename records no value/source; the status and empty document
        # list record the system default. Equality above still checks the null.
        paths = [f"{key}.{part}" for part, item in value.items() if item is not None] if isinstance(value, dict) else [key]
        require(all(restored["field_sources"].get(path) == "system" for path in paths), "Default source not recorded")

    # Existing false/true/empty JSON and nested explicit clears must be retained.
    documents = [{"document_id": str(uuid4()), "user_title": "Existing contract"}]
    values = {
        "postal_address_matches_legal": True,
        "director_name_changed": False,
        "loans_credits_leasing": {"status": "attached", "text": None, "documents": documents},
        "state_defense_order": {},
        "director_appointment_document": [],
        "third_party_guarantees": None,  # JSON null, protected at its root.
        "additional_collateral_available": None,  # JSON null, protected below the root.
    }
    sources = {
        "website_in_blocked_domains_registry": "manual",
        "director_is_pdl": "document_request",
        "loans_credits_leasing.text": "manual",
        "third_party_guarantees": "document_request",
        "additional_collateral_available.text": "manual",
        "company_email": "manual",
    }
    await seed_legacy(app_id, values=values, sources=sources)
    protected = await db_questionnaire(app_id)
    for index in range(2):
        await api.request("client", "PUT", url, json={"full_company_name": f"Preserved values {index}"})
        current = await db_questionnaire(app_id)
        for key in values.keys() | {"website_in_blocked_domains_registry", "director_is_pdl"}:
            require(current[key] == protected[key], f"Existing value or explicit clear replaced: {key}")
        require(all(current["field_sources"][key] == source for key, source in sources.items()), "Existing provenance changed")
        require(current["id"] == qid and current["questionnaire_completed_at"] == COMPLETED_AT, "Replay changed identity/date")

    # A clear supplied in the same request wins over a default and stays cleared.
    await api.request("client", "PUT", url, json={"director_name_changed": None})
    await api.request("client", "PUT", url, json={"company_email": "defaults@example.test"})
    cleared = await db_questionnaire(app_id)
    require(cleared["director_name_changed"] is None and cleared["field_sources"]["director_name_changed"] == "manual", "New manual clear was defaulted")
    progress("questionnaire_historical_defaults_http_db_passed", application_id=app_id,
        checked="new creation, missing questionnaire, legacy NULL, explicit/nested NULL, false, nonempty/empty JSON, replay, permissions, invalid payload, delivery date")


if __name__ == "__main__":
    asyncio.run(run())
