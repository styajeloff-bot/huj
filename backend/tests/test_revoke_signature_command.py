from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.revoke_signature import (
    PURPOSE_SIGNATURE_REVOKE,
    ConfirmSignatureRevokeCommand,
    RequestSignatureRevokeCommand,
    RevokeSignatureError,
    handle_confirm_signature_revoke,
    handle_request_signature_revoke,
)
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.contractors import Contractor, LeasingCompanyContractor
from infrastructure.models.signature_requests import SignatureRequest
from infrastructure.models.users import User, VerificationCode
from infrastructure.repositories import signature_request_repository as signatures
from infrastructure.repositories import sopd_operator_snapshot_repository as snapshots
from infrastructure.repositories import sopd_revoke_repository as revocations
from infrastructure.services import sopd_revoke_renderer
from tests.fakes.object_storage import FakeObjectStorage

pytestmark = pytest.mark.asyncio


@pytest.fixture
def revoke_storage(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStorage:
    async def _render_pdf(context: dict) -> bytes:
        return b"%PDF revoke"

    monkeypatch.setattr(sopd_revoke_renderer, "render_pdf", _render_pdf)
    return FakeObjectStorage()


async def _create_signed_sopd(
    db_session: AsyncSession,
) -> tuple[User, dict, LeasingCompany, LeasingCompany, Contractor, Contractor]:
    user = User(
        phone="+76662150291",
        email="revoke-signature-command@test.local",
        name="Revoke Signature Command",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    request = await signatures.create(
        db_session,
        user_id=user.id,
        application_id=None,
        document_type=signatures.DOC_TYPE_SOPD,
        subject_snapshot={"full_name": user.name},
    )
    signed = await signatures.mark_signed(
        db_session,
        request_id=request["id"],
        method="electronic",
        signed_pdf_s3_key="sopd/signed.pdf",
        signing_ip="127.0.0.1",
        signing_user_agent="pytest",
    )
    assert signed is not None

    reso_company = Company(
        name="ООО РЕСО-Лизинг",
        inn="7709401087",
        company_type="leasing_company",
    )
    vtb_company = Company(
        name="АО ВТБ Лизинг",
        inn="7709378229",
        company_type="leasing_company",
    )
    db_session.add_all([reso_company, vtb_company])
    await db_session.flush()
    reso = LeasingCompany(company_id=reso_company.id, is_active=True)
    vtb = LeasingCompany(company_id=vtb_company.id, is_active=True)
    shared = Contractor(name="ОКБ", inn="7710000001")
    reso_only = Contractor(name="Скоринг-Сервис", inn="7710000002")
    db_session.add_all([reso, vtb, shared, reso_only])
    await db_session.flush()
    db_session.add_all(
        [
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=shared.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=vtb.id,
                contractor_id=shared.id,
            ),
            LeasingCompanyContractor(
                leasing_company_id=reso.id,
                contractor_id=reso_only.id,
            ),
        ]
    )
    await snapshots.upsert(
        db_session,
        signature_request_id=signed["id"],
        user_id=user.id,
        application_id=None,
        leasing_companies=[
            {
                "id": str(reso.id),
                "company_id": str(reso_company.id),
                "name": reso_company.name,
                "inn": reso_company.inn,
            },
            {
                "id": str(vtb.id),
                "company_id": str(vtb_company.id),
                "name": vtb_company.name,
                "inn": vtb_company.inn,
            },
        ],
        contractors=[
            {
                "id": str(shared.id),
                "name": shared.name,
                "inn": shared.inn,
                "leasing_company_ids": [str(reso.id), str(vtb.id)],
                "leasing_companies": [
                    {
                        "id": str(reso.id),
                        "company_id": str(reso_company.id),
                        "name": reso_company.name,
                        "inn": reso_company.inn,
                    },
                    {
                        "id": str(vtb.id),
                        "company_id": str(vtb_company.id),
                        "name": vtb_company.name,
                        "inn": vtb_company.inn,
                    },
                ],
            },
            {
                "id": str(reso_only.id),
                "name": reso_only.name,
                "inn": reso_only.inn,
                "leasing_company_ids": [str(reso.id)],
                "leasing_companies": [
                    {
                        "id": str(reso.id),
                        "company_id": str(reso_company.id),
                        "name": reso_company.name,
                        "inn": reso_company.inn,
                    }
                ],
            },
        ],
    )
    await db_session.flush()
    return user, signed, reso, vtb, shared, reso_only


async def _latest_code(
    db_session: AsyncSession, request_id: object
) -> VerificationCode:
    result = await db_session.execute(
        sa.select(VerificationCode)
        .where(
            VerificationCode.purpose == PURPOSE_SIGNATURE_REVOKE,
            VerificationCode.entity_id == str(request_id),
        )
        .order_by(VerificationCode.created_at.desc(), VerificationCode.id.desc())
        .limit(1)
    )
    return result.scalars().one()


async def test_request_revoke_creates_code_and_expires_previous_active_code(
    db_session: AsyncSession,
) -> None:
    user, request, reso, _, _, reso_only = await _create_signed_sopd(db_session)
    old_code = VerificationCode(
        phone=user.phone,
        code="1111",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        purpose=PURPOSE_SIGNATURE_REVOKE,
        entity_id=str(request["id"]),
    )
    db_session.add(old_code)
    await db_session.flush()

    result = await handle_request_signature_revoke(
        RequestSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            leasing_company_ids=[reso.id],
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
    )

    assert result.phone_masked.endswith("**-91")
    await db_session.refresh(old_code)
    assert cast("datetime", old_code.expires_at) <= datetime.now(UTC)
    latest = await _latest_code(db_session, request["id"])
    assert latest.code == "0000"
    assert latest.purpose == PURPOSE_SIGNATURE_REVOKE
    assert latest.entity_id == str(request["id"])
    refreshed = await signatures.get_by_id(db_session, request["id"])
    assert refreshed is not None
    assert refreshed["revoke_requested_at"] is not None
    pending = await revocations.get_latest_pending(
        db_session, signature_request_id=request["id"]
    )
    assert pending is not None
    assert pending["revoked_leasing_company_ids"] == [reso.id]
    assert pending["revoked_contractor_ids"] == [reso_only.id]


async def test_confirm_revoke_invalid_code_increments_failed_attempts(
    db_session: AsyncSession,
    revoke_storage: FakeObjectStorage,
) -> None:
    user, request, reso, *_ = await _create_signed_sopd(db_session)
    await handle_request_signature_revoke(
        RequestSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            leasing_company_ids=[reso.id],
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
    )

    with pytest.raises(RevokeSignatureError) as exc_info:
        await handle_confirm_signature_revoke(
            ConfirmSignatureRevokeCommand(
                request_id=request["id"],
                actor_user_id=user.id,
                code="9999",
                client_ip="127.0.0.1",
                user_agent="pytest",
            ),
            db_session,
            revoke_storage,
        )

    assert exc_info.value.error_code == "INVALID_VERIFICATION_CODE"
    latest = await _latest_code(db_session, request["id"])
    assert latest.failed_attempts == 1


async def test_confirm_revoke_valid_code_records_operator_facts_and_code_used(
    db_session: AsyncSession,
    revoke_storage: FakeObjectStorage,
) -> None:
    user, request, reso, _, shared, reso_only = await _create_signed_sopd(
        db_session
    )
    await handle_request_signature_revoke(
        RequestSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            leasing_company_ids=[reso.id],
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
    )

    result = await handle_confirm_signature_revoke(
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

    assert result.status == signatures.STATUS_SIGNED_ELECTRONIC
    assert result.is_full_revoke is False
    assert result.document_s3_key in revoke_storage.items
    assert result.revoked_leasing_companies[0]["id"] == str(reso.id)
    assert result.revoked_contractors[0]["id"] == str(reso_only.id)
    assert result.excluded_contractors[0]["id"] == str(shared.id)
    latest = await _latest_code(db_session, request["id"])
    assert latest.used_at is not None
    unchanged = await signatures.get_by_id(db_session, request["id"])
    assert unchanged is not None
    assert unchanged["status"] == signatures.STATUS_SIGNED_ELECTRONIC
    facts = await revocations.list_revoked_operators(
        db_session, signature_request_id=request["id"]
    )
    assert {(item["operator_type"], item["operator_inn"]) for item in facts} == {
        (revocations.TYPE_LEASING_COMPANY, "7709401087"),
        (revocations.TYPE_CONTRACTOR, "7710000002"),
    }


async def test_confirm_full_revoke_marks_signature_revoked(
    db_session: AsyncSession,
    revoke_storage: FakeObjectStorage,
) -> None:
    user, request, reso, vtb, *_ = await _create_signed_sopd(db_session)
    await handle_request_signature_revoke(
        RequestSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            leasing_company_ids=[reso.id, vtb.id],
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
    )

    result = await handle_confirm_signature_revoke(
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

    assert result.status == signatures.STATUS_REVOKED
    assert result.is_full_revoke is True
    assert result.document_s3_key in revoke_storage.items
    refreshed = await signatures.get_by_id(db_session, request["id"])
    assert refreshed is not None
    assert refreshed["status"] == signatures.STATUS_REVOKED


async def test_confirm_revoke_passes_application_display_number_to_pdf_context(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_context: dict = {}

    async def _render_pdf(context: dict) -> bytes:
        captured_context.update(context)
        return b"%PDF revoke"

    monkeypatch.setattr(sopd_revoke_renderer, "render_pdf", _render_pdf)
    user, request, reso, _, shared, reso_only = await _create_signed_sopd(
        db_session
    )
    client_company = Company(
        name="ООО Клиент PDF Отзыва",
        inn="7722000498",
        company_type="dealer",
    )
    db_session.add(client_company)
    await db_session.flush()
    application = LeasingApplication(
        company_id=client_company.id,
        display_number="7709401087-0622-001",
        name="PDF Revoke Application",
        email="pdf-revoke@test.local",
    )
    db_session.add(application)
    await db_session.flush()
    await db_session.execute(
        sa.update(SignatureRequest)
        .where(SignatureRequest.id == request["id"])
        .values(application_id=application.id)
    )
    await db_session.flush()
    request["application_id"] = application.id
    await handle_request_signature_revoke(
        RequestSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            leasing_company_ids=[reso.id],
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
    )

    await handle_confirm_signature_revoke(
        ConfirmSignatureRevokeCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            code="0000",
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
        db_session,
        FakeObjectStorage(),
    )

    assert captured_context["source_document"]["display_number"] == (
        "7709401087-0622-001"
    )
    assert captured_context["source_document"]["id"] == str(request["id"])
    pdf_operator_ids = {
        item["id"]
        for item in captured_context["operators"]
        if item["operator_type"] == revocations.TYPE_CONTRACTOR
    }
    assert pdf_operator_ids == {str(shared.id), str(reso_only.id)}
