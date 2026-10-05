
"""LC response workflow commands.

The response is two named КП slots (``preliminary`` / ``final``) plus a
PDF attachment plus a final approve/reject decision. The LC opens the
application, fills both slots via the leasing calculator UI (and any
manual overrides), uploads an optional PDF, then submits a decision.

Sessions are committed in the router, never here.
"""
from __future__ import annotations

import contextlib
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.dwh_enrichment import build_lca_payload, build_proposal_payload
from application.errors import ServiceError
from application.notifications.leasing_events import record_leasing_event
from domain.entities.leasing_company_application import (
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_APPROVED_SCORING,
    LCA_STATUS_REJECTED_APPROVED,
    LCA_STATUS_REJECTED_PRESCORING,
    LeasingCompanyApplication,
)
from domain.entities.leasing_proposal import (
    ALL_KINDS,
    LeasingProposal,
)
from domain.errors import (
    LeasingCompanyApplicationNotFoundError,
    LeasingProposalNotFoundError,
    RejectReasonRequiredError,
    ResponsePdfMissingError,
    UnsupportedFileTypeError,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.messaging.dwh_events import (
    emit_lca_changed,
    emit_proposal_changed,
)
from infrastructure.repositories import (
    application_repository as app_repo,
)
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repositories import (
    leasing_proposals_repository as proposals_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_PDF_CONTENT_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "application/x-pdf"}
)
_MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


def _safe_filename(original: str) -> str:
    name = original.strip().split("/")[-1].split("\\")[-1] or "response.pdf"
    return _SAFE_FILENAME.sub("_", name)[:120]


def _build_pdf_key(lc_id: UUID, lca_id: UUID) -> str:
    return f"leasing_responses/lc_{lc_id}/lca_{lca_id}/{uuid.uuid4().hex}.pdf"


async def _resolve_link(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID | None,
) -> LeasingCompanyApplication:
    if leasing_company_id is None:
        raise LeasingCompanyApplicationNotFoundError(application_id)
    if await app_repo.get_by_id(session, application_id, for_update=True) is None:
        raise LeasingCompanyApplicationNotFoundError(application_id)
    raw = await lca_repo.get_link_for_app_and_lc(
        session,
        application_id=application_id,
        leasing_company_id=leasing_company_id,
        for_update=True,
    )
    if raw is None:
        raise LeasingCompanyApplicationNotFoundError(application_id)
    return LeasingCompanyApplication.from_dict(raw)


