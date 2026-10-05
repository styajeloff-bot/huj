"""Address linkage via real HTTP and PostgreSQL, with a synthetic FNS provider."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, new_application, progress, require


async def verify():
    guard()
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    from infrastructure.models.users import UserCompany
    from infrastructure.settings import settings

    require(settings.parser_api_url == "http://provider-fixture:8080" and settings.parser_api_key == "fixture-only", "Refusing non-fixture provider")
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    actor_id = UUID(state["users"]["client"]["id"])
    async with AsyncSessionLocal() as session:
        company = await session.scalar(select(Company).where(Company.inn == "0000992287"))
        if company is None:
            company = Company(id=uuid4(), name="22286 address fixture", inn="0000992287", company_type="other", is_active=True)
            session.add(company)
            await session.flush()
        require(company.name == "22286 address fixture", "Refusing non-fixture company")
        if await session.get(UserCompany, (actor_id, company.id)) is None:
            session.add(UserCompany(user_id=actor_id, company_id=company.id, role="client", sub_role="administrator", can_view_applications=True, can_create_applications=True))
        await session.commit()
        owned_state = deepcopy(state)
        owned_state["companies"]["client"]["company_id"] = str(company.id)
    app_id = await new_application(owned_state)
    url = f"/api/v1/questionnaire/{app_id}"
    form_url = f"/api/v1/applications/{app_id}/questionnaire"
    mode = ROOT / "provider-mode.json"
    previous_mode = mode.read_text() if mode.exists() else json.dumps("success")
    try:
        mode.write_text(json.dumps("success"))
        first = await api.request("client", "POST", url + "/refresh")
        require(first["sources"]["fns"] == "updated", "FNS source not exercised")
        require(first["questionnaire"]["actual_address_same_as_legal"] is False, "New questionnaires must start with unlinked addresses")
        legacy_flag = first["questionnaire"]["legal_address_matches_registration"]
        qid = first["questionnaire"]["id"]
        require(first["questionnaire"]["legal_address"] == "Москва, Адрес ФНС, 1", "FNS address fixture missing")
        await api.request("client", "PUT", form_url, json={"actual_address_same_as_legal": True, "actual_address": "Несовместимое значение"})
        current = (await api.request("client", "GET", url))["questionnaire"]
        require(current["actual_address_same_as_legal"] is True and current["actual_address"] == current["legal_address"] == "Москва, Адрес ФНС, 1", "Flag or authoritative linked address not persisted")
        require((await db_questionnaire(app_id))["actual_address_same_as_legal"] is True, "HTTP result differs from stored flag")

        mode.write_text(json.dumps("address_updated"))
        refreshed = await api.request("client", "POST", url + "/refresh")
        require(refreshed["sources"]["fns"] == "updated", "Second FNS response not exercised")
        require(refreshed["questionnaire"]["actual_address"] == refreshed["questionnaire"]["legal_address"] == "Москва, Адрес ФНС, 2", "Linked actual address did not follow the accepted automatic legal address")

        await api.request("client", "PUT", url, json={"actual_address_same_as_legal": False, "actual_address": "Казань, Самостоятельный адрес, 3"})
        mode.write_text(json.dumps("success"))
        refreshed = await api.request("client", "POST", url + "/refresh")
        require(refreshed["questionnaire"]["actual_address_same_as_legal"] is False and refreshed["questionnaire"]["actual_address"] == "Казань, Самостоятельный адрес, 3", "Refresh replaced the separate manual address")
        require(refreshed["questionnaire"]["legal_address"] == "Москва, Адрес ФНС, 1", "Automatic legal address was not updated while unlinked")

        await api.request("client", "PUT", form_url, json={"legal_address": "Казань, Ручной юридический адрес, 4", "actual_address_same_as_legal": True})
        mode.write_text(json.dumps("address_updated"))
        refreshed = await api.request("client", "POST", url + "/refresh")
        require(refreshed["questionnaire"]["actual_address"] == refreshed["questionnaire"]["legal_address"] == "Казань, Ручной юридический адрес, 4", "Refresh replaced the manual legal address or its dependent copy")
        stored = await db_questionnaire(app_id)
        require(stored["field_sources"]["legal_address"] == "manual" and stored["field_sources"]["actual_address"] == "derived", "Address provenance does not reflect the explicit dependency")
        await api.request("client", "PUT", url, json={"actual_address": "Нельзя подменить связанный адрес"})
        current = (await api.request("client", "GET", url))["questionnaire"]
        require(current["actual_address"] == current["legal_address"], "Standalone PUT bypassed the linked-address invariant")

        for invalid in (None, "true", "", 1, []):
            for route in (url, form_url):
                error = await api.request("client", "PUT", route, expected=422, json={"actual_address_same_as_legal": invalid})
                require("логическим значением" in error["detail"], "Invalid flag did not produce an actionable validation error")
        for actor, expected in ((None, 401), ("outsider", (403, 404))):
            await api.request(actor, "GET", url, expected=expected)
            await api.request(actor, "PUT", form_url, expected=expected, json={"actual_address_same_as_legal": False})
            await api.request(actor, "PUT", url, expected=expected, json={"actual_address_same_as_legal": False})
            await api.request(actor, "POST", url + "/refresh", expected=expected)

        await api.request("client", "PUT", form_url, json={"actual_address_same_as_legal": False})
        current = (await api.request("client", "GET", url))["questionnaire"]
        require(current["actual_address_same_as_legal"] is False and current["actual_address"] == "Казань, Ручной юридический адрес, 4", "Unlinking alone erased the last displayed address")
        await api.request("client", "PUT", form_url, json={"actual_address": "Казань, Самостоятельный адрес, 5"})
        await api.request("client", "PUT", form_url, json={"legal_address": "Казань, Другой юридический адрес, 6"})
        current = (await api.request("client", "GET", url))["questionnaire"]
        require(current["actual_address"] == "Казань, Самостоятельный адрес, 5", "Legal address change overwrote the unlinked address")
        require(current["id"] == qid and current["legal_address_matches_registration"] == legacy_flag, "Address linkage changed the questionnaire identity or legacy registration flag")

        await api.request("client", "PUT", url, json={"legal_address": None, "actual_address_same_as_legal": True})
        refreshed = await api.request("client", "POST", url + "/refresh")
        require(refreshed["questionnaire"]["actual_address_same_as_legal"] is True and refreshed["questionnaire"]["legal_address"] is None and refreshed["questionnaire"]["actual_address"] is None, "Refresh replaced explicitly cleared manual legal address")
        progress("address_linkage_http_db_sources_permissions_passed", application_id=app_id, live_provider_verified=False)
    finally:
        mode.write_text(previous_mode)


if __name__ == "__main__":
    asyncio.run(verify())
