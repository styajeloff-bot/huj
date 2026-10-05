"""Persistence and read-contract tests for document-request history."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications import GetApplicationQuery, handle_get_application
from application.queries.documents import (
    ListDocumentRequestsQuery,
    handle_list_document_requests,
)
from application.queries.leasing_response import (
    GetLcResponseStateQuery,
    handle_get_lc_response_state,
)
from domain.errors import ApplicationNotOwnedError, DocumentAccessDeniedError
from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import (
    ApplicationDocument,
    ApplicationDocumentRequest,
    Document,
)
from infrastructure.models.users import User
from infrastructure.repositories import (
    application_documents_repository as requests_repo,
)
from presentation.schemas.documents import DocumentRequestsResponse

pytestmark = pytest.mark.asyncio


async def _seed_history_context(
    session: AsyncSession,
) -> dict[str, Any]:
    client_company = Company(name="History Client", company_type="other")
    lc_company_a = Company(name="History LC A", company_type="leasing_company")
    lc_company_b = Company(name="History LC B", company_type="leasing_company")
    session.add_all([client_company, lc_company_a, lc_company_b])
    await session.flush()

    lc_a = LeasingCompany(company_id=lc_company_a.id, is_active=True)
    lc_b = LeasingCompany(company_id=lc_company_b.id, is_active=True)
    session.add_all([lc_a, lc_b])
    await session.flush()

    author_a = User(
        phone="+76661110001",
        name="Author A",
        role="leasing_company",
        company_id=lc_company_a.id,
        is_active=True,
    )
    author_b = User(
        phone="+76661110002",
        name="Author B",
        role="leasing_company",
        company_id=lc_company_b.id,
        is_active=True,
    )
    client_user = User(
        phone="+76661110003",
        name="History Client User",
        role="client",
        company_id=client_company.id,
        is_active=True,
    )
    session.add_all([author_a, author_b, client_user])
    await session.flush()

    application = LeasingApplication(
        company_id=client_company.id,
        email="history@test.local",
        status="active",
        selected_leasing_companies=[lc_a.id, lc_b.id],
    )
    session.add(application)
    await session.flush()
    session.add_all([
        LeasingCompanyApplication(application_id=application.id, leasing_company_id=lc.id, status="documents_required")
        for lc in (lc_a, lc_b)
    ])
    await session.flush()
    return {
        "client_company": client_company,
        "lc_a": lc_a,
        "lc_b": lc_b,
        "author_a": author_a,
        "author_b": author_b,
        "client_user": client_user,
        "application": application,
    }


async def test_repeated_batch_preserves_outstanding_requests(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_history_context(db_session)
    requested_at = datetime(2026, 7, 11, 9, 0, tzinfo=UTC)
    first_batch = await requests_repo.create_requests_batch(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
        request_batch_id=uuid4(),
        requested_by=ctx["author_a"].id,
        requested_at=requested_at,
        documents=[
            {"display_name": "Паспорт", "slug": "passport"},
            {"display_name": "Баланс", "slug": "balance"},
        ],
        request_message="Первый запрос",
    )
    assert await requests_repo.mark_request_provided(
        db_session,
        request_id=first_batch[0]["id"],
        provided_at=requested_at + timedelta(minutes=1),
    )

    additional_batch = await requests_repo.create_requests_batch(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
        request_batch_id=uuid4(),
        requested_by=ctx["author_a"].id,
        requested_at=requested_at + timedelta(minutes=2),
        documents=[
            {"display_name": "Карточка счёта", "slug": "account_card"},
        ],
        request_message="Уточнённый запрос",
    )

    provided = await requests_repo.get_request_by_id(
        db_session, first_batch[0]["id"]
    )
    outstanding = await requests_repo.get_request_by_id(
        db_session, first_batch[1]["id"]
    )
    assert provided is not None and provided["status"] == "provided"
    assert outstanding is not None and outstanding["status"] == "requested"
    assert outstanding["request_batch_id"] == first_batch[1]["request_batch_id"]
    assert outstanding["display_name"] == "Баланс"
    assert outstanding["requested_by"] == ctx["author_a"].id
    assert await requests_repo.mark_request_provided(
        db_session,
        request_id=first_batch[1]["id"],
        provided_at=requested_at + timedelta(minutes=3),
    )
    assert await requests_repo.has_pending_required_requests(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
    )

    assert await requests_repo.mark_request_provided(
        db_session,
        request_id=additional_batch[0]["id"],
        provided_at=requested_at + timedelta(minutes=4),
    )
    assert not await requests_repo.has_pending_required_requests(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
    )
    history = await requests_repo.list_request_history(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
    )
    assert {row["status"] for row in history} == {"provided"}

    db_session.add(
        ApplicationDocumentRequest(
            application_id=ctx["application"].id,
            leasing_company_id=ctx["lc_a"].id,
            request_batch_id=uuid4(),
            document_type="optional_note",
            display_name="Необязательное пояснение",
            status="requested",
            is_required=False,
            requested_by=ctx["author_a"].id,
            requested_at=requested_at + timedelta(minutes=5),
        )
    )
    await db_session.flush()
    assert not await requests_repo.has_pending_required_requests(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
    )


async def test_history_grouping_scope_and_linked_document(
    db_session: AsyncSession,
    client: AsyncClient,
) -> None:
    ctx = await _seed_history_context(db_session)
    older = datetime(2026, 7, 11, 9, 0, tzinfo=UTC)
    lc_a_batch_id = uuid4()
    lc_b_batch_id = uuid4()
    lc_a_requests = await requests_repo.create_requests_batch(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_a"].id,
        request_batch_id=lc_a_batch_id,
        requested_by=ctx["author_a"].id,
        requested_at=older,
        documents=[
            {"display_name": "Паспорт директора", "slug": "director_passport"},
            {"display_name": "Баланс", "slug": "balance"},
        ],
        request_message="Для проверки",
    )
    await requests_repo.create_requests_batch(
        db_session,
        application_id=ctx["application"].id,
        leasing_company_id=ctx["lc_b"].id,
        request_batch_id=lc_b_batch_id,
        requested_by=ctx["author_b"].id,
        requested_at=older + timedelta(hours=1),
        documents=[
            {"display_name": "ОСВ", "slug": "trial_balance"},
        ],
        request_message=None,
    )

    uploaded_at = older + timedelta(minutes=15)
    document = Document(
        company_id=ctx["client_company"].id,
        document_type="director_passport",
        file_name="passport.pdf",
        file_size=2048,
        status="uploaded",
        related_application_id=ctx["application"].id,
        uploaded_at=uploaded_at,
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        ApplicationDocument(
            application_id=ctx["application"].id,
            document_id=document.id,
            document_request_id=lc_a_requests[0]["id"],
            leasing_company_id=ctx["lc_a"].id,
            status="submitted",
        )
    )
    await db_session.flush()
    assert await requests_repo.mark_request_provided(
        db_session,
        request_id=lc_a_requests[0]["id"],
        provided_at=uploaded_at,
    )

    client_result = await handle_list_document_requests(
        ListDocumentRequestsQuery(
            application_id=ctx["application"].id,
            actor_user_id=ctx["client_user"].id,
            actor_role="client",
            actor_company_id=ctx["client_company"].id,
        ),
        db_session,
    )
    assert [batch["request_batch_id"] for batch in client_result["batches"]] == [
        lc_b_batch_id,
        lc_a_batch_id,
    ]
    assert client_result["batches"][1]["leasing_company"]["name"] == "History LC A"
    assert client_result["batches"][1]["requested_by"]["name"] == "Author A"
    assert client_result["batches"][1]["comments"] == "Для проверки"
    passport_item = next(
        item
        for item in client_result["batches"][1]["items"]
        if item["slug"] == "director_passport"
    )
    linked = passport_item["document"]
    assert linked["file_name"] == "passport.pdf"
    assert linked["status"] == "submitted"
    assert linked["download_url"] == f"/api/v1/documents/{document.id}/content"
    DocumentRequestsResponse.model_validate(client_result)

    lc_result = await handle_list_document_requests(
        ListDocumentRequestsQuery(
            application_id=ctx["application"].id,
            actor_user_id=ctx["author_a"].id,
            actor_role="leasing_company",
            actor_company_id=None,
            actor_leasing_company_id=ctx["lc_a"].id,
        ),
        db_session,
    )
    assert lc_result["total"] == 1
    assert lc_result["batches"][0]["request_batch_id"] == lc_a_batch_id

    with pytest.raises(ApplicationNotOwnedError):
        await handle_list_document_requests(
            ListDocumentRequestsQuery(
                application_id=ctx["application"].id,
                actor_user_id=ctx["author_a"].id,
                actor_role="leasing_company",
                actor_company_id=ctx["lc_a"].company_id,
                actor_leasing_company_id=ctx["lc_b"].id,
            ),
            db_session,
        )

    employee_result = await handle_list_document_requests(
        ListDocumentRequestsQuery(
            application_id=ctx["application"].id,
            actor_user_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )
    assert employee_result["total"] == 2

    with pytest.raises(DocumentAccessDeniedError):
        await handle_list_document_requests(
            ListDocumentRequestsQuery(
                application_id=ctx["application"].id,
                actor_user_id=uuid4(),
                actor_role="client",
                actor_company_id=uuid4(),
            ),
            db_session,
        )

    access_token, _ = generate_tokens(
        ctx["client_user"].id,
        "client",
        ctx["client_company"].id,
    )
    response = await client.get(
        f"/api/v1/applications/{ctx['application'].id}/document-requests",
        headers={"Authorization": f"Bearer {cast('str', access_token)}"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_lc_display_status_projection_is_lifecycle_and_tenant_scoped(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_history_context(db_session)
    application = ctx["application"]
    lc_a = ctx["lc_a"]
    lc_b = ctx["lc_b"]
    links = (
        await db_session.execute(
            select(LeasingCompanyApplication).where(
                LeasingCompanyApplication.application_id == application.id
            )
        )
    ).scalars().all()
    next(link for link in links if link.leasing_company_id == lc_a.id).status = "approved_scoring"
    unrelated = LeasingApplication(
        company_id=ctx["client_company"].id,
        email="unrelated-history@test.local",
        status="active",
    )
    db_session.add(unrelated)
    await db_session.flush()
    db_session.add_all([
        ApplicationDocumentRequest(
            application_id=unrelated.id,
            leasing_company_id=lc_a.id,
            document_type="passport",
            display_name="Other application",
            status="provided",
            is_required=True,
        ),
        ApplicationDocumentRequest(
            application_id=application.id,
            leasing_company_id=lc_b.id,
            document_type="balance",
            display_name="Requested",
            status="requested",
            is_required=True,
        ),
        ApplicationDocumentRequest(
            application_id=application.id,
            leasing_company_id=lc_a.id,
            document_type="optional_note",
            display_name="Optional provided",
            status="provided",
            is_required=False,
        ),
        ApplicationDocumentRequest(
            application_id=application.id,
            leasing_company_id=lc_a.id,
            document_type="rejected_note",
            display_name="Rejected",
            status="rejected",
            is_required=True,
        ),
        ApplicationDocumentRequest(
            application_id=application.id,
            leasing_company_id=lc_a.id,
            document_type="superseded_note",
            display_name="Superseded",
            status="superseded",
            is_required=True,
        ),
    ])
    await db_session.flush()
    statuses = await requests_repo.list_lc_display_statuses(
        db_session, application_id=application.id
    )
    assert statuses == {lc_a.id: "approved_scoring", lc_b.id: "documents_required"}

    requested = ApplicationDocumentRequest(
        application_id=application.id,
        leasing_company_id=lc_a.id,
        document_type="bank_statement",
        display_name="Still requested",
        status="requested",
        is_required=True,
    )
    provided = ApplicationDocumentRequest(
        application_id=application.id,
        leasing_company_id=lc_a.id,
        document_type="passport",
        display_name="Provided",
        status="provided",
        is_required=True,
    )
    db_session.add_all([requested, provided])
    await db_session.flush()
    statuses = await requests_repo.list_lc_display_statuses(
        db_session, application_id=application.id
    )
    # A required provided request takes precedence over a required requested
    # request; optional and closed historical requests do not participate.
    assert statuses[lc_a.id] == "under_review_with_docs"
    foreign_lc_document = Document(
        company_id=ctx["client_company"].id,
        document_type="passport",
        file_name="foreign-lc-passport.pdf",
        file_size=2048,
        status="uploaded",
        related_application_id=application.id,
    )
    foreign_application_document = Document(
        company_id=ctx["client_company"].id,
        document_type="passport",
        file_name="foreign-application-passport.pdf",
        file_size=2048,
        status="uploaded",
        related_application_id=unrelated.id,
    )
    db_session.add_all([foreign_lc_document, foreign_application_document])
    await db_session.flush()
    db_session.add_all([
        # Neither mismatched scope can close the target provided request.
        ApplicationDocument(
            application_id=application.id,
            document_id=foreign_lc_document.id,
            document_request_id=provided.id,
            leasing_company_id=lc_b.id,
            status="approved",
        ),
        ApplicationDocument(
            application_id=unrelated.id,
            document_id=foreign_application_document.id,
            document_request_id=provided.id,
            leasing_company_id=lc_a.id,
            status="approved",
        ),
    ])
    await db_session.flush()
    statuses = await requests_repo.list_lc_display_statuses(
        db_session, application_id=application.id
    )
    assert statuses[lc_a.id] == "under_review_with_docs"

    approved_document = Document(
        company_id=ctx["client_company"].id,
        document_type="passport",
        file_name="approved-passport.pdf",
        file_size=2048,
        status="uploaded",
        related_application_id=application.id,
    )
    db_session.add(approved_document)
    await db_session.flush()
    db_session.add(
        ApplicationDocument(
            application_id=application.id,
            document_id=approved_document.id,
            document_request_id=provided.id,
            leasing_company_id=lc_a.id,
            status="approved",
        )
    )
    await db_session.flush()
    statuses = await requests_repo.list_lc_display_statuses(
        db_session, application_id=application.id
    )
    # A legacy provided request is closed read-only by an approved document
    # linked to the same request, application, and leasing company.
    assert statuses[lc_a.id] == "documents_required"
    assert await requests_repo.mark_request_approved(db_session, request_id=provided.id)
    statuses = await requests_repo.list_lc_display_statuses(
        db_session, application_id=application.id
    )
    assert statuses[lc_a.id] == "documents_required"
    requested = await db_session.scalar(
        select(ApplicationDocumentRequest).where(
            ApplicationDocumentRequest.application_id == application.id,
            ApplicationDocumentRequest.leasing_company_id == lc_a.id,
            ApplicationDocumentRequest.document_type == "bank_statement",
        )
    )
    assert requested is not None
    assert await requests_repo.mark_request_approved(db_session, request_id=requested.id)
    statuses = await requests_repo.list_lc_display_statuses(
        db_session, application_id=application.id
    )
    assert statuses[lc_a.id] == "approved_scoring"


async def test_application_and_lc_response_projections_are_tenant_scoped(
    db_session: AsyncSession,
    client: AsyncClient,
) -> None:
    ctx = await _seed_history_context(db_session)
    application = ctx["application"]
    lc_a = ctx["lc_a"]
    lc_b = ctx["lc_b"]
    links = (
        await db_session.execute(
            select(LeasingCompanyApplication).where(
                LeasingCompanyApplication.application_id == application.id
            )
        )
    ).scalars().all()
    link_a = next(link for link in links if link.leasing_company_id == lc_a.id)
    link_b = next(link for link in links if link.leasing_company_id == lc_b.id)
    link_a.status = "approved_scoring"
    link_b.status = "under_review"
    db_session.add_all([
        ApplicationDocumentRequest(
            application_id=application.id,
            leasing_company_id=lc_a.id,
            document_type="passport",
            display_name="A requested",
            status="requested",
            is_required=True,
        ),
        ApplicationDocumentRequest(
            application_id=application.id,
            leasing_company_id=lc_b.id,
            document_type="balance",
            display_name="B provided",
            status="provided",
            is_required=True,
        ),
    ])
    await db_session.flush()

    client_detail = await handle_get_application(
        GetApplicationQuery(
            application_id=application.id,
            actor_id=ctx["client_user"].id,
            actor_role="client",
            actor_company_id=ctx["client_company"].id,
        ),
        db_session,
    )
    client_links = {
        link["leasing_company_id"]: link
        for link in client_detail["leasing_company_applications"]
    }
    assert client_links[lc_a.id]["status"] == "approved_scoring"
    assert client_links[lc_a.id]["display_status"] == "documents_required"
    assert client_links[lc_b.id]["status"] == "under_review"
    assert client_links[lc_b.id]["display_status"] == "under_review_with_docs"

    access_token, _ = generate_tokens(
        ctx["client_user"].id,
        "client",
        ctx["client_company"].id,
    )
    response = await client.get(
        f"/api/v1/leasing-company-applications/?application_id={application.id}",
        headers={"Authorization": f"Bearer {cast('str', access_token)}"},
    )
    assert response.status_code == 200
    checkout_links = {
        link["leasing_company_id"]: link for link in response.json()["items"]
    }
    assert checkout_links[str(lc_a.id)]["status"] == "approved_scoring"
    assert checkout_links[str(lc_a.id)]["display_status"] == "documents_required"
    assert checkout_links[str(lc_b.id)]["status"] == "under_review"
    assert checkout_links[str(lc_b.id)]["display_status"] == "under_review_with_docs"

    lc_a_state = await handle_get_lc_response_state(
        GetLcResponseStateQuery(
            application_id=application.id,
            actor_leasing_company_id=lc_a.id,
            actor_user_id=ctx["author_a"].id,
            actor_company_id=lc_a.company_id,
        ),
        db_session,
    )
    # The LC cabinet exposes the authenticated LC's own link and never lets
    # another LC's provided request override this link's actual state.
    assert lc_a_state["link"]["leasing_company_id"] == lc_a.id
    assert lc_a_state["link"]["status"] == "approved_scoring"
    assert lc_a_state["link"]["display_status"] == "documents_required"
