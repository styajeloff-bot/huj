"""Integration tests for /api/v1/leasing/*."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    LeasingApplication,
)
from infrastructure.models.applications import (
    LeasingCompanyApplication as LcaModel,
)
from infrastructure.models.companies import (
    Company,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.documents import (
    ApplicationDocument,
    ApplicationDocumentRequest,
    Document,
    DocumentType,
)
from infrastructure.models.lca_status_history import (
    LeasingCompanyApplicationStatusHistory,
)
from infrastructure.models.users import User, UserCompany

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def lr_applicant_company(db_session: AsyncSession) -> Company:
    c = Company(name="LR Applicant", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def lr_lc_company(db_session: AsyncSession) -> Company:
    c = Company(name="LR LC Co", company_type="leasing_company")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def lr_other_lc_company(db_session: AsyncSession) -> Company:
    c = Company(name="LR Other LC Co", company_type="leasing_company")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def lr_leasing_company(
    db_session: AsyncSession, lr_lc_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(company_id=lr_lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def lr_other_leasing_company(
    db_session: AsyncSession, lr_other_lc_company: Company
) -> LeasingCompany:
    lc = LeasingCompany(company_id=lr_other_lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def lr_lc_user(
    db_session: AsyncSession,
    lr_lc_company: Company,
    lr_leasing_company: LeasingCompany,
) -> User:
    u = User(
        phone="+76660000001",
        email="lrlc@test.local",
        name="LR LC User",
        role="leasing_company",
        is_active=True,
        company_id=lr_lc_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        LeasingCompanyUser(
            user_id=u.id,
            leasing_company_id=lr_leasing_company.id,
        )
    )
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def lr_other_lc_user(
    db_session: AsyncSession,
    lr_other_lc_company: Company,
    lr_other_leasing_company: LeasingCompany,
) -> User:
    u = User(
        phone="+76660000002",
        email="lrother@test.local",
        name="LR Other LC User",
        role="leasing_company",
        is_active=True,
        company_id=lr_other_lc_company.id,
    )
    db_session.add(u)
    await db_session.flush()
    db_session.add(
        LeasingCompanyUser(
            user_id=u.id,
            leasing_company_id=lr_other_leasing_company.id,
        )
    )
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def lr_lc_token(lr_lc_user: User, lr_lc_company: Company) -> str:
    token, _ = generate_tokens(lr_lc_user.id, "leasing_company", lr_lc_company.id)
    return token


@pytest_asyncio.fixture
async def lr_other_lc_token(
    lr_other_lc_user: User, lr_other_lc_company: Company
) -> str:
    token, _ = generate_tokens(
        lr_other_lc_user.id, "leasing_company", lr_other_lc_company.id
    )
    return token


@pytest_asyncio.fixture
async def lr_employee(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000003",
        email="lremployee@test.local",
        name="LR Employee",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def lr_employee_token(lr_employee: User) -> str:
    token, _ = generate_tokens(lr_employee.id, "carcraft_employee", None)
    return token


@pytest_asyncio.fixture
async def lr_document_types(db_session: AsyncSession) -> tuple[DocumentType, DocumentType]:
    vat_declaration = DocumentType(
        name="Декларация по НДС",
        display_name="Декларация по НДС",
        type_code="vat_declaration_xml",
        file_types=["application/xml"],
        max_file_size_mb=25,
        auto_approve=False,
        has_form=False,
    )
    bank_statement = DocumentType(
        name="Банковская выписка",
        display_name="Банковская выписка",
        type_code="bank_statement",
        file_types=["application/pdf"],
        max_file_size_mb=5,
        auto_approve=False,
        has_form=False,
    )
    db_session.add_all([vat_declaration, bank_statement])
    await db_session.flush()
    return vat_declaration, bank_statement


async def _seed_app_and_link(
    db_session: AsyncSession,
    *,
    applicant_company: Company,
    lc: LeasingCompany,
    link_status: str = "under_review",
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=applicant_company.id,
        name="Test LR",
        email="lr-test@test.local",
        status="active",
        selected_leasing_companies=[lc.id],
    )
    db_session.add(app)
    await db_session.flush()
    db_session.add(
        LcaModel(
            application_id=app.id,
            leasing_company_id=lc.id,
            status=link_status,
        )
    )
    await db_session.flush()
    return app


# ---------------------------------------------------------------------------
# /companies
# ---------------------------------------------------------------------------


async def test_list_companies_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/leasing/companies")
    assert response.status_code == 401


async def test_list_companies_returns_active(
    client: AsyncClient,
    client_token: str,
    lr_leasing_company: LeasingCompany,
) -> None:
    response = await client.get(
        "/api/v1/leasing/companies", headers=_auth(client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(c["id"] == str(lr_leasing_company.id) for c in body["companies"])


# ---------------------------------------------------------------------------
# /applications (LC cabinet)
# ---------------------------------------------------------------------------


async def test_list_lc_applications_requires_lc_role(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.get(
        "/api/v1/leasing/applications", headers=_auth(client_token)
    )
    assert response.status_code == 403


async def test_list_lc_applications_returns_own(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
) -> None:
    await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.get(
        "/api/v1/leasing/applications", headers=_auth(lr_lc_token)
    )
    assert response.status_code == 200
    body = response.json()
    for entry in body["applications"]:
        assert entry["link"]["leasing_company_id"] == str(lr_leasing_company.id)


# ---------------------------------------------------------------------------
# Approve / reject / request-documents
# ---------------------------------------------------------------------------


async def test_decision_reject_requires_comments(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/decision",
        json={"action": "reject", "decision_comment": ""},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 400


async def test_decision_reject_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/decision",
        json={"action": "reject", "decision_comment": "Не подходит"},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "rejected_approved"


@pytest.mark.parametrize(
    "link_status",
    ["under_review", "documents_required", "under_review_with_docs"],
)
async def test_decision_approves_final_without_preliminary_proposal(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
    link_status: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
        link_status=link_status,
    )
    proposal_response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/proposals/final",
        json={
            "total_amount": 2_000_000,
            "down_payment": 400_000,
            "down_payment_percent": 20,
            "lease_term_months": 36,
            "buyout_amount": 100_000,
            "monthly_payment": 75_000,
            "total_cost": 3_200_000,
        },
        headers=_auth(lr_lc_token),
    )
    assert proposal_response.status_code == 200, proposal_response.text

    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/decision",
        json={"action": "approve", "kind": "final"},
        headers=_auth(lr_lc_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "approved_final"

    repeat_response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/decision",
        json={"action": "approve", "kind": "final"},
        headers=_auth(lr_lc_token),
    )
    assert repeat_response.status_code == 409


async def test_decision_final_without_complete_proposal_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )

    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/decision",
        json={"action": "approve", "kind": "final"},
        headers=_auth(lr_lc_token),
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "link_status",
    [
        "under_review",
        "documents_required",
        "under_review_with_docs",
        "approved_scoring",
        "approved_scoring_another_cond",
    ],
)
async def test_request_documents_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
    lr_document_types: tuple[DocumentType, DocumentType],
    link_status: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
        link_status=link_status,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={
            "requestedDocuments": [
                {
                    "source": "catalog",
                    "document_type": "vat_declaration_xml",
                    "display_name": "Декларация по НДС",
                },
                {
                    "source": "custom",
                    "display_name": "Дополнительный документ",
                },
            ],
            "comments": "Пожалуйста, загрузите",
        },
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requested_documents"] == ["vat_declaration_xml", "custom_document"]
    assert body["request_batch_id"]
    assert [item["slug"] for item in body["items"]] == [
        "vat_declaration_xml",
        "custom_document",
    ]
    assert [item["display_name"] for item in body["items"]] == [
        "Декларация по НДС",
        "Дополнительный документ",
    ]
    assert {item["status"] for item in body["items"]} == {"requested"}


async def test_request_documents_empty_list_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={"requestedDocuments": []},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 422


async def test_request_documents_preserves_prior_batch_and_history(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
    lr_document_types: tuple[DocumentType, DocumentType],
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    first = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={
            "requestedDocuments": [{
                "source": "catalog",
                "document_type": "vat_declaration_xml",
                "display_name": "Декларация по НДС",
            }],
            "comments": "Первый запрос",
        },
        headers=_auth(lr_lc_token),
    )
    assert first.status_code == 200, first.text
    second = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={
            "requestedDocuments": [
                {
                    "source": "custom",
                    "display_name": "Паспорт поручителя",
                },
                {
                    "source": "catalog",
                    "document_type": "bank_statement",
                    "display_name": "Выписка",
                },
            ],
            "comments": "Второй запрос",
        },
        headers=_auth(lr_lc_token),
    )
    assert second.status_code == 200, second.text
    assert first.json()["request_batch_id"] != second.json()["request_batch_id"]
    history = await client.get(
        f"/api/v1/applications/{app.id}/document-requests",
        headers=_auth(lr_lc_token),
    )
    assert history.status_code == 200, history.text
    batches = history.json()["batches"]
    assert [batch["comments"] for batch in batches] == [
        "Второй запрос",
        "Первый запрос",
    ]
    assert [batch["request_batch_id"] for batch in batches] == [
        second.json()["request_batch_id"],
        first.json()["request_batch_id"],
    ]
    assert sorted(item["slug"] for item in batches[0]["items"]) == [
        "bank_statement",
        "custom_document",
    ]
    assert batches[1]["items"][0]["id"] == first.json()["items"][0]["id"]
    assert all(
        item["status"] == "requested" for batch in batches for item in batch["items"]
    )
    transitions = (
        (
            await db_session.execute(
                select(LeasingCompanyApplicationStatusHistory).where(
                    LeasingCompanyApplicationStatusHistory.application_id == app.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert {(row.old_status, row.new_status) for row in transitions} == {
        ("under_review", "documents_required"),
        ("documents_required", "documents_required"),
    }


@pytest.mark.parametrize(
    "link_status",
    [
        "submitted",
        "selected_lc",
        "approved_final",
        "approved_final_another_cond",
        "rejected_prescoring",
        "rejected_approved",
        "deal",
        "closed",
    ],
)
async def test_request_documents_rejects_non_review_status_without_creating_batch(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
    link_status: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
        link_status=link_status,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={"requestedDocuments": [{"source": "custom", "display_name": "Паспорт"}]},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 400, response.text
    assert (
        await db_session.scalar(
            select(ApplicationDocumentRequest.id).where(
                ApplicationDocumentRequest.application_id == app.id,
            )
        )
        is None
    )


async def test_request_documents_rejects_other_leasing_company(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_other_lc_token: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
        link_status="documents_required",
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={"requestedDocuments": [{"source": "custom", "display_name": "Паспорт"}]},
        headers=_auth(lr_other_lc_token),
    )
    assert response.status_code == 404, response.text
    assert (
        await db_session.scalar(
            select(ApplicationDocumentRequest.id).where(
                ApplicationDocumentRequest.application_id == app.id,
            )
        )
        is None
    )


@pytest.mark.parametrize("notification_context", [False, True])
async def test_request_documents_rejects_read_only_member(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_user: User,
    lr_lc_token: str,
    lr_other_lc_company: Company,
    notification_context: bool,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
        link_status="documents_required",
    )
    db_session.add(
        UserCompany(
            user_id=lr_lc_user.id,
            company_id=lr_leasing_company.company_id,
            can_view_applications=True,
            can_create_applications=False,
        )
    )
    if notification_context:
        lr_lc_user.company_id = lr_other_lc_company.id
        lr_lc_token, _ = generate_tokens(
            lr_lc_user.id,
            lr_lc_user.role,
            lr_other_lc_company.id,
        )
    await db_session.flush()
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        params=(
            {"notification_company_id": str(lr_leasing_company.company_id)}
            if notification_context
            else {}
        ),
        json={"requestedDocuments": [{"source": "custom", "display_name": "Паспорт"}]},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 403, response.text
    assert (
        await db_session.scalar(
            select(ApplicationDocumentRequest.id).where(
                ApplicationDocumentRequest.application_id == app.id,
            )
        )
        is None
    )


async def test_request_documents_employee_does_not_infer_first_selected_lc(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_employee_token: str,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json={"requestedDocuments": [{"source": "custom", "display_name": "Паспорт"}]},
        headers=_auth(lr_employee_token),
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        (
            {"requestedDocuments": [{"source": "custom", "display_name": " "}]},
            422,
        ),
        (
            {
                "requestedDocuments": [
                    {
                        "source": "custom",
                        "display_name": "Паспорт",
                        "slug": "passport",
                    }
                ]
            },
            422,
        ),
        (
            {"requestedDocuments": [{"source": "catalog", "display_name": "Паспорт"}]},
            400,
        ),
        (
            {
                "requestedDocuments": [
                    {
                        "source": "catalog",
                        "document_type": "missing_document_type",
                        "display_name": "Неизвестный тип",
                    }
                ]
            },
            400,
        ),
        (
            {
                "requestedDocuments": [
                    {
                        "source": "custom",
                        "document_type": "vat_declaration_xml",
                        "display_name": "Произвольный документ",
                    }
                ]
            },
            400,
        ),
        (
            {
                "requestedDocuments": [
                    {
                        "source": "catalog",
                        "document_type": "vat_declaration_xml",
                        "display_name": "Декларация по НДС",
                    },
                    {
                        "source": "catalog",
                        "document_type": "vat_declaration_xml",
                        "display_name": "Дубликат декларации по НДС",
                    },
                ]
            },
            400,
        ),
    ],
)
async def test_request_documents_validates_typed_items(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
    lr_document_types: tuple[DocumentType, DocumentType],
    payload: dict,
    expected_status: int,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/request-documents",
        json=payload,
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == expected_status


async def test_anon_is_unauthorized(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
) -> None:
    app = await _seed_app_and_link(
        db_session,
        applicant_company=lr_applicant_company,
        lc=lr_leasing_company,
    )
    response = await client.put(
        f"/api/v1/leasing/applications/{app.id}/decision",
        json={"action": "reject", "decision_comment": "x"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# LC-scoped application-document approval
# ---------------------------------------------------------------------------


async def _seed_submitted_application_document(
    db_session: AsyncSession,
    *,
    application: LeasingApplication,
    leasing_company: LeasingCompany,
    company: Company,
) -> Document:
    document = Document(
        company_id=company.id,
        document_type="passport",
        file_name="passport.pdf",
        status="uploaded",
        related_application_id=application.id,
        leasing_company_status="pending",
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        ApplicationDocument(
            application_id=application.id,
            document_id=document.id,
            leasing_company_id=leasing_company.id,
            status="submitted",
        )
    )
    await db_session.flush()
    return document


async def test_approve_application_document_is_lc_scoped_and_preserves_global_status(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_token: str,
) -> None:
    application = await _seed_app_and_link(
        db_session, applicant_company=lr_applicant_company, lc=lr_leasing_company
    )
    document = await _seed_submitted_application_document(
        db_session,
        application=application,
        leasing_company=lr_leasing_company,
        company=lr_applicant_company,
    )

    requested = ApplicationDocumentRequest(
        application_id=application.id,
        leasing_company_id=lr_leasing_company.id,
        document_type="same_type",
        display_name="Exact request",
        status="provided",
        is_required=True,
    )
    same_type_other_batch = ApplicationDocumentRequest(
        application_id=application.id,
        leasing_company_id=lr_leasing_company.id,
        document_type="same_type",
        display_name="Must remain provided",
        status="provided",
        is_required=True,
    )
    db_session.add_all([requested, same_type_other_batch])
    await db_session.flush()
    association = await db_session.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.application_id == application.id,
            ApplicationDocument.document_id == document.id,
            ApplicationDocument.leasing_company_id == lr_leasing_company.id,
        )
    )
    assert association is not None
    association.document_request_id = requested.id
    await db_session.flush()

    before = await client.get(
        f"/api/v1/leasing/applications/{application.id}/documents",
        headers=_auth(lr_lc_token),
    )
    assert before.status_code == 200, before.text
    assert before.json()["documents"][0]["leasing_company_status"] == "pending"

    response = await client.patch(
        f"/api/v1/leasing/applications/{application.id}/documents/{document.id}/status",
        json={"status": "approved"},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "application_id": str(application.id),
        "document_id": str(document.id),
        "leasing_company_id": str(lr_leasing_company.id),
        "status": "approved",
        "message": "Документ одобрен",
    }
    association = await db_session.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.application_id == application.id,
            ApplicationDocument.document_id == document.id,
            ApplicationDocument.leasing_company_id == lr_leasing_company.id,
        )
    )
    assert association is not None
    assert association.status == "approved"
    await db_session.refresh(requested)
    await db_session.refresh(same_type_other_batch)
    assert requested.status == "approved"
    assert same_type_other_batch.status == "provided"
    global_document = await db_session.get(Document, document.id)
    assert global_document is not None
    assert global_document.leasing_company_status == "pending"

    after = await client.get(
        f"/api/v1/leasing/applications/{application.id}/documents",
        headers=_auth(lr_lc_token),
    )
    assert after.status_code == 200, after.text
    assert after.json()["documents"][0]["leasing_company_status"] == "approved"

    duplicate = await client.patch(
        f"/api/v1/leasing/applications/{application.id}/documents/{document.id}/status",
        json={"status": "approved"},
        headers=_auth(lr_lc_token),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Документ уже одобрен другим сотрудником."


async def test_approve_application_document_hides_other_lc_and_wrong_application(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_other_leasing_company: LeasingCompany,
    lr_lc_token: str,
    lr_other_lc_token: str,
) -> None:
    application = await _seed_app_and_link(
        db_session, applicant_company=lr_applicant_company, lc=lr_leasing_company
    )
    db_session.add(
        LcaModel(
            application_id=application.id,
            leasing_company_id=lr_other_leasing_company.id,
            status="under_review",
        )
    )
    await db_session.flush()
    document = await _seed_submitted_application_document(
        db_session,
        application=application,
        leasing_company=lr_leasing_company,
        company=lr_applicant_company,
    )
    other_lc = await client.patch(
        f"/api/v1/leasing/applications/{application.id}/documents/{document.id}/status",
        json={"status": "approved"},
        headers=_auth(lr_other_lc_token),
    )
    assert other_lc.status_code == 404

    other_application = await _seed_app_and_link(
        db_session, applicant_company=lr_applicant_company, lc=lr_leasing_company
    )
    wrong_application = await client.patch(
        f"/api/v1/leasing/applications/{other_application.id}/documents/{document.id}/status",
        json={"status": "approved"},
        headers=_auth(lr_lc_token),
    )
    assert wrong_application.status_code == 404
    association = await db_session.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.document_id == document.id
        )
    )
    assert association is not None
    assert association.status == "submitted"


async def test_approve_application_document_rejects_read_only_member(
    client: AsyncClient,
    db_session: AsyncSession,
    lr_applicant_company: Company,
    lr_leasing_company: LeasingCompany,
    lr_lc_user: User,
    lr_lc_token: str,
) -> None:
    application = await _seed_app_and_link(
        db_session, applicant_company=lr_applicant_company, lc=lr_leasing_company
    )
    document = await _seed_submitted_application_document(
        db_session,
        application=application,
        leasing_company=lr_leasing_company,
        company=lr_applicant_company,
    )
    db_session.add(
        UserCompany(
            user_id=lr_lc_user.id,
            company_id=lr_leasing_company.company_id,
            can_view_applications=True,
            can_create_applications=False,
        )
    )
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/leasing/applications/{application.id}/documents/{document.id}/status",
        json={"status": "approved"},
        headers=_auth(lr_lc_token),
    )
    assert response.status_code == 403
