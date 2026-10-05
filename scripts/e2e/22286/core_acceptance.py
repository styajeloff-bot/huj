"""Real HTTP/DB core questionnaire acceptance; OCR uses explicit technical cache fixtures.

This verifies API rendering/persistence of confidence, not a live DBrain response.
Run: python /e2e/core_acceptance.py
"""
from __future__ import annotations

import asyncio
import io
import json
from urllib.parse import quote
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, progress, require


async def run():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    company_id = state["companies"]["client"]["company_id"]
    request = {"company_id": company_id, "source_type": "platform", "name": "Core 22286", "vehicles": [{"modification_id": "questionnaire22286-model", "custom_price": "1000000", "is_model_order": True}]}
    key = str(uuid4())
    created = await api.request("client", "POST", "/api/v1/applications", expected=201, json=request, headers={"Idempotency-Key": key})
    app_id = created["application_id"]
    replay = await api.request("client", "POST", "/api/v1/applications", expected=(200, 201), json=request, headers={"Idempotency-Key": key})
    require(replay["application_id"] == app_id, "Creation retry duplicated application")
    initial = await db_questionnaire(app_id)
    require(initial is not None, "New application has no questionnaire")
    q_url = f"/api/v1/questionnaire/{app_id}"
    form_url = f"/api/v1/applications/{app_id}/questionnaire"
    qid = initial["id"]
    await api.request(None, "GET", q_url, expected=401)
    await api.request("outsider", "GET", q_url, expected=(403, 404))
    await api.request("outsider", "POST", q_url+"/refresh", expected=(403, 404))
    payload = {
        "full_company_name": "Ручное имя компании", "legal_address": "Москва, улица Первая, 1",
        "company_phone": "+74951234567", "company_email": "core@example.test", "company_website": "https://example.test",
        "postal_address_matches_legal": True, "postal_address": "Поддельное значение",
        "contact_person": {"name": "Контакт Контактов", "position": "Менеджер", "phone": "+74951234568", "email": "contact@example.test"},
        "electronic_document_management_systems": {"sbis": True, "diadoc": False, "kontur": False, "other": True, "other_name": "Своя система", "not_used": False},
        "director_is_pdl": True, "director_pdl_related_person": "Иванов Иван", "director_name_changed": True,
        "questionnaire_completed_at": "2026-01-01T00:00:00Z", "personal_data_processing_consent": [{"text": "Forged"}],
        "loans_credits_leasing": {"status": "attached", "documents": [{"document_id": str(uuid4()), "user_title": "Forged"}]},
    }
    await api.request("client", "PUT", form_url, json=payload)
    current = (await api.request("client", "GET", q_url))["questionnaire"]
    require(current["postal_address"] == payload["legal_address"], "Derived postal address not authoritative")
    require(current["phone"] == payload["contact_person"]["phone"], "Primary contact compatibility lost")
    require(current["questionnaire_completed_at"] is None and not current["personal_data_processing_consent"], "Server-managed field forged")
    require("field_sources" not in current, "Technical sources exposed")
    require(current["loans_credits_leasing"]["status"] == "missing", "Client forged document status")
    require((await db_questionnaire(app_id))["updated_at"] > initial["updated_at"], "Update timestamp unchanged")
    for bad in ({"company_phone": "bad"}, {"company_email": "invalid"}, {"company_website": "https://"}, {"employee_count": -1}, {"postal_address_matches_legal": "true"}, {"registration_date": "2026-02-30"}, {"director_is_pdl": True, "director_pdl_related_person": ""}, {"electronic_document_management_systems": {"other": True, "other_name": ""}}):
        await api.request("client", "PUT", q_url, expected=422, json=bad)
    await api.request("client", "PUT", form_url, json={"director_is_pdl": False, "director_name_changed": False, "electronic_document_management_systems": {"not_used": True, "sbis": True, "other": True, "other_name": "obsolete"}, "company_website": None, "legal_address": "Москва, улица Вторая, 2"})
    current = (await api.request("client", "GET", q_url))["questionnaire"]
    require(current["director_pdl_related_person"] is None and current["director_name_changed"] is False, "PDL/name checkbox reset failed")
    require(current["postal_address"] == current["legal_address"], "Postal address did not follow legal address")
    require(current["electronic_document_management_systems"]["sbis"] is False, "EDO exclusivity failed")
    refreshed = await api.request("client", "POST", q_url+"/refresh")
    require(refreshed["questionnaire"]["full_company_name"] == payload["full_company_name"] and refreshed["questionnaire"]["company_website"] is None, "Refresh replaced manual value or clear")
    require(refreshed["sources"]["fns"] in {"updated", "unavailable"}, "Unexpected fixture source status")
    second = await api.request("client", "POST", "/api/v1/applications", expected=201, json=request, headers={"Idempotency-Key": str(uuid4())})
    require((await db_questionnaire(second["application_id"]))["id"] != qid, "Another application reused questionnaire")
    require((await db_questionnaire(app_id))["id"] == qid, "Existing questionnaire identity changed")
    progress("core_creation_forms_sources_passed", application_id=app_id)

    dictionaries = {}
    for kind, count in (("beneficial_owner_bases", 8), ("beneficial_owner_absence_reasons", 7)):
        path = "/api/v1/questionnaire-dictionaries/" + kind
        values = (await api.request("client", "GET", path))["items"]
        require(len(values) >= count, "Dictionary seeds missing")
        dictionaries[kind] = {v["code"]: v for v in values}
        await api.request("client", "GET", path+"?include_inactive=true", expected=403)
        await api.request("client", "POST", path, expected=403, json={"code": "forbidden", "name": "Forbidden"})
    path = "/api/v1/questionnaire-dictionaries/beneficial_owner_bases"
    value = await api.request("admin", "POST", path, expected=201, json={"code": "fixture_"+uuid4().hex, "name": "Тестовое основание"})
    basis_id = value["id"]
    person_id = str(uuid4())
    person = {"id": person_id, "full_name": "Ручной Бенефициар Иванович", "inn": "000000000012", "share": "50", "beneficial_owner_basis": basis_id, "is_pdl": True, "pdl_related_person_name": "Родственник", "name_changed": True, "confidence": {"surname": 98}}
    await api.request("client", "PUT", q_url, json={"has_beneficiary": True, "beneficiaries": [person]})
    await api.request("admin", "PATCH", path+"/"+basis_id, json={"name": "Переименованное основание", "is_active": False})
    active = (await api.request("client", "GET", path))["items"]
    require(not any(v["id"] == basis_id for v in active), "Inactive dictionary entry remains selectable")
    historical = (await api.request("client", "GET", path+"?selected_id="+basis_id))["items"]
    require(any(v["id"] == basis_id and v["name"] == "Переименованное основание" for v in historical), "Historical dictionary label lost")
    await api.request("client", "PUT", q_url, json={"beneficiaries": [person]})
    await api.request("client", "PUT", f"/api/v1/questionnaire/{second['application_id']}", expected=422, json={"has_beneficiary": True, "beneficiaries": [person]})
    require("confidence" not in json.dumps((await db_questionnaire(app_id))["beneficiaries"]), "Confidence persisted to questionnaire")
    absence = dictionaries["beneficial_owner_absence_reasons"]["other"]["id"]
    await api.request("client", "PUT", q_url, expected=422, json={"has_beneficiary": False, "no_beneficial_owner_reason": absence})
    await api.request("client", "PUT", q_url, json={"has_beneficiary": False, "no_beneficial_owner_reason": absence, "no_beneficial_owner_reason_details": "Обоснованная причина"})
    require((await db_questionnaire(app_id))["beneficiaries"] == [], "Absence left beneficiary records")
    await api.request("client", "PUT", q_url, json={"has_beneficiary": True, "beneficiaries": [{**person, "beneficial_owner_basis": dictionaries['beneficial_owner_bases']['direct_ownership_over_25']['id']}]})
    require((await db_questionnaire(app_id))["no_beneficial_owner_reason"] is None, "Switching back left absence reason")
    progress("core_dictionaries_beneficiaries_passed")

    await verify_confidence(api, state, app_id, q_url, person_id)
    await verify_founder(api, state)
    await verify_candidate_roles(api, state)
    await verify_legacy_person_identity(api, state)
    await verify_registration_address(api, state)
    await verify_passport_identity(api, state)
    await verify_person_payload_contract(api, state)
    await verify_counterparty_comment(api, state)
    progress("core_acceptance_passed", application_id=app_id, confidence_evidence="technical DB/cache fixtures, not live DBrain")


