from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import httpx
import pytest

from infrastructure.services.mobile_id.client import (
    LocalMobileIdProvider,
    MobileIdProviderUnavailableError,
    get_mobile_id_provider,
)
from infrastructure.services.mobile_id.eqid import EqidMobileIdProvider
from infrastructure.settings import settings


@pytest.mark.asyncio
async def test_eqid_provider_sends_match_request_and_accepts_matching_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/code"):
            return httpx.Response(
                200,
                json={
                    "request_id": "eqid-request-1",
                    "status": "completed",
                    "result": {
                        "matched": True,
                        "birthdate_match": "Y",
                        "family_name_match": "Y",
                        "given_name_match": "Y",
                    },
                },
            )
        return httpx.Response(
            201,
            json={
                "request_id": "eqid-request-1",
                "status": "waiting_for_code",
                "phone_masked": "+7 *** *** *414",
            },
        )

    monkeypatch.setattr(settings, "eqid_token", "unit-test-token")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        provider = EqidMobileIdProvider(http_client=client)
        started = await provider.start(
            user_id=uuid4(),
            phone_number="+7 (918) 684-74-14",
            birthdate=date(1991, 1, 8),
            correlation_id=uuid4(),
            family_name=" Иванов ",
            given_name="Иван",
        )
        result = await provider.submit_sms_code(
            auth_req_id=started.auth_req_id,
            smsotp_endpoint=None,
            code="1234",
            phone_number="+79186847414",
            birthdate=date(1991, 1, 8),
        )
    finally:
        await client.aclose()

    start_payload = json.loads(requests[0].content)
    assert start_payload == {
        "operation": "premiuminfo_match",
        "phone": "79186847414",
        "birth_date": "1991-01-08",
        "family_name": "Иванов",
        "given_name": "Иван",
    }
    assert requests[0].headers["Authorization"] == "Bearer unit-test-token"
    assert json.loads(requests[1].content) == {"code": "1234"}
    assert started.auth_req_id == "eqid-request-1"
    assert result.mobile_id_sub == "eqid-request-1"
    assert result.birthdate_match == "Y"


@pytest.mark.asyncio
async def test_eqid_provider_rejects_any_non_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "eqid_token", "unit-test-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "eqid-request-2",
                "status": "completed",
                    "result": {
                        "matched": False,
                        "birthdate_match": "Y",
                        "family_name_match": "Y",
                        "given_name_match": "Y",
                        "middle_name_match": "N-AV",
                    },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MobileIdProviderUnavailableError) as error_info:
            await EqidMobileIdProvider(http_client=client).submit_sms_code(
                auth_req_id="eqid-request-2",
                smsotp_endpoint=None,
                code="1234",
                phone_number="79186847414",
                birthdate=date(1991, 1, 8),
            )
    finally:
        await client.aclose()

    assert error_info.value.status_code == 422


def test_mobile_id_provider_factory_selects_eqid_and_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mobile_id_enabled", True)
    monkeypatch.setattr(settings, "mobile_id_provider", "eqid")
    assert isinstance(get_mobile_id_provider(), EqidMobileIdProvider)

    monkeypatch.setattr(settings, "mobile_id_provider", "local")
    assert isinstance(get_mobile_id_provider(), LocalMobileIdProvider)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "eqid-request-3", "status": "waiting_for_code"},
        {"request_id": "eqid-request-3", "status": "completed", "result": {}},
    ],
)
async def test_eqid_provider_rejects_pending_or_malformed_code_response(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    secret = "secret-token-that-must-not-leak"
    code = "9876"
    monkeypatch.setattr(settings, "eqid_token", secret)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MobileIdProviderUnavailableError) as error_info:
            await EqidMobileIdProvider(http_client=client).submit_sms_code(
                auth_req_id="eqid-request-3",
                smsotp_endpoint=None,
                code=code,
                phone_number="79186847414",
                birthdate=date(1991, 1, 8),
            )
    finally:
        await client.aclose()

    assert error_info.value.status_code == 502
    assert secret not in str(error_info.value)
    assert code not in str(error_info.value)
