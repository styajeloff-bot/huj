"""Real bank TXT upload → installed carcraft-bor → DB/S3 → questionnaire E2E."""
from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, progress, require


async def fixture(state):
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    from infrastructure.models.users import User, UserCompany, UserSession
    load_and_validate_key_configuration()
    company_id, user_id, sid = uuid4(), uuid4(), uuid4()
    inn = f"{company_id.int % 10000000000:010d}"
    async with AsyncSessionLocal() as session:
        session.add(Company(id=company_id, name="22286 Bank fixture", inn=inn, company_type="other", is_active=True))
        session.add(User(id=user_id, role="client", company_id=company_id, name="22286 Bank client",
            phone=f"+7{user_id.int % 10000000000:010d}", is_active=True, phone_verified=True))
        await session.flush()
        session.add(UserCompany(user_id=user_id, company_id=company_id, role="client", sub_role="administrator",
            can_view_applications=True, can_create_applications=True))
        token, refresh = generate_tokens(user_id, "client", company_id, refresh_session_id=sid)
        session.add(UserSession(id=sid, user_id=user_id, refresh_token_hash=hash_refresh_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=1), ip_address="127.0.0.1", user_agent="22286 bank E2E"))
        await session.commit()
    state["users"]["bank_client"] = {"access_token": token, "csrf": secrets.token_urlsafe(24)}
    return company_id, user_id, inn


async def new_app(company_id, user_id):
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingApplication
    app_id = uuid4()
    async with AsyncSessionLocal() as session:
        session.add(LeasingApplication(id=app_id, company_id=company_id, created_by=user_id, status="active",
            display_number="22286-bank-" + app_id.hex[:10], name="Bank projection E2E"))
        await session.commit()
    return str(app_id)


def statement(inn, *, self_only=False):
    own_account = "40702810000000000001"
    today = datetime.now(UTC).strftime("%d.%m.%Y")
    rows = [
        ("7701234560", "ООО  Контрагент", "40702810000000000002", inn, "Клиент", own_account),
        (inn, "Клиент", own_account, "7701234560", "ООО Контрагент", "40702810000000000002"),
        (inn, "Клиент", own_account, "7701234561", "ООО Поставщик", "40702810000000000003"),
        (inn, "Клиент", own_account, inn, "Клиент", "40702810000000000004"),
    ]
    if self_only:
        rows = rows[-1:]
    text = f"""1CClientBankExchange
ВерсияФормата=1.03
Отправитель=fixture-{uuid4()}
ДатаНачала={today}
ДатаКонца={today}
РасчСчет={own_account}
СекцияРасчСчет
ДатаНачала={today}
ДатаКонца={today}
РасчСчет={own_account}
НачальныйОстаток=0.00
ВсегоПоступило=100.00
ВсегоСписано=300.00
КонечныйОстаток=-200.00
КонецРасчСчет
"""
    for i, (payer_inn, payer_name, payer_account, recipient_inn, recipient_name, recipient_account) in enumerate(rows, 1):
        text += f"""СекцияДокумент=Платежное поручение
Номер={i}
Дата={today}
Сумма=100.00
ПлательщикИНН={payer_inn}
Плательщик1={payer_name}
ПлательщикСчет={payer_account}
ПлательщикБанк1=Тестовый банк
ПлательщикБИК=044525225
ПолучательИНН={recipient_inn}
Получатель1={recipient_name}
ПолучательСчет={recipient_account}
ПолучательБанк1=Тестовый банк
ПолучательБИК=044525225
НазначениеПлатежа=Оплата по счету за товар
КонецДокумента
"""
    return text.encode("cp1251")


