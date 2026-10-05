"""DWH snapshot / changed event publishers.

Fire-and-forget publishes to Kafka.  The event-worker batch-consumes these
messages and persists them to ClickHouse.

Failure policy: never raise.  DWH is observational — a broken pipe to Kafka
must not block business operations.  Failures are logged at WARNING and
dropped.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from infrastructure.messaging.broker import get_broker
from infrastructure.messaging.topics import (
    APP_VEHICLE_CHANGED,
    APP_VEHICLE_SNAPSHOT,
    CALCULATION_CREATED,
    CALCULATION_SNAPSHOT,
    COMPANY_CHANGED,
    COMPANY_SNAPSHOT,
    COMPENSATION_CHANGED,
    COMPENSATION_SNAPSHOT,
    DOCUMENT_CHANGED,
    DOCUMENT_SNAPSHOT,
    EXCHANGE_BID_CHANGED,
    EXCHANGE_BID_SNAPSHOT,
    EXCHANGE_REQUEST_CHANGED,
    EXCHANGE_REQUEST_SNAPSHOT,
    LCA_CHANGED,
    LCA_SNAPSHOT,
    LEASING_APPLICATION_CHANGED,
    LEASING_APPLICATION_SNAPSHOT,
    PROPOSAL_CHANGED,
    PROPOSAL_SNAPSHOT,
    PURCHASE_ORDER_CHANGED,
    PURCHASE_ORDER_SNAPSHOT,
    QUESTIONNAIRE_CHANGED,
    QUESTIONNAIRE_SNAPSHOT,
    SUPPORT_PROGRAM_CHANGED,
    SUPPORT_PROGRAM_SNAPSHOT,
    USER_CHANGED,
    USER_SNAPSHOT,
    VEHICLE_CHANGED,
    VEHICLE_SNAPSHOT,
)
from infrastructure.metrics import DWH_MESSAGES_PUBLISHED, DWH_PUBLISH_FAILURES

logger = logging.getLogger("carcraft-backend")

_tasks: set[asyncio.Task[None]] = set()


def serialise_dwh_value(value: Any) -> Any:
    """Convert DWH values to the stable JSON shape stored in durable batches."""
    result: Any
    if isinstance(value, UUID):
        result = str(value)
    elif isinstance(value, (datetime, date)):
        result = value.isoformat()
    elif isinstance(value, Decimal):
        result = str(value)
    elif isinstance(value, Enum):
        result = serialise_dwh_value(value.value)
    elif isinstance(value, dict):
        result = {str(k): serialise_dwh_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        result = [serialise_dwh_value(v) for v in value]
    else:
        result = value
    return result


# Kept for existing producer contract tests and internal callers.
_serialise_value = serialise_dwh_value


def _schedule_publish(topic: str, payload: dict[str, Any]) -> None:
    pending_before = len(_tasks)
    serialised = serialise_dwh_value(payload)
    task = asyncio.create_task(_publish(topic, serialised))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    logger.debug(
        "dwh_emit_scheduled topic=%s pending_before=%d pending_after=%d",
        topic,
        pending_before,
        len(_tasks),
    )


async def _publish(topic: str, payload: dict[str, Any]) -> None:
    try:
        await get_broker().publish(payload, topic=topic)
    except Exception as exc:
        DWH_PUBLISH_FAILURES.labels(topic=topic).inc()
        logger.warning("dwh_event_publish_failed topic=%s err=%s", topic, exc)
    else:
        DWH_MESSAGES_PUBLISHED.labels(topic=topic).inc()


def emit(topic: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget publish of a DWH event to Kafka."""
    _schedule_publish(topic, payload)


async def publish_dwh_batch(topic: str, payloads: list[dict[str, Any]]) -> None:
    """Awaited batch publish of DWH events (for use inside taskiq workers).

    Unlike :func:`emit` (fire-and-forget, fit for request handlers), bulk
    importers run in the taskiq worker and must apply backpressure: we await
    each publish so a 600K-row import doesn't schedule hundreds of thousands of
    detached tasks. Raises so durable import orchestration can persist retry
    state instead of silently losing events.
    """
    broker = get_broker()
    for payload in payloads:
        try:
            await broker.publish(serialise_dwh_value(payload), topic=topic)
        except Exception as exc:
            DWH_PUBLISH_FAILURES.labels(topic=topic).inc()
            logger.warning("dwh_batch_publish_failed topic=%s err=%s", topic, exc)
            raise
        else:
            DWH_MESSAGES_PUBLISHED.labels(topic=topic).inc()