async def verify_confidence(api, state, app_id, q_url, beneficiary_id):
    from PIL import Image
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import passport_recognition_repository as cache
    from infrastructure.repositories import sopd_passport_snapshot_repository as snapshots
    from infrastructure.services.document_recognition import calculate_file_hash
    from application.services.sopd_passport import map_dbrain
    from application.services.passport_profile_fields import PASSPORT_MAIN_TYPE, PASSPORT_REGISTRATION_TYPE
    await api.request("client", "PUT", q_url, json={"director_full_name": "Тестов Иван Иванович", "director_inn": "000000000001"})
    user_id = UUID(state["users"]["client"]["id"])
    fields = {"surname": "Тестов", "first_name": "Иван", "other_names": "Иванович", "nationality": "Российская Федерация", "sex": "male", "date_of_birth": "1980-01-01", "place_of_birth": "Москва", "series_and_number": "1234 123456", "date_of_issue": "2020-01-01", "subdivision_code": "123-456", "issuing_authority": "УМВД России"}
    raw = {"items": [{"fields": fields, "confidence": {key: 0.98 for key in fields}}]}
    raw["items"][0]["confidence"]["place_of_birth"] = 0
    mapped, confidence = map_dbrain(raw)
    async with AsyncSessionLocal() as session:
        for key in ("000000000001", "beneficiary:"+beneficiary_id):
            await snapshots.upsert_recognition(session, application_id=UUID(app_id), signer_key=key, owner_user_id=user_id, fields={**mapped, **({"_expected_full_name": "Ручной Бенефициар Иванович"} if key.startswith("beneficiary:") else {})}, confidence=confidence)
        await session.commit()
    key = "000000000001"
    path = f"/api/v1/applications/{app_id}/sopd-signers/{quote(key, safe='')}/passport"
    original = await api.request("client", "GET", path)
    require(original["confidence"]["birthPlace"] == 0, "Zero confidence disappeared")
    await api.request("outsider", "GET", path, expected=(403, 404))
    changed = {**original["fields"], "birthPlace": "Казань", "nationality": "Казахстан"}
    draft = await api.request("client", "PATCH", path+"/draft", json={"fields": changed, "editedFields": ["birthPlace", "nationality"]})
    require("birthPlace" not in draft["confidence"] and draft["confidence"]["surname"] == 98, "Edit hid all confidence")
    reloaded = await api.request("client", "GET", path)
    require(reloaded["confidence"] == draft["confidence"] and reloaded["fields"]["birthPlace"] == "Казань", "Reload lost per-field mask")
    confirmed = await api.request("client", "PATCH", path, json={"fields": changed, "editedFields": ["birthPlace", "nationality"]})
    require(confirmed["actionsAllowed"] and confirmed["confidence"]["surname"] == 98, "Confirmation lost unedited confidence")
    q = await db_questionnaire(app_id)
    require(q["director_birth_place"] == "Казань" and q["director_passport_number"] == "123456", "Confirmed passport missing from questionnaire")

    # The real recognition HTTP route consumes explicit cached provider fixtures.
    image = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(image, format="PNG")
    image_bytes = image.getvalue()
    async with AsyncSessionLocal() as session:
        for passport_type in (PASSPORT_MAIN_TYPE, PASSPORT_REGISTRATION_TYPE):
            if await cache.get_cached(session, user_id=user_id, file_hash=calculate_file_hash(image_bytes), passport_type=passport_type) is None:
                await cache.save(session, user_id=user_id, file_hash=calculate_file_hash(image_bytes), passport_type=passport_type, raw_data=raw, mapped_data=mapped, confidence_data=confidence, recognition_task_id=None)
        await session.commit()
    recognition_path = path.replace("/passport", "/passport-recognition")
    result = await api.request("client", "POST", recognition_path, files={"passport_main": ("main.png", image_bytes, "image/png"), "passport_registration": ("registration.png", image_bytes, "image/png")})
    require(
        result["fields"]["birthPlace"] == "Москва"
        and result["fields"]["nationality"] == "Казахстан"
        and result["confidence"]["birthPlace"] == 0
        and result["confidence"]["surname"] == 98
        and result["editedFields"] == [],
        "OCR did not atomically replace manual fields while preserving only citizenship",
    )
    from infrastructure.repositories import documents_repository
    async with AsyncSessionLocal() as session:
        documents = await documents_repository.list_for_application(session, application_id=UUID(app_id))
        passports = [row for row in documents if row["document_type"].startswith("sopd_passport_")]
        require(len(passports) == 2, "Passport images not attached to application")
        require({row["file_name"] for row in passports} == {"main.png", "registration.png"}, "Original passport filenames lost")
        ids = {row["id"] for row in passports}
    for document in passports:
        await api.request("client", "GET", f"/api/v1/documents/{document['id']}/content", raw=True)
        await api.request("outsider", "GET", f"/api/v1/documents/{document['id']}/content", expected=(403, 404), raw=True)
    await api.request("client", "POST", recognition_path, files={"passport_main": ("main.png", image_bytes, "image/png"), "passport_registration": ("registration.png", image_bytes, "image/png")})
    async with AsyncSessionLocal() as session:
        documents = await documents_repository.list_for_application(session, application_id=UUID(app_id))
        require({row["id"] for row in documents if row["document_type"].startswith("sopd_passport_")} == ids, "Repeated OCR duplicated passport files")
    beneficiary_path = f"/api/v1/applications/{app_id}/sopd-signers/beneficiary%3A{beneficiary_id}/passport"
    beneficiary_preview = await api.request("client", "GET", beneficiary_path)
    require(beneficiary_preview["nameMismatch"], "Beneficiary name mismatch not exposed")
    rejected = await api.request("client", "PATCH", beneficiary_path, expected=422, json={"fields": mapped, "editedFields": []})
    require(rejected["detail"]["code"] == "PASSPORT_NAME_MISMATCH", "Mismatched OCR was rejected for an unrelated reason")
    matching = {**mapped, "surname": "Ручной", "name": "Бенефициар", "patronymic": "Иванович"}
    # A subsequent upload supplies a new, matching OCR snapshot; editing manual
    # fields must not bypass the immutable name check for the original upload.
    async with AsyncSessionLocal() as session:
        await snapshots.upsert_recognition(session, application_id=UUID(app_id),
            signer_key="beneficiary:" + beneficiary_id, owner_user_id=user_id,
            fields={**matching, "_expected_full_name": "Ручной Бенефициар Иванович"}, confidence=confidence)
        await session.commit()
    await api.request("client", "PATCH", beneficiary_path, json={"fields": matching, "editedFields": []})
    beneficiary = next(person for person in (await db_questionnaire(app_id))["beneficiaries"] if person["id"] == beneficiary_id)
    require(beneficiary["full_name"] == "Ручной Бенефициар Иванович" and beneficiary["passport_number"] == "123456", "Beneficiary passport projection missing")
    require("confidence" not in json.dumps(beneficiary), "Beneficiary contains confidence")
    foreign = {**mapped, "nationality": "Казахстан", "passportSeries": "AB-X", "passportNumber": "KZ/A-123456789", "code": "FOREIGN-ABC"}
    await api.request("client", "PATCH", path, json={"fields": foreign, "editedFields": ["nationality", "passportSeries", "passportNumber", "code"]})
    require((await db_questionnaire(app_id))["director_passport_number"] == foreign["passportNumber"], "Foreign passport rejected or truncated")
    progress("core_passport_confidence_api_passed")


