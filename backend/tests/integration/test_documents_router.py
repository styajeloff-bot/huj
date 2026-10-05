"""Integration tests for /api/v1/documents/* — Phase 10 R4 unified surface."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import (
    ApplicationDocument,
    ApplicationDocumentRequest,
    DocumentType,
)
from infrastructure.models.lca_status_history import (
    LeasingCompanyApplicationStatusHistory,
)
from infrastructure.models.users import User
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_storage() -> Iterator[FakeObjectStorage]:
    fake = FakeObjectStorage()
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


@pytest_asyncio.fixture
async def docs_company(db_session: AsyncSession) -> Company:
    c = Company(name="Docs Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def docs_client_user(
    db_session: AsyncSession, docs_company: Company
) -> User:
    user = User(
        phone="+76660000001",
        email="docsclient@test.local",
        name="Docs Client",
        role="client",
        is_active=True,
        company_id=docs_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def docs_client_token(
    docs_client_user: User, docs_company: Company
) -> str:
    token, _ = generate_tokens(
        docs_client_user.id, "client", docs_company.id
    )
    return token


@pytest_asyncio.fixture
async def other_company(db_session: AsyncSession) -> Company:
    c = Company(name="Other Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def other_client_user(
    db_session: AsyncSession, other_company: Company
) -> User:
    user = User(
        phone="+76660000002",
        email="other@test.local",
        name="Other Client",
        role="client",
        is_active=True,
        company_id=other_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_client_token(
    other_client_user: User, other_company: Company
) -> str:
    token, _ = generate_tokens(
        other_client_user.id, "client", other_company.id
    )
    return token


@pytest_asyncio.fixture
async def docs_employee(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000003",
        email="docsempl@test.local",
        name="Docs Employee",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def docs_employee_token(docs_employee: User) -> str:
    token, _ = generate_tokens(docs_employee.id, "carcraft_employee", None)
    return token


@pytest_asyncio.fixture
async def passport_type(db_session: AsyncSession) -> DocumentType:
    row = DocumentType(
        name="Паспорт",
        type_code="passport",
        file_types=["image/jpeg", "application/pdf"],
        max_file_size_mb=5,
        auto_approve=False,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def docs_application(
    db_session: AsyncSession, docs_company: Company
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=docs_company.id,
        email="docs-app@test.local",
        status="active",
        selected_leasing_companies=[],
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)
    return app


@pytest_asyncio.fixture
async def docs_document_request(
    db_session: AsyncSession,
    docs_application: LeasingApplication,
    docs_client_user: User,
) -> ApplicationDocumentRequest:
    lc_company = Company(
        name="Request LC", company_type="leasing_company"
    )
    db_session.add(lc_company)
    await db_session.flush()
    lc = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    docs_application.selected_leasing_companies = [lc.id]
    db_session.add(
        LeasingCompanyApplication(
            application_id=docs_application.id,
            leasing_company_id=lc.id,
            status="documents_required",
        )
    )
    request = ApplicationDocumentRequest(
        application_id=docs_application.id,
        leasing_company_id=lc.id,
        document_type="requested_passport",
        display_name="Паспорт директора",
        status="requested",
        requested_by=docs_client_user.id,
    )
    db_session.add(request)
    await db_session.flush()
    await db_session.refresh(request)
    return request


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_list_documents_anon_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/documents/")
    assert response.status_code == 401


async def test_upload_anon_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"x", "image/jpeg")},
        data={"document_type": "passport"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Unified upload (POST /documents)
# ---------------------------------------------------------------------------


async def test_upload_single_golden_path(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    response = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"jpeg data", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["documents"][0]["document_type"] == "passport"
    assert body["documents"][0]["version"] == 1


async def test_upload_multi_file_batch(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    files = [
        ("files", ("a.jpg", b"a-bytes", "image/jpeg")),
        ("files", ("b.pdf", b"b-bytes", "application/pdf")),
    ]
    data = {"document_types": '["passport", "passport"]'}
    response = await client.post(
        "/api/v1/documents/",
        files=files,
        data=data,
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total"] == 2


async def test_upload_rejects_bad_content_type(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    response = await client.post(
        "/api/v1/documents/",
        files={"files": ("x.exe", b"hi", "application/octet-stream")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 400


async def test_upload_rejects_too_large(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    big = b"\0" * (6 * 1024 * 1024)
    response = await client.post(
        "/api/v1/documents/",
        files={"files": ("big.jpg", big, "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 413


async def test_upload_rejects_both_parent_and_application(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
    docs_application: LeasingApplication,
) -> None:
    _ = passport_type
    response = await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={
            "document_type": "passport",
            "application_id": str(docs_application.id),
            "parent_document_id": "1",
        },
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 422


async def test_upload_mismatched_types_count_returns_422(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    files = [
        ("files", ("a.jpg", b"a", "image/jpeg")),
        ("files", ("b.jpg", b"b", "image/jpeg")),
    ]
    data = {"document_types": '["passport"]'}
    response = await client.post(
        "/api/v1/documents/",
        files=files,
        data=data,
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 422


async def test_upload_version_flow_increments(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    v1 = await client.post(
        "/api/v1/documents/",
        files={"files": ("v1.jpg", b"v1", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    assert v1.status_code == 201
    doc_id = v1.json()["documents"][0]["id"]

    v2 = await client.post(
        "/api/v1/documents/",
        files={"files": ("v2.jpg", b"v2", "image/jpeg")},
        data={"parent_document_id": str(doc_id)},
        headers=_auth(docs_client_token),
    )
    assert v2.status_code == 201, v2.text
    new_doc = v2.json()["documents"][0]
    assert new_doc["version"] == 2
    assert new_doc["parent_document_id"] == doc_id

    versions = await client.get(
        f"/api/v1/documents/{doc_id}/versions",
        headers=_auth(docs_client_token),
    )
    assert versions.status_code == 200
    assert versions.json()["total"] == 2


async def test_upload_for_application_attaches(
    client: AsyncClient,
    docs_client_token: str,
    docs_application: LeasingApplication,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("app.jpg", b"jpg", "image/jpeg")},
        data={
            "document_type": "passport",
            "application_id": str(docs_application.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["application_id"] == str(docs_application.id)


async def test_upload_for_document_request_links_and_completes_review(
    client: AsyncClient,
    db_session: AsyncSession,
    docs_client_token: str,
    docs_application: LeasingApplication,
    docs_document_request: ApplicationDocumentRequest,
) -> None:
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("requested.pdf", b"pdf", "application/pdf")},
        data={
            "application_id": str(docs_application.id),
            "document_request_id": str(docs_document_request.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["documents"][0]["document_type"] == "requested_passport"

    await db_session.refresh(docs_document_request)
    assert docs_document_request.status == "provided"
    assert docs_document_request.provided_at is not None
    link = (
        await db_session.execute(
            select(ApplicationDocument).where(
                ApplicationDocument.document_request_id
                == docs_document_request.id
            )
        )
    ).scalar_one()
    assert str(link.document_id) == body["documents"][0]["id"]
    assert link.status == "submitted"

    lca = (
        await db_session.execute(
            select(LeasingCompanyApplication).where(
                LeasingCompanyApplication.application_id
                == docs_application.id
            )
        )
    ).scalar_one()
    assert lca.status == "under_review_with_docs"
    history = (
        await db_session.execute(
            select(LeasingCompanyApplicationStatusHistory).where(
                LeasingCompanyApplicationStatusHistory.lca_id == lca.id,
                LeasingCompanyApplicationStatusHistory.new_status
                == "under_review_with_docs",
            )
        )
    ).scalar_one()
    assert history.old_status == "documents_required"


async def test_upload_auto_approved_requested_document_closes_exact_request(
    client: AsyncClient,
    db_session: AsyncSession,
    docs_client_token: str,
    docs_application: LeasingApplication,
    docs_document_request: ApplicationDocumentRequest,
) -> None:
    auto_type = DocumentType(
        name="Автоодобряемый паспорт",
        type_code=docs_document_request.document_type,
        file_types=["application/pdf"],
        max_file_size_mb=5,
        auto_approve=True,
    )
    same_type_other_batch = ApplicationDocumentRequest(
        application_id=docs_application.id,
        leasing_company_id=docs_document_request.leasing_company_id,
        document_type=docs_document_request.document_type,
        display_name="Другой пакет",
        status="requested",
        is_required=True,
    )
    db_session.add_all([auto_type, same_type_other_batch])
    await db_session.flush()
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("approved.pdf", b"pdf", "application/pdf")},
        data={
            "application_id": str(docs_application.id),
            "document_request_id": str(docs_document_request.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 201, upload.text
    await db_session.refresh(docs_document_request)
    await db_session.refresh(same_type_other_batch)
    assert docs_document_request.status == "approved"
    assert same_type_other_batch.status == "requested"
    linked = await db_session.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.document_request_id == docs_document_request.id
        )
    )
    assert linked is not None and linked.status == "approved"


async def test_upload_for_document_request_rejects_superseded(
    client: AsyncClient,
    db_session: AsyncSession,
    docs_client_token: str,
    docs_application: LeasingApplication,
    docs_document_request: ApplicationDocumentRequest,
) -> None:
    docs_document_request.status = "superseded"
    await db_session.flush()
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("old.pdf", b"pdf", "application/pdf")},
        data={
            "application_id": str(docs_application.id),
            "document_request_id": str(docs_document_request.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 400


async def test_upload_same_slug_across_batches_completes_only_after_both_uploads(
    client: AsyncClient,
    db_session: AsyncSession,
    docs_client_token: str,
    docs_application: LeasingApplication,
    docs_document_request: ApplicationDocumentRequest,
) -> None:
    pending = ApplicationDocumentRequest(
        application_id=docs_application.id,
        leasing_company_id=docs_document_request.leasing_company_id,
        document_type=docs_document_request.document_type,
        display_name="Паспорт поручителя",
        status="requested",
        is_required=True,
    )
    db_session.add(pending)
    await db_session.flush()
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("requested.pdf", b"pdf", "application/pdf")},
        data={
            "application_id": str(docs_application.id),
            "document_request_id": str(docs_document_request.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 201, upload.text
    lca = (
        await db_session.execute(
            select(LeasingCompanyApplication).where(
                LeasingCompanyApplication.application_id
                == docs_application.id
            )
        )
    ).scalar_one()
    assert lca.status == "documents_required"
    await db_session.refresh(pending)
    assert pending.status == "requested"
    assert pending.request_batch_id != docs_document_request.request_batch_id
    second_upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("second.pdf", b"pdf second", "application/pdf")},
        data={
            "application_id": str(docs_application.id),
            "document_request_id": str(pending.id),
        },
        headers=_auth(docs_client_token),
    )
    assert second_upload.status_code == 201, second_upload.text
    assert second_upload.json()["documents"][0]["id"] != upload.json()["documents"][0]["id"]
    await db_session.refresh(lca)
    await db_session.refresh(pending)
    await db_session.refresh(docs_document_request)
    assert lca.status == "under_review_with_docs"
    assert pending.status == docs_document_request.status == "provided"


async def test_upload_for_document_request_rejects_other_application(
    client: AsyncClient,
    db_session: AsyncSession,
    docs_client_token: str,
    docs_company: Company,
    docs_document_request: ApplicationDocumentRequest,
) -> None:
    other_application = LeasingApplication(
        company_id=docs_company.id,
        email="other-owned-app@test.local",
        status="active",
        selected_leasing_companies=[
            docs_document_request.leasing_company_id
        ],
    )
    db_session.add(other_application)
    await db_session.flush()
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("wrong.pdf", b"pdf", "application/pdf")},
        data={
            "application_id": str(other_application.id),
            "document_request_id": str(docs_document_request.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 403


async def test_upload_for_document_request_requires_application_and_one_file(
    client: AsyncClient,
    docs_client_token: str,
    docs_application: LeasingApplication,
    docs_document_request: ApplicationDocumentRequest,
) -> None:
    missing_application = await client.post(
        "/api/v1/documents/",
        files={"files": ("one.pdf", b"pdf", "application/pdf")},
        data={"document_request_id": str(docs_document_request.id)},
        headers=_auth(docs_client_token),
    )
    assert missing_application.status_code == 422

    multiple_files = await client.post(
        "/api/v1/documents/",
        files=[
            ("files", ("one.pdf", b"one", "application/pdf")),
            ("files", ("two.pdf", b"two", "application/pdf")),
        ],
        data={
            "application_id": str(docs_application.id),
            "document_request_id": str(docs_document_request.id),
        },
        headers=_auth(docs_client_token),
    )
    assert multiple_files.status_code == 422


# ---------------------------------------------------------------------------
# Get / list
# ---------------------------------------------------------------------------


async def test_get_document_denies_foreign_company(
    client: AsyncClient,
    docs_client_token: str,
    other_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 201
    doc_id = upload.json()["documents"][0]["id"]

    forbidden = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers=_auth(other_client_token),
    )
    assert forbidden.status_code == 403


async def test_get_document_returns_404_unknown(
    client: AsyncClient, docs_client_token: str
) -> None:
    response = await client.get(
        "/api/v1/documents/ffffffff-ffff-ffff-ffff-ffffffffffff", headers=_auth(docs_client_token)
    )
    assert response.status_code == 404


async def test_list_documents_returns_company_docs(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    response = await client.get(
        "/api/v1/documents/", headers=_auth(docs_client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1


async def test_list_with_scope_user(
    client: AsyncClient,
    docs_client_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    response = await client.get(
        "/api/v1/documents/?scope=user",
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_list_with_enhanced_returns_requirements(
    client: AsyncClient,
    docs_client_token: str,
) -> None:
    response = await client.get(
        "/api/v1/documents/?scope=user&enhanced=true",
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "requirements" in body
    assert "documents" in body


# ---------------------------------------------------------------------------
# Status change (PATCH)
# ---------------------------------------------------------------------------


async def test_status_change_employee_only(
    client: AsyncClient,
    docs_client_token: str,
    docs_employee_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    doc_id = upload.json()["documents"][0]["id"]
    # Client cannot change status — scope denied (403).
    as_client = await client.patch(
        f"/api/v1/documents/{doc_id}/status",
        json={"status": "approved"},
        headers=_auth(docs_client_token),
    )
    assert as_client.status_code == 403

    as_employee = await client.patch(
        f"/api/v1/documents/{doc_id}/status",
        json={"status": "approved", "comments": "ok"},
        headers=_auth(docs_employee_token),
    )
    assert as_employee.status_code == 200, as_employee.text
    assert as_employee.json()["document"]["leasing_company_status"] == "approved"


async def test_status_change_invalid_transition_returns_400(
    client: AsyncClient,
    docs_client_token: str,
    docs_employee_token: str,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(docs_client_token),
    )
    doc_id = upload.json()["documents"][0]["id"]
    # pending -> approved
    await client.patch(
        f"/api/v1/documents/{doc_id}/status",
        json={"status": "approved"},
        headers=_auth(docs_employee_token),
    )
    # approved -> pending is NOT allowed
    response = await client.patch(
        f"/api/v1/documents/{doc_id}/status",
        json={"status": "pending"},
        headers=_auth(docs_employee_token),
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Application-scoped reads (moved to /applications/:id/documents)
# ---------------------------------------------------------------------------


async def test_list_for_application(
    client: AsyncClient,
    docs_client_token: str,
    docs_application: LeasingApplication,
    passport_type: DocumentType,
) -> None:
    _ = passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("app.jpg", b"jpg", "image/jpeg")},
        data={
            "document_type": "passport",
            "application_id": str(docs_application.id),
        },
        headers=_auth(docs_client_token),
    )
    assert upload.status_code == 201, upload.text

    listing = await client.get(
        f"/api/v1/applications/{docs_application.id}/documents",
        headers=_auth(docs_client_token),
    )
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["application_id"] == str(docs_application.id)


async def test_list_for_application_denies_foreign_company(
    client: AsyncClient,
    other_client_token: str,
    docs_application: LeasingApplication,
) -> None:
    response = await client.get(
        f"/api/v1/applications/{docs_application.id}/documents",
        headers=_auth(other_client_token),
    )
    assert response.status_code == 403


async def test_list_requirements_returns_empty_for_no_lcs(
    client: AsyncClient,
    docs_client_token: str,
    docs_application: LeasingApplication,
) -> None:
    response = await client.get(
        f"/api/v1/applications/{docs_application.id}/documents?requested=true",
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0


async def test_list_requirements_resolves_for_selected_lc(
    client: AsyncClient,
    db_session: AsyncSession,
    docs_client_token: str,
    docs_company: Company,
    passport_type: DocumentType,
) -> None:
    # Seed a leasing company + requirement.
    lc_company = Company(name="LC A", company_type="leasing_company")
    db_session.add(lc_company)
    await db_session.flush()
    lc = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    from infrastructure.models.applications import (
        LeasingCompanyDocumentRequirement,
    )
    req = LeasingCompanyDocumentRequirement(
        leasing_company_id=lc.id,
        document_type_id=passport_type.id,
        is_required=True,
        is_mandatory=True,
        is_active=True,
    )
    db_session.add(req)
    application = LeasingApplication(
        company_id=docs_company.id,
        email="req-app@test.local",
        status="active",
        selected_leasing_companies=[lc.id],
    )
    db_session.add(application)
    await db_session.flush()
    await db_session.refresh(application)

    response = await client.get(
        f"/api/v1/applications/{application.id}/documents?requested=true",
        headers=_auth(docs_client_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["requirements"][0]["document_type"] == "passport"
    assert body["requirements"][0]["is_required"] is True


# ---------------------------------------------------------------------------
# SOPD
# ---------------------------------------------------------------------------


async def test_sopd_download_returns_file_or_404(
    client: AsyncClient, docs_client_token: str
) -> None:
    # Depending on the layout, the file may or may not be present. Either
    # a 200 with binary content or a 404 with a JSON error is acceptable.
    response = await client.get(
        "/api/v1/documents/sopd/download",
        headers=_auth(docs_client_token),
    )
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert len(response.content) > 0
