"""Invite CEO / founders to sign СОПД.

Called from the checkout step-4 of a leasing application. For each signer
the applicant lists:

    - **phone given**  → electronic track: find-or-create user by phone,
      link to company, issue a one-shot magic link, create a СОПД
      signature request, send SMS with the short URL.
    - **phone omitted** → physical track: the applicant owns a pending SOPD
      signature request, prints СОПД, gets it wet-signed, and uploads the
      scan through the canonical ``upload-physical`` signature flow.

Idempotency: if the same phone is already a user + linked to the same
company, we re-use them and just issue a fresh magic link.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.document_recognition import SessionFactory
from application.errors import ServiceError
from application.queries.applications.get_application import (
    ApplicationAccessQuery,
    get_authorized_application,
)
from application.services.application_sopd_candidates import (
    application_signer_candidates,
)
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.repositories import auth_repository as repo
from infrastructure.repositories import (
    company_registration_repository as company_reg_repo,
)
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import (
    magic_link_repository as magic_link_repo,
)
from infrastructure.repositories import (
    signature_request_repository as signature_repo,
)
from infrastructure.repositories import (
    sopd_passport_snapshot_repository as passport_snapshot_repo,
)
from infrastructure.services import sms as sms_service
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_PHONE_RE = re.compile(r"^\+7\d{10}$")
_SOPD_MAGIC_LINK_TTL_SECONDS = 24 * 3600
_SOPD_FLOW_ELECTRONIC = "electronic_invitation"
_SOPD_FLOW_PHYSICAL_OWNER_UPLOAD = "physical_owner_upload"


@dataclass
class SignerPayload:
    signer_key: str
    full_name: str
    inn: str | None = None
    passport: str | None = None
    gender: Literal["male", "female"] | None = None
    phone: str | None = None


@dataclass
class InviteSignersCommand:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    company_lookup_provider: CompanyLookupProvider | None
    company_id: UUID
    application_id: uuid.UUID | None = None
    signers: list[SignerPayload] = field(default_factory=list)
    session_factory: SessionFactory | None = None


@dataclass
class SignerInviteResult:
    full_name: str
    phone: str | None
    user_id: UUID | None
    mode: Literal["electronic", "physical"]
    magic_link_sent: bool
    signature_request_ids: list[UUID]


async def handle_invite_signers(
    cmd: InviteSignersCommand, session: AsyncSession
) -> list[SignerInviteResult]:
    company = await company_repo.get_company_by_id(session, cmd.company_id)
    if company is None:
        raise ServiceError("Компания не найдена", 404)
    if cmd.application_id is None:
        raise ServiceError("Для приглашения СОПД требуется заявка", 422)
    application, _ = await get_authorized_application(
        ApplicationAccessQuery(
            application_id=cmd.application_id, actor_id=cmd.actor_user_id,
            actor_role=cmd.actor_role, actor_company_id=cmd.actor_company_id,
        ), session,
    )
    if application.get("company_id") != cmd.company_id:
        raise ServiceError("Компания не соответствует заявке", 422)
    candidates = await application_signer_candidates(session, application_id=cmd.application_id, company=company, provider=cmd.company_lookup_provider)
    candidates_by_key = {candidate["key"]: candidate for candidate in candidates}
    if any(signer.signer_key not in candidates_by_key for signer in cmd.signers):
        raise ServiceError("Подписант СОПД не найден", 404)

    results: list[SignerInviteResult] = []
    for signer in cmd.signers:
        candidate = candidates_by_key[signer.signer_key]
        if signer.phone:
            result = await _invite_electronic(
                session, signer=signer, candidate=candidate, company=company, cmd=cmd
            )
        else:
            snapshot = await passport_snapshot_repo.get_for_signer(
                session, application_id=cmd.application_id, signer_key=signer.signer_key
            )
            if (snapshot is None or snapshot["owner_user_id"] != cmd.actor_user_id
                    or not snapshot["confirmed_fields"] or snapshot["has_unsaved_changes"]):
                raise ServiceError("Подтвердите паспортные данные перед бумажным СОПД", 409)
            request_id = snapshot.get("signature_request_id")
            if request_id is not None:
                request = await signature_repo.get_by_id(session, request_id)
                if request is None or request["invited_by_user_id"] != cmd.actor_user_id:
                    raise ServiceError("СОПД недоступно для изменения", 409)
            else:
                request = await signature_repo.create(
                    session,
                    # The applicant uploads the wet-signed scan, so they own
                    # this request and the canonical upload-physical guard.
                    user_id=cmd.actor_user_id,
                    application_id=cmd.application_id,
                    document_type=signature_repo.DOC_TYPE_SOPD,
                    subject_snapshot=_subject_snapshot(
                        candidate=candidate,
                        company=company,
                        flow=_SOPD_FLOW_PHYSICAL_OWNER_UPLOAD,
                    ),
                    invited_by_user_id=cmd.actor_user_id,
                )
                bound = await passport_snapshot_repo.bind_request(
                    session,
                    application_id=cmd.application_id,
                    signer_key=signer.signer_key,
                    request_id=request["id"],
                    owner_user_id=cmd.actor_user_id,
                )
                if bound is None:
                    raise ServiceError("Подтвердите паспортные данные перед бумажным СОПД", 409)
                request_id = request["id"]
            result = SignerInviteResult(
                full_name=str(candidate["full_name"]),
                phone=None,
                user_id=cmd.actor_user_id,
                mode="physical",
                magic_link_sent=False,
                signature_request_ids=[request_id],
            )
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Internal


async def _invite_electronic(
    session: AsyncSession,
    *,
    signer: SignerPayload,
    candidate: dict[str, Any],
    company: Any,
    cmd: InviteSignersCommand,
) -> SignerInviteResult:
    # handle_invite_signers validates this once for the batch; keep the
    # invariant explicit here for the repository calls below.
    assert cmd.application_id is not None
    phone = _normalise_phone(signer.phone or "")

    existing = await repo.find_user_by_phone(session, phone)
    is_new_user = existing is None
    if is_new_user:
        user = await repo.create_user(
            session,
            phone=phone,
            email=None,
            name=str(candidate["full_name"]),
            password_hash="",
            company_id=None,
            phone_verified=False,
        )
        # We default is_active=true in create_user; invited users must
        # stay inactive until they click the magic link.
        await repo.set_user_active(session, user["id"], False)
    else:
        user = existing

    await company_reg_repo.ensure_user_company_link(
        session, user_id=user["id"], company_id=cmd.company_id
    )

    passport_snapshot = await passport_snapshot_repo.get_for_signer(
        session,
        application_id=cmd.application_id,
        signer_key=signer.signer_key,
    )
    if (
        passport_snapshot is None
        or passport_snapshot["owner_user_id"] != cmd.actor_user_id
        or not passport_snapshot.get("confirmed_fields")
        or passport_snapshot.get("has_unsaved_changes")
    ):
        raise ServiceError("Подтвердите паспортные данные перед отправкой СОПД", 409)

    bound_request_id = passport_snapshot.get("signature_request_id")
    sopd: dict[str, Any]
    if bound_request_id is not None:
        bound_request = await signature_repo.get_by_id(session, bound_request_id)
        if not _is_reusable_electronic_sopd(
            bound_request,
            application_id=cmd.application_id,
            owner_user_id=cmd.actor_user_id,
            signer_key=signer.signer_key,
            signer_user_id=user["id"],
        ):
            # A snapshot binding is immutable. In particular, do not replace
            # an existing paper, signed, cancelled, another-applicant, or
            # another-recipient request with a new SMS request.
            raise ServiceError("СОПД недоступно для повторного приглашения", 409)
        sopd = bound_request
    else:
        snapshot = _subject_snapshot(
            candidate=candidate,
            company=company,
            flow=_SOPD_FLOW_ELECTRONIC,
            phone=phone,
        )
        sopd = await signature_repo.create(
            session,
            user_id=user["id"],
            application_id=cmd.application_id,
            document_type=signature_repo.DOC_TYPE_SOPD,
            subject_snapshot=snapshot,
            sent_at=datetime.now(UTC),
            invited_by_user_id=cmd.actor_user_id,
        )
        bound = await passport_snapshot_repo.bind_request(
            session,
            application_id=cmd.application_id,
            signer_key=signer.signer_key,
            request_id=sopd["id"],
            owner_user_id=cmd.actor_user_id,
        )
        if bound is None:
            raise ServiceError("Подтвердите паспортные данные перед отправкой СОПД", 409)

    # Re-invite: kill any outstanding magic-link for this user so only the
    # newest one is live. Otherwise an invitee could end up with two valid
    # URLs in their SMS history and the stale one would still activate them.
    if existing is not None:
        await magic_link_repo.delete_unused_for_user(session, user_id=user["id"])

    link = await magic_link_repo.create(
        session,
        user_id=user["id"],
        ttl_seconds=_SOPD_MAGIC_LINK_TTL_SECONDS,
    )
    short_url = (
        f"{settings.public_url.rstrip('/')}"
        f"{settings.magic_link_path_prefix}/{link['token']}"
    )

    # Passport images are intentionally handled only by the canonical scoped
    # recognition endpoints before/after invite; never match them to FIO here.

    # Best-effort SMS. If it fails, the records remain — the operator can
    # resend later from an admin tool. We do not unwind the DB writes.
    magic_link_sent = await _send_invite_sms(phone, short_url)

    logger.info("SOPD invite dispatched application_id=%s sms=%s", cmd.application_id, magic_link_sent)
    return SignerInviteResult(
        full_name=str(candidate["full_name"]),
        phone=phone,
        user_id=user["id"],
        mode="electronic",
        magic_link_sent=magic_link_sent,
        signature_request_ids=[sopd["id"]],
    )


def _subject_snapshot(
    *,
    candidate: dict[str, Any],
    company: dict[str, Any],
    flow: str,
    phone: str | None = None,
) -> dict[str, Any]:
    """Build request data solely from the server-resolved signer candidate.

    ``flow`` is an internal, persisted discriminator. It is never read from
    the invitation payload and later server-side recognition updates preserve
    it while appending metadata to the snapshot.
    """
    snapshot: dict[str, Any] = {
        "signer_key": candidate["key"],
        "full_name": candidate["full_name"],
        "inn": candidate.get("inn"),
        "role": candidate.get("role"),
        "role_label": candidate.get("role_label"),
        "signing_method": candidate.get("signing_method"),
        "source": candidate.get("source"),
        "share": candidate.get("share"),
        "sopd_flow": flow,
        "company_name": company.get("name"),
        "company_inn": company.get("inn"),
    }
    if phone is not None:
        snapshot["phone"] = phone
    return snapshot


def _is_reusable_electronic_sopd(
    request: dict[str, Any] | None,
    *,
    application_id: UUID,
    owner_user_id: UUID,
    signer_key: str,
    signer_user_id: UUID,
) -> bool:
    """Whether an immutable snapshot binding may be re-invited by SMS."""
    if request is None:
        return False
    subject = request.get("subject_snapshot") or {}
    return (
        request.get("document_type") == signature_repo.DOC_TYPE_SOPD
        and request.get("status") == signature_repo.STATUS_PENDING
        and request.get("application_id") == application_id
        and request.get("invited_by_user_id") == owner_user_id
        and request.get("user_id") == signer_user_id
        and subject.get("signer_key") == signer_key
        and subject.get("sopd_flow") == _SOPD_FLOW_ELECTRONIC
    )


async def _send_invite_sms(phone: str, short_url: str) -> bool:
    text = (
        "CarCraft: вас приглашают подписать согласие на обработку "
        f"персональных данных. Откройте ссылку: {short_url}"
    )
    # Never pass the SMS body to logging: it contains a one-shot bearer URL.
    logger.info("SOPD invite SMS dispatch")
    try:
        await sms_service.send_text_sms(phone, text)
    except Exception:
        logger.warning("Invite SMS dispatch failed")
        return False
    return True


def _normalise_phone(raw: str) -> str:
    trimmed = (raw or "").strip().replace(" ", "").replace("-", "")
    if trimmed.startswith("8") and len(trimmed) == 11:
        trimmed = "+7" + trimmed[1:]
    elif trimmed.startswith("7") and len(trimmed) == 11:
        trimmed = "+" + trimmed
    if not _PHONE_RE.match(trimmed):
        raise ServiceError(
            "Некорректный номер телефона (ожидается +7XXXXXXXXXX)",
            400,
        )
    return trimmed
