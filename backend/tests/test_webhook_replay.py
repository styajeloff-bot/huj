"""Tests for webhook replay protection.

Covers the replay-protection layer applied to ModulBank webhooks:
  - first-sight webhook processes normally (payment updated)
  - identical replay is rejected (no re-processing) but still 200
  - disabling the feature via settings lets replays through
  - Redis errors fail closed by default; fail-open flag inverts that
"""
from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.cache import webhook_replay
from infrastructure.models.payments import Payment
from infrastructure.models.payments import (
    PurchaseOrder as PurchaseOrderModel,
)
from infrastructure.models.users import User
from infrastructure.settings import settings
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pending_card_payment(
    db_session: AsyncSession, client_user: User, test_vehicle: Vehicle
) -> dict[str, Any]:
    """Pending card payment tied to a gateway transaction id."""
    order = PurchaseOrderModel(
        user_id=client_user.id,
        vehicle_id=test_vehicle.id,
        purchase_type="full_purchase",
        status="reserved",
        total_price=Decimal("2000000.00"),
        paid_amount=Decimal("0"),
        remaining_amount=Decimal("2000000.00"),
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    payment = Payment(
        purchase_order_id=order.id,
        user_id=client_user.id,
        payment_type="full_purchase",
        amount=Decimal("2000000.00"),
        status="pending_payment",
        payment_method="card",
        gateway_transaction_id=f"CARCRAFT-REPLAY-{order.id}",
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    db_session.add(payment)
    await db_session.flush()
    await db_session.refresh(payment)

    return {"order": order, "payment": payment}


@pytest.fixture
def _replay_enabled() -> Generator[None, None, None]:
    """Force replay protection on (the default) and restore after."""
    prev = settings.webhook_replay_enabled
    settings.webhook_replay_enabled = True
    try:
        yield
    finally:
        settings.webhook_replay_enabled = prev


@pytest.fixture
def _replay_disabled() -> Generator[None, None, None]:
    prev = settings.webhook_replay_enabled
    settings.webhook_replay_enabled = False
    try:
        yield
    finally:
        settings.webhook_replay_enabled = prev


@pytest.fixture
def _replay_fail_open() -> Generator[None, None, None]:
    prev = settings.webhook_replay_fail_open
    settings.webhook_replay_fail_open = True
    try:
        yield
    finally:
        settings.webhook_replay_fail_open = prev


async def test_webhook_first_sight_is_processed(
    client: AsyncClient,
    db_session: AsyncSession,
    pending_card_payment: dict,
    _replay_enabled: None,
) -> None:
    """First-time webhook with valid signature completes the payment."""
    payment = pending_card_payment["payment"]
    txn = payment.gateway_transaction_id

    with (
        patch(
            "infrastructure.services.payment_gateway.verify_modulbank_signature",
            return_value=True,
        ),
        patch(
            "presentation.routers.payments.payment_gateway.start_fiscalization_task",
        ),
    ):
        resp = await client.post(
            "/api/v1/payments/webhook/modulbank",
            json={
                "order_id": txn,
                "status": "success",
                "signature": "first-sight-sig",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    await db_session.refresh(payment)
    assert payment.status == "completed"


async def test_replayed_webhook_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    pending_card_payment: dict,
    _replay_enabled: None,
) -> None:
    """Replaying the same webhook leaves the payment untouched."""
    payment = pending_card_payment["payment"]
    txn = payment.gateway_transaction_id

    body = {
        "order_id": txn,
        "status": "success",
        "signature": "replay-sig-aaaa",
    }

    with (
        patch(
            "infrastructure.services.payment_gateway.verify_modulbank_signature",
            return_value=True,
        ),
        patch(
            "presentation.routers.payments.payment_gateway.start_fiscalization_task",
        ) as start_fiscalization_task,
    ):
        first = await client.post("/api/v1/payments/webhook/modulbank", json=body)
        assert first.status_code == 200
        assert first.json()["ok"] is True

        await db_session.refresh(payment)
        assert payment.status == "completed"
        assert start_fiscalization_task.call_count == 1

        # Flip the payment back to pending so we can detect any
        # re-processing: if the replay is NOT blocked the handler would
        # flip it to completed again.
        payment.status = "pending_payment"
        await db_session.flush()

        second = await client.post("/api/v1/payments/webhook/modulbank", json=body)

    assert second.status_code == 200
    # replay handler returns 200 with ok=true (the wrapper) + processed=false
    data = second.json()
    assert data["ok"] is True
    assert data.get("processed") is False
    assert data.get("replay") is True

    await db_session.refresh(payment)
    # Payment was NOT re-processed.
    assert payment.status == "pending_payment"
    assert start_fiscalization_task.call_count == 1


async def test_replay_protection_disabled_allows_duplicates(
    client: AsyncClient,
    db_session: AsyncSession,
    pending_card_payment: dict,
    _replay_disabled: None,
) -> None:
    """With the feature flag off, the same webhook is reprocessed."""
    payment = pending_card_payment["payment"]
    txn = payment.gateway_transaction_id

    body = {
        "order_id": txn,
        "status": "success",
        "signature": "feature-off-sig",
    }

    with (
        patch(
            "infrastructure.services.payment_gateway.verify_modulbank_signature",
            return_value=True,
        ),
        patch(
            "presentation.routers.payments.payment_gateway.start_fiscalization_task",
        ),
    ):
        first = await client.post("/api/v1/payments/webhook/modulbank", json=body)
        assert first.status_code == 200
        assert first.json()["ok"] is True

        await db_session.refresh(payment)
        assert payment.status == "completed"

        # The second call does not get rejected as replay — but it hits
        # the already-completed branch, so the handler returns
        # already_completed=True (not replay=True). The key signal: we
        # never pass through the replay-rejection branch.
        second = await client.post("/api/v1/payments/webhook/modulbank", json=body)

    assert second.status_code == 200
    data = second.json()
    assert data["ok"] is True
    assert data.get("replay") is None
    # Confirms the already-completed path — i.e. we got past the replay
    # check rather than being short-circuited by it.
    assert data.get("already_completed") is True


async def test_seen_before_fails_closed_on_redis_error() -> None:
    """When Redis raises, default behavior treats the nonce as replayed."""
    prev_fail_open = settings.webhook_replay_fail_open
    settings.webhook_replay_fail_open = False
    try:

        class _BrokenRedis:
            async def set(self, *args: Any, **kwargs: Any) -> None:
                raise RedisError("boom")

        with patch(
            "infrastructure.cache.webhook_replay.get_redis",
            return_value=_BrokenRedis(),
        ):
            result = await webhook_replay.seen_before("nonce-for-fail-closed")
        assert result is True
    finally:
        settings.webhook_replay_fail_open = prev_fail_open


async def test_seen_before_fails_open_when_flag_set(
    _replay_fail_open: None,
) -> None:
    """With fail-open flag on, Redis errors let the webhook through."""

    class _BrokenRedis:
        async def set(self, *args: Any, **kwargs: Any) -> None:
            raise RedisError("boom")

    with patch(
        "infrastructure.cache.webhook_replay.get_redis",
        return_value=_BrokenRedis(),
    ):
        result = await webhook_replay.seen_before("nonce-for-fail-open")
    assert result is False


async def test_seen_before_roundtrip_against_fakeredis() -> None:
    """First call is not-seen, second call is replay."""
    nonce = "txn-abc:sig-xyz"
    assert await webhook_replay.seen_before(nonce) is False
    assert await webhook_replay.seen_before(nonce) is True
