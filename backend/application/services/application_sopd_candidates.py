"""Application-scoped SOPD people, including manually added beneficiaries."""
from __future__ import annotations

from contextlib import suppress
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.sopd_signer_candidates import (
    build_sopd_signer_candidates,
    normalize_sopd_share,
)
from domain.errors import CompanyLookupUnavailableError, SopdSignerResolutionError
from domain.questionnaire_people import normalize_stored_people
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.repositories import application_repository as app_repo

PERSON_COLLECTIONS = {
    "founder": "founders",
    "beneficiary": "beneficiaries",
    "representative": "other_representatives",
    "director_management_company": "other_representatives",
}


def questionnaire_person_id(
    questionnaire: dict[str, Any], *, role: str, signer_key: str,
) -> UUID | None:
    """Resolve a key's declared contract once; projection uses only the UUID.

    Canonical role:UUID keys identify that card even if another card contains
    the same signer_key. Historical founder INNs and opaque stored keys remain
    supported only when they identify exactly one person in the declared role.
    """
    collection = PERSON_COLLECTIONS.get(role)
    if collection is None:
        raise ServiceError("Роль подписанта не связана с карточкой физического лица", 409)
    people = [person for person in questionnaire.get(collection) or [] if isinstance(person, dict)]
    prefix, separator, suffix = signer_key.partition(":")
    canonical_id = None
    if separator and prefix in {"founder", "beneficiary", "representative"}:
        # Older records used opaque suffixes, for example representative:legacy.
        with suppress(ValueError):
            canonical_id = UUID(suffix)
    if canonical_id is not None:
        if prefix != role:
            raise ServiceError("Роль подписанта не соответствует карточке", 409)
        matches = [person for person in people if UUID(person["id"]) == canonical_id]
    elif role == "founder" and len(signer_key) == 12 and signer_key.isdecimal():
        matches = [person for person in people if person.get("inn") == signer_key]
    else:
        matches = [person for person in people if person.get("signer_key") == signer_key]
    if not matches and role == "director_management_company":
        # Management-company directors may sign SOPD without a questionnaire card.
        # Confirm their passport, but do not fabricate a representative to project it.
        return None
    if len(matches) != 1:
        raise ServiceError("Карточка подписанта отсутствует или определена неоднозначно", 409)
    return UUID(matches[0]["id"])


def _candidate_person_matches(
    questionnaire: dict[str, Any], *, role: str, signer_key: str,
    expected_id: UUID | None = None,
) -> bool:
    try:
        identifier = questionnaire_person_id(questionnaire, role=role, signer_key=signer_key)
    except ServiceError:
        return False
    return identifier is not None and (expected_id is None or identifier == expected_id)


async def application_signer_candidates(
    session: AsyncSession, *, application_id: UUID,
    company: dict[str, Any], provider: CompanyLookupProvider | None = None,
) -> list[dict[str, Any]]:
    questionnaire = normalize_stored_people(
        await app_repo.get_questionnaire(session, application_id) or {}, application_id,
    )
    source = dict(company)
    manual_sources = {"manual", "document_request"}
    sources = questionnaire.get("field_sources") or {}
    for field in ("director_full_name", "director_inn"):
        if questionnaire.get(field) or sources.get(field) in manual_sources:
            source[field] = questionnaire[field]
    if "founders" in questionnaire and questionnaire["founders"] is not None:
        source["founders"] = questionnaire["founders"]
    manual_clear = any(sources.get(field) in manual_sources and not questionnaire.get(field) for field in ("director_full_name", "director_inn"))
    if sources.get("director_full_name") in manual_sources and not questionnaire.get("director_full_name"):
        source["director_inn"] = None
    try:
        candidates = await build_sopd_signer_candidates(source, None if manual_clear else provider)
    except (CompanyLookupUnavailableError, SopdSignerResolutionError):
        # Saved people remain editable during a provider outage.
        candidates = await build_sopd_signer_candidates(source, None) if source.get("director_full_name") and len(str(source.get("director_inn") or "")) != 10 else []
    if not questionnaire.get("founders") and any(key == "founders" or key.startswith("founders.") for key in sources):
        candidates = [candidate for candidate in candidates if candidate["role"] != "founder"]
    candidates = [
        candidate for candidate in candidates
        if candidate["role"] != "founder" or _candidate_person_matches(
            questionnaire, role="founder", signer_key=candidate["key"],
        )
    ]
    for field, role, label in (
        ("beneficiaries", "beneficiary", "Бенефициарный владелец"),
        ("other_representatives", "representative", "Представитель"),
    ):
        for person in questionnaire.get(field) or []:
            if not isinstance(person, dict) or not person.get("id") or not person.get("full_name"):
                continue
            key = str(person.get("signer_key") or f"{role}:{person['id']}")
            if not _candidate_person_matches(
                questionnaire, role=role, signer_key=key, expected_id=UUID(person["id"]),
            ):
                continue
            if any(item["key"] == key for item in candidates):
                continue
            candidates.append({
                "key": key, "role": role, "role_label": label,
                "full_name": person["full_name"], "inn": person.get("inn"),
                "share": normalize_sopd_share(person.get("share_percentage", person.get("share"))), "signing_method": "sms",
                "source": "questionnaire", "sort_order": len(candidates) + 1,
            })
    return candidates
