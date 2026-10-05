"""Payment webhook routes: FastAPI port of Express payment.routes.js."""
import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_db
from infrastructure.services import modulkassa, payment_gateway
from infrastructure.services import special_equipment_payment_callbacks as callbacks
from infrastructure.services.payment_models import (
    ModulbankWebhookPayload,
    ModulkassaWebhookPayload,
)
from presentation.schemas.payments import WebhookResponse

logger = logging.getLogger("carcraft-backend")

router = APIRouter()


def _webhook_error_response(error_code: str) -> JSONResponse:
    return JSONResponse(content={"ok": False, "processed": False, "error_code": error_code})


def _safe_validation_error_shape(exc: ValidationError) -> dict[str, Any]:
    """Return diagnostics without rejected values or user-controlled field names."""

    errors = exc.errors(include_url=False, include_input=False)
    return {
        "count": len(errors),
        "types": sorted({str(error.get("type") or "unknown") for error in errors}),
    }


async def _read_webhook_payload(request: Request) -> dict[str, Any] | None:
    """Parse JSON/form input without letting malformed bodies escape as 500."""

    try:
        content_type = getattr(request, "headers", {}).get("content-type", "")
        if "application/json" in content_type or not content_type:
            payload = await request.json()
        else:
            payload = dict(await request.form())
    except Exception:
        logger.warning("Webhook body parsing failed")
        return None
    return payload if isinstance(payload, dict) else None


def _valid_modulkassa_callback_token(request: Request) -> bool:
    if not modulkassa.callback_auth_required():
        return True
    expected = payment_gateway.settings.modulkassa_callback_token
    if not expected:
        return False
    received = (
        request.headers.get("X-Modulkassa-Callback-Token")
        or request.query_params.get("token")
        or ""
    )
    return hmac.compare_digest(received, expected)


@router.post(
    "/webhook/modulbank",
    response_model=WebhookResponse,
    include_in_schema=False,
    summary="Webhook ModulBank",
    description=(
        "Принимает callback от ModulBank, проверяет подпись и всегда отвечает HTTP 200, "
        "чтобы платёжный шлюз не ретраил запрос по нашим внутренним ошибкам."
    ),
)
async def webhook_modulbank(  # noqa: PLR0911, PLR0912 -- always-200 states
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """ModulBank payment callback — no JWT auth, signature-verified internally."""
    raw_payload = await _read_webhook_payload(request)
    if raw_payload is None:
        return _webhook_error_response("INVALID_PAYLOAD")

    try:
        callback_data = ModulbankWebhookPayload.model_validate(raw_payload)
    except ValidationError as exc:
        logger.warning(
            "ModulBank webhook payload validation failed errors=%s",
            _safe_validation_error_shape(exc),
        )
        return _webhook_error_response("INVALID_PAYLOAD")

    is_special = callbacks.is_special_equipment_callback(callback_data)
    if is_special:
        inbox: dict[str, Any] | None = None
        lease: dict[str, Any] | None = None
        inbox_committed = False
        try:
            inbox, _created = await callbacks.persist_verified_callback(
                callback_data,
                session,
            )
            # Durability boundary: callback survives every later exception.
            await session.commit()
            inbox_committed = True
            if inbox["status"] in {"processed", "manual_review"}:
                return JSONResponse(
                    content={
                        "ok": True,
                        "processed": inbox["status"] == "processed",
                        "manual_review": inbox["status"] == "manual_review",
                        "replay": True,
                    }
                )
            claimed = await callbacks.claim_callbacks(
                session,
                inbox_id=inbox["id"],
                limit=1,
            )
            await session.commit()
            if not claimed:
                return JSONResponse(
                    content={"ok": True, "processed": False, "queued": True}
                )
            lease = claimed[0]
            result, fiscalization_payment_ids = (
                await callbacks.process_claimed_callback(
                    session,
                    inbox_id=lease["id"],
                    lease_token=lease["lease_token"],
                )
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if lease is not None:
                try:
                    await callbacks.mark_callback_retry(
                        session,
                        inbox_id=lease["id"],
                        lease_token=lease["lease_token"],
                        error=exc,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Failed to release special-equipment callback lease"
                    )
            logger.exception("Special-equipment ModulBank callback queued")
            # A verified row is already committed and the task sweep recovers it.
            if inbox_committed:
                return JSONResponse(
                    content={"ok": True, "processed": False, "queued": True}
                )
            return _webhook_error_response("PROCESSING_ERROR")
    else:
        try:
            result, fiscalization_payment_ids = (
                await payment_gateway.handle_payment_callback(
                    callback_data,
                    session,
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("ModulBank webhook error")
            # Always 200 — prevent ModulBank from retrying on our errors
            return _webhook_error_response("PROCESSING_ERROR")

    # Schedule fiscalization AFTER commit, outside the try-block: we must not
    # roll back an already-committed payment if task scheduling raises.
    for payment_id in fiscalization_payment_ids:
        try:
            if is_special:
                from application.tasks.payments import (
                    fiscalize_special_equipment_payment_task,
                )

                await fiscalize_special_equipment_payment_task.kiq(
                    str(payment_id)
                )
            else:
                payment_gateway.start_fiscalization_task(payment_id)
        except Exception:
            logger.exception("Failed to schedule fiscalization for payment %s", payment_id)
    return JSONResponse(content={"ok": True, **jsonable_encoder(result)})


@router.post(
    "/webhook/modulkassa",
    response_model=WebhookResponse,
    include_in_schema=False,
    summary="Webhook ModulKassa",
    description=(
        "Принимает callback по фискализации от ModulKassa и всегда отвечает HTTP 200, "
        "чтобы внешний сервис не ретраил запрос на наши внутренние ошибки."
    ),
)
async def webhook_modulkassa(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """ModulKassa fiscal receipt callback — no JWT auth."""
    if not _valid_modulkassa_callback_token(request):
        logger.warning("ModulKassa webhook authentication failed")
        return _webhook_error_response("INVALID_AUTH")
    raw_payload = await _read_webhook_payload(request)
    if raw_payload is None:
        return _webhook_error_response("INVALID_PAYLOAD")
    try:
        callback_data = ModulkassaWebhookPayload.model_validate(raw_payload)
    except ValidationError as exc:
        logger.warning(
            "ModulKassa webhook payload validation failed errors=%s",
            _safe_validation_error_shape(exc),
        )
        return _webhook_error_response("INVALID_PAYLOAD")

    try:
        receipt_jobs = await payment_gateway.handle_fiscal_callback(
            callback_data,
            session,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("ModulKassa webhook error")
        return _webhook_error_response("PROCESSING_ERROR")

    # Receipt downloads are untrusted network I/O and therefore start only
    # after fiscal state has committed.  Scheduling failure must never undo a
    # successful fiscal callback; the durable sweep will retry pending rows.
    for payment_id, source_url in receipt_jobs:
        try:
            payment_gateway.start_special_equipment_receipt_task(
                payment_id,
                source_url,
            )
        except Exception:
            logger.exception(
                "Failed to schedule special-equipment receipt ingestion payment=%s",
                payment_id,
            )
    return JSONResponse(content={"ok": True, "processed": True})
