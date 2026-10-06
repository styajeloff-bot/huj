
"""Compensation commands and handlers."""
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from domain.entities.compensation import Compensation
from domain.errors import CompensationNotFoundError, TooManyCompensationsError
from domain.services.object_storage import ObjectStorage
from domain.values import (
    CalculationBase,
    CompensationStatus,
    CompensationValueType,
    PayerType,
    PaymentSchedulePeriod,
    PaymentScheduleType,
    RecipientType,
)
from infrastructure.repositories import compensation_repository as repo
from infrastructure.services.document_storage import build_compensation_key

logger = logging.getLogger("carcraft-backend")

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_COMPENSATION_DOCUMENT_SIZE = 10 * 1024 * 1024
_ALLOWED_COMPENSATION_DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".xls", ".xlsx"}
)
_COMPENSATION_DOCUMENT_PURPOSES = frozenset(
    {"acceptance", "rejection", "payment"}
)


@dataclass
class CreateCompensationCommand:
    applied_support_id: UUID
    application_id: uuid.UUID | None
    vehicle_id: UUID | None
    payer: str
    recipient: str
    calculation_base: str
    calculation_base_amount: float | Decimal | None
    value_type: str
    value: float
    source: str = "platform"
    exchange_request_id: UUID | None = None
    fast_deal_id: UUID | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    min_percent: float | None = None
    max_percent: float | None = None
    payment_schedule_type: str = "days_count"
    payment_schedule_period: str | None = None
    payment_schedule_value: str | None = None
    comment: str = ""
    created_by: UUID | None = None


@dataclass
class CreateBulkCompensationsCommand:
    applied_support_id: UUID
    application_id: uuid.UUID | None
    vehicle_id: UUID | None
    compensations: list[dict]
    created_by: UUID | None = None
    source: str = "platform"
    exchange_request_id: UUID | None = None
    fast_deal_id: UUID | None = None


@dataclass
class UpdateCompensationStatusCommand:
    compensation_id: UUID
    status: str
    actor_role: str
    paid_at: datetime | None = None
    documents: list[dict] | None = None
    reason: str | None = None


@dataclass
class CancelSupportCompensationsCommand:
    applied_support_id: UUID


@dataclass
class UploadCompensationDocumentCommand:
    compensation_id: UUID
    actor_user_id: UUID
    actor_role: str
    purpose: str
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class DownloadedCompensationDocument:
    filename: str
    content_type: str
    data: bytes


@dataclass
class RecalculateCompensationsCommand:
    applied_support_id: UUID


