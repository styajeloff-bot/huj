"""Application questionnaire consent text derived from actual signed SOPDs."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as applications
from infrastructure.repositories import signature_request_repository as signatures
from infrastructure.repositories import sopd_operator_snapshot_repository as operators
from infrastructure.repositories import sopd_revoke_repository as revocations
from infrastructure.settings import settings

CONSENT_PREFIXES = {
    "personal_data_processing_consent": "Согласие получено в",
    "legal_entity_credit_report_consent": "Согласие получено в",
    "individual_credit_report_consent": "Согласие получено в",
    "credit_bureau_data_transfer_consent": "Согласие получено в",
    "marketing_communications_consent": "Согласие получено в",
    "information_accuracy_declaration": "Заверение получено в",
    "information_verification_consent": "Согласие получено в",
    "permitted_data_recipients": "Указаны в",
    "telecom_data_transfer_consent": "Согласие получено в",
    "federal_register_inclusion_consent": "Согласие получено в",
    "affiliates_data_transfer_consent": "Согласие получено в",
    "electronic_documents_equivalence_consent": "Признание получено в",
    "automated_marketing_consent": "Согласие получено в",
    "biometric_data_processing_consent": "Согласие получено в",
}
CONSENT_FIELDS = frozenset({
    *CONSENT_PREFIXES, "consent_validity_period", "consent_revocation_procedure",
})
_SIGNED = frozenset({signatures.STATUS_SIGNED_ELECTRONIC, signatures.STATUS_SIGNED_PHYSICAL})


def three_calendar_years(value: date) -> date:
    try:
        return value.replace(year=value.year + 3)
    except ValueError:
        return value.replace(year=value.year + 3, day=28)


async def build_consent_projection(
    session: AsyncSession,
    application_id: UUID,
    leasing_company_id: UUID | None = None,
) -> dict[str, Any]:
    rows = await signatures.list_for_application(session, application_id)
    rows.sort(key=lambda row: row.get("signed_at") or datetime.min.replace(tzinfo=UTC), reverse=True)
    latest: set[str] = set()
    active: list[dict[str, Any]] = []
    validity: list[str] = []
    withdrawal: list[str] = []
    for row in rows:
        if row["status"] not in {*_SIGNED, signatures.STATUS_REVOKED}:
            continue
        subject = row.get("subject_snapshot") or {}
        signer_key = str(subject.get("signer_key") or f"user:{row['user_id']}")
        if signer_key in latest:
            continue
        latest.add(signer_key)
        signed_at = row.get("signed_at")
        if row["status"] not in _SIGNED or row.get("revoked_at") or not isinstance(signed_at, datetime):
            continue
        if leasing_company_id is not None and not await _covers_leasing_company(
            session, row["id"], leasing_company_id
        ):
            continue
        signed_date = signed_at.astimezone(ZoneInfo(settings.notification_business_timezone)).date()
        expires = three_calendar_years(signed_date)
        # No printed SOPD number exists in the current signature contract.
        # The request UUID remains an explicit reference, never a fabricated number.
        reference = f"СОПД от {signed_date:%d.%m.%Y}"
        active.append({
            "signature_request_id": str(row["id"]),
            "signer_key": signer_key,
            "full_name": str(subject.get("full_name") or ""),
            "signed_at": signed_at.isoformat(),
            "expires_at": expires.isoformat(),
            "reference": reference,
        })
        validity.append(f"Срок действия согласий до {expires:%d.%m.%Y}, согласно {reference}")
        withdrawal.append(f"Порядок отзыва согласий указан в тексте {reference}.")
    payload: dict[str, Any] = {
        name: [
            {**item, "text": f"{prefix} {item['reference']}"}
            for item in active
        ]
        for name, prefix in CONSENT_PREFIXES.items()
    }
    payload["consent_validity_period"] = "\n".join(validity) or None
    payload["consent_revocation_procedure"] = "\n".join(withdrawal) or None
    return payload


async def refresh_consent_projection(session: AsyncSession, application_id: UUID | None) -> None:
    if application_id is None:
        return
    await applications.upsert_questionnaire(
        session, application_id=application_id,
        payload=await build_consent_projection(session, application_id), source="sopd",
    )


async def _covers_leasing_company(
    session: AsyncSession, signature_request_id: UUID, leasing_company_id: UUID
) -> bool:
    scope = await operators.get_by_signature_request_id(session, signature_request_id)
    if scope is None or str(leasing_company_id) not in {
        str(item.get("id")) for item in scope["leasing_companies"]
    }:
        return False
    revoked = await revocations.list_revoked_operators(
        session, signature_request_id=signature_request_id
    )
    return not any(
        item["operator_type"] == "leasing_company"
        and item["leasing_company_id"] == leasing_company_id
        for item in revoked
    )
