from __future__ import annotations

from datetime import date, datetime
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.signature_requests import SignatureRequest
from infrastructure.models.users import ClientProfile, MagicLink, User
from infrastructure.services.document_recognition import PassportPage, RecognitionResult

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_passport_preview_returns_normalized_gender(
    client: AsyncClient,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_recognize(pages: list[PassportPage]) -> Any:
        return type(
            "Batch",
            (),
            {
                "per_page": {
                    page.passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": (
                                        {
                                            "sex": {"text": "Ж"},
                                            "surname": {"text": "Иванова"},
                                            "first_name": {"text": "Анна"},
                                            "other_names": {"text": "Сергеевна"},
                                        }
                                        if page.passport_type == "ceo_passport_page23"
                                        else {"address": {"text": "г. Казань"}}
                                    )
                                }
                            ]
                        },
                        task_id=f"{page.passport_type}-task",
                    )
                    for page in pages
                }
            },
        )()

    monkeypatch.setattr(
        "presentation.routers.signatures.recognize_passport_batch",
        fake_recognize,
        raising=False,
    )

    response = await client.post(
        "/api/v1/signatures/passport-recognition/preview",
        files={
            "passport_main": ("main.jpg", b"main", "image/jpeg"),
            "passport_registration": ("reg.jpg", b"reg", "image/jpeg"),
        },
        headers=_auth(client_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["gender"] == "female"
    assert body["full_name"] == "Иванова Анна Сергеевна"
    assert body["address"] == "г. Казань"


async def test_passport_preview_requires_both_pages(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.post(
        "/api/v1/signatures/passport-recognition/preview",
        files={"passport_main": ("main.jpg", b"main", "image/jpeg")},
        headers=_auth(client_token),
    )

    assert response.status_code == 422


async def test_invite_signer_persists_gender_in_subject_snapshot(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = Company(name="Gender Snapshot Co", company_type="other")
    db_session.add(company)
    await db_session.flush()

    async def fake_sms(phone: str, short_url: str) -> bool:
        _ = (phone, short_url)
        return True

    monkeypatch.setattr(
        "application.commands.invite_signers._send_invite_sms",
        fake_sms,
    )

    response = await client.post(
        "/api/v1/signatures/invite",
        data={
            "payload": (
                "{"
                f'"company_id":"{company.id}",'
                '"application_id":null,'
                '"signers":[{'
                '"full_name":"Иванова Анна",'
                '"inn":"165903352444",'
                '"phone":"+76664444444",'
                '"gender":"female"'
                "}]"
                "}"
            )
        },
        headers=_auth(client_token),
    )

    assert response.status_code == 200, response.text
    row = (
        await db_session.execute(
            select(SignatureRequest).where(
                SignatureRequest.subject_snapshot["inn"].astext == "165903352444"
            )
        )
    ).scalar_one()
    assert row.subject_snapshot["gender"] == "female"


async def test_update_signature_passport_recognition_persists_ids_in_snapshot(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = Company(name="Passport Update Co", company_type="other")
    db_session.add(company)
    await db_session.flush()

    async def fake_sms(phone: str, short_url: str) -> bool:
        _ = (phone, short_url)
        return True

    async def fake_recognize(pages: list[PassportPage]) -> Any:
        return type(
            "Batch",
            (),
            {
                "per_page": {
                    page.passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": (
                                        {
                                            "surname": {"text": "Петров"},
                                            "first_name": {"text": "Петр"},
                                            "other_names": {"text": "Петрович"},
                                        }
                                        if page.passport_type == "ceo_passport_page23"
                                        else {
                                            "address": {
                                                "text": "г. Москва, ул. Новая, д. 1"
                                            }
                                        }
                                    )
                                }
                            ]
                        },
                        task_id=f"{page.passport_type}-task",
                    )
                    for page in pages
                }
            },
        )()

    monkeypatch.setattr(
        "application.commands.invite_signers._send_invite_sms",
        fake_sms,
    )
    monkeypatch.setattr(
        "application.commands.signature_passport.recognize_passport_batch",
        fake_recognize,
        raising=False,
    )

    invite = await client.post(
        "/api/v1/signatures/invite",
        data={
            "payload": (
                "{"
                f'"company_id":"{company.id}",'
                '"application_id":null,'
                '"signers":[{'
                '"full_name":"Петров Петр Петрович",'
                '"inn":"165903352444",'
                '"phone":"+76664444444",'
                '"gender":"male"'
                "}]"
                "}"
            )
        },
        headers=_auth(client_token),
    )
    assert invite.status_code == 200, invite.text
    request_id = invite.json()["results"][0]["signature_request_ids"][0]

    response = await client.patch(
        f"/api/v1/signatures/{request_id}/passport-recognition",
        files={
            "passport_main": ("main-new.jpg", b"main-new", "image/jpeg"),
            "passport_registration": ("reg-new.jpg", b"reg-new", "image/jpeg"),
        },
        headers=_auth(client_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["signature_request_id"] == request_id
    assert set(body["passport_recognition_ids"]) == {
        "ceo_passport_page23",
        "ceo_passport_registration",
    }

    row = await db_session.get(SignatureRequest, request_id)
    assert row is not None
    assert (
        row.subject_snapshot["passport_recognition_ids"]
        == body["passport_recognition_ids"]
    )


async def test_update_signature_passport_recognition_rejects_full_name_mismatch(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = Company(name="Passport Mismatch Co", company_type="other")
    db_session.add(company)
    await db_session.flush()

    async def fake_sms(phone: str, short_url: str) -> bool:
        _ = (phone, short_url)
        return True

    async def fake_recognize(pages: list[PassportPage]) -> Any:
        return type(
            "Batch",
            (),
            {
                "per_page": {
                    page.passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": (
                                        {
                                            "surname": {"text": "Иванов"},
                                            "first_name": {"text": "Иван"},
                                            "other_names": {"text": "Иванович"},
                                        }
                                        if page.passport_type == "ceo_passport_page23"
                                        else {"address": {"text": "г. Москва"}}
                                    )
                                }
                            ]
                        },
                        task_id=f"{page.passport_type}-task",
                    )
                    for page in pages
                }
            },
        )()

    monkeypatch.setattr(
        "application.commands.invite_signers._send_invite_sms",
        fake_sms,
    )
    monkeypatch.setattr(
        "application.commands.signature_passport.recognize_passport_batch",
        fake_recognize,
        raising=False,
    )

    invite = await client.post(
        "/api/v1/signatures/invite",
        data={
            "payload": (
                "{"
                f'"company_id":"{company.id}",'
                '"application_id":null,'
                '"signers":[{'
                '"full_name":"Петров Петр Петрович",'
                '"inn":"165903352445",'
                '"phone":"+76664444445",'
                '"gender":"male"'
                "}]"
                "}"
            )
        },
        headers=_auth(client_token),
    )
    assert invite.status_code == 200, invite.text
    request_id = invite.json()["results"][0]["signature_request_ids"][0]

    response = await client.patch(
        f"/api/v1/signatures/{request_id}/passport-recognition",
        files={
            "passport_main": ("main-other.jpg", b"main-other", "image/jpeg"),
            "passport_registration": ("reg-other.jpg", b"reg-other", "image/jpeg"),
        },
        headers=_auth(client_token),
    )

    assert response.status_code == 422, response.text
    assert "ФИО в паспорте не совпадает" in response.json()["detail"]
    row = await db_session.get(SignatureRequest, request_id)
    assert row is not None
    await db_session.refresh(row)
    assert "passport_recognition_ids" not in row.subject_snapshot


