"""Unit-level handler tests for Phase 4 D1 (uses real DB via testcontainers
and FakeObjectStorage — avoids the full HTTP stack).

These tests exercise the command / query handlers directly, focusing on
the status machine + versioning + recognition branches without going
through routers.
"""
from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.documents import (
    ChangeDocumentStatusCommand,
    UploadDocumentCommand,
    UploadDocumentVersionCommand,
    UploadedDocumentFile,
    handle_change_document_status,
    handle_upload_document,
    handle_upload_document_version,
)
from application.queries.documents import (
    GetDocumentQuery,
    ListDocumentsQuery,
    ListDocumentVersionsQuery,
    handle_get_document,
    handle_list_document_versions,
    handle_list_documents,
)
from domain.entities.document import STATUS_APPROVED, STATUS_PENDING
from domain.errors import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
    FileTooLargeError,
    InvalidDocumentStatusError,
    UnsupportedFileTypeError,
)
from infrastructure.models.companies import Company
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
async def docs_company(db_session: AsyncSession) -> Company:
    company = Company(name="Docs Test Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


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
async def auto_approve_type(db_session: AsyncSession) -> DocumentType:
    row = DocumentType(
        name="Enterprise Card",
        type_code="enterprise_card",
        file_types=["application/pdf"],
        max_file_size_mb=10,
        auto_approve=True,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def docs_actor(
    db_session: AsyncSession, docs_company: Company
) -> User:
    user = User(
        phone="+76660000001",
        email="actor@test.local",
        name="Actor",
        role="client",
        is_active=True,
        company_id=docs_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def docs_reviewer(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660000002",
        email="reviewer@test.local",
        name="Reviewer",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Upload — happy path
# ---------------------------------------------------------------------------


async def test_upload_persists_and_sets_status_pending(
    db_session: AsyncSession,
    docs_company: Company,
    docs_actor: User,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    cmd = UploadDocumentCommand(
        actor_user_id=docs_actor.id,
        actor_company_id=docs_company.id,
        document_type="passport",
        file=UploadedDocumentFile(
            filename="pass.jpg",
            content_type="image/jpeg",
            data=b"hello world",
        ),
    )
    result = await handle_upload_document(
        cmd, db_session, _fake_storage, session_factory=None
    )
    doc = result["document"]
    assert doc is not None
    assert doc["company_id"] == docs_company.id
    assert doc["document_type"] == "passport"
    assert doc["leasing_company_status"] == STATUS_PENDING
    assert doc["version"] == 1
    assert doc["is_current_version"] is True
    assert next(iter(_fake_storage.items.keys())).startswith(
        f"documents/company_{docs_company.id}/"
    )


async def test_upload_auto_approve_sets_status_approved(
    db_session: AsyncSession,
    docs_company: Company,
    docs_actor: User,
    auto_approve_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = auto_approve_type
    cmd = UploadDocumentCommand(
        actor_user_id=docs_actor.id,
        actor_company_id=docs_company.id,
        document_type="enterprise_card",
        file=UploadedDocumentFile(
            filename="card.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.4",
        ),
    )
    result = await handle_upload_document(
        cmd, db_session, _fake_storage, session_factory=None
    )
    assert result["document"]["leasing_company_status"] == STATUS_APPROVED


async def test_upload_rejects_bad_content_type(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    cmd = UploadDocumentCommand(
        actor_user_id=uuid4(),
        actor_company_id=docs_company.id,
        document_type="passport",
        file=UploadedDocumentFile(
            filename="x.exe",
            content_type="application/octet-stream",
            data=b"MZ",
        ),
    )
    with pytest.raises(UnsupportedFileTypeError):
        await handle_upload_document(
            cmd, db_session, _fake_storage, session_factory=None
        )


async def test_upload_rejects_file_too_large(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    big = b"\0" * (6 * 1024 * 1024)
    cmd = UploadDocumentCommand(
        actor_user_id=uuid4(),
        actor_company_id=docs_company.id,
        document_type="passport",
        file=UploadedDocumentFile(
            filename="big.jpg",
            content_type="image/jpeg",
            data=big,
        ),
    )
    with pytest.raises(FileTooLargeError):
        await handle_upload_document(
            cmd, db_session, _fake_storage, session_factory=None
        )


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


async def test_upload_version_marks_parent_not_current(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    first = await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=uuid4(),
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="v1.jpg",
                content_type="image/jpeg",
                data=b"v1",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    parent_id = first["document"]["id"]

    second = await handle_upload_document_version(
        UploadDocumentVersionCommand(
            actor_user_id=uuid4(),
            actor_company_id=docs_company.id,
            parent_document_id=parent_id,
            file_filename="v2.jpg",
            file_content_type="image/jpeg",
            file_data=b"v2-content",
        ),
        db_session,
        _fake_storage,
    )
    new_doc = second["document"]
    assert new_doc["version"] == 2
    assert new_doc["is_current_version"] is True
    assert new_doc["parent_document_id"] == parent_id

    versions = await handle_list_document_versions(
        ListDocumentVersionsQuery(
            document_id=parent_id,
            actor_user_id=uuid4(),
            actor_role="client",
            actor_company_id=docs_company.id,
        ),
        db_session,
    )
    assert versions["total"] == 2
    # root is marked not-current, new one is current
    by_id = {v["id"]: v for v in versions["versions"]}
    assert by_id[parent_id]["is_current_version"] is False
    assert by_id[new_doc["id"]]["is_current_version"] is True


async def test_upload_version_requires_same_company(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    first = await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=uuid4(),
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="v1.jpg",
                content_type="image/jpeg",
                data=b"v1",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    parent_id = first["document"]["id"]

    with pytest.raises(DocumentAccessDeniedError):
        await handle_upload_document_version(
            UploadDocumentVersionCommand(
                actor_user_id=uuid4(),
                actor_company_id=uuid4(),
                parent_document_id=parent_id,
                file_filename="x.jpg",
                file_content_type="image/jpeg",
                file_data=b"stolen",
            ),
            db_session,
            _fake_storage,
        )


# ---------------------------------------------------------------------------
# Status change
# ---------------------------------------------------------------------------


async def test_change_status_writes_history(
    db_session: AsyncSession,
    docs_company: Company,
    docs_actor: User,
    docs_reviewer: User,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    first = await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=docs_actor.id,
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="v1.jpg",
                content_type="image/jpeg",
                data=b"v1",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = first["document"]["id"]

    result = await handle_change_document_status(
        ChangeDocumentStatusCommand(
            document_id=doc_id,
            actor_user_id=docs_reviewer.id,
            actor_role="carcraft_employee",
            new_status="approved",
            comments="looks good",
        ),
        db_session,
    )
    assert result["document"]["leasing_company_status"] == "approved"


async def test_change_status_rejects_invalid_transition(
    db_session: AsyncSession,
    docs_company: Company,
    docs_actor: User,
    docs_reviewer: User,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    first = await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=docs_actor.id,
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="v1.jpg",
                content_type="image/jpeg",
                data=b"v1",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = first["document"]["id"]
    # approve first
    await handle_change_document_status(
        ChangeDocumentStatusCommand(
            document_id=doc_id,
            actor_user_id=docs_reviewer.id,
            actor_role="carcraft_employee",
            new_status="approved",
        ),
        db_session,
    )
    # approved -> pending is NOT a legal transition
    with pytest.raises(InvalidDocumentStatusError):
        await handle_change_document_status(
            ChangeDocumentStatusCommand(
                document_id=doc_id,
                actor_user_id=docs_reviewer.id,
                actor_role="carcraft_employee",
                new_status="pending",
            ),
            db_session,
        )


async def test_change_status_unknown_doc(db_session: AsyncSession) -> None:
    with pytest.raises(DocumentNotFoundError):
        await handle_change_document_status(
            ChangeDocumentStatusCommand(
                document_id=uuid4(),
                actor_user_id=uuid4(),
                actor_role="carcraft_employee",
                new_status="approved",
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------


async def test_list_documents_filters_by_company(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=uuid4(),
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="a.jpg",
                content_type="image/jpeg",
                data=b"aa",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    mine = await handle_list_documents(
        ListDocumentsQuery(
            actor_user_id=uuid4(),
            actor_role="client",
            actor_company_id=docs_company.id,
        ),
        db_session,
    )
    assert mine["total"] == 1
    other = await handle_list_documents(
        ListDocumentsQuery(
            actor_user_id=uuid4(),
            actor_role="client",
            actor_company_id=uuid4(),
        ),
        db_session,
    )
    assert other["total"] == 0


async def test_get_document_denies_foreign_company(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    first = await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=uuid4(),
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="a.jpg",
                content_type="image/jpeg",
                data=b"aa",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = first["document"]["id"]
    with pytest.raises(DocumentAccessDeniedError):
        await handle_get_document(
            GetDocumentQuery(
                document_id=doc_id,
                actor_user_id=uuid4(),
                actor_role="client",
                actor_company_id=uuid4(),
            ),
            db_session,
        )


async def test_get_document_employee_sees_all(
    db_session: AsyncSession,
    docs_company: Company,
    passport_type: DocumentType,
    _fake_storage: FakeObjectStorage,
) -> None:
    _ = passport_type
    first = await handle_upload_document(
        UploadDocumentCommand(
            actor_user_id=uuid4(),
            actor_company_id=docs_company.id,
            document_type="passport",
            file=UploadedDocumentFile(
                filename="a.jpg",
                content_type="image/jpeg",
                data=b"aa",
            ),
        ),
        db_session,
        _fake_storage,
        session_factory=None,
    )
    doc_id = first["document"]["id"]
    result = await handle_get_document(
        GetDocumentQuery(
            document_id=doc_id,
            actor_user_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
        ),
        db_session,
    )
    assert result["id"] == doc_id
