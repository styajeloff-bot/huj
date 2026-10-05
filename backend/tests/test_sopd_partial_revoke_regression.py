from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.revoke_signature import (
    ConfirmSignatureRevokeCommand,
    RequestSignatureRevokeCommand,
    handle_confirm_signature_revoke,
    handle_request_signature_revoke,
)
from application.commands.sign_document import (
    UploadPhysicalSignatureCommand,
    handle_upload_physical_signature,
)
from application.queries import signature_documents
from application.queries.signature_documents import (
    RevokeDocumentDownloadQuery,
    SignatureDownloadQuery,
    handle_revoke_document_download,
    handle_signature_download,
)
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.contractors import (
    Contractor,
    LeasingCompanyContractor,
)
from infrastructure.models.users import User
from infrastructure.repositories import (
    passport_recognition_repository as passports,
)
from infrastructure.repositories import (
    signature_request_repository as signatures,
)
from infrastructure.repositories import (
    sopd_operator_snapshot_repository as snapshots,
)
from infrastructure.repositories import (
    user_identity_verification_repository as verifications,
)
from infrastructure.services import sopd_revoke_renderer
from infrastructure.services.document_storage import StoredDocument
from tests.fakes.object_storage import FakeObjectStorage

pytestmark = pytest.mark.asyncio