def _validate_kind(kind: str) -> None:
    if kind not in ALL_KINDS:
        raise LeasingProposalNotFoundError()


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _normalize_proposal_params(
    params: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(params)
    merged = {**(existing or {}), **normalized}

    total_amount = _to_decimal(merged.get("total_amount"))
    total_cost = _to_decimal(merged.get("total_cost"))

    down_payment = _to_decimal(merged.get("down_payment")) or Decimal("0")

    if total_cost is None:
        monthly_payment = _to_decimal(merged.get("monthly_payment"))
        term_months = _to_decimal(merged.get("lease_term_months"))
        buyout_amount = _to_decimal(merged.get("buyout_amount")) or Decimal("0")
        if monthly_payment is not None and term_months is not None:
            total_cost = (
                monthly_payment * term_months
                + down_payment
                + buyout_amount
            )
            normalized["total_cost"] = total_cost

    if total_amount is not None and total_cost is not None:
        normalized["total_interest"] = total_cost - total_amount - down_payment

    return normalized


# ---------------------------------------------------------------------------
# Proposal upsert / delete
# ---------------------------------------------------------------------------


@dataclass
class UpsertProposalCommand:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    kind: str
    params: dict[str, Any]


async def handle_upsert_proposal(
    cmd: UpsertProposalCommand, session: AsyncSession
) -> dict[str, Any]:
    _validate_kind(cmd.kind)
    link = await _resolve_link(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)
    link.ensure_editable()
    existing = await proposals_repo.get_by_lca_and_kind(
        session, lca_id=link.id, kind=cmd.kind
    )
    params = _normalize_proposal_params(cmd.params, existing=existing)
    result = await proposals_repo.upsert_for_lca_and_kind(
        session, lca_id=link.id, kind=cmd.kind, params=params
    )
    lca_data = await lca_repo.get_link_by_id(session, link.id)
    app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
    payload = await build_proposal_payload(session, result, lca_data, app_raw)
    emit_proposal_changed(payload)
    return cast("dict[str, Any]", result)


@dataclass
class DeleteProposalCommand:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    kind: str


async def handle_delete_proposal(
    cmd: DeleteProposalCommand, session: AsyncSession
) -> None:
    _validate_kind(cmd.kind)
    link = await _resolve_link(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)
    link.ensure_editable()
    proposal = await proposals_repo.get_by_lca_and_kind(
        session, lca_id=link.id, kind=cmd.kind
    )
    deleted = await proposals_repo.delete_by_lca_and_kind(
        session, lca_id=link.id, kind=cmd.kind
    )
    if not deleted:
        raise LeasingProposalNotFoundError()
    if proposal is not None:
        lca_data = await lca_repo.get_link_by_id(session, link.id)
        app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
        proposal["_deleted"] = True
        payload = await build_proposal_payload(session, proposal, lca_data, app_raw)
        emit_proposal_changed(payload)


# ---------------------------------------------------------------------------
# Proposal PDF slots
# ---------------------------------------------------------------------------


@dataclass
class UploadProposalPdfCommand:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    kind: str
    file_name: str
    content_type: str
    data: bytes


async def handle_upload_proposal_pdf(
    cmd: UploadProposalPdfCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    _validate_kind(cmd.kind)
    if cmd.content_type not in _PDF_CONTENT_TYPES:
        raise UnsupportedFileTypeError(content_type=cmd.content_type, allowed=list(_PDF_CONTENT_TYPES))
    if not cmd.data:
        raise ServiceError("Файл пуст", status_code=400)
    if len(cmd.data) > _MAX_PDF_BYTES:
        raise ServiceError("Файл превышает лимит 10 МБ", status_code=413)
    link = await _resolve_link(
        session, application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)
    link.ensure_editable()
    proposal = await proposals_repo.get_by_lca_and_kind(session, lca_id=link.id, kind=cmd.kind)
    if proposal is None:
        raise LeasingProposalNotFoundError()
    safe_name = _safe_filename(cmd.file_name)
    s3_key = f"leasing_responses/lc_{cmd.actor_leasing_company_id}/lca_{link.id}/{cmd.kind}/{uuid.uuid4().hex}.pdf"
    await storage.put(s3_key, cmd.data, "application/pdf")
    updated = await proposals_repo.attach_pdf_for_lca_and_kind(
        session, lca_id=link.id, kind=cmd.kind, s3_key=s3_key,
        file_name=safe_name, file_size=len(cmd.data),
    )
    if updated is None:
        raise LeasingProposalNotFoundError()
    previous_key = proposal.get("pdf_s3_key")
    if previous_key and previous_key != s3_key:
        with contextlib.suppress(Exception):
            await storage.delete(str(previous_key))
    return {"file_name": safe_name, "file_size": len(cmd.data), "uploaded_at": updated["pdf_uploaded_at"]}


@dataclass
class RemoveProposalPdfCommand:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    kind: str


async def handle_remove_proposal_pdf(
    cmd: RemoveProposalPdfCommand, session: AsyncSession, storage: ObjectStorage
) -> None:
    _validate_kind(cmd.kind)
    link = await _resolve_link(
        session, application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)
    link.ensure_editable()
    previous = await proposals_repo.detach_pdf_for_lca_and_kind(session, lca_id=link.id, kind=cmd.kind)
    if previous is None or not previous.get("pdf_s3_key"):
        raise ResponsePdfMissingError()
    with contextlib.suppress(Exception):
        await storage.delete(str(previous["pdf_s3_key"]))


async def handle_get_proposal_pdf(
    application_id: uuid.UUID, actor_leasing_company_id: UUID | None, kind: str,
    session: AsyncSession, storage: ObjectStorage,
) -> tuple[bytes, str]:
    _validate_kind(kind)
    link = await _resolve_link(
        session, application_id=application_id,
        leasing_company_id=actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=actor_leasing_company_id)
    proposal = await proposals_repo.get_by_lca_and_kind(session, lca_id=link.id, kind=kind)
    if proposal is None or not proposal.get("pdf_s3_key"):
        raise ResponsePdfMissingError()
    obj = await storage.get(str(proposal["pdf_s3_key"]))
    if obj is None:
        raise ResponsePdfMissingError()
    return obj.data, str(proposal.get("pdf_file_name") or "proposal.pdf")


# ---------------------------------------------------------------------------
# Response PDF
# ---------------------------------------------------------------------------


@dataclass
class UploadResponsePdfCommand:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None
    file_name: str
    content_type: str
    data: bytes


async def handle_upload_response_pdf(
    cmd: UploadResponsePdfCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict[str, Any]:
    if cmd.content_type not in _PDF_CONTENT_TYPES:
        raise UnsupportedFileTypeError(
            content_type=cmd.content_type, allowed=list(_PDF_CONTENT_TYPES)
        )
    if not cmd.data:
        raise ServiceError("Файл пуст", status_code=400)
    if len(cmd.data) > _MAX_PDF_BYTES:
        raise ServiceError("Файл превышает лимит 10 МБ", status_code=413)

    actor_leasing_company_id = cmd.actor_leasing_company_id
    if actor_leasing_company_id is None:
        raise LeasingCompanyApplicationNotFoundError(cmd.application_id)

    link = await _resolve_link(
        session,
        application_id=cmd.application_id,
        leasing_company_id=actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=actor_leasing_company_id)
    link.ensure_editable()

    safe_name = _safe_filename(cmd.file_name)
    s3_key = _build_pdf_key(actor_leasing_company_id, link.id)
    await storage.put(s3_key, cmd.data, "application/pdf")

    previous_key = link.response_pdf_s3_key
    await lca_repo.attach_response_pdf(
        session,
        link_id=link.id,
        s3_key=s3_key,
        file_name=safe_name,
        file_size=len(cmd.data),
    )
    if previous_key and previous_key != s3_key:
        with contextlib.suppress(Exception):
            await storage.delete(previous_key)

    updated = await lca_repo.get_link_by_id(session, link.id)
    app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
    if updated is not None:
        payload = await build_lca_payload(session, updated, app_raw)
        emit_lca_changed(payload)

    return {
        "s3_key": s3_key,
        "file_name": safe_name,
        "file_size": len(cmd.data),
    }


@dataclass
class RemoveResponsePdfCommand:
    application_id: uuid.UUID
    actor_leasing_company_id: UUID | None


async def handle_remove_response_pdf(
    cmd: RemoveResponsePdfCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> None:
    link = await _resolve_link(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)
    link.ensure_editable()
    if link.response_pdf_s3_key is None:
        raise ResponsePdfMissingError()
    snapshot = await lca_repo.detach_response_pdf(session, link_id=link.id)
    key = (snapshot or {}).get("s3_key")
    if key:
        with contextlib.suppress(Exception):
            await storage.delete(key)

    updated = await lca_repo.get_link_by_id(session, link.id)
    app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
    if updated is not None:
        payload = await build_lca_payload(session, updated, app_raw)
        emit_lca_changed(payload)


# ---------------------------------------------------------------------------
# Final decision (approve / reject)
# ---------------------------------------------------------------------------


@dataclass
class SubmitDecisionCommand:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_leasing_company_id: UUID | None
    action: str  # "approve" | "reject"
    decision_comment: str | None
    kind: str = "final"  # "preliminary" | "final"


async def handle_submit_decision(
    cmd: SubmitDecisionCommand, session: AsyncSession
) -> dict[str, Any]:
    link = await _resolve_link(
        session,
        application_id=cmd.application_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    link.ensure_owned_by_lc(leasing_company_id=cmd.actor_leasing_company_id)

    proposals_raw = await proposals_repo.list_by_lca(session, link.id)
    proposals = [LeasingProposal.from_dict(p) for p in proposals_raw]

    action = cmd.action.lower().strip()
    kind = (cmd.kind or "final").lower().strip()
    if kind not in {"preliminary", "final"}:
        raise ServiceError(
            f"Неизвестный тип КП: {kind!r}", status_code=400
        )
    if action == "reject" and not (cmd.decision_comment or "").strip():
        raise RejectReasonRequiredError()
    link.ensure_can_submit_decision(action, proposals=proposals, kind=kind)

    is_preliminary_approve = action == "approve" and kind == "preliminary"
    if action == "approve":
        if kind == "preliminary":
            new_status = LCA_STATUS_APPROVED_SCORING
        else:
            new_status = LCA_STATUS_APPROVED_FINAL
    elif kind == "preliminary":
        new_status = LCA_STATUS_REJECTED_PRESCORING
    else:
        new_status = LCA_STATUS_REJECTED_APPROVED

    old_status = link.status
    if is_preliminary_approve:
        # Preliminary submission keeps the LCA editable so the LC can still
        # work on the final КП afterwards. ``submitted_at`` stays null.
        await lca_repo.submit_prescoring(
            session,
            link_id=link.id,
            decision_comment=cmd.decision_comment,
        )
    else:
        await lca_repo.submit_decision(
            session,
            link_id=link.id,
            new_status=new_status,
            decision_comment=cmd.decision_comment,
        )
    await hist_repo.append_lca_status_history(
        session,
        lca_id=link.id,
        application_id=cmd.application_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=cmd.actor_user_id,
        decision_comment=cmd.decision_comment,
    )
    updated = await lca_repo.get_link_by_id(session, link.id)
    app_raw = await app_repo.get_by_id(session, cmd.application_id) if cmd.application_id else None
    if updated is not None:
        payload = await build_lca_payload(session, updated, app_raw)
        emit_lca_changed(payload)
    lc_name = (
        await lca_repo.get_leasing_company_display_name(
            session, link.leasing_company_id
        )
        if link.leasing_company_id
        else None
    )
    if app_raw is not None:
        await record_leasing_event(
            session, application=app_raw,
            event_type="leasing.company_decision_received",
            actor_user_id=cmd.actor_user_id,
            previous_values={"lca_status": old_status},
            new_values={"lca_status": new_status},
            payload={
                "leasing_company_id": link.leasing_company_id,
                "leasing_company_application_id": link.id,
                "proposal_kind": kind,
            },
        )
    return {
        "leasing_company_application_id": link.id,
        "leasing_company_id": link.leasing_company_id,
        "leasing_company_name": lc_name,
        "application_id": link.application_id,
        "decision": new_status,
    }


__all__ = [
    "DeleteProposalCommand",
    "RemoveResponsePdfCommand",
    "SubmitDecisionCommand",
    "UploadResponsePdfCommand",
    "UpsertProposalCommand",
    "handle_delete_proposal",
    "handle_remove_response_pdf",
    "handle_submit_decision",
    "handle_upload_response_pdf",
    "handle_upsert_proposal",
]
