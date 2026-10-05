"""Real HTTP/PostgreSQL/S3 acceptance for #22286; fixture database only.

Run in the isolated compose service from /runtime:
    python /e2e/acceptance.py keys|migrate|seed|verify|check
No provider mocks and no external messages are sent by this script.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4, uuid5

ROOT = Path("/runtime")
DATABASE = "questionnaire22286"
ORIGIN = "http://localhost:18286"
MARKER = "questionnaire-22286"


def require(value, message):
    if not value:
        raise AssertionError(message)


def progress(stage, **values):
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False, default=str), flush=True)


def identifier(name):
    return uuid5(UUID("a2222286-0000-4000-8000-000000000001"), name)


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    path.chmod(0o600)


def guard(require_keys=True):
    from infrastructure.settings import settings
    require(settings.db_host == "postgres" and settings.db_name == DATABASE, "Refusing non-fixture DB")
    require(settings.s3_bucket == DATABASE and settings.s3_endpoint == "http://minio:9000", "Refusing non-fixture S3")
    require(settings.jwt_keys_dir == "/runtime/jwt", "Refusing non-fixture JWT keys")
    require(Path.cwd() == ROOT and not (ROOT / ".env").exists(), "Refusing project dotenv")
    require(not settings.dadata_api_key or (
        settings.dadata_api_key == "fixture-only"
        and settings.dadata_api_url == "http://provider-fixture:8080/dadata"
    ), "Refusing external DaData credentials")
    require(not settings.smsc_login and not settings.smtp_host, "Refusing external message credentials")
    if require_keys:
        require((ROOT / "fixture-target.json").exists(), "Initialize fixture keys first")
    return settings


def keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    guard(False)
    marker = ROOT / "fixture-target.json"
    if marker.exists():
        require(json.loads(marker.read_text()) == {"database": DATABASE}, "Refusing another runtime")
    else:
        private_json(marker, {"database": DATABASE})
    directory = ROOT / "jwt"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (directory / "e2e.pem").exists():
        key = ec.generate_private_key(ec.SECP256R1())
        (directory / "e2e.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (directory / "e2e.pub.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    for path in directory.iterdir():
        path.chmod(0o600)
    progress("keys_ready")


def migrate(check=False):
    guard()
    from alembic import command
    from alembic.config import Config
    config = Config("/source/alembic.ini")
    config.set_main_option("script_location", "/source/alembic")
    config.set_main_option("prepend_sys_path", "/source")
    command.upgrade(config, "head")
    if check:
        command.check(config)
    progress("schema_checked" if check else "migrations_applied")


def pdf():
    from reportlab.pdfgen import canvas
    output = io.BytesIO()
    page = canvas.Canvas(output)
    page.drawString(50, 800, "Questionnaire acceptance 22286")
    page.showPage()
    page.save()
    return output.getvalue()


async def seed():
    settings = guard()
    import aioboto3
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company, LeasingCompany, LeasingCompanyUser
    from infrastructure.models.users import User, UserCompany, UserSession
    load_and_validate_key_configuration()
    async with aioboto3.Session().client("s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id, aws_secret_access_key=settings.s3_secret_access_key) as storage:
        buckets = await storage.list_buckets()
        if not any(item["Name"] == DATABASE for item in buckets["Buckets"]):
            await storage.create_bucket(Bucket=DATABASE)
    state = {"database": DATABASE, "users": {}, "companies": {}}
    async with AsyncSessionLocal() as session:
        for index, alias in enumerate(("client", "outsider", "lc_a", "lc_b"), 1):
            company_id = identifier("company/" + alias)
            company = await session.get(Company, company_id)
            if company is None:
                company = Company(id=company_id, name="22286 " + alias, inn=f"000022286{index}",
                    company_type="leasing_company" if alias.startswith("lc_") else "other", is_active=True)
                session.add(company)
                await session.flush()
            require(company.inn == f"000022286{index}", "Fixture company identity changed unexpectedly")
            state["companies"][alias] = {"company_id": str(company_id)}
            if alias.startswith("lc_"):
                lc_id = identifier("lc/" + alias)
                if await session.get(LeasingCompany, lc_id) is None:
                    session.add(LeasingCompany(id=lc_id, company_id=company_id, is_active=True))
                state["companies"][alias]["leasing_company_id"] = str(lc_id)
        await session.flush()
        for index, alias in enumerate(("admin", "client", "outsider", "lc_a", "lc_b"), 1):
            user_id = identifier("user/" + alias)
            role = "carcraft_employee" if alias == "admin" else ("leasing_company" if alias.startswith("lc_") else "client")
            company_id = UUID(state["companies"][alias]["company_id"]) if alias != "admin" else None
            user = await session.get(User, user_id)
            if user is None:
                user = User(id=user_id, name="22286 " + alias, phone=f"+700022286{index:02}", email=alias+"@questionnaire22286.test",
                    role=role, company_id=company_id, is_active=True, phone_verified=True, email_verified=True)
                session.add(user)
                await session.flush()
                if company_id:
                    session.add(UserCompany(user_id=user_id, company_id=company_id, role=role, sub_role="administrator",
                        can_view_applications=True, can_create_applications=True))
                if alias.startswith("lc_"):
                    session.add(LeasingCompanyUser(user_id=user_id, leasing_company_id=UUID(state["companies"][alias]["leasing_company_id"])))
            require(user.name == "22286 " + alias, "Fixture user changed unexpectedly")
            sid = uuid4()
            access, refresh = generate_tokens(user_id, role, company_id, refresh_session_id=sid)
            session.add(UserSession(id=sid, user_id=user_id, refresh_token_hash=hash_refresh_token(refresh),
                expires_at=datetime.now(UTC)+timedelta(days=1), ip_address="127.0.0.1", user_agent=MARKER))
            state["users"][alias] = {"id": str(user_id), "role": role, "company_id": str(company_id) if company_id else None,
                "access_token": access, "refresh_token": refresh, "csrf": secrets.token_urlsafe(24)}
        await session.commit()
    private_json(ROOT / "state.secret.json", state)
    for alias, actor in state["users"].items():
        cookies = [
            {"name": name, "value": value, "domain": "localhost", "path": "/", "expires": time.time()+86400,
                "httpOnly": http, "secure": False, "sameSite": "Lax"}
            for name, value, http in (("accessToken", actor["access_token"], True), ("refreshToken", actor["refresh_token"], True), ("csrfToken", actor["csrf"], False))
        ]
        private_json(ROOT / f"{alias}.storage.json", {"cookies": cookies, "origins": []})
    progress("fixture_users_ready")


async def fix_roles():
    guard()
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.users import UserCompany
    state = json.loads((ROOT / "state.secret.json").read_text())
    async with AsyncSessionLocal() as session:
        for actor in state["users"].values():
            if actor["company_id"]:
                membership = await session.get(UserCompany, (UUID(actor["id"]), UUID(actor["company_id"])))
                require(membership is not None, "Fixture membership missing")
                membership.role = actor["role"]
        await session.commit()
    progress("fixture_membership_roles_ready")


class API:
    def __init__(self, state):
        self.state = state

    async def request(self, actor, method, path, expected=200, raw=False, **kwargs):
        import httpx
        user = self.state["users"].get(actor)
        cookies = {"accessToken": user["access_token"], "csrfToken": user["csrf"]} if user else {}
        headers = {"Origin": ORIGIN}
        if user:
            headers["X-CSRF-Token"] = user["csrf"]
        headers.update(kwargs.pop("headers", {}))
        async with httpx.AsyncClient(base_url="http://backend:3002", trust_env=False, timeout=60, headers=headers, cookies=cookies) as client:
            response = await client.request(method, path, **kwargs)
        allowed = (expected,) if isinstance(expected, int) else expected
        require(response.status_code in allowed, f"{actor} {method} {path}: {response.status_code}; {response.text[:1000]}")
        return response if raw else (response.json() if response.content else None)


async def new_application(state, *, signed=False):
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingApplication
    from infrastructure.models.signature_requests import SignatureRequest
    from infrastructure.models.sopd_operator_snapshots import SopdOperatorSnapshot
    app_id = uuid4()
    lc_ids = [UUID(state["companies"][alias]["leasing_company_id"]) for alias in ("lc_a", "lc_b")]
    async with AsyncSessionLocal() as session:
        session.add(LeasingApplication(id=app_id, company_id=UUID(state["companies"]["client"]["company_id"]),
            created_by=UUID(state["users"]["client"]["id"]), status="active", selected_leasing_companies=lc_ids,
            display_number="22286-"+app_id.hex[:12], name="Анкета E2E"))
        await session.flush()
        if signed:
            request_id = uuid4()
            session.add(SignatureRequest(id=request_id, user_id=UUID(state["users"]["client"]["id"]), application_id=app_id,
                document_type="sopd", status="signed_physical", signed_at=datetime(2024, 2, 29, 10, tzinfo=UTC),
                subject_snapshot={"full_name": "Иванов Иван Иванович", "signer_key": "director"}))
            await session.flush()
            session.add(SopdOperatorSnapshot(signature_request_id=request_id, user_id=UUID(state["users"]["client"]["id"]),
                application_id=app_id, leasing_companies=[{"id": str(item), "name": alias} for item, alias in zip(lc_ids, ("lc_a", "lc_b"), strict=True)],
                contractors=[]))
        await session.commit()
    return str(app_id)


async def db_questionnaire(app_id):
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import application_repository
    async with AsyncSessionLocal() as session:
        return await application_repository.get_questionnaire(session, UUID(app_id))


async def verify():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    lc_a, lc_b = [state["companies"][alias]["leasing_company_id"] for alias in ("lc_a", "lc_b")]
    settings_a = f"/api/v1/leasing/companies/{lc_a}/questionnaire-settings"
    settings_b = f"/api/v1/leasing/companies/{lc_b}/questionnaire-settings"
    await api.request(None, "GET", settings_a, expected=401)
    await api.request("client", "PUT", settings_a, expected=403, json={"fields": []})
    await api.request("admin", "PUT", settings_a, expected=422, json={"fields": [{"field": "unknown", "enabled": True, "required": False}]})
    await api.request("admin", "PUT", settings_a, expected=422, json={"fields": [{"field": "company_email", "enabled": False, "required": True}]})
    await api.request("admin", "PUT", settings_a, json={"fields": [
        {"field": "company_phone", "enabled": True, "required": True},
        {"field": "company_email", "enabled": False, "required": False},
    ]})
    await api.request("admin", "PUT", settings_b, json={"fields": [
        {"field": "company_phone", "enabled": False, "required": False},
        {"field": "company_email", "enabled": True, "required": False},
    ]})
    read = await api.request("client", "GET", settings_a)
    require(any(item["field"] == "company_phone" and item["required"] for item in read["fields"]), "Settings readback lost required")
    app_id = await new_application(state, signed=True)
    q_url = f"/api/v1/questionnaire/{app_id}"
    assign = f"/api/v1/admin/applications/{app_id}/assign-leasing-companies"
    await api.request("outsider", "PUT", q_url, expected=(403, 404), json={"company_phone": "+74951234567"})
    await api.request("client", "PUT", q_url, json={"full_company_name": "ООО E2E", "company_email": "company@example.test", "director_full_name": "Иванов Иван Иванович"})
    before = await db_questionnaire(app_id)
    require(before is not None and before["questionnaire_completed_at"] is None, "Date set before delivery")
    await api.request("admin", "PUT", assign, expected=422, json={"leasing_company_ids": [lc_a, lc_b]})
    from sqlalchemy import func, select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingCompanyApplication
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(LeasingCompanyApplication).where(LeasingCompanyApplication.application_id == UUID(app_id)))
        require(count == 0, "Partial assignment escaped failed gate")
    await api.request("client", "PUT", q_url, json={"company_phone": "+74951234567"})
    # Actual settings + assignment reject structurally incomplete draft values.
    for field, incomplete in (
        ("contact_person", {"name": "Test"}),
        ("electronic_document_management_systems", {"sbis": False, "diadoc": False, "kontur": False, "other": False, "not_used": False}),
        ("main_counterparties", [{"name": "Test"}]),
        ("founders", [{"is_pdl": False}]),
        ("has_beneficiary", False),
    ):
        await api.request("admin", "PUT", settings_a, json={"fields": [{"field": field, "enabled": True, "required": True}]})
        await api.request("client", "PUT", q_url, json={field: incomplete})
        await api.request("admin", "PUT", assign, expected=422, json={"leasing_company_ids": [lc_a, lc_b]})
    reasons = (await api.request("client", "GET", "/api/v1/questionnaire-dictionaries/beneficial_owner_absence_reasons"))["items"]
    reason = next(item for item in reasons if item["is_active"] and item["code"] != "other")
    await api.request("client", "PUT", q_url, json={"has_beneficiary": False, "no_beneficial_owner_reason": reason["id"]})
    await api.request("admin", "PUT", settings_a, json={"fields": [
        {"field": "company_phone", "enabled": True, "required": True},
        {"field": "company_email", "enabled": False, "required": False},
        {"field": "website_in_blocked_domains_registry", "enabled": True, "required": True},
        {"field": "has_beneficiary", "enabled": True, "required": True},
        {"field": "no_beneficial_owner_reason", "enabled": False, "required": False},
    ]})
    await api.request("client", "PUT", q_url, json={"website_in_blocked_domains_registry": False})
    await api.request("admin", "PUT", assign, json={"leasing_company_ids": [lc_a, lc_b]})
    saved = await db_questionnaire(app_id)
    require(saved["id"] == before["id"] and saved["questionnaire_completed_at"], "Questionnaire identity/date wrong")
    require("2027-02-28" in json.dumps(saved["personal_data_processing_consent"], default=str), "Calendar-year expiry wrong")
    require("№" not in saved["personal_data_processing_consent"][0]["text"], "Fabricated SOPD number")
    completed = saved["questionnaire_completed_at"]
    await api.request("admin", "PUT", assign, json={"leasing_company_ids": [lc_a, lc_b]})
    require((await db_questionnaire(app_id))["questionnaire_completed_at"] == completed, "Duplicate assignment changed timestamp")
    for actor, visible, hidden in (("lc_a", "company_phone", "company_email"), ("lc_b", "company_email", "company_phone")):
        for path in (q_url, f"/api/v1/applications/{app_id}", f"/api/v1/leasing/applications/{app_id}/financial-bundle"):
            result = await api.request(actor, "GET", path)
            projection = result["questionnaire"]
            require(visible in projection and hidden not in projection and "field_sources" not in projection, f"Disclosure error {path}")
            if actor == "lc_a":
                require(projection["has_beneficiary"] is False and "no_beneficial_owner_reason" not in projection, "Required boolean/hidden reason dependency leaked or blocked delivery")
    await api.request("outsider", "GET", q_url, expected=(403, 404))
    progress("settings_assignment_visibility_passed")
    await api.request("lc_a", "POST", f"/api/v1/leasing/applications/{app_id}/take-in-work")

    async def request_document(slug):
        response = await api.request("lc_a", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
            json={"requestedDocuments": [{"source": "catalog", "document_type": slug, "display_name": slug}]})
        return response["items"][0]["id"]

    async def answer(request_id, *, form=None, file=False, key=None, actor="client", expected=201, title="Пользовательское название"):
        data = {"application_id": app_id, "document_request_id": request_id}
        if form is not None:
            data["form_data"] = json.dumps(form)
        files = []
        if file:
            files = [("files", ("evidence.pdf", pdf(), "application/pdf"))]
            data["user_titles"] = json.dumps([title], ensure_ascii=False)
        return await api.request(actor, "POST", "/api/v1/documents", expected=expected,
            data=data, files=files, headers={"Idempotency-Key": key or str(uuid4())})

    typed = (
        ("snils", {"number": "11223344595"}, "director_snils", "11223344595"),
        ("main_counterparties", {"counterparties": [{"name": "Поставщик", "inn": "7700000000"}]}, "main_counterparties", None),
        ("open_bank_accounts", {"accounts": [{"bank": "Банк", "bik": "044525225", "acc_number": "40702810000000000001", "correspondent_account": "30101810400000000225"}]}, "open_bank_accounts", None),
        ("beneficial_owner", {"fio": "Петров Пётр Петрович"}, "transaction_beneficiary", {"fio": "Петров Пётр Петрович"}),
    )
    for slug, form, field, expected in typed:
        request_id = await request_document(slug)
        await answer(request_id, form=form, actor="outsider", expected=403)
        if slug == "snils":
            await answer(request_id, form={"number": "123"}, expected=422)
        key = str(uuid4())
        await answer(request_id, form=form, key=key)
        await answer(request_id, form=form, key=key)
        await answer(request_id, form=form, expected=409)
        current = await db_questionnaire(app_id)
        require(current[field] == expected if expected is not None else bool(current[field]), f"Projection missing {slug}")
        require(current["id"] == before["id"] and current["questionnaire_completed_at"] == completed, "Late response created snapshot or changed delivery date")

    status_fields = (("loans_docs", "loans_credits_leasing"), ("third_member_guarantees", "third_party_guarantees"),
        ("additional_collateral", "additional_collateral_available"), ("state_defense_order", "state_defense_order"), ("appointment_docs", "director_appointment_document"))
    for slug, field in status_fields:
        request_id = await request_document(slug)
        await answer(request_id)
        require((await db_questionnaire(app_id))[field]["status"] == "missing", "Absence projection wrong")
        request_id = await request_document(slug)
        await answer(request_id, file=True, title="x" * 256, expected=422)
        await api.request("client", "POST", "/api/v1/documents", expected=(400, 422),
            data={"application_id": app_id, "document_request_id": request_id},
            files=[("files", (f"file-{i}.pdf", pdf(), "application/pdf")) for i in range(11)],
            headers={"Idempotency-Key": str(uuid4())})
        key = str(uuid4())
        response = await answer(request_id, file=True, title="Документ " + slug, key=key)
        replay = await answer(request_id, file=True, title="Документ " + slug, key=key)
        document_id = response["documents"][0]["id"]
        require(replay["documents"][0]["id"] == document_id and replay["documents"][0]["user_title"] == "Документ " + slug, "File replay changed saved document or title")
        current = await db_questionnaire(app_id)
        require(current[field]["documents"][0]["user_title"] == "Документ " + slug, "User title lost")
        await api.request("client", "GET", f"/api/v1/documents/{document_id}/content", raw=True)
        await api.request("lc_a", "GET", f"/api/v1/documents/{document_id}/content", raw=True)
        await api.request("lc_b", "GET", f"/api/v1/documents/{document_id}/content", expected=(403, 404), raw=True)
        lc_b_q = (await api.request("lc_b", "GET", q_url))["questionnaire"]
        require(field not in lc_b_q, "Other LC response reference leaked")
    for slug in ("licenses", "sro"):
        request_id = await request_document(slug)
        await answer(request_id, expected=422)
        await answer(request_id, file=True, title="Название " + slug)
    current = await db_questionnaire(app_id)
    require({item["document_type"] for item in current["licenses_or_sro_membership"]} == {"licenses", "sro"}, "License projection overwrote previous type")
    from infrastructure.models.documents import ApplicationDocument
    from infrastructure.models.notification_delivery import NotificationEventOutbox
    async with AsyncSessionLocal() as session:
        titles = (await session.scalars(select(ApplicationDocument.user_title).where(ApplicationDocument.application_id == UUID(app_id)))).all()
        require(titles and all(titles), "Application document titles missing in DB")
        events = (await session.scalars(select(NotificationEventOutbox.event_type).where(NotificationEventOutbox.aggregate_id == UUID(app_id)))).all()
        require("leasing.documents_requested" in events and "leasing.documents_uploaded" in events, "Existing notification facts not persisted")
    progress("typed_responses_files_replay_notifications_passed")
    await verify_signed_hook(api, state, app_id)
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update({"application_id": app_id, "companies": state["companies"], "users": {key: {"id": value["id"], "role": value["role"]} for key, value in state["users"].items()}})
    private_json(ROOT / "manifest.json", manifest)
    private_json(ROOT / "acceptance-result.json", {"ok": True, "application_id": app_id, "verified_at": datetime.now(UTC)})
    progress("acceptance_passed", application_id=app_id)


async def verify_signed_hook(api, state, app_id):
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.signature_requests import SignatureRequest
    from infrastructure.models.sopd_passport_snapshots import SopdPassportSnapshot
    user_id = UUID(state["users"]["client"]["id"])
    request_id = uuid4()
    fields = {"surname": "Иванов", "name": "Иван", "patronymic": "Иванович", "nationality": "Российская Федерация",
        "gender": "male", "birthDate": "1980-01-01", "birthPlace": "Москва", "passportSeries": "1234", "passportNumber": "123456",
        "givenDate": "2000-01-01", "code": "123-456", "givenWhom": "Отдел МВД"}
    async with AsyncSessionLocal() as session:
        session.add(SignatureRequest(id=request_id, user_id=user_id, invited_by_user_id=user_id, application_id=UUID(app_id),
            document_type="sopd", status="pending", subject_snapshot={"full_name": "Иванов Иван Иванович",
            "signer_key": "director", "sopd_flow": "physical_owner_upload"}))
        await session.flush()
        session.add(SopdPassportSnapshot(application_id=UUID(app_id), signer_key="director", signature_request_id=request_id,
            owner_user_id=user_id, recognition_fields=fields, recognition_confidence={"name": 99},
            draft_fields=fields, confirmed_fields=fields, has_unsaved_changes=False, confirmed_at=datetime.now(UTC)))
        await session.commit()
    await api.request("outsider", "POST", f"/api/v1/signatures/{request_id}/upload-physical", expected=403,
        files={"file": ("signed.pdf", pdf(), "application/pdf")})
    await api.request("client", "POST", f"/api/v1/signatures/{request_id}/upload-physical",
        files={"file": ("signed.pdf", pdf(), "application/pdf")})
    value = await db_questionnaire(app_id)
    refs = value["personal_data_processing_consent"]
    require(len(refs) == 1 and refs[0]["signature_request_id"] == str(request_id), "New signed SOPD did not replace old projection")
    from sqlalchemy import select
    from infrastructure.models.users import VerificationCode
    lc_a, lc_b = [state["companies"][alias]["leasing_company_id"] for alias in ("lc_a", "lc_b")]

    async def withdraw(leasing_company_id):
        await api.request("client", "POST", f"/api/v1/signatures/{request_id}/revoke",
            json={"leasing_company_ids": [leasing_company_id]})
        async with AsyncSessionLocal() as session:
            code = (await session.scalars(select(VerificationCode).where(
                VerificationCode.entity_id == str(request_id), VerificationCode.used_at.is_(None)
            ).order_by(VerificationCode.created_at.desc()))).first()
            require(code is not None, "Local verification code was not stored")
            value = code.code
        await api.request("client", "POST", f"/api/v1/signatures/{request_id}/revoke/verify", json={"code": value})
        # Age only this fixture's consumed challenge to avoid waiting for the
        # unrelated 60-second resend throttle before testing the second LC.
        async with AsyncSessionLocal() as session:
            stored = await session.get(VerificationCode, code.id)
            stored.created_at = datetime.now(UTC) - timedelta(minutes=2)
            await session.commit()

    await withdraw(lc_a)
    q_a = (await api.request("lc_a", "GET", f"/api/v1/questionnaire/{app_id}"))["questionnaire"]
    q_b = (await api.request("lc_b", "GET", f"/api/v1/questionnaire/{app_id}"))["questionnaire"]
    require(not q_a["personal_data_processing_consent"] and q_b["personal_data_processing_consent"], "Partial withdrawal lost LC scope")
    await withdraw(lc_b)
    value = await db_questionnaire(app_id)
    require(not value["personal_data_processing_consent"], "Full withdrawal did not update persisted questionnaire")
    q = (await api.request("lc_a", "GET", f"/api/v1/questionnaire/{app_id}"))["questionnaire"]
    require(not q["personal_data_processing_consent"], "Revoked SOPD or superseded old SOPD leaked")
    progress("physical_signature_partial_and_full_withdrawal_passed")



async def ui_seed():
    guard()
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    state = json.loads((ROOT / "state.secret.json").read_text())
    async with AsyncSessionLocal() as session:
        company = await session.get(Company, UUID(state["companies"]["client"]["company_id"]))
        company.director_full_name = "Иванов Иван Иванович"
        company.director_inn = "770123456789"
        await session.commit()
    app_id = await new_application(state)
    api = API(state)
    await api.request("client", "PUT", f"/api/v1/questionnaire/{app_id}", json={
        "full_company_name": "ООО Анкета UI", "inn": "0000222861", "legal_address": "Москва, Тестовая 1",
        "director_full_name": "Иванов Иван Иванович", "director_inn": "770123456789",
        "company_phone": "+74951234567", "company_email": "office@example.test",
    })
    path = ROOT / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    manifest["ui_application_id"] = app_id
    private_json(path, manifest)
    progress("ui_fixture_ready", application_id=app_id)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("keys", "migrate", "seed", "roles", "ui-seed", "verify", "check"), nargs="?", default="verify")
    action = parser.parse_args().action
    if action == "keys":
        keys()
    elif action in {"migrate", "check"}:
        migrate(action == "check")
    elif action == "seed":
        asyncio.run(seed())
    elif action == "roles":
        asyncio.run(fix_roles())
    elif action == "ui-seed":
        asyncio.run(ui_seed())
    else:
        asyncio.run(verify())


if __name__ == "__main__":
    main()
