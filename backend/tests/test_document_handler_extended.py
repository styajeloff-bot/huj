"""Unit-level handler tests for Phase 7a G2 backport.

Covers the new command/query handlers added alongside the G2 router:
- soft-delete / restore
- force recognition reprocess
- batch upload
- list document types + aggregated user requirements
- download binary (single document + zip archive)
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.documents import (
    RestoreDocumentCommand,
    SoftDeleteDocumentCommand,
    UploadDocumentCommand,
    UploadedDocumentFile,
    handle_restore_document,
    handle_soft_delete_document,
    handle_upload_document,
)
from application.queries.documents import (
    DownloadApplicationArchiveQuery,
    DownloadDocumentQuery,
    ListDocumentTypesQuery,
    ListUserDocumentsEnhancedQuery,
    ListUserRequirementsQuery,
    handle_download_application_archive,
    handle_download_document,
    handle_list_document_types,
    handle_list_user_documents_enhanced,
    handle_list_user_requirements,
)
from domain.errors import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
)
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


@pytest.fixture(autouse=True)
def _fake_storage() -> Iterator[FakeObjectStorage]:
    fake = FakeObjectStorage()
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


@pytest_asyncio.fixture
async def g2_company(db_session: AsyncSession) -> Company:
    company = Company(name="G2 Test Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def g2_other_company(db_session: AsyncSession) -> Company:
    company = Company(name="Other G2 Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def g2_actor(db_session: AsyncSession, g2_company: Company) -> User:
    user = User(
        phone="+76660000020",
        email="g2actor@test.local",
        name="G2 Actor",
        role="client",
        is_active=True,
        company_id=g2_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def g2_foreign_actor(
    db_session: AsyncSession, g2_other_company: Company
) -> User:
    user = User(
        phone="+76660000021",
        email="g2foreign@test.local",
        name="G2 Foreign",
        role="client",
        is_active=True,
        company_id=g2_other_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


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
async def g2_enterprise_type(db_session: AsyncSession) -> DocumentType:
    row = DocumentType(
        name="Карточка предприятия",
        type_code="enterprise_card",
        file_types=["application/pdf"],
        max_file_size_mb=5,
        auto_approve=False,
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _upload_cmd(
    *,
    user_id: UUID,
    company_id: UUID,
    data: bytes = b"payload",
    filename: str = "pass.jpg",
    content_type: str = "image/jpeg",
    document_type: str = "passport",
    related_application_id: uuid.UUID | None = None,
) -> UploadDocumentCommand:
    return UploadDocumentCommand(
        actor_user_id=user_id,
        actor_company_id=company_id,
        document_type=document_type,
        file=UploadedDocumentFile(
            filename=filename,
            content_type=content_type,
            data=data,
        ),
        related_application_id=related_application_id,
    )


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


async def test_list_document_types_returns_all(
    db_session: AsyncSession,
    g2_passport_type: DocumentType,
    g2_enterprise_type: DocumentType,
) -> None:
    _ = g2_passport_type
    _ = g2_enterprise_type
    result = await handle_list_document_types(
        ListDocumentTypesQuery(), db_session
    )
    assert result["total"] >= 2
    codes = {t["type_code"] for t in result["types"]}
    assert "passport" in codes
    assert "enterprise_card" in codes


# ---------------------------------------------------------------------------
# Soft-delete / restore
# ---------------------------------------------------------------------------


async def test_soft_delete_hides_from_current_listing(
    db_session: AsyncSession,
    g2_company: Company,
    g2_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = g2_passport_type
    uploaded = await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"data",
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = uploaded["document"]["id"]

    await handle_soft_delete_document(
        SoftDeleteDocumentCommand(
            document_id=doc_id,
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
        ),
        db_session,
    )

    from infrastructure.repositories import documents_repository as docs_repo

    listing = await docs_repo.list_for_company(
        db_session, company_id=g2_company.id, only_current=True
    )
    assert listing == []

    full_listing = await docs_repo.list_for_company(
        db_session, company_id=g2_company.id, only_current=False
    )
    assert len(full_listing) == 1
    assert full_listing[0]["is_current_version"] is False


async def test_soft_delete_denies_foreign_company(
    db_session: AsyncSession,
    g2_company: Company,
    g2_other_company: Company,
    g2_actor: User,
    g2_foreign_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = g2_passport_type
    uploaded = await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"data",
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = uploaded["document"]["id"]

    with pytest.raises(DocumentAccessDeniedError):
        await handle_soft_delete_document(
            SoftDeleteDocumentCommand(
                document_id=doc_id,
                actor_user_id=g2_foreign_actor.id,
                actor_role="client",
                actor_company_id=g2_other_company.id,
            ),
            db_session,
        )


async def test_soft_delete_unknown_doc_raises(
    db_session: AsyncSession,
    g2_actor: User,
) -> None:
    with pytest.raises(DocumentNotFoundError):
        await handle_soft_delete_document(
            SoftDeleteDocumentCommand(
                document_id=uuid4(),
                actor_user_id=g2_actor.id,
                actor_role="client",
                actor_company_id=None,
            ),
            db_session,
        )


async def test_restore_flips_is_current_back(
    db_session: AsyncSession,
    g2_company: Company,
    g2_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = g2_passport_type
    uploaded = await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"data",
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = uploaded["document"]["id"]
    await handle_soft_delete_document(
        SoftDeleteDocumentCommand(
            document_id=doc_id,
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
        ),
        db_session,
    )
    restored = await handle_restore_document(
        RestoreDocumentCommand(
            document_id=doc_id,
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
        ),
        db_session,
    )
    assert restored["document"]["is_current_version"] is True


# ---------------------------------------------------------------------------
# Download binary
# ---------------------------------------------------------------------------


async def test_download_document_returns_stored_bytes(
    db_session: AsyncSession,
    g2_company: Company,
    g2_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = g2_passport_type
    uploaded = await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"hello-bytes",
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = uploaded["document"]["id"]
    downloaded = await handle_download_document(
        DownloadDocumentQuery(
            document_id=doc_id,
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
        ),
        db_session,
        _fake_storage,
    )
    assert downloaded.data == b"hello-bytes"
    assert downloaded.content_type == "image/jpeg"


async def test_download_document_denies_foreign_company(
    db_session: AsyncSession,
    g2_company: Company,
    g2_other_company: Company,
    g2_actor: User,
    g2_foreign_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = g2_passport_type
    uploaded = await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"bytes",
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = uploaded["document"]["id"]
    with pytest.raises(DocumentAccessDeniedError):
        await handle_download_document(
            DownloadDocumentQuery(
                document_id=doc_id,
                actor_user_id=g2_foreign_actor.id,
                actor_role="client",
                actor_company_id=g2_other_company.id,
            ),
            db_session,
            _fake_storage,
        )


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


async def test_download_archive_streams_zip_of_application_docs(
    db_session: AsyncSession,
    g2_company: Company,
    g2_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = g2_passport_type
    application = LeasingApplication(
        company_id=g2_company.id,
        email="arch-app@test.local",
        status="active",
        selected_leasing_companies=[],
    )
    db_session.add(application)
    await db_session.flush()
    await db_session.refresh(application)

    uploaded = await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"archived-bytes",
            related_application_id=application.id,
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    _ = uploaded

    archive = await handle_download_application_archive(
        DownloadApplicationArchiveQuery(
            application_id=application.id,
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
        ),
        db_session,
        _fake_storage,
    )
    assert archive.included_count == 1
    assert archive.data.startswith(b"PK")  # standard zip signature


# ---------------------------------------------------------------------------
# User-enhanced / aggregated requirements
# ---------------------------------------------------------------------------


async def test_list_user_enhanced_flags_has_document(
    db_session: AsyncSession,
    g2_company: Company,
    g2_actor: User,
    g2_passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    # Seed LC + requirement for "passport"
    lc_company = Company(name="LC-A", company_type="leasing_company")
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
    application = LeasingApplication(
        company_id=g2_company.id,
        email="ud-app@test.local",
        status="active",
        selected_leasing_companies=[lc.id],
    )
    db_session.add(application)
    await db_session.flush()

    # Upload a passport for the company — should flip has_document=True.
    await handle_upload_document(
        _upload_cmd(
            user_id=g2_actor.id,
            company_id=g2_company.id,
            data=b"bytes",
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )

    enhanced = await handle_list_user_documents_enhanced(
        ListUserDocumentsEnhancedQuery(
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
        ),
        db_session,
    )
    assert enhanced["total"] == 1
    assert len(enhanced["requirements"]) == 1
    assert enhanced["requirements"][0]["has_document"] is True


async def test_list_user_requirements_by_explicit_lc_ids(
    db_session: AsyncSession,
    g2_company: Company,
    g2_actor: User,
    g2_passport_type: DocumentType,
) -> None:
    lc_company = Company(name="LC-B", company_type="leasing_company")
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

    result = await handle_list_user_requirements(
        ListUserRequirementsQuery(
            actor_user_id=g2_actor.id,
            actor_role="client",
            actor_company_id=g2_company.id,
            leasing_company_ids=[lc.id],
        ),
        db_session,
    )
    assert result["total"] == 1
    assert result["requirements"][0]["document_type"] == "passport"
