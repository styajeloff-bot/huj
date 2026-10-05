"""ModulBank payment gateway service."""
import asyncio
import base64
import hashlib
import logging
import math
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from domain.commerce import VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
from domain.entities.payment import PAYMENT_EXPIRY_MINUTES
from domain.errors import (
    InvalidSignatureError,
    OrderNotFoundError,
    PaymentGatewayError,
    PaymentNotFoundError,
    VehicleNotFoundError,
)
from domain.values import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    VehicleStatus,
)
from infrastructure.cache import webhook_replay
from infrastructure.database import AsyncSessionLocal
from infrastructure.messaging import auth_events
from infrastructure.repositories import purchase_repository as repo
from infrastructure.repositories import (
    special_equipment_commerce_repository as special_equipment_repo,
)
from infrastructure.services import modulkassa, special_equipment_receipts
from infrastructure.services.object_storage import get_object_storage
from infrastructure.services.payment_models import (
    ModulbankPaymentRequest,
    ModulbankPaymentResponse,
    ModulbankSbpRequest,
    ModulbankSbpResponse,
    ModulbankWebhookPayload,
    ModulkassaWebhookPayload,
    PaymentStatusDetails,
)
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

SPECIAL_EQUIPMENT_GATEWAY_PREFIX = "CARCRAFT-SE-"


class SpecialEquipmentPaymentManualReviewError(PaymentGatewayError):
    """A verified success that cannot safely mutate the sellable unit."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__("Special-equipment payment requires manual review")


# Strong references to background tasks — without this, the event loop only
# holds a weak reference and the task can be garbage-collected mid-flight.
_background_tasks: set[asyncio.Task[None]] = set()


def _merge_vehicle_gateway_callback(
    existing: Mapping[str, Any] | None,
    callback: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge provider data without trusting its commerce receipt namespace."""

    persisted = dict(existing) if isinstance(existing, Mapping) else {}
    merged = {
        **persisted,
        **{
            key: value
            for key, value in callback.items()
            if key != VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
        },
    }
    if VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE in persisted:
        merged[VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE] = persisted[
            VEHICLE_COMMERCE_IDEMPOTENCY_NAMESPACE
        ]
    return merged


# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _sanitize_client_email(value: Any) -> str:
    """ModulBank requires a valid email ≥6 chars; fall back to default."""
    if isinstance(value, str):
        candidate = value.strip()
        if len(candidate) >= 6 and _EMAIL_RE.match(candidate):
            return candidate
    return settings.modulbank_default_client_email


def _sha1hex(s: str) -> str:
    # ModulBank protocol mandates SHA-1 — not used for cryptographic security.
    # nosemgrep: bandit.B303-2 -- ModulBank requires SHA-1 for this signature protocol.
    return hashlib.sha1(s.encode()).hexdigest()  # noqa: S324


def _generate_signature(params: Mapping[str, Any]) -> str:
    """SHA-1 double hash signature per ModulBank docs.

    Steps (https://sup.modulbank.ru/algorithm_for_calculating_signature_field):
      1. Drop ``signature`` and any empty / ``None`` values.
      2. base64-encode every remaining value (string form, UTF-8).
      3. Sort keys binary-ascending, join as ``key=base64(value)`` with ``&``.
      4. ``SHA1(secret + SHA1(secret + values))``.
    """
    secret = settings.modulbank_secret_key
    if not secret:
        raise PaymentGatewayError("ModulBank secret key not configured")
    data = "&".join(
        f"{k}={base64.b64encode(str(params[k]).encode('utf-8')).decode()}"
        for k in sorted(params)
        if k != "signature"
        and params[k] is not None
        and str(params[k]) != ""
    )
    return _sha1hex(secret + _sha1hex(secret + data))


def _signed_form_params(
    payload: dict[str, Any], model: type[Any]
) -> dict[str, str]:
    """Validate, serialize to a plain string dict, and sign it.

    Returns the *exact* bag of strings that will be POSTed to ModulBank — no
    further Pydantic round-trip. Routes send this dict verbatim as the form
    body (or as JSON in ``formParams``), so the signature computed here always
    matches what the bank receives. Previously a Pydantic model was returned
    and then serialized again via ``jsonable_encoder`` (which keeps ``None``
    as ``null``), while signing used ``exclude_none=True`` — that mismatch is
    the recurring signature bug.
    """
    placeholder = {**payload, "signature": "0" * 40}
    pre = model.model_validate(placeholder)
    dumped = pre.model_dump(exclude_none=True)
    dumped.pop("signature", None)
    signed: dict[str, str] = {k: str(v) for k, v in dumped.items()}
    signed["signature"] = _generate_signature(signed)
    return signed


def verify_modulbank_signature(data: Mapping[str, Any]) -> bool:
    """Verify webhook signature using documented algorithm with legacy fallback."""
    secret = settings.modulbank_secret_key
    if not secret:
        logger.error("ModulBank secret key not configured")
        return False

    received = data.get("signature")
    if not received:
        return False

    params = {k: v for k, v in data.items() if k != "signature"}

    try:
        documented = _generate_signature(params)
        if documented == received:
            return True
    except Exception as exc:
        logger.warning("Documented signature verification failed: %s", exc)

    # Legacy fallback: sorted values concat + single SHA1
    concatenated = "".join(str(params[k]) for k in sorted(params)) + secret
    # nosemgrep: bandit.B303-2 -- ModulBank requires SHA-1 for its legacy signature fallback.
    legacy = hashlib.sha1(concatenated.encode()).hexdigest()  # noqa: S324
    if legacy == received:
        return True

    logger.error("ModulBank webhook signature mismatch", extra={"received": received})
    return False


# ---------------------------------------------------------------------------
# Internal: load user fields needed for payment params
# ---------------------------------------------------------------------------


async def _get_user_info(session: AsyncSession, user_id: UUID) -> Any:
    return await repo.get_user_info(session, user_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_payment(
    payment_id: UUID,
    session: AsyncSession,
) -> ModulbankPaymentResponse:
    """Prepare payment form params for ModulBank payment page redirect."""
    payment = await repo.get_payment_by_id(session, payment_id)
    if not payment:
        raise PaymentNotFoundError()

    order = await repo.get_by_id_with_details(session, payment["purchase_order_id"])
    if not order:
        raise OrderNotFoundError()

    order_id = f"CARCRAFT-{payment_id}"
    expires_at_value = payment.get("expires_at") or (
        datetime.now(UTC) + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)
    )

    vehicle_description = (
        f"{order.get('mark_name') or ''} {order.get('model_name') or ''}".strip()
    )

    callback_url = f"{settings.public_url}/api/v1/payments/webhook/modulbank"
    success_url = f"{settings.public_url}/cabinet?tab=my-cars&payment=success"

    payload_data: dict[str, Any] = {
        "merchant": settings.modulbank_shop_id,
        "amount": payment["amount"],
        "order_id": order_id,
        "description": f"Оплата {vehicle_description}",
        "unix_timestamp": math.floor(time.time()),
        "callback_url": callback_url,
        "callback_on_failure": "1",
        "success_url": success_url,
        "lifetime": PAYMENT_EXPIRY_MINUTES * 60,
        "show_payment_methods": '["card"]',
    }

    user = await _get_user_info(session, payment["user_id"])
    if user.get("phone"):
        payload_data["client_phone"] = user["phone"]
    payload_data["client_email"] = _sanitize_client_email(user.get("email"))
    if user.get("name"):
        payload_data["client_name"] = user["name"]

    params = _signed_form_params(payload_data, ModulbankPaymentRequest)

    return ModulbankPaymentResponse(
        form_url=settings.modulbank_form_url,
        form_params=params,
        order_id=order_id,
        amount=payment["amount"],
        expires_at=expires_at_value.isoformat(),
    )