# ---------------------------------------------------------------------------
# DWH Payload helpers — denormalize related fields at the source so
# ClickHouse materialized views never need JOIN.
# ---------------------------------------------------------------------------


def build_lca_dwh_payload(
    lca_data: dict[str, Any],
    application_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a denormalized DWH payload for LeasingCompanyApplication.

    Pulls dealer_id, dealer_company_id, client_company_id, display_number,
    vehicle_id, application_status and all financial/meta fields from the
    parent application record.
    """
    payload: dict[str, Any] = {
        "lca_id": lca_data.get("id"),
        "application_id": lca_data.get("application_id"),
        "leasing_company_id": lca_data.get("leasing_company_id"),
        "status": lca_data.get("status"),
        "review_notes": lca_data.get("review_notes"),
        "decision_comment": lca_data.get("decision_comment"),
        "response_pdf_s3_key": lca_data.get("response_pdf_s3_key"),
        "response_pdf_file_name": lca_data.get("response_pdf_file_name"),
        "response_pdf_size": lca_data.get("response_pdf_size"),
        "response_pdf_uploaded_at": lca_data.get("response_pdf_uploaded_at"),
        "submitted_at": lca_data.get("submitted_at"),
        "created_at": lca_data.get("created_at"),
        "updated_at": lca_data.get("updated_at"),
        "_deleted": lca_data.get("_deleted", False),
    }
    if application_data:
        payload["dealer_company_id"] = application_data.get("dealer_company_id")
        payload["distributor_id"] = application_data.get("distributor_id")
        payload["client_company_id"] = application_data.get("company_id")
        payload["display_number"] = application_data.get("display_number")
        payload["vehicle_id"] = application_data.get("vehicle_id")
        payload["application_status"] = application_data.get("status")
        # Financial / meta fields from application
        payload["name"] = application_data.get("name")
        payload["email"] = application_data.get("email")
        payload["total_amount"] = application_data.get("total_amount")
        payload["down_payment"] = application_data.get("down_payment")
        payload["down_payment_percent"] = application_data.get("down_payment_percent")
        payload["lease_term_months"] = application_data.get("lease_term_months")
        payload["monthly_payment"] = application_data.get("monthly_payment")
        payload["total_cost"] = application_data.get("total_cost")
        payload["markup"] = application_data.get("markup")
        payload["rate"] = application_data.get("rate")
        payload["total_interest"] = application_data.get("total_interest")
        payload["buyout_amount"] = application_data.get("buyout_amount")
        payload["vat_refund"] = application_data.get("vat_refund")
        payload["profit_tax_savings"] = application_data.get("profit_tax_savings")
        payload["total_savings"] = application_data.get("total_savings")
        payload["selected_leasing_companies"] = application_data.get("selected_leasing_companies")
        payload["leasing_company_comments"] = application_data.get("leasing_company_comments")
        payload["requested_documents"] = application_data.get("requested_documents")
        payload["questionnaire_completed"] = application_data.get("questionnaire_completed")
        payload["questionnaire_progress"] = application_data.get("questionnaire_progress")
        payload["current_stage"] = application_data.get("current_stage")
    return payload


def build_proposal_dwh_payload(
    proposal_data: dict[str, Any],
    lca_data: dict[str, Any] | None = None,
    application_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a denormalized DWH payload for LeasingProposal.

    Pulls application_id, leasing_company_id, dealer_id, dealer_company_id
    and client_company_id from the parent LCA / Application records.
    """
    payload: dict[str, Any] = {
        "proposal_id": proposal_data.get("id"),
        "leasing_company_application_id": proposal_data.get("leasing_company_application_id"),
        "kind": proposal_data.get("kind"),
        "position": proposal_data.get("position"),
        "total_amount": proposal_data.get("total_amount"),
        "down_payment": proposal_data.get("down_payment"),
        "down_payment_percent": proposal_data.get("down_payment_percent"),
        "lease_term_months": proposal_data.get("lease_term_months"),
        "monthly_payment": proposal_data.get("monthly_payment"),
        "total_cost": proposal_data.get("total_cost"),
        "markup": proposal_data.get("markup"),
        "rate": proposal_data.get("rate"),
        "total_interest": proposal_data.get("total_interest"),
        "buyout_amount": proposal_data.get("buyout_amount"),
        "vat_refund": proposal_data.get("vat_refund"),
        "profit_tax_savings": proposal_data.get("profit_tax_savings"),
        "total_savings": proposal_data.get("total_savings"),
        "client_decision_action": proposal_data.get("client_decision_action"),
        "client_decision_at": proposal_data.get("client_decision_at"),
        "client_decision_comment": proposal_data.get("client_decision_comment"),
        "created_at": proposal_data.get("created_at"),
        "updated_at": proposal_data.get("updated_at"),
        "_deleted": proposal_data.get("_deleted", False),
    }
    if lca_data:
        payload["application_id"] = lca_data.get("application_id")
        payload["leasing_company_id"] = lca_data.get("leasing_company_id")
    if application_data:
        payload["dealer_company_id"] = application_data.get("dealer_company_id")
        payload["distributor_id"] = application_data.get("distributor_id")
        payload["client_company_id"] = application_data.get("company_id")
    return payload


# ---------------------------------------------------------------------------
# LeasingApplication
# ---------------------------------------------------------------------------


def emit_leasing_application_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(LEASING_APPLICATION_SNAPSHOT, payload)


def emit_leasing_application_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(LEASING_APPLICATION_CHANGED, payload)


# ---------------------------------------------------------------------------
# LeasingCompanyApplication
# ---------------------------------------------------------------------------


def emit_lca_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(LCA_SNAPSHOT, payload)


def emit_lca_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(LCA_CHANGED, payload)


# ---------------------------------------------------------------------------
# LeasingProposal
# ---------------------------------------------------------------------------


def emit_proposal_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(PROPOSAL_SNAPSHOT, payload)


def emit_proposal_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(PROPOSAL_CHANGED, payload)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def emit_document_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(DOCUMENT_SNAPSHOT, payload)


def emit_document_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(DOCUMENT_CHANGED, payload)


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------


def emit_vehicle_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(VEHICLE_SNAPSHOT, payload)


def emit_vehicle_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(VEHICLE_CHANGED, payload)


# ---------------------------------------------------------------------------
# ApplicationVehicle
# ---------------------------------------------------------------------------


def emit_app_vehicle_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(APP_VEHICLE_SNAPSHOT, payload)


def emit_app_vehicle_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(APP_VEHICLE_CHANGED, payload)


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


def emit_company_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(COMPANY_SNAPSHOT, payload)


def emit_company_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(COMPANY_CHANGED, payload)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


def emit_user_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(USER_SNAPSHOT, payload)


def emit_user_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(USER_CHANGED, payload)


# ---------------------------------------------------------------------------
# PurchaseOrder
# ---------------------------------------------------------------------------


def emit_purchase_order_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(PURCHASE_ORDER_SNAPSHOT, payload)


def emit_purchase_order_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(PURCHASE_ORDER_CHANGED, payload)


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------


def emit_calculation_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(CALCULATION_SNAPSHOT, payload)


def emit_calculation_created(payload: dict[str, Any]) -> None:
    _schedule_publish(CALCULATION_CREATED, payload)


# ---------------------------------------------------------------------------
# Questionnaire
# ---------------------------------------------------------------------------


def emit_questionnaire_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(QUESTIONNAIRE_SNAPSHOT, payload)


def emit_questionnaire_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(QUESTIONNAIRE_CHANGED, payload)


# ---------------------------------------------------------------------------
# ExchangeRequest
# ---------------------------------------------------------------------------


def emit_exchange_request_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(EXCHANGE_REQUEST_SNAPSHOT, payload)


def emit_exchange_request_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(EXCHANGE_REQUEST_CHANGED, payload)


# ---------------------------------------------------------------------------
# ExchangeBid
# ---------------------------------------------------------------------------


def emit_exchange_bid_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(EXCHANGE_BID_SNAPSHOT, payload)


def emit_exchange_bid_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(EXCHANGE_BID_CHANGED, payload)


# ---------------------------------------------------------------------------
# SupportProgram
# ---------------------------------------------------------------------------


def emit_support_program_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(SUPPORT_PROGRAM_SNAPSHOT, payload)


def emit_support_program_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(SUPPORT_PROGRAM_CHANGED, payload)


# ---------------------------------------------------------------------------
# Compensation
# ---------------------------------------------------------------------------


def emit_compensation_snapshot(payload: dict[str, Any]) -> None:
    _schedule_publish(COMPENSATION_SNAPSHOT, payload)


def emit_compensation_changed(payload: dict[str, Any]) -> None:
    _schedule_publish(COMPENSATION_CHANGED, payload)
