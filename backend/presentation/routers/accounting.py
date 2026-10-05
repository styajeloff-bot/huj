"""Accounting-report routes — provider-agnostic bookkeeping data by INN."""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.accounting import (
    RefreshAccountingCommand,
    handle_refresh_accounting,
)
from application.errors import ServiceError, domain_to_http
from application.queries.accounting import (
    GetAccountingReportQuery,
    handle_get_accounting_report,
)
from application.queries.accounting import (
    get_accounting_history as _fetch_accounting_history,
)
from domain.errors import DomainError
from domain.services.accounting_provider import AccountingProvider
from infrastructure.database import get_db
from infrastructure.services.accounting import get_accounting_provider
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.schemas.accounting import (
    AccountingHistoryResponse,
    AccountingReportResponse,
)

logger = logging.getLogger("carcraft-backend")
router = APIRouter()

_INN_PATTERN = re.compile(r"^(?:\d{10}|\d{12})$")


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _validate_inn(inn: str) -> str:
    if not _INN_PATTERN.match(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН")
    return inn


@router.get(
    "/{inn}",
    response_model=AccountingReportResponse,
    summary="Бухгалтерская отчётность по ИНН",
    description=(
        "Возвращает нормализованную бухгалтерскую отчётность (баланс, ОФР, "
        "движение денежных средств) за доступные годы плюс предрассчитанные "
        "финансовые коэффициенты. Кеширует результат на "
        "`accounting_cache_ttl_days` дней. Формат не зависит от конкретного "
        "провайдера. 404 — ФНС не публикует отчётность по этому ИНН "
        "(новая компания, ИП). 503 — провайдер недоступен и в кеше "
        "ничего нет."
    ),
)
async def get_accounting_report(
    inn: Annotated[str, Path(description="ИНН (10 или 12 цифр)")],
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[AccountingProvider, Depends(get_accounting_provider)],
) -> JSONResponse:
    _validate_inn(inn)
    try:
        data = await handle_get_accounting_report(
            GetAccountingReportQuery(inn=inn), session, provider
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.commit()  # persist mark_not_found / mark_failed
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(data))


@router.post(
    "/{inn}/refresh",
    response_model=AccountingReportResponse,
    summary="Принудительно обновить бухгалтерскую отчётность",
    description=(
        "Вынуждает провайдера пересчитать данные, минуя TTL-кеш. "
        "Используется кнопкой «Обновить» на шаге анкеты."
    ),
)
async def refresh_accounting_report(
    inn: Annotated[str, Path(description="ИНН (10 или 12 цифр)")],
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[AccountingProvider, Depends(get_accounting_provider)],
) -> JSONResponse:
    _validate_inn(inn)
    try:
        data = await handle_refresh_accounting(
            RefreshAccountingCommand(inn=inn), session, provider
        )
        await session.commit()
    except (ServiceError, DomainError) as exc:
        await session.commit()
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(data))


def _build_history_response(inn: str, raw_history: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Aggregate raw per-table rows into year-grouped uploads."""
    # Collect all rows across tables
    all_rows: list[dict[str, Any]] = []
    for table_rows in raw_history.values():
        all_rows.extend(table_rows)

    # Group by (year, source_type, date_truncated_to_seconds)
    uploads: dict[tuple[int, str, str], int] = defaultdict(int)
    for row in all_rows:
        year = row.get("year")
        if year is None:
            continue
        source_type = row.get("source_type", "unknown")
        load_date = row.get("load_date") or row.get("updated_at")
        if isinstance(load_date, datetime):
            date_str = load_date.isoformat()
        elif load_date:
            date_str = str(load_date)
        else:
            date_str = ""
        uploads[(int(year), source_type, date_str)] += 1

    # Group by year
    year_uploads: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for (year, source_type, date_str), count in uploads.items():
        year_uploads[year].append(
            {
                "date": date_str,
                "source_type": source_type,
                "row_count": count,
            }
        )

    # Sort uploads within each year by date desc
    for uploads_list in year_uploads.values():
        uploads_list.sort(
            key=lambda u: u["date"] or "",
            reverse=True,
        )

    years = [
        {"year": year, "uploads": year_uploads[year]}
        for year in sorted(year_uploads.keys(), reverse=True)
    ]

    return {"inn": inn, "years": years}


@router.get(
    "/{inn}/history",
    response_model=AccountingHistoryResponse,
    summary="История загрузок бухгалтерской отчётности по ИНН",
    description=(
        "Возвращает историю загрузок бухгалтерской отчётности: "
        "для каждого года — список загрузок с датами, типом источника "
        "и количеством строк."
    ),
)
async def get_accounting_history(
    inn: Annotated[str, Path(description="ИНН (10 или 12 цифр)")],
    _user: Annotated[dict[str, Any], Depends(require_scopes("accounting:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _validate_inn(inn)
    raw_history = await _fetch_accounting_history(session, inn)
    data = _build_history_response(inn, raw_history)
    return JSONResponse(content=jsonable_encoder(data))