async def request_sbp_link(
    payment_id: UUID,
    session: AsyncSession,
) -> ModulbankSbpResponse:
    """Request SBP payment link from ModulBank API."""
    payment = await repo.get_payment_by_id(session, payment_id)
    if not payment:
        raise PaymentNotFoundError()

    order = await repo.get_by_id_with_details(session, payment["purchase_order_id"])
    if not order:
        raise OrderNotFoundError()

    order_id = f"CARCRAFT-{payment_id}"
    expires_at_value = payment.get("expires_at") or (
        datetime.now(UTC) + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)
    )

    vehicle_description = (
        f"{order.get('mark_name') or ''} {order.get('model_name') or ''}".strip()
    )
    description = f"Оплата {vehicle_description}"
    callback_url = f"{settings.public_url}/api/v1/payments/webhook/modulbank"

    payload_data: dict[str, Any] = {
        "merchant": settings.modulbank_shop_id,
        "amount": payment["amount"],
        "order_id": order_id,
        "description": description,
        "unix_timestamp": math.floor(time.time()),
        "callback_url": callback_url,
        "callback_on_failure": "1",
        "qr_lifetime": PAYMENT_EXPIRY_MINUTES,
    }

    user = await _get_user_info(session, payment["user_id"])
    if user.get("phone"):
        payload_data["client_phone"] = user["phone"]
    payload_data["client_email"] = _sanitize_client_email(user.get("email"))
    if user.get("name"):
        payload_data["client_name"] = user["name"]

    params = _signed_form_params(payload_data, ModulbankSbpRequest)

    logger.info(
        "Requesting SBP payment link",
        extra={"order_id": order_id, "amount": params["amount"]},
    )

    async with httpx.AsyncClient(
        timeout=settings.modulbank_sbp_request_timeout
    ) as client:
        resp = await client.post(
            settings.modulbank_sbp_api_url,
            content=_encode_form(params),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    response_data = resp.json()
    if response_data.get("status") != "ok" or not response_data.get("sbp_link"):
        logger.error(
            "ModulBank SBP API error http=%s body=%s", resp.status_code, response_data,
        )
        raise PaymentGatewayError(
            response_data.get("message")
            or response_data.get("error")
            or "Не удалось получить ссылку для оплаты через СБП"
        )

    logger.info("SBP payment link received", extra={"order_id": order_id})
    return ModulbankSbpResponse(
        sbp_link=response_data["sbp_link"],
        order_id=order_id,
        amount=payment["amount"],
        description=description,
        expires_at=expires_at_value.isoformat(),
    )


def _special_equipment_description(order: Mapping[str, Any]) -> str:
    snapshot = order.get("item_snapshot") or {}
    name = " ".join(
        str(value).strip()
        for value in (
            snapshot.get("manufacturer"),
            snapshot.get("model"),
            snapshot.get("modification"),
        )
        if value
    )
    return name or "спецтехники"


async def prepare_special_equipment_payment(
    payment_id: UUID,
    session: AsyncSession,
) -> ModulbankPaymentResponse:
    """Build the hosted-card contract for a special-equipment payment."""

    payment = await special_equipment_repo.get_payment(session, payment_id)
    if not payment:
        raise PaymentNotFoundError()
    order = await special_equipment_repo.get_order(
        session, payment["purchase_order_id"]
    )
    if not order:
        raise OrderNotFoundError()
    transaction_id = payment.get("gateway_transaction_id")
    if transaction_id != f"{SPECIAL_EQUIPMENT_GATEWAY_PREFIX}{payment_id}":
        raise PaymentGatewayError("Некорректный идентификатор платежа спецтехники")

    expires_at = payment.get("expires_at") or (
        datetime.now(UTC) + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)
    )
    payload_data: dict[str, Any] = {
        "merchant": settings.modulbank_shop_id,
        "amount": payment["amount"],
        "order_id": transaction_id,
        "description": f"Оплата спецтехники {_special_equipment_description(order)}"[:250],
        "unix_timestamp": math.floor(time.time()),
        "callback_url": f"{settings.public_url}/api/v1/payments/webhook/modulbank",
        "callback_on_failure": "1",
        "success_url": (
            f"{settings.public_url}/special-equipment/orders/{order['id']}"
            "?payment=success"
        ),
        "lifetime": PAYMENT_EXPIRY_MINUTES * 60,
        "show_payment_methods": '["card"]',
    }
    user = await _get_user_info(session, payment["user_id"])
    if user.get("phone"):
        payload_data["client_phone"] = user["phone"]
    payload_data["client_email"] = _sanitize_client_email(user.get("email"))
    if user.get("name"):
        payload_data["client_name"] = user["name"]

    return ModulbankPaymentResponse(
        form_url=settings.modulbank_form_url,
        form_params=_signed_form_params(payload_data, ModulbankPaymentRequest),
        order_id=transaction_id,
        amount=payment["amount"],
        expires_at=expires_at.isoformat(),
    )


