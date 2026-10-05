"""Foreign company name through real API/DB and an isolated HTTP provider."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, new_application, progress, require


def provider_requests():
    path = ROOT / "provider-requests.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def attributes_requests(rows):
    return [row for row in rows if row.get("includeAttributes") == ["1"]]


async def company_application(state, *, inn, ogrn, name):
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    from infrastructure.models.users import UserCompany

    async with AsyncSessionLocal() as session:
        company = await session.scalar(select(Company).where(Company.ogrn == ogrn))
        if company is None:
            company = Company(id=uuid4(), name=name, inn=inn, ogrn=ogrn, company_type="other", is_active=True)
            session.add(company)
            await session.flush()
        require(company.name == name and company.inn == inn, "Refusing non-fixture company")
        actor_id = UUID(state["users"]["client"]["id"])
        if await session.get(UserCompany, (actor_id, company.id)) is None:
            session.add(UserCompany(user_id=actor_id, company_id=company.id, role="client",
                sub_role="administrator", can_view_applications=True, can_create_applications=True))
        await session.commit()
        owned = deepcopy(state)
        owned["companies"]["client"]["company_id"] = str(company.id)
    return await new_application(owned)


async def verify():
    settings = guard()
    require(settings.parser_api_url == "http://provider-fixture:8080" and settings.parser_api_key == "fixture-only",
        "Refusing non-fixture provider")
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    mode = ROOT / "provider-mode.json"
    previous_mode = mode.read_text() if mode.exists() else json.dumps("success")
    app_id = await new_application(state)
    url = f"/api/v1/questionnaire/{app_id}"
    try:
        mode.write_text(json.dumps("success"))
        before = len(provider_requests())
        first = await api.request("client", "POST", url + "/refresh")
        require(first["sources"]["fns"] == "updated", "FNS lookup not exercised")
        questionnaire = first["questionnaire"]
        require(questionnaire["foreign_company_name"] == "Fixture International One LLC", "Full English attribute was not selected")
        require(questionnaire["employee_count"] == 42, "Optional lookup lost PB fields")
        attributes = attributes_requests(provider_requests()[before:])
        require(len(attributes) == 1 and attributes[0]["inn"] == "0000222861"
            and attributes[0]["ogrn"] is None and attributes[0]["skipPdf"] == ["1"],
            "Attributes lookup must use exact INN and skipPdf")
        stored = await db_questionnaire(app_id)
        identity, created_at = stored["id"], stored["created_at"]
        require(stored["foreign_company_name"] == questionnaire["foreign_company_name"]
            and stored["field_sources"]["foreign_company_name"] == "fns", "FNS name/provenance not persisted")

        mode.write_text(json.dumps("foreign_updated"))
        changed = await api.request("client", "POST", url + "/refresh")
        require(changed["questionnaire"]["foreign_company_name"] == "Fixture International Two LLC", "New automatic attribute was not accepted")
        for value in ("foreign_empty", "foreign_wrong_section", "foreign_conflict", "foreign_not_found",
            "foreign_invalid_shape", "foreign_invalid_json", "foreign_failure", "foreign_unavailable"):
            mode.write_text(json.dumps(value))
            result = await api.request("client", "POST", url + "/refresh")
            require(result["sources"]["fns"] == "updated" and result["questionnaire"]["employee_count"] == 42,
                f"Optional attribute failure discarded useful PB data: {value}")
            require(result["questionnaire"]["foreign_company_name"] == "Fixture International Two LLC",
                f"Optional attribute failure erased saved name: {value}")
        mode.write_text(json.dumps("foreign_duplicate"))
        repeated = await api.request("client", "POST", url + "/refresh")
        require(repeated["questionnaire"]["foreign_company_name"] == "Fixture International One LLC",
            "Identical normalized attributes must not be treated as conflicting")

        before = len(provider_requests())
        mode.write_text(json.dumps("foreign_mismatch"))
        mismatch = await api.request("client", "POST", url + "/refresh")
        require(mismatch["sources"]["fns"] == "not_found" and not attributes_requests(provider_requests()[before:]),
            "Mismatched PB identity triggered extract lookup")
        require(mismatch["questionnaire"]["foreign_company_name"] == "Fixture International One LLC",
            "Mismatched company altered saved foreign name")

        for manual in ("Manual International Name LLC", None):
            await api.request("client", "PUT", url, json={"foreign_company_name": manual})
            mode.write_text(json.dumps("foreign_updated"))
            refreshed = await api.request("client", "POST", url + "/refresh")
            stored = await db_questionnaire(app_id)
            require(refreshed["questionnaire"]["foreign_company_name"] == manual
                and stored["foreign_company_name"] == manual and stored["field_sources"]["foreign_company_name"] == "manual",
                "FNS source overwrote manual name or manual NULL")
        require(stored["id"] == identity and stored["created_at"] == created_at,
            "Refresh changed questionnaire identity/date")
        for actor, expected in ((None, 401), ("outsider", (403, 404))):
            before = len(provider_requests())
            await api.request(actor, "GET", url, expected=expected)
            await api.request(actor, "PUT", url, expected=expected, json={"foreign_company_name": "Forbidden"})
            await api.request(actor, "POST", url + "/refresh", expected=expected)
            require(len(provider_requests()) == before, "Forbidden refresh called the provider")

        mode.write_text(json.dumps("foreign_empty"))
        empty_id = await new_application(state)
        empty = await api.request("client", "POST", f"/api/v1/questionnaire/{empty_id}/refresh")
        require(empty["questionnaire"]["foreign_company_name"] is None, "Empty extract invented a foreign name")
        mode.write_text(json.dumps("success"))
        ogrn = "0000000022286"
        ogrn_app = await company_application(state, inn=None, ogrn=ogrn, name="22286 foreign OGRN fixture")
        before = len(provider_requests())
        result = await api.request("client", "POST", f"/api/v1/questionnaire/{ogrn_app}/refresh")
        require(result["questionnaire"]["foreign_company_name"] == "Fixture International One LLC", "OGRN-only company not enriched")
        attributes = attributes_requests(provider_requests()[before:])
        require(len(attributes) == 1 and attributes[0]["inn"] is None and attributes[0]["ogrn"] == ogrn,
            "OGRN-only lookup did not preserve exact identity")
        ip_app = await company_application(state, inn="000000022286", ogrn="000000000022286", name="22286 foreign IP fixture")
        before = len(provider_requests())
        result = await api.request("client", "POST", f"/api/v1/questionnaire/{ip_app}/refresh")
        require(result["sources"]["fns"] == "updated" and result["questionnaire"]["foreign_company_name"] is None,
            "IP source did not remain usable without an English organization name")
        require(not attributes_requests(provider_requests()[before:]), "IP lookup used legal-entity English-name attributes")
        progress("foreign_name_http_db_identity_manual_errors_permissions_passed", application_id=app_id, live_provider_verified=False)
    finally:
        mode.write_text(previous_mode)


if __name__ == "__main__":
    asyncio.run(verify())
