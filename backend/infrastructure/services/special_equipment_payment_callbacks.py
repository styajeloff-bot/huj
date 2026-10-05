"""Durable delivery boundary for special-equipment payment callbacks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    InvalidSignatureError,
    OrderNotFoundError,
    PaymentGatewayError,
    PaymentNotFoundError,
)
from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import (
    special_equipment_commerce_repository as repository,
)
from infrastructure.services import payment_gateway
from infrastructure.services.payment_models import ModulbankWebhookPayload
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_REDACTED_PAYLOAD_FIELDS = (
    "order_id",
    "status",
    "state",
    "result",
    "amount",
    "currency",
    "currency_code",
    "merchant",
    "merchant_id",
)


def is_special_equipment_callback(callback: ModulbankWebhookPayload) -> bool:
    transaction_id = callback.order_id or ""
    return transaction_id.startswith(payment_gateway.SPECIAL_EQUIPMENT_GATEWAY_PREFIX)


def _redacted_payload(callback: ModulbankWebhookPayload) -> dict[str, Any]:
    source = callback.model_dump(exclude_none=True)
    return {
        key: source[key]
        for key in _REDACTED_PAYLOAD_FIELDS
        if key in source
    }


async def persist_verified_callback(
    callback: ModulbankWebhookPayload,
    session: AsyncSession,
) -> tuple[dict[str, Any], bool]:
    """Verify and idempotently persist before any business-state mutation."""

    raw_payload = callback.model_dump(exclude_none=True)
    transaction_id = str(raw_payload.get("order_id") or "")
    if not transaction_id.startswith(
        payment_gateway.SPECIAL_EQUIPMENT_GATEWAY_PREFIX
    ):
        raise PaymentGatewayError("Not a special-equipment callback")
    if not payment_gateway.verify_modulbank_signature(raw_payload):
        raise InvalidSignatureError()

    signature = str(raw_payload.get("signature") or "")
    signature_digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    payload = _redacted_payload(callback)
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    event_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payment = await repository.get_payment_by_gateway_transaction(
        session,
        transaction_id,
    )
    return cast(
        "tuple[dict[str, Any], bool]",
        await repository.put_payment_callback_inbox(
            session,
            event_key=event_key,
            gateway_transaction_id=transaction_id,
            payment_id=payment["id"] if payment else None,
            signature_digest=signature_digest,
            payload=payload,
        ),
    )


async def claim_callbacks(
    session: AsyncSession,
    *,
    inbox_id: UUID | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    return cast(
        "list[dict[str, Any]]",
        await repository.claim_payment_callback_inboxes(
            session,
            now=datetime.now(UTC),
            lease_for=timedelta(
                seconds=max(1, settings.special_equipment_callback_lease_seconds)
            ),
            limit=limit,
            inbox_id=inbox_id,
        ),
    )


async def process_claimed_callback(
    session: AsyncSession,
    *,
    inbox_id: UUID,
    lease_token: UUID,
) -> tuple[dict[str, Any], list[UUID]]:
    """Apply one leased callback and terminalize its inbox row atomically."""

    inbox = await repository.get_payment_callback_inbox_for_processing(
        session,
        inbox_id,
        lease_token,
    )
    if inbox is None:
        return {"processed": False, "queued": True}, []

    try:
        async with session.begin_nested():
            result, fiscalization_ids = (
                await payment_gateway._handle_special_equipment_payment_callback(
                    inbox["gateway_transaction_id"],
                    dict(inbox["payload"]),
                    session,
                )
            )
    except payment_gateway.SpecialEquipmentPaymentManualReviewError as exc:
        await repository.update_payment_callback_inbox(
            session,
            inbox_id,
            {
                "status": "manual_review",
                "manual_review_reason": exc.reason_code,
                "last_error_code": None,
                "lease_token": None,
                "lease_until": None,
                "processed_at": datetime.now(UTC),
            },
        )
        return {
            "processed": False,
            "manual_review": True,
            "reconciliation_id": inbox_id,
        }, []
    except (PaymentNotFoundError, OrderNotFoundError, PaymentGatewayError) as exc:
        logger.warning(
            "Special-equipment callback requires manual review inbox=%s type=%s",
            inbox_id,
            type(exc).__name__,
        )
        await repository.update_payment_callback_inbox(
            session,
            inbox_id,
            {
                "status": "manual_review",
                "manual_review_reason": "BUSINESS_VALIDATION_FAILED",
                "last_error_code": type(exc).__name__[:100],
                "lease_token": None,
                "lease_until": None,
                "processed_at": datetime.now(UTC),
            },
        )
        return {
            "processed": False,
            "manual_review": True,
            "reconciliation_id": inbox_id,
        }, []

    await repository.update_payment_callback_inbox(
        session,
        inbox_id,
        {
            "status": "processed",
            "manual_review_reason": None,
            "last_error_code": None,
            "lease_token": None,
            "lease_until": None,
            "processed_at": datetime.now(UTC),
        },
    )
    return result, fiscalization_ids


async def mark_callback_retry(
    session: AsyncSession,
    *,
    inbox_id: UUID,
    lease_token: UUID,
    error: Exception,
) -> bool:
    """Release a failed lease into a bounded, durable retry state."""

    inbox = await repository.get_payment_callback_inbox_for_processing(
        session,
        inbox_id,
        lease_token,
    )
    if inbox is None:
        return False
    delays = settings.special_equipment_callback_retry_delays_seconds
    retry_index = max(0, int(inbox["attempt_count"]) - 1)
    delay = delays[min(retry_index, len(delays) - 1)] if delays else 60
    await repository.update_payment_callback_inbox(
        session,
        inbox_id,
        {
            "status": "retry",
            "next_retry_at": datetime.now(UTC) + timedelta(seconds=max(1, delay)),
            "last_error_code": type(error).__name__[:100],
            "lease_token": None,
            "lease_until": None,
        },
    )
    return True


async def retry_pending_callbacks(*, limit: int = 25) -> int:
    """Recover committed callbacks after request failure or process restart."""

    async with AsyncSessionLocal() as session:
        claimed = await claim_callbacks(session, limit=limit)
        await session.commit()
    if not claimed:
        return 0

    semaphore = asyncio.Semaphore(4)

    async def run(row: dict[str, Any]) -> None:
        async with semaphore:
            async with AsyncSessionLocal() as session:
                try:
                    _, fiscalization_ids = await process_claimed_callback(
                        session,
                        inbox_id=row["id"],
                        lease_token=row["lease_token"],
                    )
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    await mark_callback_retry(
                        session,
                        inbox_id=row["id"],
                        lease_token=row["lease_token"],
                        error=exc,
                    )
                    await session.commit()
                    logger.error(
                        "Special-equipment callback retry failed inbox=%s type=%s",
                        row["id"],
                        type(exc).__name__,
                    )
                    return
            for payment_id in fiscalization_ids:
                await payment_gateway.fiscalize_special_equipment_payments(
                    payment_id=payment_id,
                    limit=1,
                )

    await asyncio.gather(*(run(row) for row in claimed))
    return len(claimed)
