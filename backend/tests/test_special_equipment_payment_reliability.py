"""Reliability and authentication checks for special-equipment payments."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from infrastructure.logging import RedactSensitiveQueryFilter
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentPaymentCallbackInbox,
)
from infrastructure.repositories import (
    special_equipment_commerce_repository as repository,
)
from infrastructure.services import payment_gateway
from infrastructure.services import special_equipment_payment_callbacks as callbacks
from infrastructure.services.payment_models import ModulbankWebhookPayload


@pytest.mark.asyncio
async def test_verified_inbox_redacts_signature_and_deduplicates_semantics(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction_id = f"CARCRAFT-SE-{uuid4()}"

    async def no_payment(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        callbacks.payment_gateway,
        "verify_modulbank_signature",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        callbacks.repository,
        "get_payment_by_gateway_transaction",
        no_payment,
    )
    first, created = await callbacks.persist_verified_callback(
        ModulbankWebhookPayload(
            order_id=transaction_id,
            status="success",
            signature="secret-signature-one",
            amount="100.00",
            currency="RUB",
            customer_email="must-not-be-stored@example.test",
        ),
        db_session,
    )
    replay, replay_created = await callbacks.persist_verified_callback(
        ModulbankWebhookPayload(
            order_id=transaction_id,
            status="success",
            signature="secret-signature-two",
            amount="100.00",
            currency="RUB",
            customer_email="different@example.test",
        ),
        db_session,
    )

    assert created is True
    assert replay_created is False
    assert replay["id"] == first["id"]
    assert first["signature_digest"] == hashlib.sha256(
        b"secret-signature-one"
    ).hexdigest()
    assert "signature" not in first["payload"]
    assert "customer_email" not in first["payload"]


@pytest.mark.asyncio
async def test_callback_failure_is_retryable_then_processes_once(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inbox, _ = await repository.put_payment_callback_inbox(
        db_session,
        event_key=hashlib.sha256(str(uuid4()).encode()).hexdigest(),
        gateway_transaction_id=f"CARCRAFT-SE-{uuid4()}",
        payment_id=None,
        signature_digest="a" * 64,
        payload={"status": "success", "amount": "100.00", "currency": "RUB"},
    )
    first_claim = (
        await callbacks.claim_callbacks(
            db_session,
            inbox_id=inbox["id"],
            limit=1,
        )
    )[0]

    async def fail_once(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("transient")

    monkeypatch.setattr(
        callbacks.payment_gateway,
        "_handle_special_equipment_payment_callback",
        fail_once,
    )
    with pytest.raises(RuntimeError, match="transient"):
        await callbacks.process_claimed_callback(
            db_session,
            inbox_id=inbox["id"],
            lease_token=first_claim["lease_token"],
        )
    assert await callbacks.mark_callback_retry(
        db_session,
        inbox_id=inbox["id"],
        lease_token=first_claim["lease_token"],
        error=RuntimeError("transient"),
    )
    await repository.update_payment_callback_inbox(
        db_session,
        inbox["id"],
        {"next_retry_at": datetime.now(UTC) - timedelta(seconds=1)},
    )

    second_claim = (
        await callbacks.claim_callbacks(
            db_session,
            inbox_id=inbox["id"],
            limit=1,
        )
    )[0]

    async def succeed(*_args: Any, **_kwargs: Any) -> tuple[dict[str, bool], list[Any]]:
        return {"processed": True}, []

    monkeypatch.setattr(
        callbacks.payment_gateway,
        "_handle_special_equipment_payment_callback",
        succeed,
    )
    result, fiscal_ids = await callbacks.process_claimed_callback(
        db_session,
        inbox_id=inbox["id"],
        lease_token=second_claim["lease_token"],
    )
    current = await repository.get_payment_callback_inbox(db_session, inbox["id"])

    assert result == {"processed": True}
    assert fiscal_ids == []
    assert current is not None
    assert current["status"] == "processed"
    assert current["attempt_count"] == 2


@pytest.mark.asyncio
async def test_concurrent_duplicate_callback_creates_one_inbox_row(
    _engine: AsyncEngine,
) -> None:
    event_key = hashlib.sha256(str(uuid4()).encode()).hexdigest()

    async def deliver() -> tuple[Any, bool]:
        async with AsyncSession(_engine, expire_on_commit=False) as session:
            row, created = await repository.put_payment_callback_inbox(
                session,
                event_key=event_key,
                gateway_transaction_id=f"CARCRAFT-SE-{uuid4()}",
                payment_id=None,
                signature_digest="b" * 64,
                payload={"status": "success"},
            )
            await session.commit()
            return row["id"], created

    first, second = await asyncio.gather(deliver(), deliver())
    async with AsyncSession(_engine) as session:
        count = await session.scalar(
            sa.select(sa.func.count(SpecialEquipmentPaymentCallbackInbox.id)).where(
                SpecialEquipmentPaymentCallbackInbox.event_key == event_key
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentPaymentCallbackInbox).where(
                SpecialEquipmentPaymentCallbackInbox.event_key == event_key
            )
        )
        await session.commit()

    assert first[0] == second[0]
    assert sorted((first[1], second[1])) == [False, True]
    assert count == 1


@pytest.mark.asyncio
async def test_durable_fiscalization_has_no_session_during_provider_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_sessions = 0
    payment_id = uuid4()
    payment = {
        "id": payment_id,
        "purchase_order_id": uuid4(),
        "user_id": uuid4(),
        "payment_type": "full_purchase",
        "payment_method": "card",
        "status": "completed",
        "fiscal_status": "sent",
        "fiscal_receipt_id": f"{payment_id}-special-equipment",
        "receipt_storage_key": None,
    }
    updates: list[dict[str, Any]] = []

    class Session:
        async def __aenter__(self) -> Session:
            nonlocal active_sessions
            active_sessions += 1
            return self

        async def __aexit__(self, *_args: Any) -> None:
            nonlocal active_sessions
            active_sessions -= 1

        async def commit(self) -> None:
            return None

    async def claim(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [dict(payment)]

    async def build(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": payment["fiscal_receipt_id"]}

    async def get_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return dict(payment)

    async def update(
        _session: Any, _payment_id: Any, changes: dict[str, Any]
    ) -> dict[str, Any]:
        updates.append(changes)
        payment.update(changes)
        return dict(payment)

    async def create_receipt(_payload: dict[str, Any]) -> dict[str, Any]:
        assert active_sessions == 0
        await asyncio.sleep(0)
        assert active_sessions == 0
        return {"status": "COMPLETED"}

    monkeypatch.setattr(payment_gateway, "AsyncSessionLocal", Session)
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "claim_fiscalization_payments",
        claim,
    )
    monkeypatch.setattr(
        payment_gateway,
        "_build_special_equipment_fiscalization_payload",
        build,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "get_payment",
        get_payment,
    )
    monkeypatch.setattr(
        payment_gateway.special_equipment_repo,
        "update_payment",
        update,
    )
    monkeypatch.setattr(payment_gateway.modulkassa, "create_receipt", create_receipt)
    monkeypatch.setattr(
        payment_gateway,
        "start_special_equipment_receipt_task",
        lambda *_args: None,
    )

    claimed = await payment_gateway.fiscalize_special_equipment_payments(
        payment_id=payment_id,
        limit=1,
    )

    assert claimed == 1
    assert active_sessions == 0
    assert updates[-1]["fiscal_status"] == "completed"


@pytest.mark.asyncio
async def test_webhooks_keep_http_200_for_malformed_bodies(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(payment_gateway.settings, "cookie_secure", False)
    monkeypatch.setattr(payment_gateway.settings, "modulkassa_callback_token", "")
    monkeypatch.setattr(
        payment_gateway.settings,
        "modulkassa_callback_token_required",
        False,
    )
    modulbank = await client.post(
        "/api/v1/payments/webhook/modulbank",
        content=b"{broken",
        headers={"content-type": "application/json"},
    )
    modulkassa = await client.post(
        "/api/v1/payments/webhook/modulkassa",
        content=b"{broken",
        headers={"content-type": "application/json"},
    )

    assert modulbank.status_code == 200
    assert modulbank.json()["error_code"] == "INVALID_PAYLOAD"
    assert modulkassa.status_code == 200
    assert modulkassa.json()["error_code"] == "INVALID_PAYLOAD"


@pytest.mark.asyncio
async def test_webhook_validation_logs_shape_without_rejected_values(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "rejected-webhook-value-must-never-be-logged"
    monkeypatch.setattr(payment_gateway.settings, "cookie_secure", False)
    monkeypatch.setattr(payment_gateway.settings, "modulkassa_callback_token", "")
    monkeypatch.setattr(
        payment_gateway.settings,
        "modulkassa_callback_token_required",
        False,
    )
    backend_logger = logging.getLogger("carcraft-backend")
    backend_logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="carcraft-backend")
    try:
        modulbank = await client.post(
            "/api/v1/payments/webhook/modulbank",
            json={"signature": {"private": secret}},
        )
        modulkassa = await client.post(
            "/api/v1/payments/webhook/modulkassa",
            json={"id": {"private": secret}},
        )
    finally:
        backend_logger.removeHandler(caplog.handler)

    assert modulbank.status_code == 200
    assert modulbank.json()["error_code"] == "INVALID_PAYLOAD"
    assert modulkassa.status_code == 200
    assert modulkassa.json()["error_code"] == "INVALID_PAYLOAD"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered
    assert "payload validation failed errors=" in rendered
    assert "string_type" in rendered


@pytest.mark.asyncio
async def test_modulkassa_callback_token_accepts_query_or_header_and_never_logs(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "modulkassa-test-secret-never-log"
    monkeypatch.setattr(payment_gateway.settings, "cookie_secure", False)
    monkeypatch.setattr(
        payment_gateway.settings,
        "modulkassa_callback_token",
        secret,
    )
    monkeypatch.setattr(
        payment_gateway.settings,
        "modulkassa_callback_token_required",
        False,
    )
    body = {"id": "unknown-fiscal-id", "status": "COMPLETED"}

    missing = await client.post(
        "/api/v1/payments/webhook/modulkassa",
        json=body,
    )
    query = await client.post(
        f"/api/v1/payments/webhook/modulkassa?token={secret}",
        json=body,
    )
    header = await client.post(
        "/api/v1/payments/webhook/modulkassa",
        json=body,
        headers={"X-Modulkassa-Callback-Token": secret},
    )

    assert missing.json()["error_code"] == "INVALID_AUTH"
    assert query.json()["ok"] is True
    assert header.json()["ok"] is True
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_modulkassa_callback_fails_closed_on_secure_deployment(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(payment_gateway.settings, "cookie_secure", True)
    monkeypatch.setattr(
        payment_gateway.settings,
        "modulkassa_callback_url",
        "https://example.test/api/v1/payments/webhook/modulkassa",
    )
    monkeypatch.setattr(payment_gateway.settings, "modulkassa_callback_token", "")
    monkeypatch.setattr(
        payment_gateway.settings,
        "modulkassa_callback_token_required",
        False,
    )

    response = await client.post(
        "/api/v1/payments/webhook/modulkassa",
        json={"id": "unknown", "status": "COMPLETED"},
    )

    assert response.status_code == 200
    assert response.json()["error_code"] == "INVALID_AUTH"


def test_uvicorn_access_filter_redacts_callback_query_token() -> None:
    secret = "must-never-reach-uvicorn-log"
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1",
            "POST",
            f"/api/v1/payments/webhook/modulkassa?token={secret}",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert RedactSensitiveQueryFilter().filter(record) is True
    rendered = record.getMessage()
    assert secret not in rendered
    assert "token=[REDACTED]" in rendered