async def handle_create_compensation(
    cmd: CreateCompensationCommand, session: AsyncSession
) -> dict:
    applied_support = await repo.get_applied_support_by_id(
        session, cmd.applied_support_id
    )
    if applied_support is None:
        raise ServiceError("Снимок применённой поддержки не найден", 404)
    if (
        cmd.application_id is None
        and cmd.exchange_request_id is None
        and cmd.fast_deal_id is None
    ):
        cmd.application_id = applied_support.get("application_id")
        cmd.exchange_request_id = applied_support.get("exchange_request_id")
        cmd.fast_deal_id = applied_support.get("fast_deal_id")
        if cmd.exchange_request_id is not None:
            cmd.source = "exchange"
        elif cmd.fast_deal_id is not None:
            cmd.source = "fast_deal"
    others = {
        "platform": (cmd.application_id, cmd.exchange_request_id, cmd.fast_deal_id),
        "exchange": (cmd.exchange_request_id, cmd.application_id, cmd.fast_deal_id),
        "fast_deal": (cmd.fast_deal_id, cmd.application_id, cmd.exchange_request_id),
    }
    if cmd.source in others:
        own, *foreign = others[cmd.source]
        if own is None or any(value is not None for value in foreign):
            raise ServiceError("Некорректный источник компенсации", 400)
    else:
        raise ServiceError("Неизвестный источник компенсации", 400)

    existing_count = await repo.count_compensations_for_support(
        session, cmd.applied_support_id
    )
    Compensation.validate_count(existing_count)

    comp = await _build_compensation(
        session=session,
        applied_support_id=cmd.applied_support_id,
        application_id=cmd.application_id,
        vehicle_id=cmd.vehicle_id,
        payer=cmd.payer,
        recipient=cmd.recipient,
        calculation_base=cmd.calculation_base,
        calculation_base_amount=cmd.calculation_base_amount,
        value_type=cmd.value_type,
        value=cmd.value,
        min_amount=cmd.min_amount,
        max_amount=cmd.max_amount,
        min_percent=cmd.min_percent,
        max_percent=cmd.max_percent,
        payment_schedule_type=cmd.payment_schedule_type,
        payment_schedule_period=cmd.payment_schedule_period,
        payment_schedule_value=cmd.payment_schedule_value,
        comment=cmd.comment,
    )

    data = {
        "applied_support_id": cmd.applied_support_id,
        "application_id": cmd.application_id,
        "exchange_request_id": cmd.exchange_request_id,
        "fast_deal_id": cmd.fast_deal_id,
        "source": cmd.source,
        "vehicle_id": cmd.vehicle_id,
        "payer": cmd.payer,
        "recipient": cmd.recipient,
        "calculation_base": cmd.calculation_base,
        "calculation_base_amount": float(comp.calculation_base_amount),
        "value_type": cmd.value_type,
        "value": float(comp.value),
        "min_amount": float(comp.min_amount) if comp.min_amount is not None else None,
        "max_amount": float(comp.max_amount) if comp.max_amount is not None else None,
        "min_percent": float(comp.min_percent)
        if comp.min_percent is not None
        else None,
        "max_percent": float(comp.max_percent)
        if comp.max_percent is not None
        else None,
        "amount": float(comp.amount),
        "status": comp.status.value,
        "payment_schedule_type": cmd.payment_schedule_type,
        "payment_schedule_period": cmd.payment_schedule_period,
        "payment_schedule_value": cmd.payment_schedule_value,
        "due_date": comp.due_date,
        "comment": cmd.comment,
        "created_by": cmd.created_by,
    }

    result = await repo.create_compensation(session, data)
    from infrastructure.messaging.dwh_events import emit_compensation_changed
    emit_compensation_changed({
        "compensation_id": result["id"],
        "applied_support_id": cmd.applied_support_id,
        "application_id": str(cmd.application_id) if cmd.application_id else None,
        "exchange_request_id": (
            str(cmd.exchange_request_id) if cmd.exchange_request_id else None
        ),
        "fast_deal_id": str(cmd.fast_deal_id) if cmd.fast_deal_id else None,
        "source": cmd.source,
        "vehicle_id": cmd.vehicle_id,
        "payer": cmd.payer,
        "recipient": cmd.recipient,
        "calculation_base": cmd.calculation_base,
        "calculation_base_amount": str(comp.calculation_base_amount),
        "value_type": cmd.value_type,
        "value": str(comp.value),
        "min_amount": str(comp.min_amount) if comp.min_amount else None,
        "max_amount": str(comp.max_amount) if comp.max_amount else None,
        "min_percent": str(comp.min_percent) if comp.min_percent else None,
        "max_percent": str(comp.max_percent) if comp.max_percent else None,
        "amount": str(comp.amount),
        "status": comp.status.value,
        "payment_schedule_type": cmd.payment_schedule_type,
        "payment_schedule_period": cmd.payment_schedule_period,
        "payment_schedule_value": cmd.payment_schedule_value,
        "due_date": _isoformat(comp.due_date),
        "paid_at": _isoformat(comp.paid_at),
        "documents": comp.documents,
        "comment": cmd.comment,
        "created_by": cmd.created_by,
        "created_at": _isoformat(result.get("created_at")),
        "updated_at": _isoformat(result.get("updated_at")),
        "_deleted": False,
    })
    logger.info(
        "Compensation created: id=%s support=%s amount=%s",
        result["id"],
        cmd.applied_support_id,
        comp.amount,
    )
    return cast("dict[str, Any]", result)


