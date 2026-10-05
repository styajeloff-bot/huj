"""Build the Jinja context for a signer's СОПД render.

The Jinja placeholders in ``sopd.md`` expect structured passport
fields (series+number, issuing authority, department code, dates of
issue/birth, place of birth, registration address). The primary source
is passport recognition on the two passport pages uploaded by the signer —
stored in ``passport_recognition_data`` under ``(user_id, passport_type)``
with the raw provider payload in ``raw_data``.

Two passport pages contribute:

* ``ceo_passport_page23``        → recognition ``passport_main`` fields
  (surname, first_name, other_names, series_and_number,
  issuing_authority, subdivision_code, date_of_issue, date_of_birth,
  place_of_birth).
* ``ceo_passport_registration``  → recognition ``passport_registration``
  fields (address — FIAS-normalised when available).

Anything unavailable falls through to an empty string (the renderer
fills every known key), which gives us a single blank СОПД for signers
who haven't uploaded passport yet.

``full_name`` is filled from the recognition result when present; else
from the invite-time snapshot — the applicant always types a name when
inviting, so we have at least something.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.sopd_operators import (
    SopdOperatorSnapshotData,
    resolve_sopd_operator_snapshot,
)
from application.services.passport_profile_fields import (
    first_gender,
    gender_label,
)
from infrastructure.repositories import (
    application_repository as application_repo,
)
from infrastructure.repositories import (
    passport_recognition_repository as passport_repo,
)

_PASSPORT_MAIN_TYPE = "ceo_passport_page23"
_PASSPORT_REGISTRATION_TYPE = "ceo_passport_registration"
_PASSPORT_TYPES = {_PASSPORT_MAIN_TYPE, _PASSPORT_REGISTRATION_TYPE}


def _first(fields: Any, *keys: str) -> str:
    """Return the first non-empty string value among ``keys`` in ``fields``.

    The recognition provider's ``raw_data.fields`` schema isn't typed in the OpenAPI spec
    and occasionally wraps values in ``{"text": "..."}`` — handle both
    raw-string and object variants.
    """
    if not isinstance(fields, dict):
        return ""
    for key in keys:
        value = fields.get(key)
        if isinstance(value, dict):
            value = value.get("text") or value.get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _join_name(fields: Any) -> str:
    surname = _first(fields, "surname", "last_name")
    first_name = _first(fields, "first_name", "name")
    patronymic = _first(fields, "other_names", "middle_name", "patronymic")
    parts = [p for p in (surname, first_name, patronymic) if p]
    return " ".join(parts)


async def build_signer_context(
    session: AsyncSession,
    *,
    user_id: UUID,
    subject_snapshot: dict[str, Any] | None,
    application_id: UUID | None = None,
    operator_scope: SopdOperatorSnapshotData | None = None,
) -> dict[str, str]:
    """Resolve the Jinja context for a signer.

    ``subject_snapshot`` comes from ``signature_requests.subject_snapshot``
    and carries ``full_name`` / ``inn`` / ``passport`` typed at invite
    time — used as a fallback when recognition is absent.
    """
    snapshot = subject_snapshot or {}

    recognition_ids = passport_recognition_ids_from_snapshot(snapshot)
    main = await _get_snapshot_passport_record(
        session,
        user_id=user_id,
        passport_type=_PASSPORT_MAIN_TYPE,
        recognition_ids=recognition_ids,
    )
    registration = await _get_snapshot_passport_record(
        session,
        passport_type=_PASSPORT_REGISTRATION_TYPE,
        user_id=user_id,
        recognition_ids=recognition_ids,
    )

    main_fields = _extract_fields(main)
    registration_fields = _extract_fields(registration)
    questionnaire_fields = await _load_questionnaire_subject_fields(
        session,
        application_id=application_id,
        subject_snapshot=snapshot,
    )
    operators = operator_scope
    if operators is None:
        operators = await resolve_sopd_operator_snapshot(
            session, application_id=application_id
        )

    full_name = (
        _join_name(main_fields)
        or _text(questionnaire_fields.get("full_name"))
        or str(snapshot.get("full_name") or "")
    )
    address = _first(
        registration_fields,
        "address",
        "unrestricted_value",
        "address_gar",
    ) or _text(questionnaire_fields.get("address"))
    gender = first_gender(main_fields) or str(snapshot.get("gender") or "")

    return {
        "full_name": full_name,
        "gender": gender_label(gender),
        "birth_date": _first(main_fields, "date_of_birth")
        or _text(questionnaire_fields.get("birth_date")),
        "birth_place": _first(main_fields, "place_of_birth")
        or _text(questionnaire_fields.get("birth_place")),
        "passport_series_number": _first(
            main_fields,
            "series_and_number",
            "series_number",
        )
        or _text(questionnaire_fields.get("passport_series_number"))
        or str(snapshot.get("passport") or ""),
        "passport_issued_by": _first(main_fields, "issuing_authority")
        or _text(questionnaire_fields.get("passport_issued_by")),
        "passport_issued_at": _first(main_fields, "date_of_issue")
        or _text(questionnaire_fields.get("passport_issued_at")),
        "passport_code": _first(main_fields, "subdivision_code")
        or _text(questionnaire_fields.get("passport_code")),
        "address": address,
        "inn": str(snapshot.get("inn") or ""),
        "phone": str(snapshot.get("phone") or ""),
        "email": str(snapshot.get("email") or "")
        or _text(questionnaire_fields.get("email")),
        "postal_address": _text(questionnaire_fields.get("postal_address")) or address,
        "leasing_companies": operators.leasing_companies_text,
        "contractors": operators.contractors_text,
    }


def passport_recognition_ids_from_snapshot(
    subject_snapshot: dict[str, Any] | None,
) -> dict[str, UUID]:
    snapshot = subject_snapshot or {}
    raw = snapshot.get("passport_recognition_ids")
    if not isinstance(raw, dict):
        return {}

    ids: dict[str, UUID] = {}
    for passport_type, value in raw.items():
        if passport_type not in _PASSPORT_TYPES:
            continue
        try:
            ids[passport_type] = UUID(str(value))
        except (TypeError, ValueError):
            continue
    return ids


async def _get_snapshot_passport_record(
    session: AsyncSession,
    *,
    user_id: UUID,
    passport_type: str,
    recognition_ids: dict[str, UUID],
) -> dict[str, Any] | None:
    recognition_id = recognition_ids.get(passport_type)
    if recognition_id is not None:
        record = await passport_repo.get_by_id_for_user(
            session,
            recognition_id=recognition_id,
            user_id=user_id,
            passport_type=passport_type,
        )
        if record is not None:
            return cast("dict[str, Any]", record)
    latest = await passport_repo.get_latest_for_user(
        session,
        user_id=user_id,
        passport_type=passport_type,
    )
    return cast("dict[str, Any] | None", latest)


def _extract_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    """Recognition provider stores its response under ``raw_data``; the fields dict
    lives on ``raw_data.items[0].fields`` (one item per recognised doc).
    Returns an empty dict when any layer is missing — callers handle that
    as "no recognition" and fall through to snapshot/empty values.
    """
    if not record:
        return {}
    raw = record.get("raw_data")
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items")
    if not isinstance(items, list) or not items:
        return {}
    first = items[0]
    if not isinstance(first, dict):
        return {}
    fields = first.get("fields")
    return fields if isinstance(fields, dict) else {}


async def _load_questionnaire_subject_fields(
    session: AsyncSession,
    *,
    application_id: UUID | None,
    subject_snapshot: dict[str, Any],
) -> dict[str, str]:
    if application_id is None:
        return {}
    questionnaire = await application_repo.get_questionnaire(session, application_id)
    if not questionnaire:
        return {}
    return _match_questionnaire_subject(questionnaire, subject_snapshot)


def _match_questionnaire_subject(
    questionnaire: dict[str, Any], subject_snapshot: dict[str, Any]
) -> dict[str, str]:
    candidates = [_director_candidate(questionnaire)]
    candidates.extend(_founder_candidates(questionnaire.get("founders")))
    candidates = [
        item for item in candidates if item.get("full_name") or item.get("inn")
    ]
    if not candidates:
        return {}

    snapshot_name = _normalise_name(subject_snapshot.get("full_name"))
    snapshot_inn = _digits(subject_snapshot.get("inn"))

    def score(candidate: dict[str, str]) -> int:
        value = 0
        candidate_inn = _digits(candidate.get("inn"))
        candidate_name = _normalise_name(candidate.get("full_name"))
        if snapshot_inn and candidate_inn and snapshot_inn == candidate_inn:
            value += 4
        if snapshot_name and candidate_name and snapshot_name == candidate_name:
            value += 3
        return value

    best = max(candidates, key=score)
    return best if score(best) > 0 else {}


def _director_candidate(questionnaire: dict[str, Any]) -> dict[str, str]:
    full_name = _text(questionnaire.get("director_full_name")) or _join_parts(
        questionnaire.get("director_surname"),
        questionnaire.get("director_first_name"),
        questionnaire.get("director_patronymic"),
    )
    return {
        "full_name": full_name,
        "birth_date": _text(questionnaire.get("director_birth_date")),
        "birth_place": _text(questionnaire.get("director_birth_place")),
        "passport_series_number": _join_parts(
            questionnaire.get("director_passport_series"),
            questionnaire.get("director_passport_number"),
        ),
        "passport_issued_by": _text(questionnaire.get("director_passport_issued_by")),
        "passport_issued_at": _text(questionnaire.get("director_passport_issue_date")),
        "passport_code": _text(questionnaire.get("director_passport_department_code")),
        "address": _address(
            questionnaire.get("director_registration_address"),
            questionnaire.get("director_registration_house"),
            questionnaire.get("director_registration_apartment"),
        ),
        "postal_address": _text(questionnaire.get("postal_address"))
        or _text(questionnaire.get("director_registration_address"))
        or _text(questionnaire.get("legal_address")),
        "phone": _text(questionnaire.get("director_phone")),
        "email": _text(questionnaire.get("director_email")),
    }


def _founder_candidates(raw_founders: Any) -> list[dict[str, str]]:
    if not isinstance(raw_founders, list):
        return []
    return [_founder_candidate(item) for item in raw_founders if isinstance(item, dict)]


def _founder_candidate(founder: dict[str, Any]) -> dict[str, str]:
    full_name = _text(founder.get("name")) or _join_parts(
        founder.get("surname"),
        founder.get("first_name"),
        founder.get("patronymic"),
    )
    return {
        "full_name": full_name,
        "inn": _text(founder.get("inn")),
        "birth_date": _text(founder.get("birth_date")),
        "birth_place": _text(founder.get("birth_place")),
        "passport_series_number": _join_parts(
            founder.get("passport_series"),
            founder.get("passport_number"),
        )
        or _text(founder.get("passport")),
        "passport_issued_by": _text(founder.get("passport_issued_by")),
        "passport_issued_at": _text(founder.get("passport_issue_date")),
        "passport_code": _text(founder.get("passport_department_code")),
        "address": _address(
            founder.get("registration_address"),
            founder.get("registration_house"),
            founder.get("registration_apartment"),
        ),
        "postal_address": _text(founder.get("registration_address")),
        "phone": _text(founder.get("phone")),
        "email": _text(founder.get("email")),
    }


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value).strip()


def _join_parts(*values: Any) -> str:
    return " ".join(part for value in values if (part := _text(value)))


def _address(*values: Any) -> str:
    return ", ".join(part for value in values if (part := _text(value)))


def _normalise_name(value: Any) -> str:
    return " ".join(_text(value).replace("ё", "е").lower().split())


def _digits(value: Any) -> str:
    return "".join(ch for ch in _text(value) if ch.isdigit())