async def verify_founder(api, state):
    from acceptance import new_application
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import sopd_passport_snapshot_repository as snapshots
    from application.services.sopd_passport import FIELDS
    app_id = await new_application(state)
    founder_id = str(uuid4())
    signer_key = "000000000099"
    payload = {"director_full_name": "Тестов Иван Иванович", "director_inn": "000000000001",
        "founders": [{"id": founder_id, "name": "Тестов Иван Иванович", "inn": signer_key, "share": "40"}]}
    await api.request("client", "PUT", f"/api/v1/questionnaire/{app_id}", json=payload)
    fields = dict.fromkeys(FIELDS)
    fields.update(surname="Тестов", name="Иван", patronymic="Иванович", nationality="Российская Федерация", gender="male", birthDate="1980-01-01", birthPlace="Москва", passportSeries="1234", passportNumber="123456", givenDate="2020-01-01", code="123-456", givenWhom="УМВД России")
    async with AsyncSessionLocal() as session:
        await snapshots.upsert_recognition(session, application_id=UUID(app_id), signer_key=signer_key, owner_user_id=UUID(state["users"]["client"]["id"]), fields=fields, confidence={"surname": 98, "name": 97})
        await session.commit()
    path = f"/api/v1/applications/{app_id}/sopd-signers/{signer_key}/passport"
    await api.request("client", "PATCH", path, json={"fields": fields, "editedFields": []})
    first = next(person for person in (await db_questionnaire(app_id))["founders"] if person["id"] == founder_id)
    require(first["name"] == "Тестов Иван Иванович" and first["passport_number"] == "123456", "Raw INN founder mapped to wrong collection")
    changed = {**fields, "surname": "Тестова"}
    result = await api.request("client", "PATCH", path, json={"fields": changed, "editedFields": ["surname"]})
    require("surname" not in result["confidence"] and result["confidence"]["name"] == 97, "Founder manual confidence mask failed")
    person = next(person for person in (await db_questionnaire(app_id))["founders"] if person["id"] == founder_id)
    require(person["name"] == "Тестова Иван Иванович" and person["full_name"] == person["name"], "Founder name/full_name aliases diverged after manual correction")
    require(person["signer_key"] == signer_key, "Founder opaque key changed")
    progress("core_founder_raw_inn_alias_passed", application_id=app_id)