async def handle_create_bulk_compensations(
    cmd: CreateBulkCompensationsCommand, session: AsyncSession
) -> dict:
    existing_count = await repo.count_compensations_for_support(
        session, cmd.applied_support_id
    )
    total_needed = existing_count + len(cmd.compensations)
    if total_needed > 4:
        raise TooManyCompensationsError()

    results = []
    for comp_data in cmd.compensations:
        single_cmd = CreateCompensationCommand(
            applied_support_id=cmd.applied_support_id,
            application_id=cmd.application_id,
            vehicle_id=cmd.vehicle_id,
            payer=comp_data["payer"],
            recipient=comp_data["recipient"],
            calculation_base=comp_data["calculation_base"],
            calculation_base_amount=comp_data.get("calculation_base_amount"),
            value_type=comp_data["value_type"],
            value=comp_data["value"],
            source=cmd.source,
            exchange_request_id=cmd.exchange_request_id,
            fast_deal_id=cmd.fast_deal_id,
            min_amount=comp_data.get("min_amount"),
            max_amount=comp_data.get("max_amount"),
            min_percent=comp_data.get("min_percent"),
            max_percent=comp_data.get("max_percent"),
            payment_schedule_type=comp_data.get("payment_schedule_type", "days_count"),
            payment_schedule_period=comp_data.get("payment_schedule_period"),
            payment_schedule_value=comp_data.get("payment_schedule_value"),
            comment=comp_data.get("comment", ""),
            created_by=cmd.created_by,
        )
        result = await handle_create_compensation(single_cmd, session)
        results.append(result)

    return {"compensations": results}


async def handle_update_compensation_status(
    cmd: UpdateCompensationStatusCommand, session: AsyncSession
) -> dict:
    row = await repo.get_compensation_by_id(session, cmd.compensation_id)
    if not row:
        raise CompensationNotFoundError(cmd.compensation_id)

    comp = Compensation.from_dict(row)

    update_data: dict[str, Any]

    if cmd.status == CompensationStatus.ACCEPTED.value:
        if cmd.actor_role != "carcraft_employee" and row["payer"] != cmd.actor_role:
            raise ServiceError(
                "Акцептовать компенсацию может только плательщик", 403
            )
        comp.accept(comment=cmd.reason, documents=cmd.documents)
        update_data = {
            "status": comp.status.value,
            "acceptance_comment": cmd.reason,
            "documents": comp.documents,
        }
    elif cmd.status == CompensationStatus.REJECTED.value:
        if cmd.actor_role != "carcraft_employee" and row["payer"] != cmd.actor_role:
            raise ServiceError(
                "Отказать по компенсации может только плательщик", 403
            )
        comp.reject(comment=cmd.reason, documents=cmd.documents)
        update_data = {
            "status": comp.status.value,
            "rejection_comment": cmd.reason,
            "documents": comp.documents,
        }
    elif cmd.status == CompensationStatus.PAID.value:
        if cmd.actor_role != "carcraft_employee" and row["payer"] != cmd.actor_role:
            raise ServiceError(
                "Отметить компенсацию оплаченной может только плательщик", 403
            )
        comp.mark_paid(documents=cmd.documents, paid_at=cmd.paid_at)
        update_data = {
            "status": comp.status.value,
            "paid_at": comp.paid_at,
            "documents": comp.documents,
        }
    elif cmd.status == CompensationStatus.CANCELLED.value:
        if cmd.actor_role != "carcraft_employee":
            raise ServiceError(
                "Отменять компенсации вручную может только администратор", 403
            )
        comp.cancel()
        update_data = {"status": comp.status.value}
    else:
        raise ServiceError(
            "Через API доступны статусы accepted, rejected, paid и cancelled", 400
        )

    result = await repo.update_compensation(session, cmd.compensation_id, update_data)
    if not result:
        raise CompensationNotFoundError(cmd.compensation_id)

    from infrastructure.messaging.dwh_events import emit_compensation_changed
    emit_compensation_changed({
        "compensation_id": cmd.compensation_id,
        "applied_support_id": result.get("applied_support_id"),
        "application_id": str(result.get("application_id")) if result.get("application_id") else None,
        "exchange_request_id": (
            str(result.get("exchange_request_id"))
            if result.get("exchange_request_id")
            else None
        ),
        "fast_deal_id": (
            str(result.get("fast_deal_id")) if result.get("fast_deal_id") else None
        ),
        "source": result.get("source", "platform"),
        "vehicle_id": result.get("vehicle_id"),
        "payer": result.get("payer"),
        "recipient": result.get("recipient"),
        "calculation_base": result.get("calculation_base"),
        "calculation_base_amount": str(result.get("calculation_base_amount")) if result.get("calculation_base_amount") else None,
        "value_type": result.get("value_type"),
        "value": str(result.get("value")) if result.get("value") else None,
        "min_amount": str(result.get("min_amount")) if result.get("min_amount") else None,
        "max_amount": str(result.get("max_amount")) if result.get("max_amount") else None,
        "min_percent": str(result.get("min_percent")) if result.get("min_percent") else None,
        "max_percent": str(result.get("max_percent")) if result.get("max_percent") else None,
        "amount": str(result.get("amount")) if result.get("amount") else None,
        "status": result.get("status"),
        "payment_schedule_type": result.get("payment_schedule_type"),
        "payment_schedule_period": result.get("payment_schedule_period"),
        "payment_schedule_value": result.get("payment_schedule_value"),
        "due_date": _isoformat(result.get("due_date")),
        "paid_at": _isoformat(result.get("paid_at")),
        "documents": result.get("documents"),
        "comment": result.get("comment"),
        "created_by": result.get("created_by"),
        "created_at": _isoformat(result.get("created_at")),
        "updated_at": _isoformat(result.get("updated_at")),
        "_deleted": False,
    })
    logger.info(
        "Compensation %s status updated to %s", cmd.compensation_id, cmd.status
    )
    return cast("dict[str, Any]", result)


