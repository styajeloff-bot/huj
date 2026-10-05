"""Human-friendly leasing application number helpers."""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as repo

logger = logging.getLogger("carcraft-backend")


async def assign_display_number_if_missing(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    questionnaire: dict[str, Any] | None = None,
) -> str | None:
    """Generate ``<INN>-<DDMMYY>-<NNN>`` once an application has an INN."""
    if application.get("display_number"):
        return str(application["display_number"])

    application_id = _coerce_uuid(application.get("id"))
    if application_id is None:
        return None

    inn = await _resolve_inn(session, application, questionnaire or {})
    if not inn:
        return None

    display_number = await build_display_number(
        session,
        application_id=application_id,
        inn=inn,
        created_on=_application_date(application),
    )
    await repo.update_display_number(
        session,
        application_id=application_id,
        display_number=display_number,
    )
    logger.info(
        "display_number assigned application_id=%s value=%s",
        application_id,
        display_number,
    )
    return display_number


async def build_display_number(
    session: AsyncSession,
    *,
    inn: str,
    application_id: uuid.UUID | None = None,
    created_on: date_type | None = None,
) -> str:
    del application_id
    number_date = created_on or datetime.now(UTC).date()
    key = f"application_display_number:{inn}:{number_date:%Y-%m-%d}"
    await session.execute(
        sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtextextended(key, 0)))
    )
    max_seq = await repo.max_daily_display_sequence(
        session,
        company_inn=inn,
        created_on=number_date,
    )
    seq = max_seq + 1
    return f"{inn}-{number_date:%d%m%y}-{seq:03d}"


async def _resolve_inn(
    session: AsyncSession,
    application: dict[str, Any],
    questionnaire: dict[str, Any],
) -> str | None:
    company_id = application.get("company_id")
    if company_id is not None:
        inn = await repo.get_company_inn(session, company_id=company_id)
        if inn:
            return inn.strip() or None

    candidate = questionnaire.get("inn")
    if candidate is None:
        return None
    return str(candidate).strip() or None


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _application_date(application: dict[str, Any]) -> date_type | None:
    created_at = application.get("created_at")
    if not isinstance(created_at, datetime):
        return None
    if created_at.tzinfo is not None:
        return created_at.astimezone(UTC).date()
    return created_at.date()
