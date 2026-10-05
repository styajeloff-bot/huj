"""Client application visibility and document company-context regressions."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import ApplicationDocumentRequest
from infrastructure.models.users import User, UserCompany
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage

pytestmark = pytest.mark.asyncio


@dataclass
class ClientApplications:
    current_company: Company
    applicant_company: Company
    actor: User
    membership: UserCompany
    application: LeasingApplication


@pytest_asyncio.fixture
async def applications_context(db_session: AsyncSession) -> ClientApplications:
    current_company = Company(name="Current company", company_type="other")
    applicant_company = Company(name="Applicant company", company_type="other")
    db_session.add_all([current_company, applicant_company])
    await db_session.flush()
    actor = User(
        phone="+72224400001",
        role="client",
        company_id=current_company.id,
        is_active=True,
    )
    db_session.add(actor)
    await db_session.flush()
    membership = UserCompany(
        user_id=actor.id,
        company_id=applicant_company.id,
        sub_role="employee",
        can_view_applications=True,
        can_create_applications=True,
    )
    application = LeasingApplication(
        company_id=applicant_company.id,
        created_by=actor.id,
        email="application@example.test",
        status="active",
        updated_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    db_session.add_all([membership, application])
    await db_session.flush()
    return ClientApplications(
        current_company, applicant_company, actor, membership, application,
    )


def _auth(actor: User, company_id: UUID | None) -> dict[str, str]:
    token, _ = generate_tokens(actor.id, "client", company_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("context", ["other_company", "no_company", "applicant"])
async def test_client_list_contains_own_application_visible_in_detail(
    client: AsyncClient,
    applications_context: ClientApplications,
    context: Literal["other_company", "no_company", "applicant"],
) -> None:
    case = applications_context
    company_id = {
        "other_company": case.current_company.id,
        "no_company": None,
        "applicant": case.applicant_company.id,
    }[context]
    headers = _auth(case.actor, company_id)

    detail = await client.get(
        f"/api/v1/applications/{case.application.id}", headers=headers,
    )
    assert detail.status_code == 200, detail.text
    listing = await client.get("/api/v1/applications", headers=headers)

    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["applications"]] == [
        str(case.application.id),
    ]
    assert listing.json()["total"] == 1


@pytest.mark.parametrize("can_view_company", [True, False])
async def test_authorship_and_current_company_read_permission_are_independent(
    client: AsyncClient,
    db_session: AsyncSession,
    applications_context: ClientApplications,
    can_view_company: bool,
) -> None:
    case = applications_context
    db_session.add(
        UserCompany(
            user_id=case.actor.id,
            company_id=case.current_company.id,
            sub_role="employee",
            can_view_applications=can_view_company,
            can_create_applications=True,
        )
    )
    colleague_application = LeasingApplication(
        company_id=case.current_company.id,
        email="colleague@example.test",
        status="active",
    )
    db_session.add(colleague_application)
    await db_session.flush()

    listing = await client.get(
        "/api/v1/applications",
        headers=_auth(case.actor, case.current_company.id),
    )

    assert listing.status_code == 200, listing.text
    ids = {row["id"] for row in listing.json()["applications"]}
    assert str(case.application.id) in ids
    assert (str(colleague_application.id) in ids) is can_view_company
    assert listing.json()["total"] == (2 if can_view_company else 1)


async def test_explicit_company_limits_list_without_expanding_to_other_authored_rows(
    client: AsyncClient,
    db_session: AsyncSession,
    applications_context: ClientApplications,
) -> None:
    case = applications_context
    own_current = LeasingApplication(
        company_id=case.current_company.id,
        created_by=case.actor.id,
        email="own-current@example.test",
        status="active",
    )
    colleague_other = LeasingApplication(
        company_id=case.applicant_company.id,
        email="colleague-other@example.test",
        status="active",
    )
    db_session.add_all([own_current, colleague_other])
    await db_session.flush()
    headers = _auth(case.actor, case.current_company.id)

    listing = await client.get("/api/v1/applications", headers=headers)
    assert listing.status_code == 200, listing.text
    assert {row["id"] for row in listing.json()["applications"]} == {
        str(case.application.id), str(own_current.id),
    }
    selected = await client.get(
        "/api/v1/applications",
        headers=headers,
        params={"notification_company_id": str(case.applicant_company.id)},
    )

    assert selected.status_code == 200, selected.text
    assert {row["id"] for row in selected.json()["applications"]} == {
        str(case.application.id), str(colleague_other.id),
    }
    assert selected.json()["total"] == 2


@pytest.fixture
def document_storage() -> Iterator[None]:
    set_object_storage(FakeObjectStorage())
    try:
        yield
    finally:
        set_object_storage(None)


async def test_new_application_for_another_allowed_company_appears_in_client_list(
    client: AsyncClient,
    applications_context: ClientApplications,
    document_storage: None,
) -> None:
    case = applications_context
    headers = _auth(case.actor, case.current_company.id)
    created = await client.post(
        "/api/v1/applications/draft",
        headers=headers | {"Idempotency-Key": "client-list-22244"},
        json={
            "company_id": str(case.applicant_company.id),
            "vehicles": [
                {
                    "modification_id": "CLIENT-LIST-22244",
                    "quantity": 1,
                    "custom_price": "100.00",
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    application_id = created.json()["application_id"]

    detail = await client.get(
        f"/api/v1/applications/{application_id}", headers=headers,
    )
    assert detail.status_code == 200, detail.text
    listing = await client.get("/api/v1/applications", headers=headers)

    assert listing.status_code == 200, listing.text
    assert application_id in {
        row["id"] for row in listing.json()["applications"]
    }


async def test_client_list_pagination_status_and_totals_share_visible_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    applications_context: ClientApplications,
) -> None:
    case = applications_context
    first_update = datetime(2026, 9, 13, tzinfo=UTC)
    own_current = LeasingApplication(
        company_id=case.current_company.id,
        created_by=case.actor.id,
        email="own-current@example.test",
        status="rejected",
        updated_at=first_update + timedelta(seconds=1),
    )
    colleague_current = LeasingApplication(
        company_id=case.current_company.id,
        email="colleague-current@example.test",
        status="active",
        updated_at=first_update + timedelta(seconds=2),
    )
    colleague_other = LeasingApplication(
        company_id=case.applicant_company.id,
        email="colleague-other@example.test",
        status="active",
        updated_at=first_update + timedelta(seconds=3),
    )
    db_session.add_all([own_current, colleague_current, colleague_other])
    await db_session.flush()
    headers = _auth(case.actor, case.current_company.id)

    pages = [
        await client.get(
            "/api/v1/applications", headers=headers,
            params={"page": page, "limit": 1},
        )
        for page in (1, 2, 3)
    ]
    for page in pages:
        assert page.status_code == 200, page.text
        assert page.json()["total"] == 3
        assert page.json()["pagination"]["pages"] == 3
    assert [
        row["id"] for page in pages for row in page.json()["applications"]
    ] == [
        str(colleague_current.id), str(own_current.id), str(case.application.id),
    ]

    active = await client.get(
        "/api/v1/applications", headers=headers, params={"status": "active"},
    )
    assert active.status_code == 200, active.text
    assert [row["id"] for row in active.json()["applications"]] == [
        str(colleague_current.id), str(case.application.id),
    ]
    assert active.json()["total"] == 2


@pytest.mark.parametrize("invalid_context", ["foreign", "revoked", "removed"])
async def test_explicit_company_cannot_bypass_membership_or_document_access(
    client: AsyncClient,
    db_session: AsyncSession,
    applications_context: ClientApplications,
    invalid_context: Literal["foreign", "revoked", "removed"],
) -> None:
    case = applications_context
    selected_company_id = case.applicant_company.id
    if invalid_context == "foreign":
        foreign_company = Company(name="Foreign company", company_type="other")
        db_session.add(foreign_company)
        await db_session.flush()
        selected_company_id = foreign_company.id
    elif invalid_context == "revoked":
        case.membership.can_view_applications = False
    else:
        await db_session.delete(case.membership)
    await db_session.flush()
    headers = _auth(case.actor, case.current_company.id)
    selector = {"notification_company_id": str(selected_company_id)}
    application_url = f"/api/v1/applications/{case.application.id}"

    # Existing author access to the application does not grant file access.
    detail = await client.get(application_url, headers=headers)
    assert detail.status_code == 200, detail.text
    listing = await client.get("/api/v1/applications", headers=headers)
    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["applications"]] == [
        str(case.application.id),
    ]

    for url in [
        "/api/v1/applications",
        application_url,
        f"{application_url}/document-requests",
    ]:
        denied = await client.get(url, headers=headers, params=selector)
        assert denied.status_code == 403, denied.text
    upload = await client.post(
        "/api/v1/documents",
        headers=headers,
        params=selector,
        files={"files": ("requested.pdf", b"test", "application/pdf")},
        data={
            "application_id": str(case.application.id),
            "document_type": "additional_document",
        },
    )
    assert upload.status_code == 403, upload.text


async def test_membership_in_another_company_does_not_expand_default_list(
    client: AsyncClient,
    db_session: AsyncSession,
    applications_context: ClientApplications,
) -> None:
    case = applications_context
    case.application.created_by = None
    await db_session.flush()
    headers = _auth(case.actor, case.current_company.id)

    listing = await client.get("/api/v1/applications", headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["applications"] == []
    assert listing.json()["total"] == 0
    detail = await client.get(
        f"/api/v1/applications/{case.application.id}", headers=headers,
    )
    assert detail.status_code == 403, detail.text


async def test_application_company_context_supports_requested_document_lifecycle(
    client: AsyncClient,
    db_session: AsyncSession,
    applications_context: ClientApplications,
    document_storage: None,
) -> None:
    case = applications_context
    company = Company(name="Leasing provider", company_type="leasing_company")
    db_session.add(company)
    await db_session.flush()
    leasing_company = LeasingCompany(company_id=company.id, is_active=True)
    db_session.add(leasing_company)
    await db_session.flush()
    case.application.selected_leasing_companies = [leasing_company.id]
    link = LeasingCompanyApplication(
        application_id=case.application.id,
        leasing_company_id=leasing_company.id,
        status="documents_required",
    )
    document_request = ApplicationDocumentRequest(
        application_id=case.application.id,
        leasing_company_id=leasing_company.id,
        document_type="additional_document",
        display_name="Additional document",
        status="requested",
        requested_by=case.actor.id,
    )
    db_session.add_all([link, document_request])
    await db_session.flush()
    headers = _auth(case.actor, case.current_company.id)
    application_url = f"/api/v1/applications/{case.application.id}"
    detail = await client.get(application_url, headers=headers)
    assert detail.status_code == 200, detail.text
    selector = {"notification_company_id": detail.json()["company_id"]}

    history = await client.get(
        f"{application_url}/document-requests", headers=headers, params=selector,
    )
    assert history.status_code == 200, history.text
    assert history.json()["batches"][0]["items"][0]["id"] == str(
        document_request.id,
    )
    data = {
        "application_id": str(case.application.id),
        "document_request_id": str(document_request.id),
    }
    files = {"files": ("requested.pdf", b"requested document", "application/pdf")}
    denied = await client.post(
        "/api/v1/documents", headers=headers, files=files, data=data,
    )
    assert denied.status_code == 403, denied.text
    uploaded = await client.post(
        "/api/v1/documents",
        headers=headers, params=selector, files=files, data=data,
    )
    assert uploaded.status_code == 201, uploaded.text

    document_id = uploaded.json()["documents"][0]["id"]
    content = await client.get(
        f"/api/v1/documents/{document_id}/content",
        headers=headers, params=selector,
    )
    assert content.status_code == 200, content.text
    assert content.content == b"requested document"
    updated = await client.get(
        f"{application_url}/document-requests", headers=headers, params=selector,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["batches"][0]["items"][0]["status"] == "provided"

    # The same signed cookie must observe a revoked company permission.
    case.membership.can_view_applications = False
    await db_session.flush()
    denied_content = await client.get(
        f"/api/v1/documents/{document_id}/content",
        headers=headers, params=selector,
    )
    assert denied_content.status_code == 403, denied_content.text
