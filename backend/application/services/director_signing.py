"""Dispatch a signing-invitation SMS to the company general director.

Triggered by the upload handler after a *signed-document* slot is filled
(Бух. отчётность, декларации по налогу на прибыль / НДС / УСН). One slot
= one ``(application × document_type × period_label)`` triple; we never
send a second SMS for the same slot, even after re-upload.

Flow:
    1. Resolve the director's phone — preferred source is
       ``application_questionnaires.director_phone``; if empty we fall
       back to a previously-invited signer whose snapshot matches the
       questionnaire's ``director_full_name``.
    2. Find-or-create a ``users`` row for that phone.
    3. Issue a one-shot magic link (reusing the SOPD-signing flow).
    4. Create a ``signature_requests`` row with
       ``document_type = director_doc_<slot_type>``.
    5. Send the SMS via ``send_text_sms``. SMS is best-effort — the
       invitation row is persisted either way so the operator can resend
       from an admin tool later. The upload itself never fails because
       of an SMS issue.

Idempotency: the unique index on
``(application_id, document_type, COALESCE(period_label, ''))`` makes a
double-insert impossible. We check the slot first and short-circuit.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.repositories import (
    company_registration_repository as company_reg_repo,
)
from infrastructure.repositories import (
    director_signing_invitation_repository as invite_repo,
)
from infrastructure.repositories import (
    magic_link_repository as magic_link_repo,
)
from infrastructure.repositories import (
    signature_request_repository as signature_repo,
)
from infrastructure.services import sms as sms_service
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_PHONE_RE = re.compile(r"^\+7\d{10}$")

# Russian display names for SMS text — frontend uses the same labels.
SLOT_LABELS: dict[str, str] = {
    "accounting_report_xml": "Бухгалтерская отчётность",
    "profit_tax_declaration_xml": "Декларация по налогу на прибыль",
    "vat_declaration_xml": "Декларация по НДС",
    "usn_declaration_xml": "Декларация по УСН",
}


def is_director_signed_slot(document_type: str) -> bool:
    """Whether uploads of this type should trigger a director SMS."""
    return document_type in SLOT_LABELS


async def dispatch_director_signing_invitation(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    document_type: str,
    period_label: str | None,
    document_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Best-effort SMS to the director after a slot fill. Returns the
    invitation dict if anything was created (or already existed), else
    ``None`` when the slot is not director-signed or no director phone
    is available.
    """
    if not is_director_signed_slot(document_type):
        return None

    existing = await invite_repo.find_by_slot(
        session,
        application_id=application_id,
        document_type=document_type,
        period_label=period_label,
    )
    if existing is not None:
        # Slot already had an invitation; re-uploads must not re-SMS.
        return cast("dict[str, Any]", existing)

    director = await _resolve_director(session, application_id=application_id)
    if director is None:
        logger.info(
            "director-signing: no director phone found "
            "application_id=%s document_type=%s period=%s — skipping SMS",
            application_id, document_type, period_label,
        )
        return None

    director_phone = director["phone"]
    director_full_name = director.get("full_name") or "Генеральный директор"
    director_inn = director.get("inn")

    user = await _find_or_create_director_user(
        session,
        phone=director_phone,
        full_name=director_full_name,
        company_id=company_id,
    )

    # Drop any stale unused magic links for this user so only the freshly
    # issued one is live in their SMS history.
    await magic_link_repo.delete_unused_for_user(
        session, user_id=user["id"]
    )
    link = await magic_link_repo.create(
        session,
        user_id=user["id"],
        ttl_seconds=settings.magic_link_ttl_days * 86400,
    )
    short_url = (
        f"{settings.public_url.rstrip('/')}"
        f"{settings.magic_link_path_prefix}/{link['token']}"
    )

    slot_label = SLOT_LABELS.get(document_type, document_type)
    snapshot: dict[str, Any] = {
        "full_name": director_full_name,
        "inn": director_inn,
        "document_label": slot_label,
        "period_label": period_label,
        "application_id": str(application_id),
    }
    sopd = await signature_repo.create(
        session,
        user_id=user["id"],
        application_id=application_id,
        document_type=f"director_doc_{document_type}",
        subject_snapshot=snapshot,
        invited_by_user_id=actor_user_id,
    )

    invitation = await invite_repo.create(
        session,
        application_id=application_id,
        document_type=document_type,
        period_label=period_label,
        document_id=document_id,
        signature_request_id=sopd["id"],
        director_user_id=user["id"],
        director_phone=director_phone,
    )

    sms_text = _format_sms(slot_label, period_label, short_url)
    sent = await _send_sms(director_phone, sms_text)
    if sent:
        await invite_repo.mark_sms_sent(session, invitation_id=invitation["id"])
        invitation["sms_sent_at"] = "marked"  # caller doesn't rely on the value
    else:
        await invite_repo.mark_sms_failed(
            session,
            invitation_id=invitation["id"],
            error="SMS gateway error or invalid phone",
        )

    logger.info(
        "director-signing: dispatched application_id=%s slot=%s/%s phone=%s sms=%s",
        application_id, document_type, period_label, director_phone, sent,
    )
    return cast("dict[str, Any]", invitation)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_director(
    session: AsyncSession, *, application_id: uuid.UUID
) -> dict[str, Any] | None:
    """Return ``{phone, full_name, inn}`` for the application's director.

    Primary source is ``application_questionnaires.director_phone``. If
    empty, falls back to the most recent СОПД signer whose snapshot
    full-name matches the questionnaire's director (or the first signer
    when no name is recorded).
    """
    questionnaire = await app_repo.get_questionnaire(session, application_id)
    full_name = (
        questionnaire.get("director_full_name") if questionnaire else None
    )
    raw_phone = questionnaire.get("director_phone") if questionnaire else None
    questionnaire_phone = _normalise_phone(str(raw_phone)) if raw_phone else None
    if questionnaire_phone is not None:
        return {
            "phone": questionnaire_phone,
            "full_name": full_name,
            "inn": None,
        }

    signers = await signature_repo.list_signers_with_phone_for_application(
        session, application_id
    )
    for signer in signers:
        phone = signer.get("phone")
        snapshot = signer.get("snapshot") or {}
        if not phone:
            continue
        snapshot_name = (
            snapshot.get("full_name") if isinstance(snapshot, dict) else None
        )
        if full_name and snapshot_name and snapshot_name.strip() != full_name.strip():
            continue
        normalised = _normalise_phone(str(phone))
        if normalised is None:
            continue
        return {
            "phone": normalised,
            "full_name": full_name or snapshot_name,
            "inn": snapshot.get("inn") if isinstance(snapshot, dict) else None,
        }
    return None


