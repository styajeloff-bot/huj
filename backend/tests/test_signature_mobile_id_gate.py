from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import sign_document as sign_document_command
from application.commands.sign_document import (
    SignElectronicCommand,
    UploadPhysicalSignatureCommand,
    handle_sign_electronic,
    handle_upload_physical_signature,
)
from application.errors import ServiceError
from application.queries.sopd_operators import SopdOperatorSnapshotData
from domain.services.object_storage import ObjectStorage, StoredObject
from infrastructure.models.users import User
from infrastructure.repositories import (
    passport_recognition_repository as passports,
)
from infrastructure.repositories import signature_request_repository as signatures
from infrastructure.repositories import (
    sopd_operator_snapshot_repository as snapshots,
)
from infrastructure.repositories import (
    user_identity_verification_repository as verifications,
)

pytestmark = pytest.mark.asyncio

_DETAIL = "Для подписания СОПД необходимо пройти верификацию через Mobile ID."
_MISMATCH_DETAIL = (
    "Данные СОПД не совпадают с подтвержденными данными профиля. "
    "Проверьте ФИО и дату рождения."
)


class _NoopStorage(ObjectStorage):
    async def put(self, key: str, data: bytes, content_type: str) -> str:
        return key

    async def get(self, key: str) -> StoredObject | None:
        return StoredObject(
            key=key,
            content_type="application/pdf",
            size=4,
            etag=None,
            data=b"%PDF",
        )

    async def delete(self, key: str) -> bool:
        return True

    async def exists(self, key: str) -> bool:
        return True

    def public_url(self, key: str) -> str:
        return f"https://storage.example/{key}"


