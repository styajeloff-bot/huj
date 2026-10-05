from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application import document_recognition
from application.queries.signer_sopd_context import (
    build_signer_context,
    passport_recognition_ids_from_snapshot,
)
from application.services.passport_profile_fields import (
    profile_autofill_from_passport_records,
)
from infrastructure.models.users import User
from infrastructure.repositories import (
    client_repository,
    passport_recognition_repository,
)
from infrastructure.services.document_recognition import PassportPage, RecognitionResult

pytestmark = pytest.mark.asyncio


class _SessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def test_passport_batch_autofills_missing_profile_birth_date_and_address(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        phone="+76662150214",
        email="passport-autofill@test.local",
        name="Passport Autofill",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    async def fake_recognize(
        pages: list[PassportPage],
    ) -> Any:
        return type(
            "Batch",
            (),
            {
                "per_page": {
                    pages[0].passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": {
                                        "date_of_birth": {"text": "1994-07-08"},
                                        "sex": {"text": "М"},
                                    },
                                },
                            ],
                        },
                        task_id="main-task",
                    ),
                    pages[1].passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": {
                                        "address": {
                                            "value": "г. Москва, ул. Тестовая, д. 1"
                                        },
                                    },
                                },
                            ],
                        },
                        task_id="registration-task",
                    ),
                }
            },
        )()

    monkeypatch.setattr(
        document_recognition,
        "recognize_passport_batch",
        fake_recognize,
    )

    def session_factory() -> Any:
        return _SessionContext(db_session)

    await document_recognition._run_passport_batch(
        user_id=user.id,
        pages=[
            PassportPage(
                passport_type="ceo_passport_page23",
                file_bytes=b"main-passport",
                filename="main.jpg",
                content_type="image/jpeg",
            ),
            PassportPage(
                passport_type="ceo_passport_registration",
                file_bytes=b"registration-passport",
                filename="registration.jpg",
                content_type="image/jpeg",
            ),
        ],
        session_factory=session_factory,
    )

    profile = await client_repository.get_profile_with_user(db_session, user.id)

    assert profile is not None
    assert str(profile["birth_date"]) == "1994-07-08"
    assert profile["address"] == "г. Москва, ул. Тестовая, д. 1"


async def test_passport_profile_autofill_normalizes_gender_from_main_page() -> None:
    payload = profile_autofill_from_passport_records(
        main={
            "raw_data": {
                "items": [
                    {
                        "fields": {
                            "sex": {"text": "Ж"},
                        },
                    },
                ],
            },
        },
        registration=None,
    )

    assert payload["gender"] == "female"


async def test_passport_profile_autofill_builds_full_name_from_main_page() -> None:
    payload = profile_autofill_from_passport_records(
        main={
            "raw_data": {
                "items": [
                    {
                        "fields": {
                            "surname": {"text": "Иванова"},
                            "first_name": {"text": "Анна"},
                            "other_names": {"text": "Сергеевна"},
                        },
                    },
                ],
            },
        },
        registration=None,
    )

    assert payload["full_name"] == "Иванова Анна Сергеевна"


async def test_passport_recognition_ids_from_snapshot_normalizes_uuid_values() -> None:
    main_id = "3c912f6a-b3c4-4574-936b-a99ed2f983f8"
    registration_id = "7ef58866-92d1-4d34-8764-dfbd05fbcac8"

    ids = passport_recognition_ids_from_snapshot(
        {
            "passport_recognition_ids": {
                "ceo_passport_page23": main_id,
                "ceo_passport_registration": registration_id,
                "unexpected": "6f5dff45-2fed-4db0-b2d3-c6ff70a33225",
            }
        }
    )

    assert str(ids["ceo_passport_page23"]) == main_id
    assert str(ids["ceo_passport_registration"]) == registration_id
    assert "unexpected" not in ids


async def test_signer_sopd_context_prefers_recognized_gender_over_snapshot(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662157801",
        email="sopd-gender@test.local",
        name="SOPD Gender",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await passport_recognition_repository.save(
        db_session,
        user_id=user.id,
        file_hash="sopd-gender-main",
        passport_type="ceo_passport_page23",
        raw_data={
            "items": [
                {
                    "fields": {
                        "gender": {"text": "Мужской"},
                    },
                },
            ],
        },
        mapped_data={},
        confidence_data={},
        recognition_task_id=None,
    )

    context = await build_signer_context(
        db_session,
        user_id=user.id,
        subject_snapshot={"gender": "female"},
    )

    assert context["gender"] == "Мужской"
