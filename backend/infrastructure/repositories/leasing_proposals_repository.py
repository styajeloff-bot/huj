"""Persistence for ``leasing_proposals`` (commercial proposals / КП).

Async, dict-only — repos must not leak ORM objects to the application
layer (CLAUDE.md). Two named slots per LCA: ``preliminary`` and
``final``; UNIQUE constraint at the DB level enforces "one of each".
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_company_application import (
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
    LCA_STATUS_APPROVED_SCORING,
    LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
    LCA_STATUS_SELECTED_LC,
)
from infrastructure.models.applications import (
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.repository_timing import timed_repository

_PRELIMINARY_APPROVAL_STATUSES: tuple[str, ...] = (
    LCA_STATUS_APPROVED_SCORING,
    LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
)
_FINAL_APPROVAL_STATUSES: tuple[str, ...] = (
    LCA_STATUS_APPROVED_FINAL,
    LCA_STATUS_APPROVED_FINAL_ANOTHER_COND,
    LCA_STATUS_SELECTED_LC,
)
_REQUIRED_OFFER_FIELDS: tuple[Any, ...] = (
    LeasingProposal.total_amount,
    LeasingProposal.down_payment,
    LeasingProposal.down_payment_percent,
    LeasingProposal.lease_term_months,
    LeasingProposal.monthly_payment,
)


def _to_dict(row: LeasingProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "leasing_company_application_id": row.leasing_company_application_id,
        "kind": row.kind,
        "position": row.position,
        "total_amount": row.total_amount,
        "down_payment": row.down_payment,
        "down_payment_percent": row.down_payment_percent,
        "lease_term_months": row.lease_term_months,
        "monthly_payment": row.monthly_payment,
        "total_cost": row.total_cost,
        "markup": row.markup,
        "rate": row.rate,
        "total_interest": row.total_interest,
        "buyout_amount": row.buyout_amount,
        "vat_refund": row.vat_refund,
        "profit_tax_savings": row.profit_tax_savings,
        "total_savings": row.total_savings,
        "client_decision_action": row.client_decision_action,
        "client_decision_at": row.client_decision_at,
        "client_decision_comment": row.client_decision_comment,
        "pdf_s3_key": row.pdf_s3_key,
        "pdf_file_name": row.pdf_file_name,
        "pdf_size": row.pdf_size,
        "pdf_uploaded_at": row.pdf_uploaded_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _lca_to_dict(row: LeasingCompanyApplication) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "leasing_company_id": row.leasing_company_id,
        "status": row.status,
        "review_notes": row.review_notes,
        "decision_comment": row.decision_comment,
        "response_pdf_s3_key": row.response_pdf_s3_key,
        "response_pdf_file_name": row.response_pdf_file_name,
        "response_pdf_size": row.response_pdf_size,
        "response_pdf_uploaded_at": row.response_pdf_uploaded_at,
        "submitted_at": row.submitted_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

_PARAM_KEYS: frozenset[str] = frozenset(
    {
        "total_amount",
        "down_payment",
        "down_payment_percent",
        "lease_term_months",
        "monthly_payment",
        "total_cost",
        "markup",
        "rate",
        "total_interest",
        "buyout_amount",
        "vat_refund",
        "profit_tax_savings",
        "total_savings",
    }
)

@timed_repository
async def list_by_lca(
    session: AsyncSession, lca_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        sa.select(LeasingProposal)
        .where(LeasingProposal.leasing_company_application_id == lca_id)
        .order_by(LeasingProposal.kind.asc(), LeasingProposal.id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_dict(r) for r in rows]


@timed_repository
async def list_approval_offers(
    session: AsyncSession, *, application_id: UUID, kind: str
) -> list[dict[str, Any]]:
    statuses = (
        _PRELIMINARY_APPROVAL_STATUSES
        if kind == "preliminary"
        else _FINAL_APPROVAL_STATUSES
    )
    stmt = (
        sa.select(
            LeasingProposal,
            LeasingCompanyApplication,
            LeasingCompany.id.label("lc_id"),
            Company.name.label("lc_name"),
            Company.inn.label("lc_inn"),
        )
        .join(
            LeasingCompanyApplication,
            LeasingCompanyApplication.id
            == LeasingProposal.leasing_company_application_id,
        )
        .join(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyApplication.leasing_company_id,
            isouter=True,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(
            LeasingCompanyApplication.application_id == application_id,
            LeasingCompanyApplication.leasing_company_id.is_not(None),
            LeasingCompanyApplication.status.in_(statuses),
            LeasingProposal.kind == kind,
            *[field.is_not(None) for field in _REQUIRED_OFFER_FIELDS],
        )
        .order_by(
            LeasingProposal.position.asc(),
            LeasingProposal.id.asc(),
        )
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "lca": _lca_to_dict(lca),
            "leasing_company": {
                "id": lc_id,
                "name": lc_name,
                "inn": lc_inn,
            },
            "proposal": _to_dict(proposal),
        }
        for proposal, lca, lc_id, lc_name, lc_inn in rows
    ]


@timed_repository
async def get_by_lca_and_kind(
    session: AsyncSession, *, lca_id: UUID, kind: str
) -> dict[str, Any] | None:
    stmt = sa.select(LeasingProposal).where(
        LeasingProposal.leasing_company_application_id == lca_id,
        LeasingProposal.kind == kind,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_dict(row)

@timed_repository
async def upsert_for_lca_and_kind(
    session: AsyncSession,
    *,
    lca_id: UUID,
    kind: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Insert or update the proposal of the given ``kind`` under ``lca_id``.

    Filters params to known keys; preserves untouched fields on update.
    """
    row = (
        await session.execute(
            sa.select(LeasingProposal).where(
                LeasingProposal.leasing_company_application_id == lca_id,
                LeasingProposal.kind == kind,
            )
        )
    ).scalar_one_or_none()
    safe = {k: v for k, v in params.items() if k in _PARAM_KEYS}
    if row is None:
        row = LeasingProposal(
            leasing_company_application_id=lca_id,
            kind=kind,
            **safe,
        )
        session.add(row)
    else:
        for key, value in safe.items():
            setattr(row, key, value)
        cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(row)