async def _create_user_and_sopd(
    db_session: AsyncSession,
    *,
    full_name: str = "Иванов Иван Иванович",
) -> tuple[User, dict]:
    user = User(
        phone="+76662150221",
        email="mobile-id-signature@test.local",
        name=full_name,
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
    return user, request


async def _save_sopd_passport(
    db_session: AsyncSession,
    user: User,
    *,
    family_name: str = "Иванов",
    given_name: str = "Иван",
    middle_name: str = "Иванович",
    birthdate: str = "08.01.1991",
) -> None:
    await passports.save(
        db_session,
        user_id=user.id,
        file_hash=f"passport-{user.id}",
        passport_type="ceo_passport_page23",
        raw_data={
            "items": [
                {
                    "fields": {
                        "surname": family_name,
                        "first_name": given_name,
                        "other_names": middle_name,
                        "date_of_birth": birthdate,
                    }
                }
            ]
        },
        mapped_data={},
        confidence_data={},
        recognition_task_id=None,
    )


async def _mark_mobile_id_verified(
    db_session: AsyncSession,
    user: User,
    *,
    family_name: str = "Иванов",
    given_name: str = "Иван",
    middle_name: str = "Иванович",
    birthdate: date = date(1991, 1, 8),
) -> None:
    attempt = await verifications.create_attempt(
        db_session,
        user_id=user.id,
        provider=verifications.PROVIDER_MOBILE_ID,
        phone_number=user.phone,
        birthdate=birthdate,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    await verifications.mark_verified(
        db_session,
        verification_id=attempt["id"],
        mobile_id_sub="sub-signature",
        phone_number=user.phone,
        birthdate=birthdate,
        birthdate_match="Y",
        family_name=family_name,
        given_name=given_name,
        middle_name=middle_name,
    )


async def test_electronic_sopd_signing_requires_mobile_id_verification(
    db_session: AsyncSession,
) -> None:
    user, request = await _create_user_and_sopd(db_session)

    with pytest.raises(ServiceError) as exc_info:
        await handle_sign_electronic(
            SignElectronicCommand(
                request_id=request["id"],
                actor_user_id=user.id,
                signing_ip="127.0.0.1",
                signing_user_agent="pytest",
            ),
            db_session,
            _NoopStorage(),
        )

    assert exc_info.value.status_code == 403
    assert str(exc_info.value) == _DETAIL


async def test_physical_sopd_signing_requires_mobile_id_verification(
    db_session: AsyncSession,
) -> None:
    user, request = await _create_user_and_sopd(db_session)

    with pytest.raises(ServiceError) as exc_info:
        await handle_upload_physical_signature(
            UploadPhysicalSignatureCommand(
                request_id=request["id"],
                actor_user_id=user.id,
                filename="signed.pdf",
                content_type="application/pdf",
                data=b"%PDF",
                signing_ip="127.0.0.1",
                signing_user_agent="pytest",
            ),
            db_session,
        )

    assert exc_info.value.status_code == 403
    assert str(exc_info.value) == _DETAIL


async def test_verified_user_passes_sopd_gate_for_physical_signature(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, request = await _create_user_and_sopd(db_session)
    await _save_sopd_passport(db_session, user)
    await _mark_mobile_id_verified(db_session, user)

    async def _put_document(key: str, data: bytes, content_type: str) -> None:
        return None

    monkeypatch.setattr(
        "application.commands.sign_document.document_storage.put_document",
        _put_document,
    )

    signed = await handle_upload_physical_signature(
        UploadPhysicalSignatureCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            filename="signed.pdf",
            content_type="application/pdf",
            data=b"%PDF",
            signing_ip="127.0.0.1",
            signing_user_agent="pytest",
        ),
        db_session,
    )

    assert signed["status"] == signatures.STATUS_SIGNED_PHYSICAL


async def test_verified_user_cannot_sign_sopd_for_another_full_name(
    db_session: AsyncSession,
) -> None:
    user, request = await _create_user_and_sopd(db_session)
    await _save_sopd_passport(db_session, user)
    await _mark_mobile_id_verified(
        db_session,
        user,
        family_name="Кириллов",
        given_name="Кирилл",
        middle_name="Кириллович",
    )

    with pytest.raises(ServiceError) as exc_info:
        await handle_upload_physical_signature(
            UploadPhysicalSignatureCommand(
                request_id=request["id"],
                actor_user_id=user.id,
                filename="signed.pdf",
                content_type="application/pdf",
                data=b"%PDF",
                signing_ip="127.0.0.1",
                signing_user_agent="pytest",
            ),
            db_session,
        )

    assert exc_info.value.status_code == 403
    assert str(exc_info.value) == _MISMATCH_DETAIL


async def test_verified_user_cannot_sign_sopd_with_different_birthdate(
    db_session: AsyncSession,
) -> None:
    user, request = await _create_user_and_sopd(db_session)
    await _save_sopd_passport(db_session, user)
    await _mark_mobile_id_verified(
        db_session,
        user,
        birthdate=date(1990, 1, 8),
    )

    with pytest.raises(ServiceError) as exc_info:
        await handle_upload_physical_signature(
            UploadPhysicalSignatureCommand(
                request_id=request["id"],
                actor_user_id=user.id,
                filename="signed.pdf",
                content_type="application/pdf",
                data=b"%PDF",
                signing_ip="127.0.0.1",
                signing_user_agent="pytest",
            ),
            db_session,
        )

    assert exc_info.value.status_code == 403
    assert str(exc_info.value) == _MISMATCH_DETAIL


async def test_director_document_is_not_blocked_by_mobile_id_gate(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662150222",
        email="director-doc-signature@test.local",
        name="Director Doc Signature",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    request = await signatures.create(
        db_session,
        user_id=user.id,
        application_id=None,
        document_type="director_doc_passport",
        subject_snapshot={"full_name": user.name},
    )

    with pytest.raises(ServiceError) as exc_info:
        await handle_sign_electronic(
            SignElectronicCommand(
                request_id=request["id"],
                actor_user_id=user.id,
                signing_ip="127.0.0.1",
                signing_user_agent="pytest",
            ),
            db_session,
            _NoopStorage(),
        )

    assert exc_info.value.status_code == 404
    assert str(exc_info.value) == "Оригинальный документ не найден"


async def test_electronic_sopd_reuses_scope_for_pdf_and_snapshot(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, request = await _create_user_and_sopd(db_session)
    await _save_sopd_passport(db_session, user)
    await _mark_mobile_id_verified(db_session, user)

    leasing_company_id = uuid4()
    operator_scope = SopdOperatorSnapshotData(
        leasing_companies=[
            {
                "id": str(leasing_company_id),
                "company_id": str(uuid4()),
                "name": "ООО Единый Scope",
                "inn": "7709214988",
            }
        ],
        contractors=[],
        source="active_leasing_companies_fallback",
    )
    resolve_calls = 0

    async def _resolve_scope(
        session: AsyncSession,
        *,
        application_id: object,
    ) -> SopdOperatorSnapshotData:
        nonlocal resolve_calls
        resolve_calls += 1
        return operator_scope

    rendered_context: dict[str, str] = {}

    async def _render_pdf(
        *,
        session: AsyncSession,
        storage: ObjectStorage,
        context: dict[str, str],
    ) -> bytes:
        rendered_context.update(context)
        return b"%PDF signed with one scope"

    async def _put_document(
        key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        return None

    monkeypatch.setattr(
        sign_document_command,
        "resolve_sopd_operator_snapshot",
        _resolve_scope,
    )
    monkeypatch.setattr(sign_document_command, "ensure_sopd_pdf", _render_pdf)
    monkeypatch.setattr(
        sign_document_command.document_storage,
        "put_document",
        _put_document,
    )

    signed = await handle_sign_electronic(
        SignElectronicCommand(
            request_id=request["id"],
            actor_user_id=user.id,
            signing_ip="127.0.0.1",
            signing_user_agent="pytest",
        ),
        db_session,
        _NoopStorage(),
    )

    stored_scope = await snapshots.get_by_signature_request_id(
        db_session,
        signed["id"],
    )
    assert resolve_calls == 1
    assert "ООО Единый Scope" in rendered_context["leasing_companies"]
    assert stored_scope is not None
    assert stored_scope["leasing_companies"] == operator_scope.leasing_companies
    assert stored_scope["source"] == operator_scope.source
