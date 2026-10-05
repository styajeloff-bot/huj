"""Integration tests for Phase 10 R4 unified document endpoints."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyDocumentRequirement,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import DocumentType
from infrastructure.models.users import User
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _fake_storage() -> Iterator[FakeObjectStorage]:
    fake = FakeObjectStorage()
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


@pytest_asyncio.fixture
async def g2_company(db_session: AsyncSession) -> Company:
    c = Company(name="G2 Router Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def g2_user(db_session: AsyncSession, g2_company: Company) -> User:
    user = User(
        phone="+76660000010",
        email="g2router@test.local",
        name="G2 Router",
        role="client",
        is_active=True,
        company_id=g2_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def g2_token(g2_user: User, g2_company: Company) -> str:
    token, _ = generate_tokens(g2_user.id, "client", g2_company.id)
    return token


@pytest_asyncio.fixture
async def g2_other_company(db_session: AsyncSession) -> Company:
    c = Company(name="G2 Other Co", company_type="other")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def g2_other_user(
    db_session: AsyncSession, g2_other_company: Company
) -> User:
    user = User(
        phone="+76660000011",
        email="g2other@test.local",
        name="G2 Other",
        role="client",
        is_active=True,
        company_id=g2_other_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def g2_other_token(
    g2_other_user: User, g2_other_company: Company
) -> str:
    token, _ = generate_tokens(
        g2_other_user.id, "client", g2_other_company.id
    )
    return token


@pytest_asyncio.fixture
async def g2_employee(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000012",
        email="g2empl@test.local",
        name="G2 Employee",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def g2_employee_token(g2_employee: User) -> str:
    token, _ = generate_tokens(g2_employee.id, "carcraft_employee", None)
    return token


@pytest_asyncio.fixture
async def g2_passport_type(db_session: AsyncSession) -> DocumentType:
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
async def g2_application(
    db_session: AsyncSession, g2_company: Company
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=g2_company.id,
        email="g2-app@test.local",
        status="active",
        selected_leasing_companies=[],
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.refresh(app)
    return app


# ---------------------------------------------------------------------------
# Listings via unified /documents?scope=
# ---------------------------------------------------------------------------


async def test_list_scope_company_returns_company_docs(
    client: AsyncClient,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    response = await client.get(
        "/api/v1/documents/?scope=company", headers=_auth(g2_token)
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_list_scope_user_matches_company(
    client: AsyncClient,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    await client.post(
        "/api/v1/documents/",
        files={"files": ("a.jpg", b"aa", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    response = await client.get(
        "/api/v1/documents/?scope=user", headers=_auth(g2_token)
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_list_enhanced_ok_without_applications(
    client: AsyncClient,
    g2_token: str,
) -> None:
    response = await client.get(
        "/api/v1/documents/?scope=user&enhanced=true",
        headers=_auth(g2_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["requirements"] == []


async def test_list_enhanced_anon_401(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/documents/?scope=user&enhanced=true"
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


async def test_list_types_returns_seeded(
    client: AsyncClient,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    response = await client.get(
        "/api/v1/documents/types", headers=_auth(g2_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(t["type_code"] == "passport" for t in body["types"])


async def test_list_types_anon_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/documents/types")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Requirements (GET + POST)
# ---------------------------------------------------------------------------


async def test_get_requirements_returns_aggregate(
    client: AsyncClient, g2_token: str
) -> None:
    response = await client.get(
        "/api/v1/documents/requirements", headers=_auth(g2_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0


async def test_post_requirements_by_lc_ids(
    client: AsyncClient,
    db_session: AsyncSession,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    lc_company = Company(name="POST-LC", company_type="leasing_company")
    db_session.add(lc_company)
    await db_session.flush()
    lc = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    req = LeasingCompanyDocumentRequirement(
        leasing_company_id=lc.id,
        document_type_id=g2_passport_type.id,
        is_required=True,
        is_mandatory=True,
        is_active=True,
    )
    db_session.add(req)
    await db_session.flush()

    response = await client.post(
        "/api/v1/documents/requirements",
        json={"leasing_company_ids": [lc.id]},
        headers=_auth(g2_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["requirements"][0]["document_type"] == "passport"


async def test_post_requirements_rejects_empty_ids(
    client: AsyncClient, g2_token: str
) -> None:
    response = await client.post(
        "/api/v1/documents/requirements",
        json={"leasing_company_ids": []},
        headers=_auth(g2_token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Content (unified download / preview)
# ---------------------------------------------------------------------------


async def test_content_default_attachment(
    client: AsyncClient,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"download-bytes", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    assert upload.status_code == 201
    doc_id = upload.json()["documents"][0]["id"]

    response = await client.get(
        f"/api/v1/documents/{doc_id}/content", headers=_auth(g2_token)
    )
    assert response.status_code == 200
    assert response.content == b"download-bytes"
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition


async def test_content_inline_disposition(
    client: AsyncClient,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"preview-bytes", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    doc_id = upload.json()["documents"][0]["id"]
    response = await client.get(
        f"/api/v1/documents/{doc_id}/content?disposition=inline",
        headers=_auth(g2_token),
    )
    assert response.status_code == 200
    assert response.content == b"preview-bytes"
    disposition = response.headers.get("content-disposition", "")
    assert "inline" in disposition


async def test_content_denies_foreign_company(
    client: AsyncClient,
    g2_token: str,
    g2_other_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"secret", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    doc_id = upload.json()["documents"][0]["id"]
    response = await client.get(
        f"/api/v1/documents/{doc_id}/content",
        headers=_auth(g2_other_token),
    )
    assert response.status_code == 403


async def test_application_archive_returns_zip(
    client: AsyncClient,
    g2_token: str,
    g2_application: LeasingApplication,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"zipme", "image/jpeg")},
        data={
            "document_type": "passport",
            "application_id": str(g2_application.id),
        },
        headers=_auth(g2_token),
    )
    assert upload.status_code == 201
    response = await client.get(
        f"/api/v1/applications/{g2_application.id}/documents/archive",
        headers=_auth(g2_token),
    )
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" in disposition


# ---------------------------------------------------------------------------
# Delete / restore
# ---------------------------------------------------------------------------


async def test_delete_hides_and_restore_revives(
    client: AsyncClient,
    g2_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"bytes", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    doc_id = upload.json()["documents"][0]["id"]

    delete_resp = await client.delete(
        f"/api/v1/documents/{doc_id}", headers=_auth(g2_token)
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["document_id"] == doc_id

    listing = await client.get(
        "/api/v1/documents/", headers=_auth(g2_token)
    )
    assert listing.json()["total"] == 0

    restore_resp = await client.post(
        f"/api/v1/documents/{doc_id}/restore", headers=_auth(g2_token)
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["document"]["is_current_version"] is True


async def test_delete_denies_foreign_company(
    client: AsyncClient,
    g2_token: str,
    g2_other_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"bytes", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    doc_id = upload.json()["documents"][0]["id"]

    response = await client.delete(
        f"/api/v1/documents/{doc_id}", headers=_auth(g2_other_token)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Reviews (renamed from leasing-review)
# ---------------------------------------------------------------------------


async def test_reviews_require_employee_scope(
    client: AsyncClient,
    g2_token: str,
    g2_employee_token: str,
    g2_passport_type: DocumentType,
) -> None:
    _ = g2_passport_type
    upload = await client.post(
        "/api/v1/documents/",
        files={"files": ("pass.jpg", b"bytes", "image/jpeg")},
        data={"document_type": "passport"},
        headers=_auth(g2_token),
    )
    doc_id = upload.json()["documents"][0]["id"]

    forbidden = await client.post(
        f"/api/v1/documents/{doc_id}/reviews",
        json={"status": "approved"},
        headers=_auth(g2_token),
    )
    assert forbidden.status_code == 403

    allowed = await client.post(
        f"/api/v1/documents/{doc_id}/reviews",
        json={"status": "approved", "comments": "ok"},
        headers=_auth(g2_employee_token),
    )
    assert allowed.status_code == 200