async def verify_candidate_roles(api, state):
    from acceptance import new_application
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import signature_request_repository as signatures
    from application.services.sopd_passport import FIELDS
    app_id = await new_application(state)
    q_url = f"/api/v1/questionnaire/{app_id}"
    basis = (await api.request("client", "GET", "/api/v1/questionnaire-dictionaries/beneficial_owner_bases"))["items"][0]["id"]
    beneficiary_id, representative_id = str(uuid4()), str(uuid4())
    full_name = "Тестов Иван Иванович"
    await api.request("client", "PUT", q_url, json={
        "director_full_name": full_name, "director_inn": "000000000001", "has_beneficiary": True,
        "beneficiaries": [{"id": beneficiary_id, "full_name": full_name, "share": 40, "beneficial_owner_basis": basis}],
        "other_representatives": [{"id": representative_id, "full_name": full_name}],
    })
    candidates_path = f"/api/v1/applications/{app_id}/sopd-signer-candidates"
    await api.request("outsider", "GET", candidates_path, expected=(403, 404))
    candidates = (await api.request("client", "GET", candidates_path))["candidates"]
    by_role = {person["role"]: person for person in candidates}
    require({"director_applicant", "beneficiary", "representative"} <= by_role.keys(), "Candidate roles missing")
    require(by_role["beneficiary"]["share"] == "40", "Numeric beneficiary share broke textual HTTP contract")
    require(by_role["representative"]["share"] is None, "Absent representative share became a value")
    fields = dict.fromkeys(FIELDS)
    fields.update(surname="Тестов", name="Иван", patronymic="Иванович", nationality="Российская Федерация", gender="male", birthDate="1980-01-01", birthPlace="Москва", passportSeries="1234", passportNumber="123456", givenDate="2020-01-01", code="123-456", givenWhom="УМВД России")
    for role, person_id, collection in (("beneficiary", beneficiary_id, "beneficiaries"), ("representative", representative_id, "other_representatives")):
        candidate = by_role[role]
        require(candidate["key"] == role+":"+person_id, "Candidate opaque UUID key changed")
        path = f"/api/v1/applications/{app_id}/sopd-signers/{quote(candidate['key'], safe='')}/passport"
        invitation = {"company_id": state["companies"]["client"]["company_id"], "application_id": app_id,
            "signers": [{"signerKey": candidate["key"], "full_name": full_name}]}
        await api.request("client", "POST", "/api/v1/signatures/invite", expected=409, json=invitation)
        await api.request("outsider", "PATCH", path, expected=(403, 404), json={"fields": fields, "editedFields": list(FIELDS)})
        confirmed = await api.request("client", "PATCH", path, json={"fields": fields, "editedFields": list(FIELDS)})
        require(confirmed["actionsAllowed"] and confirmed["confidence"] is None, "Manual role passport did not confirm")
        person = next(person for person in (await db_questionnaire(app_id))[collection] if person["id"] == person_id)
        require(person["passport_number"] == "123456", "Manual role passport projected to wrong collection")
        result = (await api.request("client", "POST", "/api/v1/signatures/invite", json=invitation))["results"][0]
        require(result["mode"] == "physical" and not result["magic_link_sent"], "Paper invitation changed track")
        async with AsyncSessionLocal() as session:
            request = await signatures.get_by_id(session, UUID(result["signature_request_ids"][0]))
        require(request["subject_snapshot"]["role"] == role, "Invitation lost candidate role")
        require(request["subject_snapshot"]["share"] == candidate["share"], "Invitation lost normalized share")
        bound_path = f"/api/v1/signatures/{result['signature_request_ids'][0]}/passport"
        bound = await api.request("client", "GET", bound_path)
        require(bound["signerKey"] == candidate["key"] and bound["actionsAllowed"], "Bound passport response rejected candidate role")
    progress("core_candidate_roles_manual_passport_invite_passed", application_id=app_id)


