"""Update passport recognition data bound to one СОПД signature request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.passport_profile_fields import (
    PASSPORT_MAIN_TYPE,
    PASSPORT_REGISTRATION_TYPE,
    gender_label,
    profile_autofill_from_passport_records,
)
from infrastructure.repositories import (
    passport_recognition_repository as passport_repo,
)
from infrastructure.repositories import (
    signature_request_repository as signature_repo,
)
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


@dataclass(frozen=True)
class UpdateSignaturePassportCommand:
    request_id: UUID
    actor_user_id: UUID
    passport_main: PassportUploadPage
    passport_registration: PassportUploadPage


async def handle_update_signature_passport(
    cmd: UpdateSignaturePassportCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    request = await signature_repo.get_by_id(session, cmd.request_id)
    if request is None:
        raise ServiceError("Документ не найден", 404)
    if request["document_type"] != signature_repo.DOC_TYPE_SOPD:
        raise ServiceError("Паспортные данные можно обновить только для СОПД", 400)
    if request["status"] != signature_repo.STATUS_PENDING:
        raise ServiceError("СОПД уже подписано или отменено", 409)
    if request.get("invited_by_user_id") != cmd.actor_user_id:
        raise ServiceError("Нет доступа к обновлению паспортных данных", 403)

    pages = [
        PassportPage(
            passport_type=PASSPORT_MAIN_TYPE,
            file_bytes=cmd.passport_main.file_bytes,
            filename=cmd.passport_main.filename,
            content_type=cmd.passport_main.content_type,
        ),
        PassportPage(
            passport_type=PASSPORT_REGISTRATION_TYPE,
            file_bytes=cmd.passport_registration.file_bytes,
            filename=cmd.passport_registration.filename,
            content_type=cmd.passport_registration.content_type,
        ),
    ]
    records = await _recognize_or_get_cached(
        session,
        user_id=request["user_id"],
        pages=pages,
    )
    snapshot = dict(request.get("subject_snapshot") or {})
    payload = profile_autofill_from_passport_records(
        main=records.get(PASSPORT_MAIN_TYPE),
        registration=records.get(PASSPORT_REGISTRATION_TYPE),
    )
    _ensure_full_name_matches(
        expected=str(snapshot.get("full_name") or ""),
        recognized=payload.get("full_name"),
    )
    snapshot["passport_recognition_ids"] = {
        passport_type: str(record["id"]) for passport_type, record in records.items()
    }
    updated = await signature_repo.update_subject_snapshot(
        session,
        request_id=cmd.request_id,
        subject_snapshot=snapshot,
        expected_status=signature_repo.STATUS_PENDING,
        expected_document_type=signature_repo.DOC_TYPE_SOPD,
        invited_by_user_id=cmd.actor_user_id,
    )
    if updated is None:
        raise ServiceError("СОПД уже подписано или отменено", 409)

    gender = payload.get("gender")
    return {
        "signature_request_id": cmd.request_id,
        "passport_recognition_ids": snapshot["passport_recognition_ids"],
        "full_name": payload.get("full_name"),
        "gender": gender,
        "gender_label": gender_label(gender) or None,
        "birth_date": payload.get("birth_date"),
        "address": payload.get("address"),
        "passport_series": payload.get("passport_series"),
        "passport_issued_date": payload.get("passport_issued_date"),
        "passport_issued_by": payload.get("passport_issued_by"),
    }


def _ensure_full_name_matches(*, expected: str, recognized: Any) -> None:
    expected_words = _normalize_name_words(expected)
    recognized_words = _normalize_name_words(str(recognized or ""))
    if not expected_words:
        raise ServiceError("Не указано ФИО подписанта для проверки паспорта", 422)
    if not recognized_words:
        raise ServiceError(
            "Не удалось распознать ФИО в паспорте. Переснимите паспорт.",
            422,
        )
    if expected_words != recognized_words:
        raise ServiceError(
            (
                "ФИО в паспорте не совпадает с подписантом. "
                "Загрузите паспорт этого подписанта заново."
            ),
            422,
        )


def _normalize_name_words(value: str) -> set[str]:
    normalized = re.sub(r"[^\w\s]+", " ", value.lower().replace("ё", "е"))
    return {part for part in normalized.split() if part}


async def _recognize_or_get_cached(
    session: AsyncSession,
    *,
    user_id: UUID,
    pages: list[PassportPage],
) -> dict[str, dict[str, Any]]:
    hashes = {
        page.passport_type: calculate_file_hash(page.file_bytes) for page in pages
    }
    records: dict[str, dict[str, Any]] = {}
    to_recognize: list[PassportPage] = []
    for page in pages:
        cached = await passport_repo.get_cached(
            session,
            user_id=user_id,
            file_hash=hashes[page.passport_type],
            passport_type=page.passport_type,
        )
        if cached is None:
            to_recognize.append(page)
        else:
            records[page.passport_type] = cached

    if to_recognize:
        batch = await recognize_passport_batch(to_recognize)
        for page in to_recognize:
            result = batch.per_page.get(page.passport_type)
            if result is None or not result.success or result.data is None:
                raise ServiceError("Не удалось распознать паспортные данные", 422)
            recognition_id = await passport_repo.save(
                session,
                user_id=user_id,
                file_hash=hashes[page.passport_type],
                passport_type=page.passport_type,
                raw_data=result.data,
                mapped_data={"raw": result.data},
                confidence_data={},
                recognition_task_id=result.task_id,
                document_id=None,
            )
            records[page.passport_type] = {
                "id": recognition_id,
                "user_id": user_id,
                "document_id": None,
                "file_hash": hashes[page.passport_type],
                "passport_type": page.passport_type,
                "raw_data": result.data,
                "mapped_data": {"raw": result.data},
                "confidence_data": {},
                "recognition_task_id": result.task_id,
            }

    return records