async def test_invite_with_passport_rejects_full_name_mismatch_before_sms(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = Company(name="Invite Passport Mismatch Co", company_type="other")
    db_session.add(company)
    await db_session.flush()
    sent_sms: list[str] = []

    async def fake_sms(phone: str, short_url: str) -> bool:
        _ = short_url
        sent_sms.append(phone)
        return True

    async def fake_recognize(pages: list[PassportPage]) -> Any:
        return type(
            "Batch",
            (),
            {
                "per_page": {
                    page.passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": (
                                        {
                                            "surname": {"text": "Сидоров"},
                                            "first_name": {"text": "Сидор"},
                                            "other_names": {"text": "Сидорович"},
                                        }
                                        if page.passport_type == "ceo_passport_page23"
                                        else {"address": {"text": "г. Казань"}}
                                    )
                                }
                            ]
                        },
                        task_id=f"{page.passport_type}-task",
                    )
                    for page in pages
                }
            },
        )()

    monkeypatch.setattr(
        "application.commands.invite_signers._send_invite_sms",
        fake_sms,
    )
    monkeypatch.setattr(
        "application.commands.signature_passport.recognize_passport_batch",
        fake_recognize,
        raising=False,
    )

    response = await client.post(
        "/api/v1/signatures/invite",
        data={
            "payload": (
                "{"
                f'"company_id":"{company.id}",'
                '"application_id":null,'
                '"signers":[{'
                '"full_name":"Петров Петр Петрович",'
                '"inn":"165903352446",'
                '"phone":"+76664444446",'
                '"gender":"male"'
                "}]"
                "}"
            )
        },
        files={
            "passport_main": ("main-other.jpg", b"main-other", "image/jpeg"),
            "passport_registration": ("reg-other.jpg", b"reg-other", "image/jpeg"),
        },
        headers=_auth(client_token),
    )

    assert response.status_code == 422, response.text
    assert "ФИО в паспорте не совпадает" in response.json()["detail"]
    assert sent_sms == []