async def verify_legacy_person_identity(api, state):
    from acceptance import new_application
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import ApplicationQuestionnaire, LeasingApplication
    from infrastructure.models.companies import Company
    app_id = await new_application(state)
    legacy = {"inn": "000000009901", "name": "Ручное имя старой карточки", "share": None}
    async with AsyncSessionLocal() as session:
        company = await session.scalar(select(Company).where(Company.inn == "0000992286"))
        if company is None:
            company = Company(id=uuid4(), name="22286 legacy identity fixture", inn="0000992286", company_type="other", is_active=True)
            session.add(company)
            await session.flush()
        application = await session.get(LeasingApplication, UUID(app_id))
        application.company_id = company.id
        session.add(ApplicationQuestionnaire(
            id=uuid4(), application_id=UUID(app_id), founders=[legacy],
            beneficiaries=[{"full_name": "Бенефициар без идентификаторов", "birth_place": None}],
            other_representatives=[{"signer_key": "representative:legacy-key", "full_name": "Представитель старой карточки"}],
            field_sources={"founders.000000009901.name": "manual", "founders.000000009901.share": "manual",
                "founders.000000009902": "manual", "beneficiaries.0.full_name": "manual",
                "beneficiaries.0.birth_place": "manual", "other_representatives.representative:legacy-key.full_name": "manual"},
        ))
        await session.commit()
    path = f"/api/v1/questionnaire/{app_id}"
    ids = None
    for attempt in range(2):
        response = await api.request("admin", "POST", path+"/refresh")
        require(response["sources"]["fns"] == "updated", "Legacy identity fixture provider unavailable")
        q = response["questionnaire"]
        require("people_identity_map" not in q and "field_sources" not in q, "Technical identity registry exposed")
        require(len(q["founders"]) == 1, "Legacy tombstone resurrected an imported founder")
        founder = q["founders"][0]
        require(founder["name"] == legacy["name"] and founder["share"] is None, "Consecutive import overwrote legacy manual text/null")
        current_ids = {field: [str(UUID(person["id"])) for person in q[field]] for field in ("founders", "beneficiaries", "other_representatives")}
        if ids is None:
            ids = current_ids
        require(ids == current_ids, "Person UUID changed between automatic refreshes")
        stored = await db_questionnaire(app_id)
        for source_path in stored["field_sources"]:
            prefix, dot, tail = source_path.partition(".")
            if dot and prefix in current_ids:
                require(str(UUID(tail.split(".", 1)[0])) == tail.split(".", 1)[0], "Legacy source/tombstone key survived normalization")
        require(stored["field_sources"][f"founders.{founder['id']}.share"] == "manual", "Manual null source was not migrated")
    await api.request("admin", "PUT", path, json={"founders": [], "people_identity_map": {"forged": True}})
    for _ in range(2):
        response = await api.request("admin", "POST", path+"/refresh")
        require(response["questionnaire"]["founders"] == [], "Deleted UUID founder reappeared under provider UUID")
    require("forged" not in (await db_questionnaire(app_id))["people_identity_map"], "Client rewrote identity registry")
    # Old clients may resend cards without IDs; their unambiguous import alias
    # resolves to the persisted UUID rather than generating another entity.
    await api.request("admin", "PUT", path, json={"founders": [{**legacy, "name": "Ручное исправление без ID"}]})
    for _ in range(2):
        q = (await api.request("admin", "POST", path+"/refresh"))["questionnaire"]
        require(len(q["founders"]) == 1 and q["founders"][0]["id"] == ids["founders"][0], "Legacy re-add changed stable UUID")
        require(q["founders"][0]["name"] == "Ручное исправление без ID" and q["founders"][0]["share"] is None, "Re-add lost manual precedence")
    await api.request("outsider", "GET", path, expected=(403, 404))
    progress("core_legacy_person_uuid_refresh_tombstone_passed", application_id=app_id)


async def identities_only():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    await verify_legacy_person_identity(API(state), state)


async def candidates_only():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    await verify_candidate_roles(API(state), state)



async def projection_application(api, state):
    created = await api.request("client", "POST", "/api/v1/applications", expected=201,
        headers={"Idempotency-Key": str(uuid4())}, json={
            "company_id": state["companies"]["client"]["company_id"],
            "source_type": "platform", "name": "22286 passport projection regression",
            "vehicles": [{"modification_id": "questionnaire22286-model", "custom_price": "1000000", "is_model_order": True}],
        })
    app_id = created["application_id"]
    await api.request("client", "PUT", f"/api/v1/questionnaire/{app_id}", json={
        "director_full_name": "Тестов Иван Иванович", "director_inn": "000000000001",
    })
    return app_id