async def _find_or_create_director_user(
    session: AsyncSession,
    *,
    phone: str,
    full_name: str,
    company_id: uuid.UUID,
) -> dict[str, Any]:
    existing = await auth_repo.find_user_by_phone(session, phone)
    if existing is not None:
        await company_reg_repo.ensure_user_company_link(
            session, user_id=existing["id"], company_id=company_id
        )
        return dict(existing)
    user = await auth_repo.create_user(
        session,
        phone=phone,
        email=None,
        name=full_name,
        password_hash="",
        company_id=None,
        phone_verified=False,
    )
    await auth_repo.set_user_active(session, user["id"], False)
    await company_reg_repo.ensure_user_company_link(
        session, user_id=user["id"], company_id=company_id
    )
    return dict(user)


def _format_sms(slot_label: str, period_label: str | None, short_url: str) -> str:
    suffix = f" за {period_label}" if period_label else ""
    return (
        f"CarCraft: загружен документ «{slot_label}{suffix}». "
        f"Подпишите его как генеральный директор: {short_url}"
    )


async def _send_sms(phone: str, text: str) -> bool:
    # SMS bodies can contain one-shot bearer links. Log only delivery metadata;
    # the formatter redacts the destination phone as a second line of defence.
    logger.info("director-signing SMS dispatch to %s", phone)
    try:
        await sms_service.send_text_sms(phone, text)
    except Exception as exc:
        logger.warning("director-signing SMS failed for %s: %s", phone, exc)
        return False
    return True


def _normalise_phone(raw: str) -> str | None:
    trimmed = (raw or "").strip().replace(" ", "").replace("-", "")
    trimmed = trimmed.replace("(", "").replace(")", "")
    if trimmed.startswith("8") and len(trimmed) == 11:
        trimmed = "+7" + trimmed[1:]
    elif trimmed.startswith("7") and len(trimmed) == 11:
        trimmed = "+" + trimmed
    if not _PHONE_RE.match(trimmed):
        return None
    return trimmed
