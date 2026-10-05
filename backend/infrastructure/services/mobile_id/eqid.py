"""EQID PremiumInfo Match adapter for identity verification."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from domain.services.identity_verification import (
    IdentityVerificationData,
    IdentityVerificationStarted,
)
from infrastructure.services.mobile_id.client import (
    MobileIdProviderUnavailableError,
    _mask_phone,
)
from infrastructure.settings import settings


class EqidMobileIdProvider:
    """Two-step EQID ``premiuminfo_match`` provider."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    def _headers(self) -> dict[str, str]:
        token = settings.eqid_token.strip()
        if not token:
            raise MobileIdProviderUnavailableError(
                "Токен EQID не настроен.", status_code=500
            )
        return {"Authorization": f"Bearer {token}"}

    def _url(self, path: str) -> str:
        base_url = settings.eqid_base_url.strip().rstrip("/")
        if not base_url:
            raise MobileIdProviderUnavailableError(
                "Адрес EQID не настроен.", status_code=500
            )
        return f"{base_url}/{path.lstrip('/')}"

    async def _post(self, path: str, payload: Mapping[str, Any]) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(
                self._url(path), headers=self._headers(), json=dict(payload)
            )
        async with httpx.AsyncClient(
            timeout=settings.eqid_request_timeout_seconds
        ) as client:
            return await client.post(
                self._url(path), headers=self._headers(), json=dict(payload)
            )

    @staticmethod
    def _provider_error(response: httpx.Response) -> MobileIdProviderUnavailableError:
        if response.status_code == 401:
            return MobileIdProviderUnavailableError(
                "Авторизация EQID не настроена.", status_code=503
            )
        if response.status_code == 404:
            return MobileIdProviderUnavailableError(
                "Запрос EQID не найден или истёк. Запустите верификацию заново.",
                status_code=410,
            )
        if response.status_code in {400, 409, 422}:
            return MobileIdProviderUnavailableError(
                "Неверный код подтверждения. Проверьте SMS и попробуйте ещё раз.",
                status_code=422,
            )
        return MobileIdProviderUnavailableError(
            "EQID временно не смог выполнить верификацию. Попробуйте позже.",
            status_code=502,
        )

    async def start(
        self,
        *,
        user_id: UUID,
        phone_number: str,
        birthdate: date | None,
        correlation_id: UUID,
        family_name: str | None = None,
        given_name: str | None = None,
        middle_name: str | None = None,
    ) -> IdentityVerificationStarted:
        _ = (user_id, correlation_id)
        if birthdate is None:
            raise MobileIdProviderUnavailableError(
                "Для верификации через EQID укажите дату рождения.", status_code=422
            )
        if (
            not family_name
            or not family_name.strip()
            or not given_name
            or not given_name.strip()
        ):
            raise MobileIdProviderUnavailableError(
                "Для верификации через EQID укажите фамилию и имя.", status_code=422
            )
        payload: dict[str, Any] = {
            "operation": "premiuminfo_match",
            "phone": "".join(char for char in phone_number if char.isdigit()),
            "birth_date": birthdate.isoformat(),
        }
        for field, value in (
            ("family_name", family_name),
            ("given_name", given_name),
            ("middle_name", middle_name),
        ):
            if value and value.strip():
                payload[field] = value.strip()
        try:
            response = await self._post("api/v1/gateway/requests", payload)
        except httpx.HTTPError as exc:
            raise MobileIdProviderUnavailableError(
                "Не удалось связаться с EQID. Попробуйте позже.", status_code=503
            ) from exc
        if response.status_code >= 400:
            raise self._provider_error(response)
        if response.status_code != 201:
            raise MobileIdProviderUnavailableError(
                "EQID вернул неожиданный ответ при запуске проверки.",
                status_code=502,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise MobileIdProviderUnavailableError(
                "EQID вернул некорректный ответ.", status_code=502
            ) from exc
        request_id = (
            str(body.get("request_id") or "")
            if isinstance(body, Mapping)
            else ""
        )
        if not request_id or body.get("status") != "waiting_for_code":
            raise MobileIdProviderUnavailableError(
                "EQID не подтвердил отправку SMS-кода.", status_code=502
            )
        return IdentityVerificationStarted(
            auth_req_id=request_id,
            phone_masked=str(body.get("phone_masked") or _mask_phone(phone_number)),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.mobile_id_attempt_ttl_seconds),
        )

    async def submit_sms_code(
        self,
        *,
        auth_req_id: str | None,
        smsotp_endpoint: str | None,
        code: str,
        phone_number: str | None,
        birthdate: date | None,
    ) -> IdentityVerificationData:
        _ = smsotp_endpoint
        if not auth_req_id:
            raise MobileIdProviderUnavailableError(
                "Запрос EQID не найден. Запустите верификацию заново.", status_code=410
            )
        try:
            response = await self._post(
                f"api/v1/gateway/requests/{auth_req_id}/code", {"code": code}
            )
        except httpx.HTTPError as exc:
            raise MobileIdProviderUnavailableError(
                "Не удалось связаться с EQID. Попробуйте позже.", status_code=503
            ) from exc
        if response.status_code >= 400:
            raise self._provider_error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise MobileIdProviderUnavailableError(
                "EQID вернул некорректный ответ.", status_code=502
            ) from exc
        if not isinstance(body, Mapping):
            raise MobileIdProviderUnavailableError(
                "EQID вернул неполный результат проверки.", status_code=502
            )
        result = body.get("result")
        if body.get("status") != "completed" or not isinstance(result, Mapping):
            raise MobileIdProviderUnavailableError(
                "EQID вернул неполный результат проверки.", status_code=502
            )
        required_match_fields = (
            "birthdate_match",
            "family_name_match",
            "given_name_match",
        )
        if not isinstance(result.get("matched"), bool) or any(
            field not in result for field in required_match_fields
        ):
            raise MobileIdProviderUnavailableError(
                "EQID вернул неполный результат проверки.", status_code=502
            )
        if result.get("matched") is not True or any(
            result.get(field) != "Y" for field in required_match_fields
        ):
            raise MobileIdProviderUnavailableError(
                "Данные профиля не совпали с данными Mobile ID. "
                "Проверьте ФИО и дату рождения в профиле.",
                status_code=422,
            )
        return IdentityVerificationData(
            mobile_id_sub=str(body.get("request_id") or auth_req_id),
            phone_number=phone_number,
            birthdate=birthdate,
            birthdate_match=str(result.get("birthdate_match") or "Y"),
        )

    async def handle_notification(
        self,
        *,
        id_token: str,
        access_token: str,
        jwks_uri: str | None,
        phone_number: str | None,
        birthdate: date | None,
        family_name: str | None = None,
        given_name: str | None = None,
        middle_name: str | None = None,
    ) -> IdentityVerificationData:
        _ = (id_token, access_token, jwks_uri, phone_number, birthdate)
        _ = (family_name, given_name, middle_name)
        raise MobileIdProviderUnavailableError(
            "EQID не использует webhook Mobile ID.", status_code=404
        )