def projection_passport_fields():
    return {"surname": "Тестова", "name": "Анна", "patronymic": "Ивановна",
        "nationality": "Российская Федерация", "gender": "female", "birthDate": "1990-01-01",
        "birthPlace": "Москва", "passportSeries": "1234", "passportNumber": "987654",
        "givenDate": "2020-01-01", "code": "123-456", "givenWhom": "УМВД России"}


async def verify_registration_address(api, state):
    from PIL import Image
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import passport_recognition_repository as cache
    from infrastructure.services.document_recognition import calculate_file_hash
    from application.services.sopd_passport import map_dbrain
    from application.services.passport_profile_fields import PASSPORT_MAIN_TYPE, PASSPORT_REGISTRATION_TYPE
    app_id = await projection_application(api, state)
    q_url = f"/api/v1/questionnaire/{app_id}"
    person_id = str(uuid4())
    person = {"id": person_id, "full_name": "Тестова Анна Ивановна", "share": "40"}
    await api.request("client", "PUT", q_url, json={"has_beneficiary": True, "beneficiaries": [person]})
    passport_url = f"/api/v1/applications/{app_id}/sopd-signers/beneficiary%3A{person_id}/passport"
    raw_main = {"items": [{"fields": {
        "surname": "Тестова", "first_name": "Анна", "other_names": "Ивановна",
        "nationality": "Российская Федерация", "sex": "female", "date_of_birth": "1990-01-01",
        "place_of_birth": "Москва", "series_and_number": "1234 987654", "date_of_issue": "2020-01-01",
        "subdivision_code": "123-456", "issuing_authority": "УМВД России",
    }}]}

    async def recognize_and_confirm(address):
        buffer = io.BytesIO()
        Image.new("RGB", (36, 36), tuple(uuid4().bytes[:3])).save(buffer, format="PNG")
        content = buffer.getvalue()
        raw_registration = {"items": [{"fields": {"registration_address": {"text": address, "confidence": 0.96}}}]}
        async with AsyncSessionLocal() as session:
            for passport_type, raw in ((PASSPORT_MAIN_TYPE, raw_main), (PASSPORT_REGISTRATION_TYPE, raw_registration)):
                mapped, confidence = map_dbrain(raw)
                await cache.save(session, user_id=UUID(state["users"]["client"]["id"]),
                    file_hash=calculate_file_hash(content), passport_type=passport_type,
                    raw_data=raw, mapped_data=mapped, confidence_data=confidence, recognition_task_id=None)
            await session.commit()
        recognized = await api.request("client", "POST", passport_url.replace("/passport", "/passport-recognition"),
            files={"passport_main": ("main.png", content, "image/png"), "passport_registration": ("registration.png", content, "image/png")})
        require("registration_address" not in recognized["fields"], "Technical registration metadata changed the passport form contract")
        await api.request("client", "PATCH", passport_url, json={"fields": recognized["fields"], "editedFields": []})
        result = (await api.request("client", "GET", q_url))["questionnaire"]
        require(len(result["beneficiaries"]) == 1 and result["beneficiaries"][0]["id"] == person_id, "OCR replaced or duplicated the person")
        return result["beneficiaries"][0]

    result = await recognize_and_confirm("Москва, улица Регистрации, дом 1")
    require(result.get("registration_address") == "Москва, улица Регистрации, дом 1", "Registration-page OCR address did not reach the beneficiary")
    require(result["sex"] == "female" and result["passport_number"] == "987654", "Female passport projection changed")
    for manual in ("Ручной адрес, дом 2", None):
        current = (await api.request("client", "GET", q_url))["questionnaire"]["beneficiaries"][0]
        await api.request("client", "PUT", q_url, json={"beneficiaries": [{**current, "registration_address": manual}]})
        result = await recognize_and_confirm("Адрес следующего OCR, дом 3")
        require(result.get("registration_address") == manual, "Repeated OCR overwrote a manual address or explicit clear")
    await api.request("outsider", "GET", passport_url, expected=(403, 404))
    progress("beneficiary_registration_ocr_manual_precedence_passed", application_id=app_id)