async def test_invite_with_passport_fills_new_user_profile_and_one_day_link(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = Company(name="Invite Passport Profile Co", company_type="other")
    db_session.add(company)
    await db_session.flush()

    async def fake_sms(phone: str, short_url: str) -> bool:
        _ = (phone, short_url)
        return True

    async def fake_recognize(pages: list[PassportPage]) -> Any:
        return type(
            "Batch",
            (),
            {
                "per_page": {
                    page.passport_type: RecognitionResult(
                        success=True,
                        data={
                            "items": [
                                {
                                    "fields": (
                                        {
                                            "surname": {"text": "Петров"},
                                            "first_name": {"text": "Петр"},
                                            "other_names": {"text": "Петрович"},
                                            "date_of_birth": {"text": "1988-04-15"},
                                            "series_and_number": {
                                                "text": "4512 123456"
                                            },
                                            "issuing_authority": {
                                                "text": "ОВД района Тестовый"
                                            },
                                            "date_of_issue": {"text": "2010-05-20"},
                                            "sex": {"text": "М"},
                                        }
                                        if page.passport_type == "ceo_passport_page23"
                                        else {
                                            "address": {
                                                "text": "г. Москва, ул. Паспортная, д. 1"
                                            }
                                        }
                                    )
                                }
                            ]
                        },
                        task_id=f"{page.passport_type}-task",
                    )
                    for page in pages
                }
            },
        )()

    monkeypatch.setattr(
        "application.commands.invite_signers._send_invite_sms",
        fake_sms,
    )
    monkeypatch.setattr(
        "application.commands.signature_passport.recognize_passport_batch",
        fake_recognize,
        raising=False,
    )

    response = await client.post(
        "/api/v1/signatures/invite",
        data={
            "payload": (
                "{"
                f'"company_id":"{company.id}",'
                '"application_id":null,'
                '"signers":[{'
                '"full_name":"Петров Петр Петрович",'
                '"inn":"165903352447",'
                '"phone":"+76664444447",'
                '"gender":"male"'
                "}]"
                "}"
            )
        },
        files={
            "passport_main": ("main-profile.jpg", b"main-profile", "image/jpeg"),
            "passport_registration": ("reg-profile.jpg", b"reg-profile", "image/jpeg"),
        },
        headers=_auth(client_token),
    )

    assert response.status_code == 200, response.text
    invited = (
        await db_session.execute(select(User).where(User.phone == "+76664444447"))
    ).scalar_one()
    assert invited.name == "Петров Петр Петрович"

    profile = (
        await db_session.execute(
            select(ClientProfile).where(ClientProfile.user_id == invited.id)
        )
    ).scalar_one()
    birth_date = cast("date | None", profile.birth_date)
    assert birth_date and birth_date.isoformat() == "1988-04-15"
    assert profile.address == "г. Москва, ул. Паспортная, д. 1"
    assert profile.passport_series == "4512 123456"
    assert profile.passport_issued_by == "ОВД района Тестовый"
    passport_issued_date = cast("date | None", profile.passport_issued_date)
    assert passport_issued_date and passport_issued_date.isoformat() == "2010-05-20"

    link = (
        await db_session.execute(select(MagicLink).where(MagicLink.user_id == invited.id))
    ).scalar_one()
    expires_at = cast("datetime", link.expires_at)
    created_at = cast("datetime", link.created_at)
    ttl_seconds = (expires_at - created_at).total_seconds()
    assert 86_300 <= ttl_seconds <= 86_500