async def handle_upload_compensation_document(
    cmd: UploadCompensationDocumentCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    row = await repo.get_compensation_by_id(session, cmd.compensation_id)
    if not row:
        raise CompensationNotFoundError(cmd.compensation_id)

    _ensure_compensation_document_actor(row, cmd.actor_role)
    _ensure_compensation_document_purpose(row, cmd.purpose)
    _validate_compensation_document(cmd.filename, cmd.data)

    document_id = uuid.uuid4().hex
    safe_name = _safe_filename(cmd.filename)
    storage_name = f"{document_id[:8]}_{safe_name}"
    key = build_compensation_key(cmd.compensation_id, storage_name)
    content_type = cmd.content_type or "application/octet-stream"
    await storage.put(key, cmd.data, content_type)

    return {
        "id": document_id,
        "name": cmd.filename,
        "file_name": cmd.filename,
        "path": (
            f"/api/v1/compensations/{cmd.compensation_id}"
            f"/documents/{document_id}/content"
        ),
        "s3_key": key,
        "content_type": content_type,
        "size": len(cmd.data),
        "purpose": cmd.purpose,
        "uploaded_by": cmd.actor_user_id,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }


async def handle_download_compensation_document(
    *,
    compensation_id: UUID,
    document_id: str,
    actor_role: str,
    actor_company_id: UUID | None,
    session: AsyncSession,
    storage: ObjectStorage,
) -> DownloadedCompensationDocument:
    row = await repo.get_compensation_by_id(
        session,
        compensation_id,
        visible_distributor_id=actor_company_id,
        restrict_to_distributor=actor_role == "distributor",
    )
    if not row:
        raise CompensationNotFoundError(compensation_id)

    _ensure_compensation_document_viewer(row, actor_role)
    doc = _find_compensation_document(row.get("documents") or [], document_id)
    if not doc:
        raise ServiceError("Файл не найден", 404)

    key = str(doc.get("s3_key") or "")
    if not key:
        raise ServiceError("Файл не найден", 404)
    stored = await storage.get(key)
    if stored is None:
        raise ServiceError("Файл не найден", 404)

    return DownloadedCompensationDocument(
        filename=str(doc.get("file_name") or doc.get("name") or "document"),
        content_type=(
            stored.content_type
            or doc.get("content_type")
            or "application/octet-stream"
        ),
        data=stored.data,
    )


def _ensure_compensation_document_actor(row: dict[str, Any], actor_role: str) -> None:
    if actor_role == "carcraft_employee":
        return
    if row.get("payer") == actor_role:
        return
    raise ServiceError("Прикрепить файл может только плательщик", 403)


def _ensure_compensation_document_viewer(row: dict[str, Any], actor_role: str) -> None:
    if actor_role == "carcraft_employee":
        return
    if row.get("payer") == actor_role or row.get("recipient") == actor_role:
        return
    raise ServiceError("Файл не найден", 404)


def _ensure_compensation_document_purpose(row: dict[str, Any], purpose: str) -> None:
    if purpose not in _COMPENSATION_DOCUMENT_PURPOSES:
        raise ServiceError("Некорректный тип документа компенсации", 400)

    status = str(row.get("status") or "")
    if (
        purpose in {"acceptance", "rejection"}
        and status != CompensationStatus.UNDER_REVIEW.value
    ):
        raise ServiceError(
            "Файл акцепта или отказа можно приложить только к компенсации на рассмотрении",
            400,
        )
    if purpose == "payment" and status not in {
        CompensationStatus.ACCEPTED.value,
        CompensationStatus.OVERDUE.value,
    }:
        raise ServiceError(
            "Файл оплаты можно приложить только к принятой или просроченной компенсации",
            400,
        )


def _validate_compensation_document(filename: str, data: bytes) -> None:
    if not data:
        raise ServiceError("Файл пустой", 400)
    if len(data) > _MAX_COMPENSATION_DOCUMENT_SIZE:
        raise ServiceError("Файл превышает допустимый размер 10 МБ", 400)

    ext = ""
    if "." in filename:
        ext = f".{filename.rsplit('.', 1)[1].lower()}"
    if ext not in _ALLOWED_COMPENSATION_DOCUMENT_EXTENSIONS:
        raise ServiceError(
            "Допустимые форматы: PDF, DOC, DOCX, JPG, PNG, XLS, XLSX",
            400,
        )


def _safe_filename(original: str) -> str:
    name = original.strip().split("/")[-1].split("\\")[-1] or "document"
    return _SAFE_FILENAME.sub("_", name)[:120]


def _find_compensation_document(
    documents: list[dict[str, Any]], document_id: str
) -> dict[str, Any] | None:
    for document in documents:
        if str(document.get("id") or "") == document_id:
            return document
    return None


async def handle_cancel_support_compensations(
    cmd: CancelSupportCompensationsCommand, session: AsyncSession
) -> dict:
    cancelled, already_paid = await repo.cancel_compensations_for_support(
        session, cmd.applied_support_id
    )
    warnings = [
        {
            "compensation_id": c["id"],
            "amount": c["amount"],
            "message": (
                "Программа поддержки отменена, но компенсация уже оплачена. "
                "Требуется ручная обработка."
            ),
        }
        for c in already_paid
    ]
    return {
        "cancelled_count": cancelled,
        "already_paid_count": len(already_paid),
        "warnings": warnings,
    }


async def handle_auto_cancel_inactive_support_compensations(
    session: AsyncSession,
) -> dict[str, Any]:
    """Cancel open compensations for inactive support programs."""
    support_ids = await repo.list_inactive_support_ids_with_open_compensations(session)
    cancelled_count = 0
    warnings: list[dict[str, Any]] = []

    for support_id in support_ids:
        result = await handle_cancel_support_compensations(
            CancelSupportCompensationsCommand(applied_support_id=support_id),
            session,
        )
        cancelled_count += int(result["cancelled_count"])
        warnings.extend(result["warnings"])

    return {
        "supports_processed": len(support_ids),
        "cancelled_count": cancelled_count,
        "warnings": warnings,
    }


async def handle_recalculate_compensations(
    cmd: RecalculateCompensationsCommand, session: AsyncSession
) -> list[dict]:
    """Recalculate compensation amounts from the latest support or application context."""
    rows = await repo.get_compensations_for_support(session, cmd.applied_support_id)

    results = []
    for row in rows:
        if row["status"] == CompensationStatus.CANCELLED.value:
            continue

        comp = Compensation.from_dict(row)
        comp.calculation_base_amount = await _resolve_calculation_base_amount(
            session=session,
            applied_support_id=cmd.applied_support_id,
            calculation_base=comp.calculation_base,
            application_id=row.get("application_id"),
            vehicle_id=row.get("vehicle_id"),
            explicit_amount=(
                row.get("calculation_base_amount")
                if row.get("source") == "fast_deal"
                or (row.get("application_id") is None and row.get("vehicle_id") is None)
                else None
            ),
        )
        comp.compute_amount()

        if row["status"] == CompensationStatus.PAID.value:
            result = await repo.update_compensation(
                session,
                row["id"],
                {"calculation_base_amount": float(comp.calculation_base_amount)},
            )
            if result:
                results.append(result)
            continue

        result = await repo.update_compensation(
            session,
            row["id"],
            {
                "calculation_base_amount": float(comp.calculation_base_amount),
                "amount": float(comp.amount),
            },
        )
        if result:
            results.append(result)

    return results


async def handle_auto_recalculate_application_compensations(
    session: AsyncSession,
) -> int:
    """Recalculate all non-cancelled compensations bound to real applications."""
    support_ids = await repo.list_application_bound_support_ids_for_auto_recalculation(
        session
    )
    for support_id in support_ids:
        await handle_recalculate_compensations(
            RecalculateCompensationsCommand(applied_support_id=support_id),
            session,
        )
    return len(support_ids)


async def _build_compensation(
    *,
    session: AsyncSession,
    applied_support_id: UUID,
    application_id: uuid.UUID | None,
    vehicle_id: UUID | None,
    payer: str,
    recipient: str,
    calculation_base: str,
    calculation_base_amount: float | Decimal | None,
    value_type: str,
    value: float,
    min_amount: float | None,
    max_amount: float | None,
    min_percent: float | None,
    max_percent: float | None,
    payment_schedule_type: str,
    payment_schedule_period: str | None,
    payment_schedule_value: str | None,
    comment: str,
) -> Compensation:
    base = CalculationBase(calculation_base)
    comp = Compensation(
        compensation_id=None,
        applied_support_id=applied_support_id,
        payer=PayerType(payer),
        recipient=RecipientType(recipient),
        calculation_base=base,
        calculation_base_amount=await _resolve_calculation_base_amount(
            session=session,
            applied_support_id=applied_support_id,
            calculation_base=base,
            application_id=application_id,
            vehicle_id=vehicle_id,
            explicit_amount=calculation_base_amount,
        ),
        value_type=CompensationValueType(value_type),
        value=Decimal(str(value)),
        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
        max_amount=Decimal(str(max_amount)) if max_amount is not None else None,
        min_percent=Decimal(str(min_percent)) if min_percent is not None else None,
        max_percent=Decimal(str(max_percent)) if max_percent is not None else None,
        payment_schedule_type=PaymentScheduleType(payment_schedule_type),
        payment_schedule_period=(
            PaymentSchedulePeriod(payment_schedule_period)
            if payment_schedule_period
            else None
        ),
        payment_schedule_value=payment_schedule_value,
        comment=comment,
    )
    comp.compute_amount()
    comp.compute_due_date()
    return comp


async def _resolve_calculation_base_amount(
    *,
    session: AsyncSession,
    calculation_base: CalculationBase,
    applied_support_id: UUID,
    application_id: uuid.UUID | None,
    vehicle_id: UUID | None,
    explicit_amount: float | Decimal | None,
) -> Decimal:
    if explicit_amount is not None:
        return Decimal(str(explicit_amount))
    if calculation_base == CalculationBase.SUPPORT_AMOUNT:
        applied_support = await repo.get_applied_support_by_id(
            session, applied_support_id
        )
        if applied_support is None or applied_support.get("support_amount") is None:
            raise ServiceError(
                "Недостаточно данных для расчёта базы 'support_amount'.",
                400,
            )
        return Decimal(str(applied_support["support_amount"]))
    context = await repo.get_calculation_context(
        session,
        applied_support_id=applied_support_id,
        application_id=application_id,
        vehicle_id=vehicle_id,
    )
    amount = cast("Decimal | None", context.get(calculation_base.value))
    if amount is None:
        raise ServiceError(
            (
                "Недостаточно данных для расчёта базы "
                f"'{calculation_base.value}'. Проверьте заявку и автомобиль."
            ),
            400,
        )
    return amount
