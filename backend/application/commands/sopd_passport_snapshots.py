"""Use cases for SOPD passport snapshot state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.queries.applications.get_application import (
    ApplicationAccessQuery,
    get_authorized_application,
)
from application.services.application_sopd_candidates import (
    PERSON_COLLECTIONS,
    application_signer_candidates,
    questionnaire_person_id,
)
from application.services.passport_profile_fields import (
    PASSPORT_MAIN_TYPE,
    PASSPORT_REGISTRATION_TYPE,
    extract_fields,
    first_text,
)
from application.services.questionnaire_passport_projection import (
    project_confirmed_passport,
)
from application.services.sopd_passport import (
    FIELDS,
    PassportValidationError,
    map_dbrain,
)
from domain.questionnaire_people import normalize_stored_people
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import company_repository as company_repo
from infrastructure.repositories import (
    passport_recognition_repository as recognition_repo,
)
from infrastructure.repositories import signature_request_repository as signature_repo
from infrastructure.repositories import sopd_passport_snapshot_repository as repo
from infrastructure.services.document_recognition import (
    PassportPage,
    calculate_file_hash,
    recognize_passport_batch,
)


@dataclass(frozen=True)
class PassportUploadPage:
    file_bytes: bytes
    filename: str
    content_type: str


def response(snapshot: dict[str, Any]) -> dict[str, Any]:
    fields = snapshot["draft_fields"] if snapshot["has_unsaved_changes"] else (snapshot["confirmed_fields"] or snapshot["draft_fields"])
    edited = set(snapshot.get("edited_fields") or [])
    confidence = {key: value for key, value in snapshot["recognition_confidence"].items() if key not in edited and key in FIELDS}
    original_name = " ".join(str(snapshot["recognition_fields"].get(key) or "").strip() for key in ("surname", "name", "patronymic"))
    expected_name = snapshot["recognition_fields"].get("_expected_full_name")
    name_mismatch = bool(expected_name and " ".join(str(expected_name).casefold().replace("ё", "е").split()) != " ".join(original_name.casefold().replace("ё", "е").split()))
    return {
        "applicationId": snapshot["application_id"], "signerKey": snapshot["signer_key"],
        "signatureRequestId": snapshot["signature_request_id"], "fields": {key: fields.get(key) for key in FIELDS},
        "confidence": confidence or None,
        "showConfidence": bool(confidence),
        "editedFields": sorted(edited),
        "nameMismatch": name_mismatch,
        "passportFiles": snapshot.get("passport_files") or [],
        "hasUnsavedChanges": snapshot["has_unsaved_changes"],
        "actionsAllowed": bool(snapshot["confirmed_fields"]) and not snapshot["has_unsaved_changes"],
    }


async def require_request_snapshot(session: AsyncSession, *, request_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
    request = await signature_repo.get_by_id(session, request_id)
    if request is None:
        raise ServiceError("Документ не найден", 404)
    if request["document_type"] != signature_repo.DOC_TYPE_SOPD or request["invited_by_user_id"] != actor_user_id:
        raise ServiceError("Нет доступа к паспортным данным", 403)
    if request["status"] != signature_repo.STATUS_PENDING:
        raise ServiceError("СОПД недоступно для изменения", 409)
    snapshot = await repo.get_for_request(session, request_id)
    if snapshot is None:
        raise ServiceError("Подтверждённый снимок паспорта отсутствует", 409)
    snapshot["signer_role"] = (request.get("subject_snapshot") or {}).get("role")
    snapshot["expected_full_name"] = (request.get("subject_snapshot") or {}).get("full_name")
    snapshot["passport_files"] = await _passport_files(session, snapshot)
    return snapshot


async def require_application_signer_snapshot(
    session: AsyncSession, *, access: ApplicationAccessQuery, signer_key: str,
    provider: CompanyLookupProvider, allow_bound_request: bool = False,
) -> dict[str, Any] | None:
    """Authorize the application first, then accept only a current opaque key."""
    application, _ = await get_authorized_application(access, session)
    company_id = application.get("company_id")
    company = await company_repo.get_company_by_id(session, company_id) if company_id else None
    candidates = await application_signer_candidates(session, application_id=access.application_id, company=company, provider=provider) if company else []
    if signer_key not in {candidate["key"] for candidate in candidates}:
        raise ServiceError("Подписант СОПД не найден", 404)
    snapshot = await repo.get_for_signer(session, application_id=access.application_id, signer_key=signer_key)
    # A bound snapshot is not exposed by general application passport routes;
    # the paper-PDF route opts in after applying the same owner/access checks.
    if snapshot is not None and (
        snapshot["owner_user_id"] != access.actor_id
        or (snapshot["signature_request_id"] is not None and not allow_bound_request)
    ):
        raise ServiceError("Нет доступа к паспортным данным", 403)
    if snapshot is not None:
        snapshot["signer_role"] = next(candidate["role"] for candidate in candidates if candidate["key"] == signer_key)
        snapshot["passport_files"] = await _passport_files(session, snapshot)
    return snapshot


async def _passport_files(session: AsyncSession, snapshot: dict[str, Any]) -> list[dict[str, str]]:
    from infrastructure.repositories import documents_repository as documents_repo

    return await documents_repo.list_sopd_passport_metadata(
        session,
        application_id=snapshot["application_id"],
        signer_key=snapshot["signer_key"],
    )


async def expected_full_name_for_application_signer(
    session: AsyncSession, *, access: ApplicationAccessQuery, signer_key: str,
    provider: CompanyLookupProvider,
) -> str | None:
    application, _ = await get_authorized_application(access, session)
    company_id = application.get("company_id")
    company = await company_repo.get_company_by_id(session, company_id) if company_id else None
    if company is None:
        return None
    candidates = await application_signer_candidates(
        session, application_id=access.application_id, company=company, provider=provider,
    )
    candidate = next((item for item in candidates if item["key"] == signer_key), None)
    if candidate is None:
        return None
    questionnaire = normalize_stored_people(
        await app_repo.get_questionnaire(session, access.application_id) or {},
        access.application_id,
    )
    role = str(candidate["role"])
    if role == "director_applicant":
        return str(questionnaire.get("director_full_name") or "").strip() or None
    if role in PERSON_COLLECTIONS:
        identifier = questionnaire_person_id(questionnaire, role=role, signer_key=signer_key)
        if identifier is not None:
            person = next(
                (
                    item for item in questionnaire.get(PERSON_COLLECTIONS[role]) or []
                    if isinstance(item, dict) and UUID(item["id"]) == identifier
                ),
                None,
            )
            if person is not None:
                return str(person.get("full_name") or person.get("name") or "").strip() or None
    return str(candidate.get("full_name") or "").strip() or None


async def recognize(
    session: AsyncSession, *, application_id: UUID, signer_key: str, owner_user_id: UUID,
    passport_main: PassportUploadPage, passport_registration: PassportUploadPage,
    snapshot_id: UUID | None = None, expected_full_name: str | None = None,
) -> dict[str, Any]:
    """Write raw cache and the scoped recognition snapshot in one transaction."""
    pages = [
        PassportPage(PASSPORT_MAIN_TYPE, passport_main.file_bytes, passport_main.filename, passport_main.content_type),
        PassportPage(PASSPORT_REGISTRATION_TYPE, passport_registration.file_bytes, passport_registration.filename, passport_registration.content_type),
    ]
    records: dict[str, dict[str, Any]] = {}
    missing: list[PassportPage] = []
    for page in pages:
        cached = await recognition_repo.get_cached(session, user_id=owner_user_id, file_hash=calculate_file_hash(page.file_bytes), passport_type=page.passport_type)
        if cached is None:
            missing.append(page)
        else:
            records[page.passport_type] = cached
    if missing:
        batch = await recognize_passport_batch(missing)
        for page in missing:
            result = batch.per_page.get(page.passport_type)
            if result is None or not result.success or result.data is None:
                raise ServiceError("Не удалось распознать паспортные данные", 422)
            mapped, confidence = map_dbrain(result.data)
            recognition_id = await recognition_repo.save(
                session, user_id=owner_user_id, file_hash=calculate_file_hash(page.file_bytes), passport_type=page.passport_type,
                raw_data=result.data, mapped_data=mapped, confidence_data=confidence, recognition_task_id=result.task_id,
            )
            records[page.passport_type] = {"id": recognition_id, "raw_data": result.data}
    fields, confidence = map_dbrain(records[PASSPORT_MAIN_TYPE]["raw_data"])
    registration = extract_fields(records[PASSPORT_REGISTRATION_TYPE])
    address = first_text(
        registration, "address", "unrestricted_value", "address_gar", "registration_address",
    )
    if address:
        # Technical OCR metadata is projected only after confirmation. It is not
        # part of the passport form or its required fields/confidence contract.
        fields["_registration_address"] = address
    if expected_full_name:
        fields["_expected_full_name"] = expected_full_name
    if snapshot_id is None:
        snapshot = await repo.upsert_recognition(
            session, application_id=application_id, signer_key=signer_key,
            owner_user_id=owner_user_id, fields=fields, confidence=confidence,
        )
    else:
        # Caller has checked request type/status/owner and that this snapshot
        # belongs to that request. Updating by PK preserves the binding.
        snapshot = await repo.update_recognition(
            session, snapshot_id=snapshot_id, fields=fields, confidence=confidence
        )
    if snapshot is None:
        raise ServiceError("Нет доступа к паспортным данным", 403)
    from application.services.sopd_passport_files import attach_passport_images
    await attach_passport_images(session, application_id=application_id, signer_key=signer_key, pages=[
        {"page": "main", "content": passport_main.file_bytes, "content_type": passport_main.content_type, "filename": passport_main.filename},
        {"page": "registration", "content": passport_registration.file_bytes, "content_type": passport_registration.content_type, "filename": passport_registration.filename},
    ])
    snapshot["passport_files"] = await _passport_files(session, snapshot)
    return response(snapshot)


async def begin_manual_snapshot(
    session: AsyncSession, *, application_id: UUID, signer_key: str, owner_user_id: UUID,
    expected_full_name: str | None,
) -> dict[str, Any]:
    fields: dict[str, Any] = dict.fromkeys(FIELDS)
    if expected_full_name:
        fields["_expected_full_name"] = expected_full_name
    snapshot = await repo.upsert_recognition(
        session, application_id=application_id, signer_key=signer_key,
        owner_user_id=owner_user_id, fields=fields, confidence={},
    )
    if snapshot is None:
        raise ServiceError("Нет доступа к паспортным данным", 403)
    from infrastructure.repositories import application_repository as app_repo
    from infrastructure.services.company_lookup import get_company_lookup_provider
    application = await app_repo.get_by_id(session, application_id)
    company = await company_repo.get_company_by_id(session, application["company_id"]) if application and application.get("company_id") else None
    if company:
        candidates = await application_signer_candidates(session, application_id=application_id, company=company, provider=get_company_lookup_provider())
        snapshot["signer_role"] = next((item["role"] for item in candidates if item["key"] == signer_key), None)
    return snapshot


def _validated_payload(fields: dict[str, Any], edited_fields: list[str]) -> dict[str, Any]:
    if set(fields) - set(FIELDS) or set(edited_fields) - set(FIELDS):
        raise ServiceError("Неизвестное поле паспорта", 422)
    if any(value is not None and not isinstance(value, str) for value in fields.values()):
        raise ServiceError("Поля паспорта должны содержать текст", 422)
    if any(isinstance(value, str) and len(value) > 500 for value in fields.values()):
        raise ServiceError("Слишком длинное значение поля паспорта", 422)
    return {key: (str(fields[key]).strip() or None) if fields.get(key) is not None else None for key in FIELDS}


async def save_draft(session: AsyncSession, snapshot: dict[str, Any], fields: dict[str, Any], edited_fields: list[str] | None = None) -> dict[str, Any]:
    mask = edited_fields or []
    values = _validated_payload(fields, mask)
    updated = await repo.save_draft(session, snapshot_id=snapshot["id"], fields=values, edited_fields=mask)
    updated["passport_files"] = snapshot.get("passport_files") or []
    return response(updated)


async def confirm(session: AsyncSession, snapshot: dict[str, Any], fields: dict[str, Any], edited_fields: list[str] | None = None) -> dict[str, Any]:
    mask = edited_fields or []
    values = _validated_payload(fields, mask)
    try:
        from application.services.sopd_passport import validate
        validate(
            values,
            snapshot["recognition_fields"],
            expected_full_name=snapshot.get("expected_full_name"),
        )
    except PassportValidationError as exc:
        raise PassportServiceError(exc) from exc
    confirmed = await repo.confirm(session, snapshot_id=snapshot["id"], fields=values, edited_fields=mask)
    confirmed["signer_role"] = snapshot.get("signer_role")
    confirmed["passport_files"] = snapshot.get("passport_files") or []
    await project_confirmed_passport(session, confirmed)
    return response(confirmed)


class PassportServiceError(ServiceError):
    def __init__(self, error: PassportValidationError):
        super().__init__(error.message, 422)
        self.code, self.fields = error.code, error.fields
