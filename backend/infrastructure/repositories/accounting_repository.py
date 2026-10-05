"""Persistence for accounting metadata.

Repo returns dicts — never ORM objects (see CLAUDE.md layer rules).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.accounting_metadata import AccountingMetadata
from infrastructure.models.companies import Company
from infrastructure.repository_timing import timed_repository


def _to_dict(record: AccountingMetadata) -> dict[str, Any]:
    return {
        "id": record.id,
        "inn": record.inn,
        "company_id": record.company_id,
        "provider_name": record.provider_name,
        "period_years": record.period_years,
        "organization": record.organization,
        "audit_report": record.audit_report,
        "clarification_url": record.clarification_url,
        "year_files": record.year_files,
        "computed_ratios": record.computed_ratios,
        "fetch_status": record.fetch_status,
        "fetch_attempts": record.fetch_attempts,
        "last_fetch_error": record.last_fetch_error,
        "last_fetch_at": (
            str(record.last_fetch_at) if record.last_fetch_at else None
        ),
        "is_active": record.is_active,
        "superseded_by": record.superseded_by,
        "created_at": (
            str(record.created_at) if record.created_at else None
        ),
        "updated_at": (
            str(record.updated_at) if record.updated_at else None
        ),
    }

@timed_repository
async def get_by_inn(
    session: AsyncSession, inn: str
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(AccountingMetadata).where(AccountingMetadata.inn == inn)
    )
    record = result.scalars().first()
    if record is None:
        return None
    return _to_dict(record)

@timed_repository
async def _get_company_id(session: AsyncSession, inn: str) -> UUID | None:
    result = await session.execute(
        sa.select(Company.id).where(Company.inn == inn)
    )
    return result.scalar_one_or_none()

@timed_repository
async def upsert_metadata(
    session: AsyncSession,
    *,
    inn: str,
    provider_name: str,
    period_years: list[int],
    organization: dict[str, Any],
    audit_report: dict[str, Any] | None,
    clarification_url: str | None,
    year_files: list[dict[str, Any]],
    computed_ratios: list[dict[str, Any]],
) -> dict[str, Any]:
    record = (
        await session.execute(
            sa.select(AccountingMetadata).where(AccountingMetadata.inn == inn)
        )
    ).scalars().first()
    if record is None:
        record = AccountingMetadata(
            inn=inn,
            provider_name=provider_name,
            fetch_status="pending",
            fetch_attempts=0,
            is_active=True,
        )
        session.add(record)

    record.provider_name = provider_name
    record.company_id = await _get_company_id(session, inn)
    record.period_years = period_years
    record.organization = organization
    record.audit_report = audit_report
    record.clarification_url = clarification_url
    record.year_files = year_files
    record.computed_ratios = computed_ratios
    record.fetch_status = "success"
    record.fetch_attempts = int(record.fetch_attempts or 0) + 1
    record.last_fetch_error = None
    cast("Any", record).last_fetch_at = datetime.now(UTC)
    cast("Any", record).updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)

@timed_repository
async def _get_or_create_stub(
    session: AsyncSession, inn: str, provider_name: str
) -> AccountingMetadata:
    record = (
        await session.execute(
            sa.select(AccountingMetadata).where(AccountingMetadata.inn == inn)
        )
    ).scalars().first()
    if record is None:
        record = AccountingMetadata(
            inn=inn,
            provider_name=provider_name,
            fetch_status="pending",
            fetch_attempts=0,
            is_active=True,
        )
        session.add(record)
    else:
        record.provider_name = provider_name
    return record

@timed_repository
async def mark_not_found(
    session: AsyncSession, inn: str, provider_name: str
) -> dict[str, Any]:
    record = await _get_or_create_stub(session, inn, provider_name)
    record.company_id = await _get_company_id(session, inn)
    record.fetch_status = "not_found"
    record.fetch_attempts = int(record.fetch_attempts or 0) + 1
    record.last_fetch_error = None
    record.last_fetch_at = datetime.now(UTC)
    record.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)

@timed_repository
async def mark_failed(
    session: AsyncSession, inn: str, provider_name: str, error_message: str
) -> dict[str, Any]:
    record = await _get_or_create_stub(session, inn, provider_name)
    record.company_id = await _get_company_id(session, inn)
    record.fetch_status = "failed"
    record.fetch_attempts = int(record.fetch_attempts or 0) + 1
    record.last_fetch_error = error_message
    record.last_fetch_at = datetime.now(UTC)
    record.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)