@timed_repository
async def attach_pdf_for_lca_and_kind(
    session: AsyncSession,
    *,
    lca_id: UUID,
    kind: str,
    s3_key: str,
    file_name: str,
    file_size: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.select(LeasingProposal).where(
                LeasingProposal.leasing_company_application_id == lca_id,
                LeasingProposal.kind == kind,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.pdf_s3_key = s3_key
    row.pdf_file_name = file_name
    row.pdf_size = file_size
    row.pdf_uploaded_at = datetime.now(UTC)
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(row)


@timed_repository
async def detach_pdf_for_lca_and_kind(
    session: AsyncSession, *, lca_id: UUID, kind: str
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.select(LeasingProposal).where(
                LeasingProposal.leasing_company_application_id == lca_id,
                LeasingProposal.kind == kind,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    previous = _to_dict(row)
    row.pdf_s3_key = None
    row.pdf_file_name = None
    row.pdf_size = None
    row.pdf_uploaded_at = None
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return previous


@timed_repository
async def get_by_id(
    session: AsyncSession, proposal_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(LeasingProposal, proposal_id)
    if row is None:
        return None
    return _to_dict(row)

@timed_repository
async def record_client_decision(
    session: AsyncSession,
    *,
    proposal_id: UUID,
    action: str,
    comment: str | None,
) -> dict[str, Any] | None:
    """Stamp the client's accept/reject decision on a КП."""
    row = await session.get(LeasingProposal, proposal_id)
    if row is None:
        return None
    now = datetime.now(UTC)
    row.client_decision_action = action
    row.client_decision_comment = comment
    cast("Any", row).client_decision_at = now
    cast("Any", row).updated_at = now
    await session.flush()
    return _to_dict(row)

@timed_repository
async def clear_client_decision(
    session: AsyncSession,
    *,
    proposal_id: UUID,
) -> dict[str, Any] | None:
    """Снять решение клиента с КП (отмена «Принято КП»)."""
    row = await session.get(LeasingProposal, proposal_id)
    if row is None:
        return None
    row.client_decision_action = None
    row.client_decision_comment = None
    cast("Any", row).client_decision_at = None
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(row)

@timed_repository
async def delete_by_lca_and_kind(
    session: AsyncSession, *, lca_id: UUID, kind: str
) -> bool:
    row = (
        await session.execute(
            sa.select(LeasingProposal).where(
                LeasingProposal.leasing_company_application_id == lca_id,
                LeasingProposal.kind == kind,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True

__all__ = [
    "attach_pdf_for_lca_and_kind",
    "clear_client_decision",
    "delete_by_lca_and_kind",
    "detach_pdf_for_lca_and_kind",
    "get_by_id",
    "get_by_lca_and_kind",
    "list_approval_offers",
    "list_by_lca",
    "record_client_decision",
    "upsert_for_lca_and_kind",
]