async def _verify_signer_identity(
    db_session: AsyncSession,
    *,
    user: User,
) -> None:
    await passports.save(
        db_session,
        user_id=user.id,
        file_hash=f"partial-revoke-passport-{user.id}",
        passport_type="ceo_passport_page23",
        raw_data={
            "items": [
                {
                    "fields": {
                        "surname": "Иванов",
                        "first_name": "Иван",
                        "other_names": "Иванович",
                        "date_of_birth": "08.01.1991",
                    }
                }
            ]
        },
        mapped_data={},
        confidence_data={},
        recognition_task_id=None,
    )
    attempt = await verifications.create_attempt(
        db_session,
        user_id=user.id,
        phone_number=user.phone,
        birthdate=date(1991, 1, 8),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    await verifications.mark_verified(
        db_session,
        verification_id=attempt["id"],
        mobile_id_sub="partial-revoke-regression",
        phone_number=user.phone,
        birthdate=date(1991, 1, 8),
        birthdate_match="Y",
        family_name="Иванов",
        given_name="Иван",
        middle_name="Иванович",
    )


async def test_empty_distribution_signs_operator_snapshot_and_allows_partial_revoke(  # noqa: PLR0915
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        phone="+76662149801",
        email="partial-revoke-regression@test.local",
        name="Иванов Иван Иванович",
        role="client",
        is_active=True,
    )
    applicant_company = Company(
        name="ООО Клиент частичного отзыва",
        inn="6450214981",
        company_type="dealer",
    )
    reso_company = Company(
        name="ООО РЕСО-Лизинг для регрессионного теста",
        inn="7709214981",
        company_type="leasing_company",
    )
    vtb_company = Company(
        name="АО ВТБ Лизинг для регрессионного теста",
        inn="7709214982",
        company_type="leasing_company",
    )
    inactive_company = Company(
        name="ООО Неактивная ЛК для регрессионного теста",
        inn="7709214983",
        company_type="leasing_company",
    )
    db_session.add_all(
        [
            user,
            applicant_company,
            reso_company,
            vtb_company,
            inactive_company,
        ]
    )
    await db_session.flush()

    application = LeasingApplication(
        company_id=applicant_company.id,
        created_by=user.id,
        display_number="21498-REGRESSION",
        selected_leasing_companies=[],
    )
    reso = LeasingCompany(company_id=reso_company.id, is_active=True)
    vtb = LeasingCompany(company_id=vtb_company.id, is_active=True)
    inactive = LeasingCompany(company_id=inactive_company.id, is_active=False)
    shared_contractor = Contractor(
        name="АО Общее кредитное бюро",
        inn="7710214981",
    )
    reso_contractor = Contractor(
        name="ООО Скоринг РЕСО",
        inn="7710214982",
    )
    db_session.add_all(
        [
            application,
            reso,
            vtb,
            inactive,
            shared_contractor,
            reso_contractor,
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=shared_contractor.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=vtb.id,
                contractor_id=shared_contractor.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=reso_contractor.id,
            ),
        ]
    )
    await db_session.flush()

    await _verify_signer_identity(db_session, user=user)
    request = await signatures.create(
        db_session,
        user_id=user.id,
        application_id=application.id,
        document_type=signatures.DOC_TYPE_SOPD,
        subject_snapshot={
            "full_name": user.name,
            "phone": user.phone,
            "email": user.email,
        },
    )

    original_pdf = b"%PDF original signed SOPD"
    stored_signed_documents: dict[str, tuple[bytes, str]] = {}

    async def _put_signed_document(
        key: str,
        data: bytes,
        content_type: str,
    ) -> StoredDocument:
        stored_signed_documents[key] = (data, content_type)
        return StoredDocument(
            key=key,
            public_url=f"http://signed-storage/{key}",
        )

    async def _get_signed_document(key: str) -> bytes | None:
        stored = stored_signed_documents.get(key)
        return stored[0] if stored is not None else None

    monkeypatch.setattr(
        "application.commands.sign_document.document_storage.put_document",
        _put_signed_document,
    )
    monkeypatch.setattr(
        "application.queries.signature_documents.document_storage.get_document",
        _get_signed_document,
    )

    signed = await handle_upload_physical_signature(
        UploadPhysicalSignatureCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            filename="signed-sopd.pdf",
            content_type="application/pdf",
            data=original_pdf,
            signing_ip="127.0.0.1",
            signing_user_agent="pytest",
        ),
        db_session,
    )

    assert signed["status"] == signatures.STATUS_SIGNED_PHYSICAL
    assert stored_signed_documents[signed["signed_pdf_s3_key"]] == (
        original_pdf,
        "application/pdf",
    )
    downloaded_original = await handle_signature_download(
        SignatureDownloadQuery(
            request_id=request["id"],
            actor_user_id=user.id,
        ),
        db_session,
        FakeObjectStorage(),
    )
    assert downloaded_original == original_pdf

    await db_session.refresh(application)
    assert application.selected_leasing_companies == []
    distribution_links = (
        await db_session.execute(
            sa.select(LeasingCompanyApplication).where(
                LeasingCompanyApplication.application_id == application.id
            )
        )
    ).scalars()
    assert list(distribution_links) == []

    snapshot = await snapshots.get_by_signature_request_id(
        db_session,
        request["id"],
    )
    assert snapshot is not None
    assert {item["id"] for item in snapshot["leasing_companies"]} == {
        str(reso.id),
        str(vtb.id),
    }
    assert str(inactive.id) not in {
        item["id"] for item in snapshot["leasing_companies"]
    }
    assert {item["id"] for item in snapshot["contractors"]} == {
        str(shared_contractor.id),
        str(reso_contractor.id),
    }

    initiated = await handle_request_signature_revoke(
        RequestSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            leasing_company_ids=[reso.id],
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
    )
    assert initiated.is_full_revoke is False
    assert initiated.revoked_leasing_companies[0]["id"] == str(reso.id)
    assert initiated.revoked_contractors[0]["id"] == str(reso_contractor.id)
    assert initiated.excluded_contractors[0]["id"] == str(shared_contractor.id)

    revoke_pdf = b"%PDF partial revoke"

    async def _render_revoke_pdf(context: dict) -> bytes:
        return revoke_pdf

    monkeypatch.setattr(sopd_revoke_renderer, "render_pdf", _render_revoke_pdf)
    revoke_storage = FakeObjectStorage()
    confirmed = await handle_confirm_signature_revoke(
        ConfirmSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            code="0000",
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
        revoke_storage,
    )

    assert confirmed.is_full_revoke is False
    assert confirmed.status == signatures.STATUS_SIGNED_PHYSICAL
    assert confirmed.document_s3_key in revoke_storage.items
    assert revoke_storage.items[confirmed.document_s3_key].data == revoke_pdf
    downloaded_revoke, revoke_media_type = await handle_revoke_document_download(
        RevokeDocumentDownloadQuery(
            request_id=request["id"],
            revoke_request_id=confirmed.revoke_request_id,
            actor_user_id=user.id,
        ),
        db_session,
        revoke_storage,
    )
    assert downloaded_revoke == revoke_pdf
    assert revoke_media_type == "application/pdf"

    current_context: dict[str, str] = {}
    current_pdf = b"%PDF current SOPD after partial revoke"

    async def _render_current_sopd(
        *,
        session: AsyncSession,
        storage: FakeObjectStorage,
        context: dict[str, str],
    ) -> bytes:
        current_context.update(context)
        return current_pdf

    monkeypatch.setattr(
        signature_documents,
        "ensure_sopd_pdf",
        _render_current_sopd,
    )
    downloaded_current = await handle_signature_download(
        SignatureDownloadQuery(
            request_id=request["id"],
            actor_user_id=user.id,
        ),
        db_session,
        revoke_storage,
    )

    assert downloaded_current == current_pdf
    assert vtb_company.name in current_context["leasing_companies"]
    assert reso_company.name not in current_context["leasing_companies"]
    assert shared_contractor.name in current_context["contractors"]
    assert reso_contractor.name not in current_context["contractors"]
    assert reso_company.name not in current_context["contractors"]
