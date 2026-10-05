"""Sign a signature_request — electronic (PEP) or uploaded scan (physical).

Ownership:
    * ``request_id`` must belong to ``actor_user_id`` (the person whose
      name is on the document). If not, 403 Forbidden.
    * Status must be ``pending``. Re-signing is not allowed.

Audit trail:
    * Electronic: we capture ``signing_ip``, ``signing_user_agent``, the
      rendered PDF bytes (stored in S3) and timestamp ``signed_at``.
    * Physical: the uploaded file is stored verbatim; the same audit
      fields are populated from the uploader's request.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.signer_sopd_context import build_signer_context
from application.queries.sopd_cache import ensure_sopd_pdf
from application.queries.sopd_operators import (
    SopdOperatorSnapshotData,
    resolve_sopd_operator_snapshot,
)
from application.services.passport_profile_fields import parse_date
from application.services.questionnaire_consents import refresh_consent_projection
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import (
    director_signing_invitation_repository as dir_invite_repo,
)
from infrastructure.repositories import (
    documents_repository as docs_repo,
)
from infrastructure.repositories import (
    signature_request_repository as repo,
)
from infrastructure.repositories import (
    sopd_operator_snapshot_repository as snapshot_repo,
)
from infrastructure.repositories import (
    sopd_passport_snapshot_repository as passport_snapshot_repo,
)
from infrastructure.repositories import (
    user_identity_verification_repository as identity_verification_repo,
)
from infrastructure.services import document_storage

logger = logging.getLogger("carcraft-backend")

_ALLOWED_PHYSICAL_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/heic",
}
_SOPD_MOBILE_ID_REQUIRED_DETAIL = (
    "Для подписания СОПД необходимо пройти верификацию через Mobile ID."
)
_SOPD_IDENTITY_MISMATCH_DETAIL = (
    "Данные СОПД не совпадают с подтвержденными данными профиля. "
    "Проверьте ФИО и дату рождения."
)
# Persisted only by the server when the applicant creates a paper request.
# Requests without this discriminator, including all electronic requests,
# remain subject to the Mobile ID gate.
_SOPD_FLOW_PHYSICAL_OWNER_UPLOAD = "physical_owner_upload"


@dataclass
class SignElectronicCommand:
    request_id: UUID
    actor_user_id: UUID
    signing_ip: str | None
    signing_user_agent: str | None


@dataclass
class CancelSignatureCommand:
    """Admin-initiated cancellation (carcraft_employee only)."""

    request_id: UUID


async def handle_cancel_signature(
    cmd: CancelSignatureCommand, session: AsyncSession
) -> dict[str, Any]:
    """Transition pending → cancelled. Already-signed rows return 409."""
    request = await repo.get_by_id(session, cmd.request_id)
    if request is None:
        raise ServiceError("Документ не найден", 404)
    if request["status"] != repo.STATUS_PENDING:
        raise ServiceError(
            "Документ уже подписан или отменён — отменять нечего", 409
        )
    cancelled = await repo.mark_cancelled(session, request_id=cmd.request_id)
    if cancelled is None:
        # Raced with a concurrent sign — tell the admin to retry.
        raise ServiceError("Документ уже подписан", 409)
    logger.info("Signature request %s cancelled by admin", cmd.request_id)
    return cast("dict[str, Any]", cancelled)


@dataclass
class UploadPhysicalSignatureCommand:
    request_id: UUID
    actor_user_id: UUID
    filename: str
    content_type: str
    data: bytes
    signing_ip: str | None
    signing_user_agent: str | None


async def handle_sign_electronic(
    cmd: SignElectronicCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    request = await _load_owned(session, cmd.request_id, cmd.actor_user_id)
    if request["status"] != repo.STATUS_PENDING:
        raise ServiceError("Документ уже подписан или отменён", 409)
    operator_scope = await _resolve_sopd_operator_scope(session, request)
    await _require_mobile_id_for_sopd(
        session, request, operator_scope=operator_scope
    )

    pdf_bytes = await _render_signed_pdf(
        document_type=request["document_type"],
        session=session,
        storage=storage,
        request_id=cmd.request_id,
        operator_scope=operator_scope,
    )

    key = document_storage.build_user_key(
        cmd.actor_user_id,
        f"signatures/{uuid.uuid4().hex}-{request['document_type']}-signed.pdf",
    )
    await document_storage.put_document(key, pdf_bytes, "application/pdf")

    signed = await repo.mark_signed(
        session,
        request_id=cmd.request_id,
        method="electronic",
        signed_pdf_s3_key=key,
        signing_ip=cmd.signing_ip,
        signing_user_agent=cmd.signing_user_agent,
    )
    if signed is None:
        # Rare — a concurrent sign attempt raced us.
        raise ServiceError("Документ уже подписан", 409)
    await _persist_sopd_operator_snapshot(
        session, signed, operator_scope=operator_scope
    )
    if signed["document_type"] == repo.DOC_TYPE_SOPD:
        await refresh_consent_projection(session, signed.get("application_id"))
    logger.info(
        "Signature %s signed electronically by user %s",
        cmd.request_id,
        cmd.actor_user_id,
    )
    return cast("dict[str, Any]", signed)


async def handle_upload_physical_signature(
    cmd: UploadPhysicalSignatureCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.content_type not in _ALLOWED_PHYSICAL_TYPES:
        raise ServiceError(
            "Разрешены только PDF / PNG / JPEG / HEIC для скана", 415
        )

    request = await _load_owned(session, cmd.request_id, cmd.actor_user_id)
    if request["status"] != repo.STATUS_PENDING:
        raise ServiceError("Документ уже подписан или отменён", 409)
    operator_scope = await _resolve_sopd_operator_scope(session, request)
    if not await _is_paper_sopd_owner_upload(session, request, cmd.actor_user_id):
        await _require_mobile_id_for_sopd(
            session, request, operator_scope=operator_scope
        )

    # Preserve the uploaded filename's extension; reconstruct if missing.
    suffix = ""
    if "." in cmd.filename:
        suffix = "." + cmd.filename.rsplit(".", 1)[-1]
    key = document_storage.build_user_key(
        cmd.actor_user_id,
        f"signatures/{uuid.uuid4().hex}-{request['document_type']}-scan{suffix}",
    )
    await document_storage.put_document(key, cmd.data, cmd.content_type)

    signed = await repo.mark_signed(
        session,
        request_id=cmd.request_id,
        method="physical",
        signed_pdf_s3_key=key,
        signing_ip=cmd.signing_ip,
        signing_user_agent=cmd.signing_user_agent,
    )
    if signed is None:
        raise ServiceError("Документ уже подписан", 409)
    await _persist_sopd_operator_snapshot(
        session, signed, operator_scope=operator_scope
    )
    if signed["document_type"] == repo.DOC_TYPE_SOPD:
        await refresh_consent_projection(session, signed.get("application_id"))
    logger.info(
        "Signature %s uploaded (physical scan) by user %s",
        cmd.request_id,
        cmd.actor_user_id,
    )
    return cast("dict[str, Any]", signed)


# ---------------------------------------------------------------------------
# Helpers


async def _load_owned(
    session: AsyncSession, request_id: UUID, actor_user_id: UUID
) -> dict[str, Any]:
    request = await repo.get_by_id(session, request_id)
    if request is None:
        raise ServiceError("Документ не найден", 404)
    if request["user_id"] != actor_user_id:
        raise ServiceError("Нет доступа к документу", 403)
    return cast("dict[str, Any]", request)


async def _resolve_sopd_operator_scope(
    session: AsyncSession,
    request: dict[str, Any],
) -> SopdOperatorSnapshotData | None:
    if request["document_type"] != repo.DOC_TYPE_SOPD:
        return None
    return await resolve_sopd_operator_snapshot(
        session,
        application_id=request.get("application_id"),
    )


async def _require_mobile_id_for_sopd(
    session: AsyncSession,
    request: dict[str, Any],
    *,
    operator_scope: SopdOperatorSnapshotData | None = None,
) -> None:
    if request["document_type"] != repo.DOC_TYPE_SOPD:
        return
    verified = await identity_verification_repo.get_latest_verified_for_user(
        session,
        user_id=request["user_id"],
        provider=identity_verification_repo.PROVIDER_MOBILE_ID,
    )
    if verified is None:
        raise ServiceError(_SOPD_MOBILE_ID_REQUIRED_DETAIL, 403)
    context = await _confirmed_sopd_context(session, request, operator_scope)
    if not _sopd_identity_matches_verified_profile(verified, context):
        logger.info("SOPD identity mismatch signature_request_id=%s", request["id"])
        raise ServiceError(_SOPD_IDENTITY_MISMATCH_DETAIL, 403)


async def _is_paper_sopd_owner_upload(
    session: AsyncSession,
    request: dict[str, Any],
    actor_user_id: UUID,
) -> bool:
    """Allow only the applicant-owned paper flow to upload another signer's scan.

    A normal SOPD upload remains subject to Mobile ID identity matching. The
    exception is tied to the immutable snapshot/request binding created by the
    paper invite flow: the uploader must be both request owner and inviter,
    and the bound snapshot must match that uploader, application and opaque
    signer key.
    """
    subject = request.get("subject_snapshot") or {}
    if (
        request["document_type"] != repo.DOC_TYPE_SOPD
        or request["user_id"] != actor_user_id
        or request.get("invited_by_user_id") != actor_user_id
        or request.get("application_id") is None
        or subject.get("sopd_flow") != _SOPD_FLOW_PHYSICAL_OWNER_UPLOAD
    ):
        return False

    snapshot = await passport_snapshot_repo.get_for_request(session, request["id"])
    return bool(
        snapshot
        and snapshot.get("owner_user_id") == actor_user_id
        and snapshot.get("application_id") == request["application_id"]
        and snapshot.get("signer_key") == subject.get("signer_key")
        and snapshot.get("confirmed_fields")
        and not snapshot.get("has_unsaved_changes")
    )


def _sopd_identity_matches_verified_profile(
    verified: dict[str, Any],
    context: dict[str, str],
) -> bool:
    verified_name = _normalise_identity_name(_verified_full_name(verified))
    sopd_name = _normalise_identity_name(context.get("full_name"))
    verified_birthdate = parse_date(verified.get("birthdate"))
    sopd_birthdate = parse_date(context.get("birth_date"))
    return bool(
        verified_name
        and sopd_name
        and verified_birthdate is not None
        and sopd_birthdate is not None
        and verified_name == sopd_name
        and verified_birthdate == sopd_birthdate
    )


def _verified_full_name(verified: dict[str, Any]) -> str:
    return " ".join(
        part
        for key in ("family_name", "given_name", "middle_name")
        if (part := str(verified.get(key) or "").strip())
    )


def _normalise_identity_name(value: Any) -> str:
    text = str(value or "").replace("ё", "е").lower()
    return " ".join(re.sub(r"[^0-9a-zа-я]+", " ", text).split())


async def _render_signed_pdf(
    *,
    document_type: str,
    session: AsyncSession,
    storage: ObjectStorage,
    request_id: UUID,
    operator_scope: SopdOperatorSnapshotData | None = None,
) -> bytes:
    if document_type == repo.DOC_TYPE_SOPD:
        request = await repo.get_by_id(session, request_id)
        if request is None:
            raise ServiceError("Документ не найден", 404)
        context = await _confirmed_sopd_context(session, request, operator_scope)
        return await ensure_sopd_pdf(
            session=session, storage=storage, context=context
        )
    if repo.is_director_doc_type(document_type):
        invitation = await dir_invite_repo.get_by_signature_request_id(
            session, request_id
        )
        if invitation is None or invitation.get("document_id") is None:
            raise ServiceError("Оригинальный документ не найден", 404)
        document = await docs_repo.get_by_id(
            session, invitation["document_id"]
        )
        if document is None or not document.get("s3_key"):
            raise ServiceError("Оригинальный документ не найден", 404)
        data = await document_storage.get_document(str(document["s3_key"]))
        if data is None:
            raise ServiceError("Оригинальный документ не найден", 404)
        return data
    raise ServiceError(f"Неизвестный тип документа: {document_type}", 400)


def _passport_context(fields: dict[str, Any]) -> dict[str, str]:
    def value(key: str) -> str:
        return str(fields.get(key) or "").strip()

    return {
        "full_name": " ".join(x for x in (value("surname"), value("name"), value("patronymic")) if x),
        "gender": "Мужской" if value("gender") == "male" else "Женский" if value("gender") == "female" else "",
        "birth_date": value("birthDate"), "birth_place": value("birthPlace"),
        "passport_series_number": " ".join(x for x in (value("passportSeries"), value("passportNumber")) if x),
        "passport_issued_by": value("givenWhom"), "passport_issued_at": value("givenDate"), "passport_code": value("code"),
    }


async def _confirmed_sopd_context(session: AsyncSession, request: dict[str, Any], operator_scope: SopdOperatorSnapshotData | None) -> dict[str, str]:
    snapshot = await passport_snapshot_repo.get_for_request(session, request["id"])
    if snapshot is None or not snapshot.get("confirmed_fields"):
        raise ServiceError("Подтверждённый снимок паспорта отсутствует", 409)
    if snapshot.get("has_unsaved_changes"):
        raise ServiceError("Есть несохранённые изменения паспортных данных", 409)
    context = await build_signer_context(session, user_id=request["user_id"], subject_snapshot=request.get("subject_snapshot"), application_id=request.get("application_id"), operator_scope=operator_scope)
    context.update(_passport_context(snapshot["confirmed_fields"]))
    return context


async def _persist_sopd_operator_snapshot(
    session: AsyncSession,
    request: dict[str, Any],
    *,
    operator_scope: SopdOperatorSnapshotData | None = None,
) -> None:
    if request["document_type"] != repo.DOC_TYPE_SOPD:
        return
    operators = operator_scope
    if operators is None:
        operators = await resolve_sopd_operator_snapshot(
            session,
            application_id=request.get("application_id"),
        )
    await snapshot_repo.upsert(
        session,
        signature_request_id=request["id"],
        user_id=request["user_id"],
        application_id=request.get("application_id"),
        leasing_companies=operators.leasing_companies,
        contractors=operators.contractors,
        source=operators.source,
    )
