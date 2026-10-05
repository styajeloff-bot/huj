"""Client-initiated СОПД revoke flow with SMS verification."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.signer_sopd_context import build_signer_context
from application.queries.sopd_operators import resolve_sopd_operator_snapshot
from application.services.questionnaire_consents import refresh_consent_projection
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import application_repository as application_repo
from infrastructure.repositories import auth_repository
from infrastructure.repositories import signature_request_repository as repo
from infrastructure.repositories import (
    sopd_operator_snapshot_repository as snapshot_repo,
)
from infrastructure.repositories import sopd_revoke_repository as revoke_repo
from infrastructure.repositories import verification_code_repository as codes_repo
from infrastructure.repositories.verification_code_repository import (
    VerificationCodeDict,
)
from infrastructure.services import sopd_revoke_renderer
from infrastructure.services.sms import (
    get_verification_code,
    is_test_phone,
    send_text_sms,
)

logger = logging.getLogger("carcraft-backend")

PURPOSE_SIGNATURE_REVOKE = "signature_revoke"
CODE_TTL_SECONDS = 600
RESEND_DELAY_SECONDS = 60
MAX_CODES_PER_MINUTE = 5
MAX_FAILED_ATTEMPTS = 5


@dataclass(frozen=True)
class RequestSignatureRevokeCommand:
    request_id: UUID
    actor_user_id: UUID
    leasing_company_ids: list[UUID]
    client_ip: str | None
    user_agent: str | None


@dataclass(frozen=True)
class ConfirmSignatureRevokeCommand:
    request_id: UUID
    actor_user_id: UUID
    code: str
    client_ip: str | None
    user_agent: str | None


@dataclass(frozen=True)
class RevokeInitiated:
    message: str
    revoke_request_id: UUID
    phone_masked: str
    code_ttl_seconds: int
    resend_delay_seconds: int
    revoke_requested_at: datetime
    revoked_leasing_companies: list[dict[str, Any]]
    revoked_contractors: list[dict[str, Any]]
    excluded_contractors: list[dict[str, Any]]
    is_full_revoke: bool


@dataclass(frozen=True)
class RevokeConfirmed:
    message: str
    status: str
    revoke_request_id: UUID
    confirmed_at: datetime
    revoke_requested_at: datetime | None
    revoked_leasing_companies: list[dict[str, Any]]
    revoked_contractors: list[dict[str, Any]]
    excluded_contractors: list[dict[str, Any]]
    is_full_revoke: bool
    document_s3_key: str
    revoke_document_download_url: str


@dataclass(frozen=True)
class RevokeOptionsQuery:
    request_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True)
class RevokeOptions:
    leasing_companies: list[dict[str, Any]]
    contractors: list[dict[str, Any]]


class RevokeSignatureError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


async def handle_request_signature_revoke(
    cmd: RequestSignatureRevokeCommand, session: AsyncSession
) -> RevokeInitiated:
    request = await _load_owned_request(
        session, cmd.request_id, cmd.actor_user_id
    )
    _ensure_revocable(request)
    plan = await _build_revoke_plan(
        session,
        request=request,
        selected_leasing_company_ids=cmd.leasing_company_ids,
    )

    user = await auth_repository.find_user_by_id(session, request["user_id"])
    phone = (user or {}).get("phone")
    if not phone:
        raise RevokeSignatureError(
            "PHONE_NOT_FOUND",
            "У пользователя не найден номер телефона.",
            400,
        )

    await _ensure_rate_limit(session, phone)
    await _invalidate_active_codes(session, cmd.request_id)
    await revoke_repo.cancel_pending_for_signature(
        session, signature_request_id=cmd.request_id
    )
    pending = await revoke_repo.create_pending(
        session,
        signature_request_id=cmd.request_id,
        user_id=cmd.actor_user_id,
        application_id=request.get("application_id"),
        selected_leasing_company_ids=plan["selected_leasing_company_ids"],
        revoked_leasing_company_ids=plan["revoked_leasing_company_ids"],
        revoked_contractor_ids=plan["revoked_contractor_ids"],
        excluded_contractor_ids=plan["excluded_contractor_ids"],
        operators_snapshot=plan["operators_snapshot"],
    )

    code = get_verification_code(phone)
    expires_at = datetime.now(UTC) + timedelta(seconds=CODE_TTL_SECONDS)
    await codes_repo.create_code(
        session,
        phone=phone,
        code=code,
        expires_at=expires_at,
        purpose=PURPOSE_SIGNATURE_REVOKE,
        entity_id=str(cmd.request_id),
    )

    updated = await repo.request_revoke(session, request_id=cmd.request_id)
    if updated is None:
        latest = await repo.get_by_id(session, cmd.request_id)
        _ensure_revocable(latest or request)
        raise RevokeSignatureError(
            "SIGNATURE_NOT_SIGNED",
            "СОПД не подписано. Отзыв невозможен.",
            400,
        )

    _fire_sms(
        phone,
        (
            "Код подтверждения отзыва согласия на обработку "
            f"персональных данных: {code}. Действителен 10 минут. "
            "Никому не сообщайте."
        ),
    )
    masked = _mask_phone(phone)
    logger.info(
        "sopd_revoke_initiated user_id=%s signature_request_id=%s "
        "phone_masked=%s ip=%s user_agent=%s",
        cmd.actor_user_id,
        cmd.request_id,
        masked,
        cmd.client_ip,
        cmd.user_agent,
    )
    return RevokeInitiated(
        message=f"Код подтверждения отправлен на номер {masked}",
        revoke_request_id=cast("UUID", pending["id"]),
        phone_masked=masked,
        code_ttl_seconds=CODE_TTL_SECONDS,
        resend_delay_seconds=RESEND_DELAY_SECONDS,
        revoke_requested_at=cast("datetime", updated["revoke_requested_at"]),
        revoked_leasing_companies=plan["revoked_leasing_companies"],
        revoked_contractors=plan["revoked_contractors"],
        excluded_contractors=plan["excluded_contractors"],
        is_full_revoke=plan["is_full_revoke"],
    )


async def handle_get_signature_revoke_options(
    query: RevokeOptionsQuery, session: AsyncSession
) -> RevokeOptions:
    request = await _load_owned_request(
        session, query.request_id, query.actor_user_id
    )
    _ensure_revocable(request)
    scope = await _load_or_create_operator_snapshot(session, request)
    revoked = await revoke_repo.list_revoked_operators(
        session, signature_request_id=query.request_id
    )
    revoked_lc_ids = {
        item["leasing_company_id"]
        for item in revoked
        if item["operator_type"] == revoke_repo.TYPE_LEASING_COMPANY
        and item.get("leasing_company_id") is not None
    }
    revoked_contractor_ids = {
        item["contractor_id"]
        for item in revoked
        if item["operator_type"] == revoke_repo.TYPE_CONTRACTOR
        and item.get("contractor_id") is not None
    }
    leasing_companies = []
    for item in scope["leasing_companies"]:
        item_id = _uuid_from_snapshot(item.get("id"))
        already_revoked = item_id in revoked_lc_ids if item_id else False
        leasing_companies.append(
            {
                **item,
                "already_revoked": already_revoked,
                "disabled": already_revoked,
                "disabled_reason": "Уже отозвано" if already_revoked else None,
            }
        )
    contractors = []
    for item in scope["contractors"]:
        item_id = _uuid_from_snapshot(item.get("id"))
        contractors.append(
            {
                **item,
                "already_revoked": item_id in revoked_contractor_ids
                if item_id
                else False,
            }
        )
    return RevokeOptions(
        leasing_companies=leasing_companies,
        contractors=contractors,
    )


async def handle_confirm_signature_revoke(
    cmd: ConfirmSignatureRevokeCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> RevokeConfirmed:
    request = await _load_owned_request(
        session, cmd.request_id, cmd.actor_user_id
    )
    _ensure_revocable(request)
    if not request.get("revoke_requested_at"):
        raise RevokeSignatureError(
            "NO_ACTIVE_REVOKE_REQUEST",
            "Нет активной заявки на отзыв. Вызовите /revoke для создания кода.",
            400,
        )
    pending = await revoke_repo.get_latest_pending(
        session, signature_request_id=cmd.request_id
    )
    if pending is None:
        raise RevokeSignatureError(
            "NO_ACTIVE_REVOKE_REQUEST",
            "Нет активной заявки на отзыв. Вызовите /revoke для создания кода.",
            400,
        )

    code = await _get_latest_revoke_code(session, cmd.request_id)
    if code is None:
        raise RevokeSignatureError(
            "NO_ACTIVE_REVOKE_REQUEST",
            "Нет активной заявки на отзыв. Вызовите /revoke для создания кода.",
            400,
        )

    now = datetime.now(UTC)
    expires_at = _aware(code["expires_at"])
    if code["used_at"] is not None or expires_at <= now:
        logger.warning(
            "sopd_revoke_code_expired user_id=%s signature_request_id=%s "
            "expired_at=%s",
            cmd.actor_user_id,
            cmd.request_id,
            expires_at.isoformat(),
        )
        raise RevokeSignatureError(
            "CODE_EXPIRED",
            "Код подтверждения истёк. Запросите новый код.",
            422,
            {"expired_at": expires_at.isoformat()},
        )

    failed_attempts = int(code["failed_attempts"] or 0)
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        raise RevokeSignatureError(
            "TOO_MANY_FAILED_ATTEMPTS",
            "Превышено количество попыток. Запросите новый код.",
            422,
            {
                "max_attempts": MAX_FAILED_ATTEMPTS,
                "failed_attempts": failed_attempts,
            },
        )

    if code["code"] != cmd.code:
        updated_code = await codes_repo.increment_failed_attempts(
            session, code_id=code["id"]
        )
        failed_attempts = (
            updated_code["failed_attempts"]
            if updated_code is not None
            else failed_attempts + 1
        )
        remaining = max(0, MAX_FAILED_ATTEMPTS - failed_attempts)
        logger.warning(
            "sopd_revoke_invalid_code user_id=%s signature_request_id=%s "
            "attempt=%s",
            cmd.actor_user_id,
            cmd.request_id,
            failed_attempts,
        )
        raise RevokeSignatureError(
            "INVALID_VERIFICATION_CODE",
            "Неверный код подтверждения.",
            422,
            {"attempts_remaining": remaining},
        )

    confirmed = await revoke_repo.confirm_request(
        session,
        revoke_request_id=pending["id"],
        revoke_ip=cmd.client_ip,
        revoke_user_agent=cmd.user_agent,
    )
    if confirmed is None:
        raise RevokeSignatureError(
            "NO_ACTIVE_REVOKE_REQUEST",
            "Нет активной заявки на отзыв. Вызовите /revoke для создания кода.",
            400,
        )
    operators_snapshot = cast("dict[str, Any]", confirmed["operators_snapshot"])
    document_s3_key = await _store_revoke_document(
        session,
        storage,
        request=request,
        revoke_request=confirmed,
        operators_snapshot=operators_snapshot,
    )
    stored = await revoke_repo.set_document_key(
        session,
        revoke_request_id=confirmed["id"],
        document_s3_key=document_s3_key,
    )
    if stored is not None:
        confirmed = stored
    facts = _operator_facts_from_snapshot(operators_snapshot)
    await revoke_repo.insert_operator_facts(
        session,
        revoke_request_id=confirmed["id"],
        signature_request_id=cmd.request_id,
        user_id=cmd.actor_user_id,
        operators=facts,
    )
    is_full_revoke = bool(operators_snapshot.get("is_full_revoke"))
    final_request = request
    if is_full_revoke:
        revoked = await repo.mark_revoked(
            session,
            request_id=cmd.request_id,
            revoke_ip=cmd.client_ip,
            revoke_user_agent=cmd.user_agent,
        )
        if revoked is None:
            raise RevokeSignatureError(
                "SIGNATURE_NOT_SIGNED",
                "СОПД не подписано. Отзыв невозможен.",
                400,
            )
        final_request = revoked

    await refresh_consent_projection(session, request.get("application_id"))
    await codes_repo.mark_used(session, code_id=code["id"], used_at=datetime.now(UTC))
    logger.info(
        "sopd_revoke_confirmed user_id=%s signature_request_id=%s "
        "revoked_at=%s ip=%s user_agent=%s",
        cmd.actor_user_id,
        cmd.request_id,
        confirmed["confirmed_at"],
        cmd.client_ip,
        cmd.user_agent,
    )
    return RevokeConfirmed(
        message="Отзыв согласия на обработку персональных данных подтверждён.",
        status=cast("str", final_request["status"]),
        revoke_request_id=cast("UUID", confirmed["id"]),
        confirmed_at=cast("datetime", confirmed["confirmed_at"]),
        revoke_requested_at=cast(
            "datetime | None", final_request["revoke_requested_at"]
        ),
        revoked_leasing_companies=operators_snapshot["revoked_leasing_companies"],
        revoked_contractors=operators_snapshot["revoked_contractors"],
        excluded_contractors=operators_snapshot["excluded_contractors"],
        is_full_revoke=is_full_revoke,
        document_s3_key=document_s3_key,
        revoke_document_download_url=_revoke_document_download_url(
            cmd.request_id, cast("UUID", confirmed["id"])
        ),
    )


async def _load_owned_request(
    session: AsyncSession, request_id: UUID, actor_user_id: UUID
) -> dict[str, Any]:
    request = await repo.get_by_id(session, request_id)
    if request is None:
        raise RevokeSignatureError(
            "SIGNATURE_NOT_FOUND",
            "Запрос на подпись не найден.",
            404,
            {"request_id": str(request_id)},
        )
    if request["user_id"] != actor_user_id:
        raise RevokeSignatureError(
            "ACCESS_DENIED",
            "Вы не являетесь владельцем данного СОПД.",
            403,
            {
                "request_user_id": str(request["user_id"]),
                "current_user_id": str(actor_user_id),
            },
        )
    return cast("dict[str, Any]", request)


async def _load_or_create_operator_snapshot(
    session: AsyncSession, request: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    stored = await snapshot_repo.get_by_signature_request_id(
        session, request["id"]
    )
    if stored is not None:
        return {
            "leasing_companies": cast(
                "list[dict[str, Any]]", stored["leasing_companies"]
            ),
            "contractors": cast("list[dict[str, Any]]", stored["contractors"]),
        }

    operators = await resolve_sopd_operator_snapshot(
        session, application_id=request.get("application_id")
    )
    if not operators.leasing_companies:
        raise RevokeSignatureError(
            "SOPD_OPERATOR_SCOPE_NOT_FOUND",
            "Невозможно определить список лизинговых компаний для этого СОПД.",
            400,
            {"signature_request_id": str(request["id"])},
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
    return {
        "leasing_companies": operators.leasing_companies,
        "contractors": operators.contractors,
    }


async def _build_revoke_plan(
    session: AsyncSession,
    *,
    request: dict[str, Any],
    selected_leasing_company_ids: list[UUID],
) -> dict[str, Any]:
    if not selected_leasing_company_ids:
        raise RevokeSignatureError(
            "LEASING_COMPANIES_REQUIRED",
            "Выберите хотя бы одну лизинговую компанию для отзыва.",
            422,
        )

    scope = await _load_or_create_operator_snapshot(session, request)
    leasing_company_by_id = {
        parsed_id: item
        for item in scope["leasing_companies"]
        if (parsed_id := _uuid_from_snapshot(item.get("id"))) is not None
    }
    contractor_by_id = {
        parsed_id: item
        for item in scope["contractors"]
        if (parsed_id := _uuid_from_snapshot(item.get("id"))) is not None
    }
    scope_lc_ids = set(leasing_company_by_id)

    selected_ids = _dedupe_uuid_list(selected_leasing_company_ids)
    invalid_ids = [item for item in selected_ids if item not in scope_lc_ids]
    if invalid_ids:
        raise RevokeSignatureError(
            "LEASING_COMPANY_OUT_OF_SCOPE",
            "Выбрана лизинговая компания, которой нет в этом СОПД.",
            422,
            {"leasing_company_ids": [str(item) for item in invalid_ids]},
        )

    confirmed = await revoke_repo.list_revoked_operators(
        session, signature_request_id=request["id"]
    )
    already_revoked_lc_ids = {
        item["leasing_company_id"]
        for item in confirmed
        if item["operator_type"] == revoke_repo.TYPE_LEASING_COMPANY
        and item.get("leasing_company_id") is not None
    }
    already_revoked_contractor_ids = {
        item["contractor_id"]
        for item in confirmed
        if item["operator_type"] == revoke_repo.TYPE_CONTRACTOR
        and item.get("contractor_id") is not None
    }

    selected_set = set(selected_ids)
    revoked_lc_ids = [
        item for item in selected_ids if item not in already_revoked_lc_ids
    ]
    active_after_revoke = scope_lc_ids - already_revoked_lc_ids - selected_set

    revoked_contractors: list[dict[str, Any]] = []
    excluded_contractors: list[dict[str, Any]] = []
    for contractor_id, contractor in contractor_by_id.items():
        linked_lc_ids = {
            parsed
            for raw in contractor.get("leasing_company_ids") or []
            if (parsed := _uuid_from_snapshot(raw)) is not None
        }
        if not linked_lc_ids.intersection(selected_set):
            continue
        if contractor_id in already_revoked_contractor_ids:
            continue
        if linked_lc_ids.intersection(active_after_revoke):
            excluded_contractors.append(contractor)
        else:
            revoked_contractors.append(contractor)

    if not revoked_lc_ids and not revoked_contractors:
        raise RevokeSignatureError(
            "OPERATORS_ALREADY_REVOKED",
            "По выбранным лизинговым компаниям уже нет операторов для отзыва.",
            409,
        )

    revoked_leasing_companies = [
        leasing_company_by_id[item] for item in revoked_lc_ids
    ]
    operators_snapshot = {
        "selected_leasing_companies": [
            leasing_company_by_id[item] for item in selected_ids
        ],
        "revoked_leasing_companies": revoked_leasing_companies,
        "revoked_contractors": revoked_contractors,
        "excluded_contractors": excluded_contractors,
        "document_leasing_companies": [],
        "document_contractors": [],
        "is_full_revoke": not active_after_revoke,
    }
    if operators_snapshot["is_full_revoke"]:
        operators_snapshot["document_leasing_companies"] = scope["leasing_companies"]
        operators_snapshot["document_contractors"] = list(contractor_by_id.values())
    else:
        operators_snapshot["document_leasing_companies"] = revoked_leasing_companies
        operators_snapshot["document_contractors"] = [
            *revoked_contractors,
            *excluded_contractors,
        ]
    return {
        "selected_leasing_company_ids": selected_ids,
        "revoked_leasing_company_ids": revoked_lc_ids,
        "revoked_contractor_ids": [
            cast("UUID", _uuid_from_snapshot(item.get("id")))
            for item in revoked_contractors
        ],
        "excluded_contractor_ids": [
            cast("UUID", _uuid_from_snapshot(item.get("id")))
            for item in excluded_contractors
        ],
        "operators_snapshot": operators_snapshot,
        "revoked_leasing_companies": revoked_leasing_companies,
        "revoked_contractors": revoked_contractors,
        "excluded_contractors": excluded_contractors,
        "is_full_revoke": not active_after_revoke,
    }


def _operator_facts_from_snapshot(
    operators_snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for item in operators_snapshot.get("revoked_leasing_companies") or []:
        if not isinstance(item, dict):
            continue
        facts.append(
            {
                "operator_type": revoke_repo.TYPE_LEASING_COMPANY,
                "leasing_company_id": _uuid_from_snapshot(item.get("id")),
                "contractor_id": None,
                "operator_name": str(item.get("name") or ""),
                "operator_inn": str(item.get("inn") or ""),
            }
        )
    for item in operators_snapshot.get("revoked_contractors") or []:
        if not isinstance(item, dict):
            continue
        facts.append(
            {
                "operator_type": revoke_repo.TYPE_CONTRACTOR,
                "leasing_company_id": None,
                "contractor_id": _uuid_from_snapshot(item.get("id")),
                "operator_name": str(item.get("name") or ""),
                "operator_inn": str(item.get("inn") or ""),
            }
        )
    return facts


async def _store_revoke_document(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    request: dict[str, Any],
    revoke_request: dict[str, Any],
    operators_snapshot: dict[str, Any],
) -> str:
    revoke_request_id = cast("UUID", revoke_request["id"])
    user_id = cast("UUID", request["user_id"])
    key = sopd_revoke_renderer.build_revoke_document_key(
        user_id=user_id,
        revoke_request_id=revoke_request_id,
    )
    operators = _operators_for_revoke_document(operators_snapshot)
    subject = await build_signer_context(
        session,
        user_id=user_id,
        subject_snapshot=request.get("subject_snapshot"),
        application_id=request.get("application_id"),
    )
    source_document = await _source_document_context(session, request)
    pdf_bytes = await sopd_revoke_renderer.render_pdf(
        {
            "subject": subject,
            "source_document": source_document,
            "requested_at": revoke_request.get("requested_at")
            or request.get("revoke_requested_at"),
            "confirmed_at": revoke_request.get("confirmed_at"),
            "is_full_revoke": bool(operators_snapshot.get("is_full_revoke")),
            "operators": operators,
        }
    )
    await storage.put(key, pdf_bytes, "application/pdf")
    return key


async def _source_document_context(
    session: AsyncSession, request: dict[str, Any]
) -> dict[str, Any]:
    application_id = request.get("application_id")
    display_number = None
    if application_id is not None:
        application = await application_repo.get_by_id(session, application_id)
        if application is not None:
            display_number = application.get("display_number")
    return {
        "id": str(request.get("id") or ""),
        "display_number": display_number,
        "signed_at": request.get("signed_at")
        or request.get("sent_at")
        or request.get("created_at"),
    }


def _operators_for_revoke_document(
    operators_snapshot: dict[str, Any]
) -> list[dict[str, Any]]:
    leasing_companies = (
        operators_snapshot.get("document_leasing_companies")
        or operators_snapshot.get("revoked_leasing_companies")
        or []
    )
    contractors = (
        operators_snapshot.get("document_contractors")
        or operators_snapshot.get("revoked_contractors")
        or []
    )
    result = [
        {**item, "operator_type": revoke_repo.TYPE_LEASING_COMPANY}
        for item in leasing_companies
        if isinstance(item, dict)
    ]
    result.extend(
        {**item, "operator_type": revoke_repo.TYPE_CONTRACTOR}
        for item in contractors
        if isinstance(item, dict)
    )
    return result


def _revoke_document_download_url(
    signature_request_id: UUID, revoke_request_id: UUID
) -> str:
    return (
        f"/api/v1/signatures/{signature_request_id}/"
        f"revoke-documents/{revoke_request_id}/download"
    )


def _dedupe_uuid_list(values: list[UUID]) -> list[UUID]:
    result: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _uuid_from_snapshot(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _ensure_revocable(request: dict[str, Any]) -> None:
    if request["status"] == repo.STATUS_REVOKED:
        raise RevokeSignatureError(
            "ALREADY_REVOKED",
            "СОПД уже отозвано.",
            409,
            {"revoked_at": request.get("revoked_at")},
        )
    allowed = [repo.STATUS_SIGNED_ELECTRONIC, repo.STATUS_SIGNED_PHYSICAL]
    if request["status"] not in allowed:
        raise RevokeSignatureError(
            "SIGNATURE_NOT_SIGNED",
            "СОПД не подписано. Отзыв невозможен.",
            400,
            {"current_status": request["status"], "allowed_statuses": allowed},
        )


async def _ensure_rate_limit(session: AsyncSession, phone: str) -> None:
    since = datetime.now(UTC) - timedelta(seconds=60)
    count = await codes_repo.count_recent_for_phone(
        session, phone=phone, purpose=PURPOSE_SIGNATURE_REVOKE, since=since
    )
    if count >= MAX_CODES_PER_MINUTE:
        raise RevokeSignatureError(
            "TOO_MANY_REQUESTS",
            "Превышен лимит запросов. Попробуйте через 60 секунд.",
            429,
            {"retry_after_seconds": RESEND_DELAY_SECONDS},
        )


async def _invalidate_active_codes(session: AsyncSession, request_id: UUID) -> None:
    now = datetime.now(UTC)
    await codes_repo.invalidate_active_codes(
        session,
        purpose=PURPOSE_SIGNATURE_REVOKE,
        entity_id=str(request_id),
        expires_at=now,
    )


async def _get_latest_revoke_code(
    session: AsyncSession, request_id: UUID
) -> VerificationCodeDict | None:
    return cast(
        "VerificationCodeDict | None",
        await codes_repo.get_latest_code(
            session, purpose=PURPOSE_SIGNATURE_REVOKE, entity_id=str(request_id)
        ),
    )


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        return f"+7 ({digits[1:4]}) ***-**-{digits[-2:]}"
    if len(digits) == 10:
        return f"+7 ({digits[0:3]}) ***-**-{digits[-2:]}"
    return phone[:3] + " *** *** ** **"


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def _send_sms_background(phone: str, text: str) -> None:
    try:
        await send_text_sms(phone, text)
    except Exception as exc:
        logger.error("sopd_revoke_sms_failed phone=%s err=%s", phone, exc)


_sms_tasks: set[asyncio.Task[None]] = set()


def _fire_sms(phone: str, text: str) -> None:
    if is_test_phone(phone):
        return
    task = asyncio.create_task(_send_sms_background(phone, text))
    _sms_tasks.add(task)
    task.add_done_callback(_sms_tasks.discard)