async def request_special_equipment_sbp_link(
    payment_id: UUID,
    session: AsyncSession,
) -> ModulbankSbpResponse:
    """Create a ModulBank SBP link for a special-equipment payment."""

    payment = await special_equipment_repo.get_payment(session, payment_id)
    if not payment:
        raise PaymentNotFoundError()
    order = await special_equipment_repo.get_order(
        session, payment["purchase_order_id"]
    )
    if not order:
        raise OrderNotFoundError()
    transaction_id = payment.get("gateway_transaction_id")
    if transaction_id != f"{SPECIAL_EQUIPMENT_GATEWAY_PREFIX}{payment_id}":
        raise PaymentGatewayError("Некорректный идентификатор платежа спецтехники")

    expires_at = payment.get("expires_at") or (
        datetime.now(UTC) + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)
    )
    description = f"Оплата спецтехники {_special_equipment_description(order)}"[:250]
    payload_data: dict[str, Any] = {
        "merchant": settings.modulbank_shop_id,
        "amount": payment["amount"],
        "order_id": transaction_id,
        "description": description,
        "unix_timestamp": math.floor(time.time()),
        "callback_url": f"{settings.public_url}/api/v1/payments/webhook/modulbank",
        "callback_on_failure": "1",
        "qr_lifetime": PAYMENT_EXPIRY_MINUTES,
    }
    user = await _get_user_info(session, payment["user_id"])
    if user.get("phone"):
        payload_data["client_phone"] = user["phone"]
    payload_data["client_email"] = _sanitize_client_email(user.get("email"))
    if user.get("name"):
        payload_data["client_name"] = user["name"]
    params = _signed_form_params(payload_data, ModulbankSbpRequest)

    async with httpx.AsyncClient(
        timeout=settings.modulbank_sbp_request_timeout
    ) as client:
        response = await client.post(
            settings.modulbank_sbp_api_url,
            content=_encode_form(params),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    try:
        response_data = response.json()
    except ValueError as exc:
        logger.error(
            "ModulBank special-equipment SBP returned non-JSON response",
            extra={"http_status": response.status_code},
        )
        raise PaymentGatewayError(
            "Некорректный ответ платёжного шлюза СБП"
        ) from exc
    if not isinstance(response_data, dict):
        raise PaymentGatewayError("Некорректный ответ платёжного шлюза СБП")
    if response_data.get("status") != "ok" or not response_data.get("sbp_link"):
        logger.error(
            "ModulBank special-equipment SBP error",
            extra={
                "http_status": response.status_code,
                "provider_status": response_data.get("status"),
                "provider_error_code": response_data.get("code"),
            },
        )
        raise PaymentGatewayError(
            response_data.get("message")
            or response_data.get("error")
            or "Не удалось получить ссылку для оплаты через СБП"
        )
    return ModulbankSbpResponse(
        sbp_link=response_data["sbp_link"],
        order_id=transaction_id,
        amount=payment["amount"],
        description=description,
        expires_at=expires_at.isoformat(),
    )


async def _lock_vehicle_payment_callback_context(
    transaction_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Lock callback context in the global vehicle/order/payment order."""

    preliminary_payment = await repo.get_payment_by_gateway_id(
        session,
        transaction_id,
    )
    if not preliminary_payment:
        logger.error("ModulBank webhook: payment not found", extra={"order_id": transaction_id})
        raise PaymentNotFoundError()
    vehicle = await repo.get_vehicle_for_update(
        session,
        preliminary_payment["order_vehicle_id"],
    )
    if vehicle is None:
        raise VehicleNotFoundError(preliminary_payment["order_vehicle_id"])
    order = await repo.get_order_for_update(
        session,
        preliminary_payment["purchase_order_id"],
    )
    if order is None:
        raise OrderNotFoundError()
    payment = await repo.get_payment_by_gateway_id_for_update(
        session,
        transaction_id,
    )
    if (
        payment is None
        or payment["id"] != preliminary_payment["id"]
        or payment["purchase_order_id"] != order["id"]
        or payment["order_vehicle_id"] != order["vehicle_id"]
        or order["vehicle_id"] != preliminary_payment["order_vehicle_id"]
    ):
        raise PaymentGatewayError("Webhook payment/order binding mismatch")
    return cast("dict[str, Any]", payment)


async def handle_payment_callback(
    callback_data: ModulbankWebhookPayload,
    session: AsyncSession,
) -> tuple[dict[str, bool], list[UUID]]:
    """Process ModulBank webhook. Returns {processed: bool}."""
    payload = callback_data.model_dump(exclude_none=True)
    logger.info("ModulBank webhook received", extra={"order_id": payload.get("order_id")})

    if not verify_modulbank_signature(payload):
        logger.error("ModulBank webhook: invalid signature", extra={"order_id": payload.get("order_id")})
        raise InvalidSignatureError()

    transaction_id = payload.get("order_id", "")
    # The HTTP delivery boundary persists special-equipment callbacks in its
    # PostgreSQL inbox before calling this business handler. Redis must not
    # acknowledge such a callback before that durable commit.
    if transaction_id.startswith(SPECIAL_EQUIPMENT_GATEWAY_PREFIX):
        return await _handle_special_equipment_payment_callback(
            transaction_id,
            payload,
            session,
        )

    # Replay protection — signature alone doesn't prove freshness. Before
    # any DB write, stash a per-webhook nonce in Redis with a TTL covering
    # the replay window. If the gateway happens to genuinely re-send the
    # same webhook (network retry etc.), we still return the 200-shaped
    # success payload so they don't escalate retries.
    if settings.webhook_replay_enabled:
        signature = str(payload.get("signature") or "")
        # Prefer transaction_id + signature (stable, collision-free across
        # payments). If the gateway ever omits order_id in a callback
        # shape we haven't seen, fall back to hashing the signature —
        # worse replay granularity but still safe.
        if transaction_id:
            nonce = f"{transaction_id}:{signature}"
        else:
            nonce = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        if await webhook_replay.seen_before(nonce):
            logger.warning(
                "webhook_replay_rejected nonce_prefix=%s order_id=%s",
                nonce[:16],
                transaction_id,
            )
            auth_events.emit(
                auth_events.WEBHOOK_REPLAY_REJECTED,
                source="modulbank",
                nonce_prefix=nonce[:16],
            )
            return {"processed": False, "replay": True}, []

    payment = await _lock_vehicle_payment_callback_context(
        transaction_id,
        session,
    )

    if payment["status"] == PaymentStatus.COMPLETED:
        logger.info("ModulBank webhook: payment already completed", extra={"payment_id": payment["id"]})
        return {"processed": True, "already_completed": True}, []

    if payment["status"] != PaymentStatus.PENDING:
        logger.warning(
            "ModulBank webhook: unexpected payment status",
            extra={"payment_id": payment["id"], "status": payment["status"]},
        )
        return {"processed": False}, []

    is_success = (
        payload.get("status") == "success"
        or payload.get("state") == "COMPLETE"
        or payload.get("result") == "ok"
    )

    if is_success:
        payment_ids = await _complete_payment(payment, payload, session)
    else:
        await _fail_payment(payment, payload, session)
        payment_ids = []

    return {"processed": True}, payment_ids


async def _handle_special_equipment_payment_callback(
    transaction_id: str,
    payload: dict[str, Any],
    session: AsyncSession,
) -> tuple[dict[str, Any], list[UUID]]:
    """Route a verified shared webhook to the isolated equipment aggregate."""

    preliminary_payment = (
        await special_equipment_repo.get_payment_by_gateway_transaction(
            session,
            transaction_id,
        )
    )
    if not preliminary_payment:
        logger.error(
            "ModulBank webhook: special-equipment payment not found",
            extra={"order_id": transaction_id},
        )
        raise PaymentNotFoundError()
    order = await special_equipment_repo.get_order(
        session,
        preliminary_payment["purchase_order_id"],
        lock=True,
    )
    if order is None:
        raise OrderNotFoundError()
    payment = await special_equipment_repo.get_payment_by_gateway_transaction(
        session,
        transaction_id,
        lock=True,
    )
    if payment is None:
        raise PaymentNotFoundError()
    _validate_special_equipment_callback_binding(
        transaction_id=transaction_id,
        payment=payment,
        order=order,
        payload=payload,
    )
    is_success = (
        payload.get("status") == "success"
        or payload.get("state") == "COMPLETE"
        or payload.get("result") == "ok"
    )
    if payment["status"] == "completed":
        return {"processed": True, "already_completed": True}, []
    if payment["status"] != "pending":
        if not is_success:
            return {"processed": True, "already_terminal": True}, []
        order = await _prepare_late_special_equipment_success(
            payment,
            order,
            session,
        )
    if is_success:
        fiscalization_ids = await _complete_special_equipment_payment(
            payment,
            order,
            payload,
            session,
        )
    else:
        await _fail_special_equipment_payment(payment, order, payload, session)
        fiscalization_ids = []
    return {"processed": True}, fiscalization_ids


async def _prepare_late_special_equipment_success(  # noqa: PLR0912
    payment: dict[str, Any],
    order: dict[str, Any],
    session: AsyncSession,
) -> dict[str, Any]:
    """Permit only a provably safe late success; otherwise reconcile manually."""

    if (
        payment["status"] == "refunded"
        or payment.get("refunded_at") is not None
        or order.get("refund_external_reference") is not None
        or order.get("refunded_amount") is not None
    ):
        raise SpecialEquipmentPaymentManualReviewError(
            "LATE_SUCCESS_REFUND_REQUIRED"
        )
    if payment["status"] != "expired":
        raise SpecialEquipmentPaymentManualReviewError(
            "LATE_SUCCESS_PAYMENT_TERMINAL"
        )

    payment_type = payment["payment_type"]
    if payment_type == "preorder":
        if order["status"] == "preordered":
            return order
        if order["status"] != "expired":
            raise SpecialEquipmentPaymentManualReviewError(
                "LATE_SUCCESS_PREORDER_TERMINAL"
            )
        return cast(
            "dict[str, Any]",
            await special_equipment_repo.update_order(
                session,
                order["id"],
                {"status": "preordered", "hold_expires_at": None},
            ),
        )
    if payment_type == "remaining_balance" and order["status"] == "reserved":
        return order

    if payment_type == "leasing_monthly":
        if order["status"] != "leasing_active":
            raise SpecialEquipmentPaymentManualReviewError(
                "LATE_SUCCESS_LEASING_ORDER_INACTIVE"
            )
        schedule_id = _special_equipment_schedule_id(payment)
        schedule = await special_equipment_repo.get_schedule_item(
            session,
            schedule_id,
            lock=True,
        )
        if (
            schedule is None
            or schedule["purchase_order_id"] != order["id"]
            or schedule["is_paid"]
            or Decimal(str(schedule["amount"])) != Decimal(str(payment["amount"]))
        ):
            raise SpecialEquipmentPaymentManualReviewError(
                "LATE_SUCCESS_LEASING_SCHEDULE_TERMINAL"
            )
        if schedule.get("payment_id") not in (None, payment["id"]):
            raise SpecialEquipmentPaymentManualReviewError(
                "LATE_SUCCESS_LEASING_SCHEDULE_REBOUND"
            )
        if schedule.get("payment_id") is None:
            try:
                await special_equipment_repo.attach_schedule_payment(
                    session,
                    schedule_id,
                    payment["id"],
                )
            except Exception as exc:
                raise SpecialEquipmentPaymentManualReviewError(
                    "LATE_SUCCESS_LEASING_SCHEDULE_REBOUND"
                ) from exc
        return order

    if order["status"] == "payment_pending":
        return order
    if order["status"] != "expired":
        reason = (
            "LATE_SUCCESS_ORDER_CANCELLED"
            if order["status"] in {"cancelled", "cancellation_requested"}
            else "LATE_SUCCESS_ORDER_TERMINAL"
        )
        raise SpecialEquipmentPaymentManualReviewError(reason)
    if await special_equipment_repo.order_allocations_have_conflicts(
        session,
        order["id"],
        excluding_application_id=order.get("leasing_application_id"),
    ):
        raise SpecialEquipmentPaymentManualReviewError(
            "LATE_SUCCESS_PRODUCT_RECLAIMED"
        )

    restored = await special_equipment_repo.update_order(
        session,
        order["id"],
        {"status": "payment_pending", "hold_expires_at": None},
    )
    await special_equipment_repo.update_order_allocations_sale_status(
        session,
        order["id"],
        "reserved",
    )
    return cast("dict[str, Any]", restored)


def _validate_special_equipment_callback_binding(
    *,
    transaction_id: str,
    payment: Mapping[str, Any],
    order: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    expected_transaction_id = (
        f"{SPECIAL_EQUIPMENT_GATEWAY_PREFIX}{payment['id']}"
    )
    if (
        transaction_id != expected_transaction_id
        or payment.get("gateway_transaction_id") != expected_transaction_id
        or payment.get("purchase_order_id") != order.get("id")
    ):
        raise PaymentGatewayError("Webhook payment/order binding mismatch")

    raw_amount = payload.get("amount")
    if raw_amount is None:
        raise PaymentGatewayError("Webhook amount is missing")
    try:
        callback_amount = Decimal(str(raw_amount))
    except (ArithmeticError, ValueError) as exc:
        raise PaymentGatewayError("Webhook amount is invalid") from exc
    if not callback_amount.is_finite() or callback_amount <= 0:
        raise PaymentGatewayError("Webhook amount is invalid")
    if callback_amount != Decimal(str(payment["amount"])):
        raise PaymentGatewayError("Webhook amount mismatch")

    raw_currency = payload.get("currency") or payload.get("currency_code")
    expected_currency = str(order.get("currency_code") or "RUB").upper()
    if raw_currency is not None and str(raw_currency).upper() != expected_currency:
        raise PaymentGatewayError("Webhook currency mismatch")
    if expected_currency != "RUB":
        raise PaymentGatewayError("Unsupported special-equipment payment currency")

    raw_merchant = payload.get("merchant") or payload.get("merchant_id")
    if raw_merchant is not None and str(raw_merchant) != settings.modulbank_shop_id:
        raise PaymentGatewayError("Webhook merchant mismatch")


def _special_equipment_schedule_id(payment: Mapping[str, Any]) -> UUID:
    raw_schedule_id = (payment.get("gateway_response") or {}).get("schedule_id")
    try:
        return UUID(str(raw_schedule_id))
    except (TypeError, ValueError) as exc:
        raise PaymentGatewayError(
            "Special-equipment leasing payment has no valid schedule binding"
        ) from exc


async def _complete_special_equipment_payment(
    payment: dict[str, Any],
    order: dict[str, Any],
    callback_data: dict[str, Any],
    session: AsyncSession,
) -> list[UUID]:
    """Atomically complete equipment payment, order and sellable-unit state."""

    if payment["payment_type"] == "leasing_monthly":
        if order["status"] != "leasing_active":
            raise PaymentGatewayError("Leasing order is not payable")
        schedule_id = _special_equipment_schedule_id(payment)
        schedule = await special_equipment_repo.get_schedule_item(
            session, schedule_id, lock=True
        )
        if (
            schedule is None
            or schedule["purchase_order_id"] != order["id"]
            or schedule.get("payment_id") != payment["id"]
            or schedule["is_paid"]
            or Decimal(str(schedule["amount"])) != Decimal(str(payment["amount"]))
        ):
            raise PaymentGatewayError(
                "Leasing payment does not match an unpaid schedule item"
            )
        amount = Decimal(str(payment["amount"]))
        paid_amount = Decimal(str(order["paid_amount"])) + amount
        total_price = Decimal(str(order["total_price"]))
        if paid_amount > total_price:
            raise PaymentGatewayError(
                "Сумма платежей превышает стоимость лизингового заказа"
            )
        await special_equipment_repo.update_payment(
            session,
            payment["id"],
            {
                "status": "completed",
                "paid_at": datetime.now(UTC),
                "gateway_response": {
                    **(payment.get("gateway_response") or {}),
                    **callback_data,
                },
                "fiscal_status": "pending",
                "error_message": None,
            },
        )
        marked = await special_equipment_repo.mark_schedule_paid(
            session, schedule_id, payment["id"]
        )
        if marked is None:
            raise PaymentGatewayError("Leasing schedule item was already processed")
        await special_equipment_repo.update_order(
            session,
            order["id"],
            {
                "status": "leasing_active",
                "paid_amount": paid_amount,
                "remaining_amount": total_price - paid_amount,
                "hold_expires_at": None,
            },
        )
        logger.info(
            "Special-equipment leasing payment %s completed for order %s",
            payment["id"],
            order["id"],
        )
        return [payment["id"]]

    allowed_status = (
        "reserved"
        if payment["payment_type"] == "remaining_balance"
        else "preordered"
        if payment["payment_type"] == "preorder"
        else "payment_pending"
    )
    if order["status"] != allowed_status:
        raise PaymentGatewayError("Order is not payable in its current state")

    amount = Decimal(str(payment["amount"]))
    paid_amount = Decimal(str(order["paid_amount"])) + amount
    total_price = Decimal(str(order["total_price"]))
    if paid_amount > total_price:
        raise PaymentGatewayError("Сумма платежей превышает стоимость спецтехники")
    remaining_amount = total_price - paid_amount
    is_preorder = payment["payment_type"] == "preorder"
    is_prepayment = (
        payment["payment_type"] == "reservation" and remaining_amount > 0
    )
    target_order_status = (
        "preordered" if is_preorder else "reserved" if is_prepayment else "purchased"
    )
    target_product_status = "reserved" if is_prepayment else "sold"
    gateway_response = {
        **(payment.get("gateway_response") or {}),
        **callback_data,
    }
    await special_equipment_repo.update_payment(
        session,
        payment["id"],
        {
            "status": "completed",
            "paid_at": datetime.now(UTC),
            "gateway_response": gateway_response,
            "fiscal_status": "pending",
            "error_message": None,
        },
    )
    await special_equipment_repo.update_order(
        session,
        order["id"],
        {
            "status": target_order_status,
            "paid_amount": paid_amount,
            "remaining_amount": remaining_amount,
            "hold_expires_at": None,
        },
    )
    if not is_preorder:
        await special_equipment_repo.update_order_allocations_sale_status(
            session,
            order["id"],
            target_product_status,
        )
    logger.info(
        "Special-equipment payment %s completed for order %s",
        payment["id"],
        order["id"],
    )
    return [payment["id"]]


async def _fail_special_equipment_payment(
    payment: dict[str, Any],
    order: dict[str, Any],
    callback_data: dict[str, Any],
    session: AsyncSession,
) -> None:
    """Fail one attempt; release only an unpaid initial equipment hold."""

    message = (
        callback_data.get("error_message")
        or callback_data.get("error")
        or "Payment failed"
    )
    await special_equipment_repo.update_payment(
        session,
        payment["id"],
        {
            "status": "failed",
            "gateway_response": {
                **(payment.get("gateway_response") or {}),
                **callback_data,
            },
            "error_message": message,
        },
    )
    if payment["payment_type"] == "leasing_monthly":
        await special_equipment_repo.clear_schedule_payment(
            session,
            _special_equipment_schedule_id(payment),
            payment["id"],
        )
    is_preorder = payment["payment_type"] == "preorder"
    is_initial = payment["payment_type"] in {
        "reservation",
        "preorder",
        "full_purchase",
    }
    if (
        is_initial
        and Decimal(str(order["paid_amount"])) == Decimal("0.00")
        and order["status"] == ("preordered" if is_preorder else "payment_pending")
    ):
        await special_equipment_repo.update_order(
            session,
            order["id"],
            {"status": "failed", "hold_expires_at": None},
        )
        if not is_preorder:
            await special_equipment_repo.release_order_allocations_if_unclaimed(
                session, order["id"]
            )


async def _complete_payment(
    payment: dict[str, Any] | Any, callback_data: dict[str, Any], session: AsyncSession
) -> list[UUID]:
    """Complete a successful payment: update payment, order, vehicle, trigger fiscalization."""
    existing_gateway_response = payment.get("gateway_response") or {}
    merged_gateway_response = _merge_vehicle_gateway_callback(
        existing_gateway_response,
        callback_data,
    )
    await repo.update_payment(
        session,
        payment["id"],
        {
            "status": PaymentStatus.COMPLETED,
            "paid_at": datetime.now(UTC),
            "gateway_response": merged_gateway_response,
        },
    )

    order = await repo.get_by_id_with_details(session, payment["purchase_order_id"])
    if order is None:
        raise OrderNotFoundError()
    new_paid = Decimal(str(order["paid_amount"])) + Decimal(str(payment["amount"]))
    new_remaining = max(
        Decimal("0.00"),
        Decimal(str(order["total_price"])) - new_paid,
    )

    order_update: dict = {"paid_amount": new_paid, "remaining_amount": new_remaining}

    if payment["payment_type"] == PaymentType.RESERVATION:
        order_update["status"] = OrderStatus.RESERVED
    elif payment["payment_type"] in (PaymentType.REMAINING_BALANCE, PaymentType.FULL_PURCHASE):
        order_update["status"] = OrderStatus.PURCHASED

    await repo.update_order(session, payment["purchase_order_id"], order_update)

    if payment["payment_type"] in (PaymentType.FULL_PURCHASE, PaymentType.REMAINING_BALANCE):
        await repo.update_vehicle_status_in_transaction(session, order["vehicle_id"], VehicleStatus.SOLD)

    if payment["payment_type"] == PaymentType.LEASING_MONTHLY:
        schedule_id = existing_gateway_response.get("schedule_id")
        if schedule_id:
            await repo.mark_schedule_item_paid(session, schedule_id, payment["id"])

    logger.info("Payment %s completed for order %s", payment["id"], payment["purchase_order_id"])
    should_fiscalize = payment["payment_method"] != PaymentMethod.BANK_TRANSFER
    return [payment["id"]] if should_fiscalize else []


def start_fiscalization_task(payment_id: UUID) -> None:
    """Schedule fiscalization after the surrounding transaction has committed."""
    task = asyncio.create_task(trigger_fiscalization(payment_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _extract_receipt_url(
    payload: Mapping[str, Any] | None,
    *,
    depth: int = 0,
) -> str | None:
    """Extract known receipt URL fields without persisting the provider body."""

    if not payload or depth > 3:
        return None
    for key in (
        "ofd_receipt_url",
        "ofdReceiptUrl",
        "receipt_url",
        "receiptUrl",
        "ofd_url",
        "ofdUrl",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("data", "result", "receipt", "document"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            value = _extract_receipt_url(nested, depth=depth + 1)
            if value:
                return value
    return None


def _safe_special_fiscal_metadata(payload: Mapping[str, Any] | None) -> dict[str, str]:
    """Retain only non-sensitive provider state; URLs/payloads never persist."""

    result: dict[str, str] = {}
    if payload:
        for key, limit in (("id", 255), ("status", 50)):
            value = payload.get(key)
            if isinstance(value, (str, int)):
                result[key] = str(value)[:limit]
    return result


async def _fail_payment(
    payment: dict[str, Any] | Any, callback_data: dict[str, Any], session: AsyncSession
) -> None:
    """Handle failed payment."""
    merged_gateway_response = _merge_vehicle_gateway_callback(
        payment.get("gateway_response"),
        callback_data,
    )
    await repo.update_payment(
        session,
        payment["id"],
        {
            "status": PaymentStatus.FAILED,
            "gateway_response": merged_gateway_response,
            "error_message": (
                callback_data.get("error_message")
                or callback_data.get("error")
                or "Payment failed"
            ),
        },
    )

    if payment["payment_type"] in (PaymentType.RESERVATION, PaymentType.FULL_PURCHASE):
        order = await repo.get_by_id_with_details(session, payment["purchase_order_id"])
        if not order:
            return
        payments = await repo.get_payments_by_order_id(session, payment["purchase_order_id"])
        has_completed = any(
            p["id"] != payment["id"] and p["status"] == PaymentStatus.COMPLETED for p in payments
        )

        if not has_completed:
            await repo.update_vehicle_status_in_transaction(session, order["vehicle_id"], VehicleStatus.AVAILABLE)
            await repo.update_order(
                session, payment["purchase_order_id"], {"status": OrderStatus.CANCELLED}
            )

    logger.info("Payment %s failed for order %s", payment["id"], payment["purchase_order_id"])


def _adapt_special_equipment_receipt(
    payment: dict[str, Any],
    order: dict[str, Any],
    scenario: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Reuse the proven ModulKassa schema without passing legacy vehicle rows."""

    snapshot = order.get("item_snapshot") or {}
    adapted_order = {
        "mark_name": snapshot.get("mark") or snapshot.get("manufacturer"),
        "model_name": " ".join(
            str(value).strip()
            for value in (snapshot.get("model"), snapshot.get("modification"))
            if value
        ),
        "vin": snapshot.get("vin"),
        "total_price": order["total_price"],
    }
    payload = modulkassa.build_receipt_payload(
        payment,
        adapted_order,
        scenario,
        extra,
    )
    # One stable provider id makes retries idempotent after timeouts/restarts.
    if payment.get("fiscal_receipt_id"):
        payload["id"] = payment["fiscal_receipt_id"]
    payload["docNum"] = f"{SPECIAL_EQUIPMENT_GATEWAY_PREFIX}{payment['id']}"
    for position in payload.get("inventPositions", []):
        name = str(position.get("name") or "")
        position["name"] = name.replace(
            "Аванс за автомобиль", "Аванс за спецтехнику"
        ).replace("Автомобиль", "Спецтехника")
    return payload


async def _build_special_equipment_fiscalization_payload(
    session: AsyncSession,
    payment: dict[str, Any],
) -> dict[str, Any]:
    order = await special_equipment_repo.get_order(
        session,
        payment["purchase_order_id"],
    )
    if order is None:
        raise OrderNotFoundError()

    extra: dict[str, Any] = {}
    payment_type = payment["payment_type"]
    if payment_type in {"reservation", "preorder"}:
        scenario = "advance"
    elif payment_type == "remaining_balance":
        scenario = "final_after_advance"
        payments = await special_equipment_repo.list_order_payments(
            session,
            payment["purchase_order_id"],
        )
        advance = next(
            (
                row
                for row in payments
                if row["payment_type"] == "reservation"
                and row["status"] == "completed"
            ),
            None,
        )
        extra["advanceAmount"] = advance["amount"] if advance else 0
    else:
        scenario = "full_payment"

    user = await _get_user_info(session, payment["user_id"])
    extra.update(
        {
            "email": user.get("email"),
            "phone": user.get("phone"),
            "clientName": user.get("name"),
        }
    )
    return _adapt_special_equipment_receipt(
        payment,
        order,
        scenario,
        extra,
    )


async def fiscalize_special_equipment_payments(
    *,
    payment_id: UUID | None = None,
    limit: int = 25,
) -> int:
    """Claim, send and finalize durable fiscal jobs without provider-session overlap."""

    now = datetime.now(UTC)
    plans: list[tuple[dict[str, Any], dict[str, Any]]] = []
    async with AsyncSessionLocal() as session:
        claimed = await special_equipment_repo.claim_fiscalization_payments(
            session,
            now=now,
            sent_stale_after=timedelta(
                seconds=max(1, settings.fiscalization_sent_stale_seconds)
            ),
            failed_retry_after=timedelta(
                seconds=max(1, settings.fiscalization_failed_retry_seconds)
            ),
            limit=limit,
            payment_id=payment_id,
        )
        for payment in claimed:
            try:
                payload = await _build_special_equipment_fiscalization_payload(
                    session,
                    payment,
                )
            except Exception as exc:
                await special_equipment_repo.update_payment(
                    session,
                    payment["id"],
                    {
                        "fiscal_status": "failed",
                        "fiscal_error_message": type(exc).__name__[:100],
                    },
                )
                logger.error(
                    "Special-equipment fiscal plan failed payment=%s type=%s",
                    payment["id"],
                    type(exc).__name__,
                )
                continue
            plans.append((payment, payload))
        await session.commit()

    # No AsyncSession exists while waiting on ModulKassa.
    for payment, receipt_payload in plans:
        payment_id_value = payment["id"]
        try:
            fiscal_response = await modulkassa.create_receipt(receipt_payload)
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                current = await special_equipment_repo.get_payment(
                    session,
                    payment_id_value,
                    lock=True,
                )
                if (
                    current
                    and current.get("fiscal_status") != "completed"
                    and current.get("fiscal_receipt_id") == receipt_payload["id"]
                ):
                    await special_equipment_repo.update_payment(
                        session,
                        payment_id_value,
                        {
                            "fiscal_status": "failed",
                            "fiscal_error_message": type(exc).__name__[:100],
                        },
                    )
                    await session.commit()
            logger.error(
                "Special-equipment fiscalization failed payment=%s type=%s",
                payment_id_value,
                type(exc).__name__,
            )
            continue

        receipt_url = _extract_receipt_url(fiscal_response)
        should_ingest = False
        async with AsyncSessionLocal() as session:
            current = await special_equipment_repo.get_payment(
                session,
                payment_id_value,
                lock=True,
            )
            if current is None:
                continue
            if current.get("fiscal_status") == "completed":
                continue
            if current.get("fiscal_receipt_id") != receipt_payload["id"]:
                logger.warning(
                    "Ignoring stale fiscal response payment=%s",
                    payment_id_value,
                )
                continue
            should_ingest = not bool(current.get("receipt_storage_key"))
            await special_equipment_repo.update_payment(
                session,
                payment_id_value,
                {
                    "fiscal_status": "completed",
                    "fiscal_response": _safe_special_fiscal_metadata(
                        fiscal_response
                    ),
                    "fiscal_error_message": None,
                    "receipt_ingestion_status": (
                        "pending" if should_ingest else "completed"
                    ),
                    "receipt_ingestion_error_code": None,
                    "receipt_ingestion_next_retry_at": (
                        datetime.now(UTC) if should_ingest else None
                    ),
                },
            )
            await session.commit()
        if should_ingest:
            try:
                start_special_equipment_receipt_task(
                    payment_id_value,
                    receipt_url,
                )
            except Exception:
                logger.exception(
                    "Failed to schedule receipt ingestion payment=%s",
                    payment_id_value,
                )
        logger.info(
            "Special-equipment fiscalization completed payment=%s",
            payment_id_value,
        )
    return len(claimed)


async def _special_equipment_fiscalization_attempt(
    session: AsyncSession,
    payment: dict[str, Any],
    retry_count: int,
) -> bool:
    # Compatibility entrypoint for callers of the legacy in-process scheduler.
    # Close its lookup session before the durable implementation performs any
    # provider I/O. The scheduled sweep is the source of retry durability.
    del retry_count
    await session.rollback()
    await session.close()
    await fiscalize_special_equipment_payments(
        payment_id=payment["id"],
        limit=1,
    )
    return True


async def _fiscalization_attempt(  # noqa: PLR0911 -- explicit terminal states
    payment_id: UUID, retry_count: int
) -> bool:
    """Single fiscalization attempt. Returns True on success, False on failure.

    Opens its own short-lived session — caller releases the connection between
    retries via the surrounding `sleep`.
    """
    async with AsyncSessionLocal() as session:
        payment = await repo.get_payment_by_id(session, payment_id)
        if not payment:
            special_equipment_payment = await special_equipment_repo.get_payment(
                session,
                payment_id,
            )
            if special_equipment_payment:
                return await _special_equipment_fiscalization_attempt(
                    session,
                    special_equipment_payment,
                    retry_count,
                )
            return True
        if payment["status"] != PaymentStatus.COMPLETED:
            return True
        if payment.get("fiscal_status") == "completed":
            return True
        if payment.get("payment_method") == PaymentMethod.BANK_TRANSFER:
            return True

        try:
            await repo.update_payment(session, payment_id, {"fiscal_status": "pending"})

            order = await repo.get_by_id_with_details(session, payment["purchase_order_id"])
            if not order:
                logger.error("Order %d not found for payment %d", payment["purchase_order_id"], payment_id)
                return True

            extra: dict = {}
            ptype = payment["payment_type"]
            if ptype == PaymentType.FULL_PURCHASE:
                scenario = "full_payment"
            elif ptype == PaymentType.RESERVATION:
                scenario = "advance"
            elif ptype == PaymentType.REMAINING_BALANCE:
                scenario = "final_after_advance"
                payments = await repo.get_payments_by_order_id(session, payment["purchase_order_id"])
                advance = next(
                    (p for p in payments if p["payment_type"] == PaymentType.RESERVATION and p["status"] == PaymentStatus.COMPLETED),
                    None,
                )
                extra["advanceAmount"] = advance["amount"] if advance else 0
            else:
                scenario = "full_payment"

            user = await _get_user_info(session, payment["user_id"])
            extra.update({"email": user.get("email"), "phone": user.get("phone"), "clientName": user.get("name")})

            receipt_payload = modulkassa.build_receipt_payload(payment, order, scenario, extra)

            await repo.update_payment(session, payment_id, {"fiscal_status": "sent"})
            await session.commit()

            fiscal_response = await modulkassa.create_receipt(receipt_payload)

            await repo.update_payment(
                session,
                payment_id,
                {
                    "fiscal_status": "completed",
                    "fiscal_receipt_id": receipt_payload["id"],
                    "fiscal_response": fiscal_response,
                    "fiscal_retry_count": retry_count,
                },
            )
            await session.commit()
            logger.info("Fiscalization completed for payment %d, receipt %s", payment_id, receipt_payload["id"])
            return True

        except Exception as error:
            await session.rollback()
            logger.error("Fiscalization failed for payment %d, attempt %d: %s", payment_id, retry_count + 1, error)
            await repo.update_payment(
                session,
                payment_id,
                {
                    "fiscal_status": "failed",
                    "fiscal_error_message": str(error),
                    "fiscal_retry_count": retry_count,
                },
            )
            await session.commit()
            return False


async def trigger_fiscalization(payment_id: UUID) -> None:
    """Fire-and-forget fiscalization with retry. Each attempt uses its own session;
    no DB connection is held across `sleep` between retries.
    """
    delays = settings.fiscalization_retry_delays_seconds
    max_retries = len(delays)
    for retry_count in range(max_retries + 1):
        success = await _fiscalization_attempt(payment_id, retry_count)
        if success:
            return
        if retry_count >= max_retries:
            logger.error("Fiscalization exhausted retries for payment %d. Manual intervention required.", payment_id)
            return
        delay = delays[retry_count]
        logger.info("Scheduling fiscal retry %d for payment %d in %ds", retry_count + 1, payment_id, delay)
        await asyncio.sleep(delay)


def start_special_equipment_receipt_task(
    payment_id: UUID,
    source_url: str | None = None,
) -> None:
    """Schedule private receipt ingestion after fiscal success is committed."""

    task = asyncio.create_task(
        trigger_special_equipment_receipt_ingestion(payment_id, source_url)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _record_receipt_ingestion_failure(
    payment_id: UUID,
    *,
    retry_count: int,
    error_code: str,
) -> bool:
    """Record a retryable failure without changing successful fiscal state."""

    delays = settings.modulkassa_receipt_retry_delays_seconds
    delay = delays[min(retry_count, len(delays) - 1)] if delays else 300
    next_retry_at = datetime.now(UTC) + timedelta(seconds=max(1, delay))
    async with AsyncSessionLocal() as session:
        payment = await special_equipment_repo.get_payment(
            session,
            payment_id,
            lock=True,
        )
        if not payment:
            return True
        if payment.get("receipt_storage_key"):
            await special_equipment_repo.update_payment(
                session,
                payment_id,
                {
                    "receipt_ingestion_status": "completed",
                    "receipt_ingestion_error_code": None,
                    "receipt_ingestion_next_retry_at": None,
                },
            )
            await session.commit()
            return True
        if payment.get("fiscal_status") != "completed":
            return True
        await special_equipment_repo.update_payment(
            session,
            payment_id,
            {
                "receipt_ingestion_status": "failed",
                "receipt_ingestion_retry_count": retry_count,
                "receipt_ingestion_error_code": error_code[:100],
                "receipt_ingestion_next_retry_at": next_retry_at,
            },
        )
        await session.commit()
    return False


async def _resolve_receipt_source_url(
    source_url: str | None,
    fiscal_receipt_id: Any,
) -> str:
    if source_url:
        return source_url
    if not isinstance(fiscal_receipt_id, str) or not fiscal_receipt_id:
        raise special_equipment_receipts.ReceiptIngestionError(
            "RECEIPT_PROVIDER_ID_MISSING"
        )
    provider_status = await modulkassa.check_receipt_status(fiscal_receipt_id)
    resolved = _extract_receipt_url(provider_status)
    if not resolved:
        raise special_equipment_receipts.ReceiptIngestionError(
            "RECEIPT_URL_MISSING"
        )
    return resolved


async def _receipt_ingestion_attempt(  # noqa: PLR0911 -- explicit terminal states
    payment_id: UUID,
    source_url: str | None,
    retry_count: int,
    *,
    already_claimed: bool = False,
) -> bool:
    """Run one attempt without keeping a DB connection during network I/O."""

    try:
        async with AsyncSessionLocal() as session:
            payment = await special_equipment_repo.get_payment(
                session,
                payment_id,
                lock=True,
            )
            if not payment:
                return True
            if payment.get("receipt_storage_key"):
                if payment.get("receipt_ingestion_status") != "completed":
                    await special_equipment_repo.update_payment(
                        session,
                        payment_id,
                        {
                            "receipt_ingestion_status": "completed",
                            "receipt_ingestion_error_code": None,
                            "receipt_ingestion_next_retry_at": None,
                        },
                    )
                    await session.commit()
                return True
            if payment.get("fiscal_status") != "completed":
                return True
            if (
                payment.get("receipt_ingestion_status") == "processing"
                and not already_claimed
            ):
                return True
            fiscal_receipt_id = payment.get("fiscal_receipt_id")
            await special_equipment_repo.update_payment(
                session,
                payment_id,
                {
                    "receipt_ingestion_status": "processing",
                    "receipt_ingestion_error_code": None,
                    "receipt_ingestion_next_retry_at": None,
                },
            )
            await session.commit()

        current_source_url = await _resolve_receipt_source_url(
            source_url,
            fiscal_receipt_id,
        )

        storage_key = await special_equipment_receipts.ingest_receipt_pdf(
            payment_id=payment_id,
            source_url=current_source_url,
            storage=get_object_storage(),
        )

        async with AsyncSessionLocal() as session:
            current = await special_equipment_repo.get_payment(
                session,
                payment_id,
                lock=True,
            )
            if not current:
                return True
            await special_equipment_repo.update_payment(
                session,
                payment_id,
                {
                    "receipt_storage_key": (
                        current.get("receipt_storage_key") or storage_key
                    ),
                    "receipt_ingestion_status": "completed",
                    "receipt_ingestion_retry_count": retry_count,
                    "receipt_ingestion_error_code": None,
                    "receipt_ingestion_next_retry_at": None,
                },
            )
            await session.commit()
        logger.info(
            "Special-equipment receipt ingested payment=%s",
            payment_id,
        )
        return True
    except special_equipment_receipts.ReceiptIngestionError as exc:
        error_code = exc.code
    except Exception as exc:
        error_code = "RECEIPT_INGESTION_INTERNAL_ERROR"
        logger.error(
            "Special-equipment receipt ingestion internal failure payment=%s type=%s",
            payment_id,
            type(exc).__name__,
        )

    logger.warning(
        "Special-equipment receipt ingestion failed payment=%s attempt=%s code=%s",
        payment_id,
        retry_count + 1,
        error_code,
    )
    return await _record_receipt_ingestion_failure(
        payment_id,
        retry_count=retry_count,
        error_code=error_code,
    )


async def trigger_special_equipment_receipt_ingestion(
    payment_id: UUID,
    source_url: str | None = None,
) -> None:
    """Ingest with bounded retries; sleeps never hold a database connection."""

    delays = settings.modulkassa_receipt_retry_delays_seconds
    for retry_count in range(len(delays) + 1):
        if await _receipt_ingestion_attempt(payment_id, source_url, retry_count):
            return
        if retry_count == len(delays):
            logger.error(
                "Special-equipment receipt exhausted immediate retries payment=%s",
                payment_id,
            )
            return
        await asyncio.sleep(max(1, delays[retry_count]))


async def retry_pending_special_equipment_receipts(*, limit: int = 25) -> int:
    """Durably retry due/abandoned receipt jobs and return claimed count."""

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        claimed = await special_equipment_repo.claim_receipt_ingestions(
            session,
            now=now,
            processing_stale_after=timedelta(
                seconds=max(
                    1,
                    settings.modulkassa_receipt_processing_stale_seconds,
                )
            ),
            limit=limit,
        )
        await session.commit()

    if not claimed:
        return 0

    semaphore = asyncio.Semaphore(4)

    async def run(row: dict[str, Any]) -> None:
        async with semaphore:
            await _receipt_ingestion_attempt(
                row["id"],
                None,
                int(row.get("receipt_ingestion_retry_count") or 0) + 1,
                already_claimed=True,
            )

    await asyncio.gather(*(run(row) for row in claimed))
    return len(claimed)


async def handle_fiscal_callback(
    callback_data: ModulkassaWebhookPayload,
    session: AsyncSession,
) -> list[tuple[UUID, str | None]]:
    """Handle ModulKassa fiscal receipt callback."""
    payload = callback_data.model_dump(exclude_none=True)
    logger.info("ModulKassa webhook received", extra={"id": payload.get("id")})

    payment_obj = await repo.get_payment_by_fiscal_receipt_id(session, payload.get("id"))
    special_equipment_payment = None
    if not payment_obj:
        special_equipment_payment = (
            await special_equipment_repo.get_payment_by_fiscal_receipt_id(
                session,
                payload.get("id"),
            )
        )

    if not payment_obj and not special_equipment_payment:
        logger.error("ModulKassa webhook: payment not found for receipt", extra={"id": payload.get("id")})
        return []

    if special_equipment_payment:
        callback_status = payload.get("status", "")
        if callback_status in ("COMPLETED", "completed"):
            receipt_url = _extract_receipt_url(payload)
            has_stored_receipt = bool(
                special_equipment_payment.get("receipt_storage_key")
            )
            ingestion_in_progress = (
                special_equipment_payment.get("receipt_ingestion_status")
                == "processing"
            )
            await special_equipment_repo.update_payment(
                session,
                special_equipment_payment["id"],
                {
                    "fiscal_status": "completed",
                    "fiscal_response": _safe_special_fiscal_metadata(payload),
                    "fiscal_error_message": None,
                    "receipt_ingestion_status": (
                        "completed"
                        if has_stored_receipt
                        else "processing"
                        if ingestion_in_progress
                        else "pending"
                    ),
                    "receipt_ingestion_error_code": None,
                    "receipt_ingestion_next_retry_at": (
                        None
                        if has_stored_receipt or ingestion_in_progress
                        else datetime.now(UTC)
                    ),
                },
            )
            if not has_stored_receipt and not ingestion_in_progress:
                return [(special_equipment_payment["id"], receipt_url)]
        else:
            await special_equipment_repo.update_payment(
                session,
                special_equipment_payment["id"],
                {
                    "fiscal_status": "failed",
                    "fiscal_response": _safe_special_fiscal_metadata(payload),
                    "fiscal_error_message": "Fiscal receipt failed",
                },
            )
        return []

    assert payment_obj is not None
    cb_status = payload.get("status", "")
    is_success = cb_status in ("COMPLETED", "completed")

    if is_success:
        receipt_url = payload.get("ofd_receipt_url") or payload.get("receipt_url")
        await repo.update_payment(
            session,
            payment_obj["id"],
            {
                "fiscal_status": "completed",
                "fiscal_response": payload,
                "receipt_url": receipt_url,
            },
        )
        logger.info("Fiscal receipt completed for payment %d, URL: %s", payment_obj["id"], receipt_url)
    else:
        await repo.update_payment(
            session,
            payment_obj["id"],
            {
                "fiscal_status": "failed",
                "fiscal_response": payload,
                "fiscal_error_message": payload.get("error") or "Fiscal receipt failed",
            },
        )
        logger.error("Fiscal receipt failed for payment %d", payment_obj["id"])
    return []


async def expire_stale_payments(session: AsyncSession) -> None:
    """Expire legacy payments and isolated special-equipment checkout holds."""
    rows = await repo.find_pending_expired_payments(session)
    if rows:
        logger.info("Expiring %d stale pending payments", len(rows))

    now = datetime.now(UTC)
    for candidate in rows:
        try:
            vehicle = await repo.get_vehicle_for_update(
                session,
                candidate["vehicle_id"],
            )
            if vehicle is None:
                continue
            order = await repo.get_order_for_update(
                session,
                candidate["purchase_order_id"],
            )
            if order is None or order["vehicle_id"] != candidate["vehicle_id"]:
                continue
            payment = await repo.get_payment_by_id_for_update(
                session,
                candidate["id"],
            )
            if payment is None or payment["purchase_order_id"] != order["id"]:
                continue
            expires_at = payment.get("expires_at")
            if not isinstance(expires_at, datetime):
                continue
            comparable_expiry = (
                expires_at.replace(tzinfo=UTC)
                if expires_at.tzinfo is None
                else expires_at
            )
            if (
                payment["status"] != PaymentStatus.PENDING
                or comparable_expiry >= now
            ):
                continue
            await repo.update_payment(
                session,
                payment["id"],
                {"status": PaymentStatus.FAILED, "error_message": "Payment expired (timeout)"},
            )

            if payment["payment_type"] in (PaymentType.RESERVATION, PaymentType.FULL_PURCHASE):
                payments = await repo.get_payments_by_order_id(session, payment["purchase_order_id"])
                has_completed = any(
                    p["id"] != payment["id"] and p["status"] == PaymentStatus.COMPLETED for p in payments
                )

                if not has_completed:
                    await repo.update_vehicle_status_in_transaction(
                        session,
                        order["vehicle_id"],
                        VehicleStatus.AVAILABLE,
                    )
                    await repo.update_order(
                        session,
                        payment["purchase_order_id"],
                        {"status": OrderStatus.CANCELLED},
                    )

            logger.info("Expired payment %s for order %s", payment["id"], payment["purchase_order_id"])
        except Exception as err:
            logger.error("Failed to expire payment %s: %s", candidate["id"], err)

    await _expire_stale_special_equipment_payments(session)


async def _expire_stale_special_equipment_payments(
    session: AsyncSession,
) -> None:
    """Release unpaid initial holds but preserve already-paid reservations."""

    now = datetime.now(UTC)
    gateway_payments = (
        await special_equipment_repo.find_expired_gateway_payments(
            session,
            now=now,
        )
    )
    for candidate in gateway_payments:
        order = await special_equipment_repo.get_order(
            session,
            candidate["purchase_order_id"],
            lock=True,
        )
        if order is None:
            continue
        payment = await special_equipment_repo.get_payment(
            session,
            candidate["id"],
            lock=True,
        )
        if (
            payment is None
            or payment["purchase_order_id"] != order["id"]
            or payment["status"] != "pending"
            or payment.get("expires_at") is None
            or payment["expires_at"] > now
        ):
            continue
        await special_equipment_repo.update_payment(
            session,
            payment["id"],
            {
                "status": "expired",
                "error_message": "Payment expired (timeout)",
            },
        )
        if payment["payment_type"] == "leasing_monthly":
            await special_equipment_repo.clear_schedule_payment(
                session,
                _special_equipment_schedule_id(payment),
                payment["id"],
            )
        is_preorder = payment["payment_type"] == "preorder"
        is_unpaid_initial = (
            payment["payment_type"] in {"reservation", "preorder", "full_purchase"}
            and Decimal(str(order["paid_amount"])) == Decimal("0.00")
            and order["status"] == ("preordered" if is_preorder else "payment_pending")
        )
        if is_unpaid_initial:
            await special_equipment_repo.update_order(
                session,
                order["id"],
                {"status": "expired", "hold_expires_at": None},
            )
            if not is_preorder:
                await special_equipment_repo.release_order_allocations_if_unclaimed(
                    session, order["id"]
                )

    expired_orders = await special_equipment_repo.find_expired_initial_orders(
        session,
        now=now,
    )
    for order in expired_orders:
        payments = await special_equipment_repo.list_order_payments(
            session,
            order["id"],
        )
        if any(
            payment.get("payment_method") == "bank_transfer"
            and payment["status"] == "processing"
            for payment in payments
        ):
            continue
        if any(payment["status"] == "completed" for payment in payments):
            continue
        for payment in payments:
            if payment["status"] not in {"pending", "processing"}:
                continue
            await special_equipment_repo.update_payment(
                session,
                payment["id"],
                {
                    "status": "expired",
                    "error_message": "Payment expired (checkout hold timeout)",
                },
            )
        await special_equipment_repo.update_order(
            session,
            order["id"],
            {"status": "expired", "hold_expires_at": None},
        )
        await special_equipment_repo.release_order_allocations_if_unclaimed(
            session, order["id"]
        )


async def get_payment_status(
    payment_id: UUID,
    session: AsyncSession,
) -> PaymentStatusDetails | None:
    """Get current payment status for frontend polling."""
    payment = await repo.get_payment_by_id(session, payment_id)
    if not payment:
        return None
    return PaymentStatusDetails(
        id=payment["id"],
        status=payment["status"],
        fiscal_status=payment.get("fiscal_status"),
        receipt_url=payment.get("receipt_url"),
        error_message=payment.get("error_message"),
        paid_at=payment.get("paid_at"),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _encode_form(params: dict) -> bytes:
    from urllib.parse import urlencode
    return urlencode(params).encode()