async def verify_passport_identity(api, state):
    app_id = await projection_application(api, state)
    q_url = f"/api/v1/questionnaire/{app_id}"
    wrong_id, target_id = str(uuid4()), str(uuid4())
    signer_key = "beneficiary:" + target_id
    wrong = {"id": wrong_id, "full_name": "Другая Анна Ивановна", "signer_key": signer_key}
    target = {"id": target_id, "full_name": "Тестова Анна Ивановна"}
    await api.request("client", "PUT", q_url, json={"has_beneficiary": True, "beneficiaries": [wrong, target]})
    path = f"/api/v1/applications/{app_id}/sopd-signers/{quote(signer_key, safe='')}/passport"
    fields = projection_passport_fields()
    await api.request("outsider", "PATCH", path, expected=(403, 404), json={"fields": fields})
    await api.request("client", "PATCH", path, json={"fields": fields, "editedFields": []})
    current = (await api.request("client", "GET", q_url))["questionnaire"]
    people = {person["id"]: person for person in current["beneficiaries"]}
    require(people[target_id].get("passport_number") == fields["passportNumber"], "A conflicting signer_key stole the canonical UUID passport")
    require(not people[wrong_id].get("passport_number") and len(people) == 2, "Passport wrote another person or fabricated a card")
    candidates = (await api.request("client", "GET", f"/api/v1/applications/{app_id}/sopd-signer-candidates"))["candidates"]
    require(next(item for item in candidates if item["key"] == signer_key)["full_name"] == target["full_name"], "Candidate key names another UUID card")
    other_app_id = await projection_application(api, state)
    await api.request("client", "PATCH", path.replace(app_id, other_app_id), expected=(403, 404),
        json={"fields": fields, "editedFields": []})
    invitation = await api.request("client", "POST", "/api/v1/signatures/invite", json={
        "company_id": state["companies"]["client"]["company_id"], "application_id": app_id,
        "signers": [{"signerKey": signer_key, "full_name": target["full_name"]}],
    })
    request_id = invitation["results"][0]["signature_request_ids"][0]
    await api.request("client", "PUT", q_url, json={"beneficiaries": [people[wrong_id]]})
    before = (await api.request("client", "GET", q_url))["questionnaire"]
    await api.request("client", "PATCH", f"/api/v1/signatures/{request_id}/passport", expected=(404, 409),
        json={"fields": {**fields, "passportNumber": "111111"}, "editedFields": ["passportNumber"]})
    require((await api.request("client", "GET", q_url))["questionnaire"] == before, "A deleted bound signer was recreated or projected onto another person")

    founder_key = "000000000099"
    founders = [{"id": str(uuid4()), "name": name, "inn": founder_key, "share": "40"}
                for name in ("Тестова Анна Ивановна", "Другая Анна Ивановна")]
    await api.request("client", "PUT", q_url, json={"founders": founders})
    before = (await api.request("client", "GET", q_url))["questionnaire"]
    founder_path = f"/api/v1/applications/{app_id}/sopd-signers/{founder_key}/passport"
    await api.request("client", "PATCH", founder_path, expected=(404, 409), json={"fields": fields})
    require((await api.request("client", "GET", q_url))["questionnaire"] == before, "An ambiguous legacy INN selected the first founder")
    # A management-company director can confirm an existing bound SOPD without
    # inventing an unrelated representative card in the application questionnaire.
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.signature_requests import SignatureRequest
    from infrastructure.models.sopd_passport_snapshots import SopdPassportSnapshot
    user_id = UUID(state["users"]["client"]["id"])
    management_request_id = uuid4()
    async with AsyncSessionLocal() as session:
        session.add(SignatureRequest(id=management_request_id, application_id=UUID(app_id),
            user_id=user_id, invited_by_user_id=user_id, document_type="sopd", status="pending",
            subject_snapshot={"role": "director_management_company", "signer_key": "000000000077"}))
        await session.flush()
        session.add(SopdPassportSnapshot(application_id=UUID(app_id), signer_key="000000000077",
            signature_request_id=management_request_id, owner_user_id=user_id,
            recognition_fields=fields, recognition_confidence={}, draft_fields=fields,
            confirmed_fields=fields, has_unsaved_changes=False))
        await session.commit()
    confirmed = await api.request("client", "PATCH", f"/api/v1/signatures/{management_request_id}/passport",
        json={"fields": fields, "editedFields": []})
    require(confirmed["actionsAllowed"], "Management-company SOPD confirmation lost its existing contract")
    require((await api.request("client", "GET", q_url))["questionnaire"] == before, "Management-company passport fabricated a questionnaire card")
    progress("passport_uuid_identity_collision_and_deleted_target_passed", application_id=app_id)


async def verify_person_payload_contract(api, state):
    from acceptance import new_application
    app_id = await new_application(state)
    url = f"/api/v1/questionnaire/{app_id}"
    form_url = f"/api/v1/applications/{app_id}/questionnaire"
    people = {
        kind: {"id": str(uuid4()), "full_name": f"Проверка {kind}", "share_percentage": 30}
        for kind in ("founders", "beneficiaries", "other_representatives")
    }
    await api.request("client", "PUT", url, json={
        "director_full_name": "Тестов Иван Иванович", "director_inn": "000000000001",
        "has_beneficiary": True, "company_phone": "+74951234567",
        **{kind: [person] for kind, person in people.items()},
    })
    rejected = 0
    invalid_fields = (
        ("full_name", 123), ("name", ["Имя"]), ("inn", 123456789012),
        ("passport_number", {"number": "123456"}), ("registration_address", True),
        ("pdl_related_person_name", []), ("is_pdl", "false"), ("name_changed", 1),
        ("no_patronymic", "true"), ("actual_same_as_registration", 0),
        ("birth_date", 19800101), ("birth_date", "2026-02-30"),
        ("passport_issue_date", "31.02.2020"), ("registration_date", {}),
        ("id", 123), ("id", "not-a-uuid"), ("beneficial_owner_basis", 123),
        ("beneficial_owner_basis", "not-a-uuid"),
    )
    invalid_shares = ("100.0000000000000001", "-0.0000000000000001", -1, 101, "NaN", "Infinity", "-Infinity", True, False, {}, [])

    async def reject_unchanged(kind, changes):
        nonlocal rejected
        before = await db_questionnaire(app_id)
        response = await api.request("client", "PUT", url if rejected % 2 == 0 else form_url,
            expected=422, json={"company_phone": "+74950000001", kind: [{**people[kind], **changes}]})
        require(bool(response.get("detail")), f"{kind}/{changes} returned no validation message")
        require(await db_questionnaire(app_id) == before, f"Rejected {kind}/{changes} partially persisted")
        rejected += 1

    for kind, person in people.items():
        for field, value in invalid_fields:
            await reject_unchanged(kind, {field: value})
        for field in ("share", "share_percentage"):
            for value in invalid_shares:
                # Keep the other alias valid to detect validation bypasses.
                await reject_unchanged(kind, {"share": 30, "share_percentage": 30, field: value})
        for field in ("share", "share_percentage"):
            for value, expected in ((0, 0), (100, 100), (25.5, 25.5), ("0", 0), ("100", 100), ("25.5", 25.5), (None, None), ("", None)):
                await api.request("client", "PUT", url, json={kind: [{**person, field: value}]})
                saved = next(item for item in (await db_questionnaire(app_id))[kind] if item["id"] == person["id"])
                require(saved.get(field) == expected and not isinstance(saved.get(field), str),
                    f"{kind}.{field} failed numeric boundary/clearing: {value!r} -> {saved.get(field)!r}")
        await api.request("client", "PUT", url, json={kind: [{**person,
            "birth_date": "29.02.2000", "passport_issue_date": "2020-01-01",
            "registration_date": "", "is_pdl": False, "name_changed": True,
            "registration_address": None, "beneficial_owner_basis": None,
        }]})
        saved = next(item for item in (await db_questionnaire(app_id))[kind] if item["id"] == person["id"])
        require(saved["birth_date"] == "2000-02-29" and saved["passport_issue_date"] == "2020-01-01",
            "Valid dates were not normalized")
        require(saved["name_changed"] is True and saved["registration_address"] is None,
            "Valid nested values/clearing lost")
    candidates = await api.request("client", "GET", f"/api/v1/applications/{app_id}/sopd-signer-candidates")
    require(candidates["candidates"] and all(isinstance(item["full_name"], str) for item in candidates["candidates"]),
        "Valid questionnaire no longer produces signer candidates")
    progress("person_nested_types_exact_shares_atomic_http_db_passed", application_id=app_id,
        rejected_payloads=rejected, collections=list(people), checked="both PUT routes, atomic 422, Decimal boundaries, both aliases, dates, clearing, signer candidates")


