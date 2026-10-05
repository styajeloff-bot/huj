from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.bank_statements import BankStatementImport
from infrastructure.models.companies import Company
from infrastructure.models.documents import Document, DocumentApplication
from infrastructure.models.users import User
from infrastructure.services.object_storage import get_object_storage

pytestmark = pytest.mark.asyncio

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "bank_statements"
    / "receipt_06.06.2025_17.06.2026.txt"
)


def _auth_headers(token: str) -> dict[str, str]:
    csrf = "test-csrf-token"
    return {
        "Cookie": f"accessToken={token}; csrfToken={csrf}",
        "X-CSRF-Token": csrf,
    }


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = (data, content_type)
        return f"memory://{key}"

    async def get(self, key: str) -> None:
        return None

    async def delete(self, key: str) -> bool:
        return bool(self.objects.pop(key, None))

    async def exists(self, key: str) -> bool:
        return key in self.objects

    def public_url(self, key: str) -> str:
        return f"memory://{key}"


async def _auth_context(db_session: AsyncSession, client: AsyncClient) -> tuple[str, Company]:
    from main import app

    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    company = Company(
        name="ИП Леонов Илья Константинович",
        inn="501906237893",
        company_type="other",
    )
    db_session.add(company)
    await db_session.flush()
    user = User(
        phone="+76660002162",
        email="21620@test.local",
        name="Bank Statement User",
        role="client",
        company_id=company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    token, _ = generate_tokens(user.id, "client", company.id)
    return token, company


async def _application(db_session: AsyncSession, company: Company) -> LeasingApplication:
    application = LeasingApplication(company_id=company.id, status="active")
    db_session.add(application)
    await db_session.flush()
    return application


def _statement_bytes(
    *,
    statement_account: str = "40802810000000360978",
    payer_inn: str = "7704217370",
    payer_account: str = "40702810300000051346",
    recipient_inn: str = "501906237893",
    recipient_account: str = "40802810000000360978",
) -> bytes:
    return (
        "1CClientBankExchange\n"
        "ВерсияФормата=1.03\n"
        "ДатаНачала=01.01.2026\n"
        "ДатаКонца=31.01.2026\n"
        f"РасчСчет={statement_account}\n"
        "СекцияРасчСчет\n"
        "ДатаНачала=01.01.2026\n"
        "ДатаКонца=31.01.2026\n"
        f"РасчСчет={statement_account}\n"
        "НачальныйОстаток=0.00\n"
        "ВсегоПоступило=100.00\n"
        "ВсегоСписано=0.00\n"
        "КонечныйОстаток=100.00\n"
        "КонецРасчСчет\n"
        "СекцияДокумент=Платежное поручение\n"
        "Номер=1\n"
        "Дата=02.01.2026\n"
        "Сумма=100.00\n"
        f"ПлательщикИНН={payer_inn}\n"
        f"ПлательщикСчет={payer_account}\n"
        f"ПолучательИНН={recipient_inn}\n"
        f"ПолучательСчет={recipient_account}\n"
        "НазначениеПлатежа=Оплата по счету\n"
        "КонецДокумента\n"
    ).encode("cp1251")


async def test_upload_demo_bank_statement(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, company = await _auth_context(db_session, client)
    application = await _application(db_session, company)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={"files": ("receipt_06.06.2025_17.06.2026.txt", FIXTURE.read_bytes(), "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["transactions_count"] == 351
    assert data["items"][0]["accounts_count"] == 3
    assert data["total_transactions_count"] == 351


async def test_upload_rejects_non_txt(client: AsyncClient, db_session: AsyncSession) -> None:
    token, _company = await _auth_context(db_session, client)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        files={"files": ("statement.xml", b"<xml/>", "application/xml")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Неверный формат. Загрузите файл в формате .txt"}


async def test_upload_invalid_text_message(client: AsyncClient, db_session: AsyncSession) -> None:
    token, company = await _auth_context(db_session, client)
    application = await _application(db_session, company)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={"files": ("statement.txt", b"not a bank statement", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Файл не является банковской выпиской. Проверьте содержимое файла"
    }


async def test_duplicate_upload_does_not_duplicate_transactions(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, company = await _auth_context(db_session, client)
    application = await _application(db_session, company)
    files = {"files": ("receipt_06.06.2025_17.06.2026.txt", FIXTURE.read_bytes(), "text/plain")}

    first = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files=files,
    )
    second = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={"files": ("receipt_06.06.2025_17.06.2026.txt", FIXTURE.read_bytes(), "text/plain")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["items"][0]["import_id"] == second.json()["items"][0]["import_id"]


async def test_upload_creates_document_and_application_link(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, company = await _auth_context(db_session, client)
    application = await _application(db_session, company)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={"files": ("receipt_06.06.2025_17.06.2026.txt", FIXTURE.read_bytes(), "text/plain")},
    )

    assert response.status_code == 200
    document_id = response.json()["items"][0]["document_id"]
    document = await db_session.get(Document, document_id)
    assert document is not None
    assert document.document_type == "bank_statement_txt"
    link = (
        await db_session.execute(
            select(DocumentApplication).where(
                DocumentApplication.document_id == document.id,
                DocumentApplication.application_id == application.id,
            )
        )
    ).scalar_one_or_none()
    assert link is not None


async def test_upload_rejects_application_from_other_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, _company = await _auth_context(db_session, client)
    other_company = Company(
        name="Other IP",
        inn="501906237899",
        company_type="other",
    )
    db_session.add(other_company)
    await db_session.flush()
    application = LeasingApplication(company_id=other_company.id, status="active")
    db_session.add(application)
    await db_session.flush()

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={
            "files": (
                "receipt_06.06.2025_17.06.2026.txt",
                FIXTURE.read_bytes(),
                "text/plain",
            )
        },
    )

    assert response.status_code == 403


async def test_upload_requires_application_id(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, _company = await _auth_context(db_session, client)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        files={"files": ("statement.txt", _statement_bytes(), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Не удалось определить заявку для загрузки выписки"}


async def test_upload_rejects_statement_account_owned_by_other_inn(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, company = await _auth_context(db_session, client)
    application = await _application(db_session, company)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={
            "files": (
                "foreign-owner.txt",
                _statement_bytes(recipient_inn="7700000000"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Выписка по счету принадлежит организации с ИНН 7700000000, а не выбранной компании"
    }


async def test_upload_rejects_transaction_without_selected_company_inn(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token, company = await _auth_context(db_session, client)
    application = await _application(db_session, company)

    data = (
        _statement_bytes()
        + (
            "СекцияДокумент=Платежное поручение\n"
            "Номер=2\n"
            "Дата=03.01.2026\n"
            "Сумма=50.00\n"
            "ПлательщикИНН=7700000000\n"
            "ПлательщикСчет=40702810999999999999\n"
            "ПолучательИНН=7800000000\n"
            "ПолучательСчет=40702810888888888888\n"
            "НазначениеПлатежа=Чужая операция\n"
            "КонецДокумента\n"
        ).encode("cp1251")
    )

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={"files": ("foreign-transaction.txt", data, "text/plain")},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Выписка не принадлежит выбранной компании. Проверьте файл или выберите правильную компанию."
    }


async def test_dealer_uploads_statement_to_application_company(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    from main import app

    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    dealer_company = Company(name="Dealer Company", inn="7700000099", company_type="dealer")
    client_company = Company(
        name="ИП Леонов Илья Константинович",
        inn="501906237893",
        company_type="other",
    )
    db_session.add_all([dealer_company, client_company])
    await db_session.flush()
    dealer = User(
        phone="+76660002166",
        email="21620-dealer@test.local",
        name="Dealer User",
        role="dealer",
        company_id=dealer_company.id,
        is_active=True,
    )
    db_session.add(dealer)
    application = LeasingApplication(
        company_id=client_company.id,
        dealer_company_id=dealer_company.id,
        status="active",
    )
    db_session.add(application)
    await db_session.flush()
    token, _ = generate_tokens(dealer.id, "dealer", dealer_company.id)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={"files": ("receipt_06.06.2025_17.06.2026.txt", FIXTURE.read_bytes(), "text/plain")},
    )

    assert response.status_code == 200
    document = await db_session.get(Document, response.json()["items"][0]["document_id"])
    assert document is not None
    assert document.company_id == client_company.id
    import_row = (
        await db_session.execute(
            select(BankStatementImport).where(BankStatementImport.document_id == document.id)
        )
    ).scalar_one()
    assert import_row.company_id == client_company.id


async def test_distributor_cannot_upload_statement_to_arbitrary_application(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    from main import app

    storage = FakeStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    distributor_company = Company(
        name="Distributor Company",
        inn="7700000098",
        company_type="distributor",
    )
    client_company = Company(
        name="ИП Леонов Илья Константинович",
        inn="501906237893",
        company_type="other",
    )
    db_session.add_all([distributor_company, client_company])
    await db_session.flush()
    distributor = User(
        phone="+76660002167",
        email="21620-distributor@test.local",
        name="Distributor User",
        role="distributor",
        company_id=distributor_company.id,
        is_active=True,
    )
    db_session.add(distributor)
    application = LeasingApplication(company_id=client_company.id, status="active")
    db_session.add(application)
    await db_session.flush()
    token, _ = generate_tokens(distributor.id, "distributor", distributor_company.id)

    response = await client.post(
        "/api/v1/bank-statements/uploads",
        headers=_auth_headers(token),
        data={"application_id": str(application.id)},
        files={
            "files": (
                "receipt_06.06.2025_17.06.2026.txt",
                FIXTURE.read_bytes(),
                "text/plain",
            )
        },
    )

    assert response.status_code == 403
