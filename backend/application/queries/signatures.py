"""Read-side queries for signature_requests (personal cabinet)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import signature_request_repository as repo
from infrastructure.repositories import (
    sopd_operator_snapshot_repository as snapshot_repo,
)
from infrastructure.repositories import sopd_revoke_repository as revoke_repo


@dataclass(frozen=True)
class ListMySignaturesQuery:
    user_id: UUID
    statuses: list[str] | None = None


async def handle_list_my_signatures(
    query: ListMySignaturesQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    items = cast(
        "list[dict[str, Any]]",
        await repo.list_for_user(
            session, user_id=query.user_id, statuses=query.statuses
        ),
    )
    for item in items:
        if item.get("document_type") == repo.DOC_TYPE_SOPD:
            await _attach_sopd_operator_statuses(session, item)
    return items


async def _attach_sopd_operator_statuses(
    session: AsyncSession, item: dict[str, Any]
) -> None:
    if item["status"] == repo.STATUS_PENDING:
        item["sopd_operators"] = []
        item["sopd_revoke_summary"] = None
        return
    snapshot = await snapshot_repo.get_by_signature_request_id(session, item["id"])
    if snapshot is None:
        item["sopd_operators"] = []
        item["sopd_revoke_summary"] = None
        return

    facts = await revoke_repo.list_revoked_operators(
        session, signature_request_id=item["id"]
    )
    revoked_lc = {
        fact["leasing_company_id"]: fact
        for fact in facts
        if fact["operator_type"] == revoke_repo.TYPE_LEASING_COMPANY
        and fact.get("leasing_company_id") is not None
    }
    operators: list[dict[str, Any]] = []
    active_lc_ids: list[str] = []

    for company in snapshot["leasing_companies"]:
        operator = _operator_row(
            item,
            source=company,
            operator_type=revoke_repo.TYPE_LEASING_COMPANY,
            fact=revoked_lc.get(_uuid_value(company.get("id"))),
        )
        operators.append(operator)
        if operator["status"] == "active":
            active_lc_ids.append(str(company["id"]))

    revoked_count = sum(1 for operator in operators if operator["status"] == "revoked")
    item["sopd_operators"] = operators
    item["sopd_revoke_summary"] = {
        "has_partial_revoke": item["status"] != repo.STATUS_REVOKED
        and revoked_count > 0,
        "revoked_count": revoked_count,
        "active_count": len(operators) - revoked_count,
        "active_leasing_company_ids": active_lc_ids,
    }


def _operator_row(
    signature: dict[str, Any],
    *,
    source: dict[str, Any],
    operator_type: str,
    fact: dict[str, Any] | None,
) -> dict[str, Any]:
    is_legacy_full_revoke = signature["status"] == repo.STATUS_REVOKED and fact is None
    status = "revoked" if fact is not None or is_legacy_full_revoke else "active"
    revoke_request_id = fact.get("revoke_request_id") if fact else None
    document_s3_key = fact.get("document_s3_key") if fact else None
    download_url = (
        _revoke_document_download_url(signature["id"], revoke_request_id)
        if revoke_request_id and document_s3_key
        else None
    )
    return {
        "operator_type": operator_type,
        "id": str(source.get("id") or ""),
        "name": source.get("name"),
        "inn": source.get("inn"),
        "status": status,
        "revoked_at": (
            fact.get("confirmed_at")
            if fact
            else signature.get("revoked_at")
            if is_legacy_full_revoke
            else None
        ),
        "revoke_request_id": str(revoke_request_id) if revoke_request_id else None,
        "revoke_document_s3_key": document_s3_key,
        "revoke_document_download_url": download_url,
        "leasing_company_ids": source.get("leasing_company_ids") or [],
        "leasing_companies": source.get("leasing_companies") or [],
    }


def _uuid_value(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _revoke_document_download_url(
    signature_request_id: UUID, revoke_request_id: UUID
) -> str:
    return (
        f"/api/v1/signatures/{signature_request_id}/"
        f"revoke-documents/{revoke_request_id}/download"
    )