async def verify_counterparty_comment(api, state):
    from consent_document_acceptance import new_application
    app_id = await new_application(state)
    await api.request("lc_a", "POST", f"/api/v1/leasing/applications/{app_id}/take-in-work")
    history_url = f"/api/v1/applications/{app_id}/document-requests"

    async def request():
        result = await api.request("lc_a", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
            json={"requestedDocuments": [{"source": "catalog", "document_type": "main_counterparties", "display_name": "Контрагенты с комментарием"}]})
        return result["items"][0]["id"]

    async def answer(request_id, rows, expected=201):
        return await api.request("client", "POST", "/api/v1/documents", expected=expected,
            data={"application_id": app_id, "document_request_id": request_id,
                "form_data": json.dumps({"counterparties": rows}, ensure_ascii=False)},
            headers={"Idempotency-Key": str(uuid4())})

    base = {"name": "Поставщик без комментария", "inn": "7700000000"}
    old_id = await request()
    await answer(old_id, [base])
    current_id = await request()
    for extra in ({"comment": 123}, {"comment": True}, {"comment": []}, {"comment": {}}, {"unexpected": "value"}):
        before = await db_questionnaire(app_id)
        history_before = await api.request("client", "GET", history_url)
        await answer(current_id, [{**base, **extra}], 422)
        require(await db_questionnaire(app_id) == before, "Invalid counterparty response changed questionnaire")
        require(await api.request("client", "GET", history_url) == history_before, "Invalid counterparty response changed request history")
    rows = [
        {"name": "Поставщик с комментарием", "inn": "770000000001", "comment": "  Поставка техники по договору № 41  "},
        {**base, "comment": None},
        {"name": "Пустой комментарий", "inn": "7700000002", "comment": "   "},
    ]
    expected = [{**rows[0], "comment": rows[0]["comment"].strip()}, base, {"name": rows[2]["name"], "inn": rows[2]["inn"]}]
    await answer(current_id, rows)
    stored = await db_questionnaire(app_id)
    require(stored["main_counterparties"] == expected, "Optional comment was lost or old row shape changed")
    response = await api.request("client", "GET", f"/api/v1/questionnaire/{app_id}")
    require(response["questionnaire"]["main_counterparties"] == expected, "Assembled questionnaire lost comments")
    history = await api.request("client", "GET", history_url)
    items = {item["id"]: item for batch in history["batches"] for item in batch["items"]}
    require(items[old_id]["form_data"] == {"counterparties": [base]}, "Historical no-comment response changed")
    require(items[current_id]["form_data"] == {"counterparties": expected} and not items[current_id]["attachments"], "History lost comment or unexpectedly required files")
    progress("counterparty_optional_comment_http_db_history_passed", application_id=app_id,
        checked="old no-comment, optional string/null/empty, invalid types/unknown keys, atomic 422, persistence, history, assembled projection")


async def audit_only():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    await verify_person_payload_contract(api, state)
    await verify_counterparty_comment(api, state)


async def projection_only(kind):
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    if kind == "registration-address":
        await verify_registration_address(api, state)
    else:
        await verify_passport_identity(api, state)

async def founder_only():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    await verify_founder(API(state), state)


if __name__ == "__main__":
    import sys
    asyncio.run(audit_only() if "audit" in sys.argv else projection_only(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] in {"registration-address", "passport-identity"} else identities_only() if "identities" in sys.argv else candidates_only() if "candidates" in sys.argv else founder_only() if "founder" in sys.argv else run())