async def verify():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    company_id, user_id, inn = await fixture(state)
    api = API(state)
    app_id = await new_app(company_id, user_id)
    q_url = f"/api/v1/questionnaire/{app_id}"
    await api.request("bank_client", "PUT", q_url, json={"company_phone": "+74951234567"})
    initial = await db_questionnaire(app_id)

    async def upload(data, actor="bank_client", expected=200):
        return await api.request(actor, "POST", "/api/v1/bank-statements/uploads", expected=expected,
            data={"application_id": app_id}, files=[("files", ("statement.txt", data, "text/plain"))])

    raw = statement(inn)
    await upload(raw, actor="outsider", expected=(403, 404))
    await upload(raw, actor=None, expected=401)
    await upload(b"not a statement", expected=422)
    require((await db_questionnaire(app_id))["main_counterparties"] is None, "Failed bank upload changed questionnaire")
    await upload(statement(inn, self_only=True))
    require((await db_questionnaire(app_id))["main_counterparties"] is None, "Self transfers became counterparties")
    result = await upload(raw)
    saved = await db_questionnaire(app_id)
    expected = [{"name": "ООО Контрагент", "inn": "7701234560"}, {"name": "ООО Поставщик", "inn": "7701234561"}]
    require(saved["main_counterparties"] == expected, f"Actual bank analyzer projection mismatch: {saved['main_counterparties']}")
    require(saved["field_sources"]["main_counterparties"] == "bank_statement", "Automatic source missing")
    require(saved["id"] == initial["id"] and saved["questionnaire_completed_at"] is None, "Bank upload changed q identity/delivery date")
    replay = await upload(raw)
    require(result["items"][0]["import_id"] == replay["items"][0]["import_id"], "Duplicate TXT created another import")
    doc_id = result["items"][0]["document_id"]
    await api.request("bank_client", "GET", f"/api/v1/documents/{doc_id}/content", raw=True)
    await api.request("outsider", "GET", f"/api/v1/documents/{doc_id}/content", expected=(403, 404), raw=True)
    analytics_url = f"/api/v1/bank-statements/companies/{company_id}/analytics"
    analytics = await api.request("bank_client", "GET", analytics_url)
    require(any(row["inn"] == "7701234560" for row in analytics["top_clients"]), "Existing analytics no longer recognizes client")
    await api.request("outsider", "GET", analytics_url, expected=403)

    from sqlalchemy import func, select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.bank_statements import BankTransaction
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(BankTransaction).where(BankTransaction.company_id == company_id))
        require(count == 5, "Duplicate upload persisted more transactions")
    # Refresh existing company statements into only the requested new application.
    second = await new_app(company_id, user_id)
    refreshed = await api.request("bank_client", "POST", f"/api/v1/questionnaire/{second}/refresh")
    require(refreshed["questionnaire"]["main_counterparties"] == expected, "Refresh ignored existing parsed statements")
    require((await db_questionnaire(app_id))["id"] == saved["id"], "Refresh changed another application")

    manual = [{"name": "Ручной контрагент", "inn": "7700000000"}]
    await api.request("bank_client", "PUT", q_url, json={"main_counterparties": manual})
    await upload(statement(inn))
    require((await db_questionnaire(app_id))["main_counterparties"] == manual, "Bank analyzer overwrote manual values")
    await api.request("bank_client", "PUT", q_url, json={"main_counterparties": []})
    await upload(statement(inn))
    require((await db_questionnaire(app_id))["main_counterparties"] == [], "Bank analyzer overwrote manual clear")

    lc_id = state["companies"]["lc_a"]["leasing_company_id"]
    settings_url = f"/api/v1/leasing/companies/{lc_id}/questionnaire-settings"
    original_settings = (await api.request("admin", "GET", settings_url))["fields"]
    try:
        await api.request("admin", "PUT", settings_url, json={"fields": []})
        await api.request("admin", "PUT", f"/api/v1/admin/applications/{app_id}/assign-leasing-companies", json={"leasing_company_ids": [lc_id]})
    finally:
        await api.request("admin", "PUT", settings_url, json={"fields": [{key: item[key] for key in ("field", "enabled", "required")} for item in original_settings]})
    await api.request("lc_a", "POST", f"/api/v1/leasing/applications/{app_id}/take-in-work")
    requested = await api.request("lc_a", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
        json={"requestedDocuments": [{"source": "catalog", "document_type": "main_counterparties", "display_name": "Контрагенты"}]})
    request_id = requested["items"][0]["id"]
    answer = [{"name": "Контрагент из дозапроса", "inn": "7700000001"}]
    await api.request("bank_client", "POST", "/api/v1/documents", expected=201,
        data={"application_id": app_id, "document_request_id": request_id, "form_data": json.dumps({"counterparties": answer})},
        headers={"Idempotency-Key": str(uuid4())})
    completed = (await db_questionnaire(app_id))["questionnaire_completed_at"]
    await upload(statement(inn))
    await upload(b"invalid", expected=422)
    final = await db_questionnaire(app_id)
    require(final["main_counterparties"] == answer and final["field_sources"]["main_counterparties"] == "document_request", "Analyzer replaced explicit document-request answer")
    require(final["questionnaire_completed_at"] == completed, "Bank upload changed delivery date")
    progress("bank_upload_analyzer_questionnaire_passed", application_id=app_id, real_installed_sdk=True)


if __name__ == "__main__":
    asyncio.run(verify())
