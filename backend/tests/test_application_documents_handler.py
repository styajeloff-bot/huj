"""Unit-level handler tests for Phase 4 D2 requirements + D1 event consumer.

After Phase 15 H3 the document-request / review / pending-reviews flow
was deleted because no frontend consumed it; the requirements alias
(`/leasing/document-requirements`) plus the DocumentUploadedEvent
subscriber remain, so this suite keeps their coverage.
"""
from __future__ import annotations

import uuid
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.application_documents_tasks import (
    event_to_dict,
    handle_document_uploaded,
)
from application.commands.application_documents import (
    RequirementInput,
    UpdateRequirementsCommand,
    handle_update_requirements,
)
from application.queries.application_documents import (
    ListLcRequirementsQuery,
    handle_list_lc_requirements,
)
from domain.errors import (
    DocumentTypeNotFoundError,
    LeasingCompanyNotFoundError,
    RequirementsUpdateAccessDeniedError,
)
from domain.events.documents_events import DocumentUploadedEvent
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import DocumentType

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def lc_company(db_session: AsyncSession) -> Company:
    row = Company(name="LC Co", company_type="leasing_company")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def leasing_company(
    db_session: AsyncSession, lc_company: Company
) -> LeasingCompany:
    row = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def lc_company_b(db_session: AsyncSession) -> Company:
    row = Company(name="LC Co B", company_type="leasing_company")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def leasing_company_b(
    db_session: AsyncSession, lc_company_b: Company
) -> LeasingCompany:
    row = LeasingCompany(company_id=lc_company_b.id, is_active=True)
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def document_type(db_session: AsyncSession) -> DocumentType:
    row = DocumentType(
        name="Паспорт",
        type_code="passport",
        file_types=["image/jpeg"],
        max_file_size_mb=5,
        auto_approve=False,
    )
    db_session.add(row)
    await db_session.flush()
    return row


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


async def test_update_requirements_replace_wholesale(
    db_session: AsyncSession,
    leasing_company: LeasingCompany,
    document_type: DocumentType,
) -> None:
    cmd = UpdateRequirementsCommand(
        leasing_company_id=leasing_company.id,
        actor_user_id=uuid4(),
        actor_role="leasing_company",
        actor_leasing_company_id=leasing_company.id,
        requirements=[
            RequirementInput(
                document_type="passport",
                is_required=True,
                is_mandatory=True,
                sort_order=1,
            ),
        ],
    )
    res = await handle_update_requirements(cmd, db_session)
    assert res["updated_count"] == 1

    listed = await handle_list_lc_requirements(
        ListLcRequirementsQuery(
            leasing_company_id=leasing_company.id,
            actor_user_id=uuid4(),
            actor_role="leasing_company",
            actor_leasing_company_id=leasing_company.id,
        ),
        db_session,
    )
    assert listed["summary"]["total"] == 1
    assert listed["requirements"][0]["document_type"] == "passport"


async def test_update_requirements_lc_forbidden_for_other(
    db_session: AsyncSession,
    leasing_company: LeasingCompany,
    leasing_company_b: LeasingCompany,
) -> None:
    cmd = UpdateRequirementsCommand(
        leasing_company_id=leasing_company_b.id,
        actor_user_id=uuid4(),
        actor_role="leasing_company",
        actor_leasing_company_id=leasing_company.id,
        requirements=[],
    )
    with pytest.raises(RequirementsUpdateAccessDeniedError):
        await handle_update_requirements(cmd, db_session)


async def test_update_requirements_unknown_type_code(
    db_session: AsyncSession,
    leasing_company: LeasingCompany,
) -> None:
    cmd = UpdateRequirementsCommand(
        leasing_company_id=leasing_company.id,
        actor_user_id=uuid4(),
        actor_role="carcraft_employee",
        actor_leasing_company_id=None,
        requirements=[
            RequirementInput(document_type="non_existent", is_required=True),
        ],
    )
    with pytest.raises(DocumentTypeNotFoundError):
        await handle_update_requirements(cmd, db_session)


async def test_list_requirements_unknown_lc(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(LeasingCompanyNotFoundError):
        await handle_list_lc_requirements(
            ListLcRequirementsQuery(
                leasing_company_id=uuid4(),
                actor_user_id=uuid4(),
                actor_role="carcraft_employee",
                actor_leasing_company_id=None,
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# DocumentUploadedEvent subscriber
# ---------------------------------------------------------------------------


async def test_event_to_dict_roundtrip() -> None:
    event = DocumentUploadedEvent(
        document_id=uuid4(),
        company_id=uuid4(),
        uploaded_by_user_id=uuid4(),
        document_type="passport",
        application_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        auto_approved=True,
    )
    payload = event_to_dict(event)
    assert payload["document_id"] == event.document_id
    assert payload["auto_approved"] is True
    assert payload["application_id"] == uuid.UUID("00000000-0000-0000-0000-000000000004")
    assert isinstance(payload["occurred_at"], str)


async def test_handle_document_uploaded_does_not_raise() -> None:
    event = DocumentUploadedEvent(
        document_id=uuid4(),
        company_id=uuid4(),
        uploaded_by_user_id=uuid4(),
        document_type="passport",
        application_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        auto_approved=True,
    )
    payload = event_to_dict(event)
    await handle_document_uploaded(payload)


async def test_handle_document_uploaded_ignores_bad_payload() -> None:
    await handle_document_uploaded({"document_id": "not-an-int"})


async def test_handle_document_uploaded_no_app_noop() -> None:
    await handle_document_uploaded({"document_id": 1, "application_id": 0})
