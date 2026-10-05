"""Dealer cabinet API (Phase 5 E3 + Phase 7a G4).

Covers the following dealer-scoped surfaces:

- ``POST /invite-client`` — send an SMS invite to a phone number. Creates a
  minimal ``client`` user if the phone is new; silent no-op otherwise.
- ``GET /vehicles`` / ``POST /vehicles`` / ``PUT /vehicles/{id}`` — dealer
  inventory. Thin wrappers over Phase 2 B1 with ownership coerced by the
  B1 handler.
- ``GET /inventory`` / ``POST /inventory`` / ``PUT /inventory/{id}`` /
  ``DELETE /inventory/{id}`` — Express-compatible aliases on the vehicles
  surface above; add/update/delete resolve to the same B1 commands.
- ``GET /applications`` — leasing applications visible to the current
  dealer (Phase 3 ownership via company_id).
- ``GET /profile`` / ``PUT /profile`` — self-service profile (user +
  company) + aggregated sales stats.
- ``GET /clients`` — clients invited by this dealer (derived from
  application ownership via company_id).
- ``GET /reports`` — thin shim on the F1 reports surface with
  ``role='dealer'`` forced; supports ``?format=xlsx|csv`` for streaming
  file downloads per REST_CONVENTIONS §3.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.dealer import (
    InviteClientCommand,
    handle_invite_client,
)
from application.commands.reports.export_report import (
    ExportReportCommand,
    handle_export_report,
)
from application.errors import ServiceError, domain_to_http
from application.queries.dealer import (
    ListDealerClientsQuery,
    handle_list_dealer_clients,
)
from application.queries.reports import (
    GetDealerReportQuery,
    handle_get_dealer_report,
)
from domain.errors import DomainError
from domain.services.scopes import (
    APPLICATIONS_READ,
    APPLICATIONS_WRITE,
    REPORTS_READ,
)
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.dependencies.export_format import (
    ExportFormat,
    export_format_dep,
)
from presentation.schemas.dealer import (
    DealerClientsResponse,
    InviteClientRequest,
    InviteClientResponse,
)

router = APIRouter()

_applications_read = require_scopes(APPLICATIONS_READ)
_applications_write = require_scopes(APPLICATIONS_WRITE)
_reports_access = require_scopes(REPORTS_READ)


_DEALER_ROLES: frozenset[str] = frozenset({"dealer", "carcraft_employee"})


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_dealer_role(user: dict[str, Any]) -> None:
    role = str(user.get("role") or "")
    if role not in _DEALER_ROLES:
        raise HTTPException(status_code=403, detail="Доступ запрещён")


# ---------------------------------------------------------------------------
# Invite client
# ---------------------------------------------------------------------------


@router.post(
    "/invite-client",
    response_model=InviteClientResponse,
    summary="Отправить SMS-инвайт клиенту",
    description=(
        "Создаёт (если нужно) пользователя с ролью `client` по указанному "
        "номеру телефона и отправляет код регистрации через SMS. Повторный "
        "вызов для существующего телефона — silent no-op (код пересылается)."
    ),
    dependencies=[Depends(_applications_write)],
)
async def invite_client(
    body: InviteClientRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    _require_dealer_role(user)
    try:
        result = await handle_invite_client(
            InviteClientCommand(
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                phone=body.phone,
                name=body.name,
                email=body.email,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Dealer clients
# ---------------------------------------------------------------------------


@router.get(
    "/clients",
    response_model=DealerClientsResponse,
    summary="Клиенты, приглашённые дилером",
    description=(
        "Возвращает уникальных клиентов, чьи заявки были созданы текущим "
        "дилером (через company_id). Поддерживает фильтрацию по статусу активности "
        "и поиск по имени/email/телефону, а также пагинацию."
    ),
    dependencies=[Depends(_applications_read)],
)
async def list_dealer_clients(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> JSONResponse:
    _require_dealer_role(user)
    result = await handle_list_dealer_clients(
        ListDealerClientsQuery(
            dealer_id=user["company_id"],
            search=search,
            is_active=is_active,
            page=page,
            limit=limit,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))





# ---------------------------------------------------------------------------
# G4 — Reports shims (force role=dealer)
# ---------------------------------------------------------------------------


def _parse_iso_tz(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail="Некорректный формат даты (требуется ISO-8601)",
        ) from err
    if parsed.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="Даты должны быть с указанием таймзоны",
        )
    return parsed


@router.get(
    "/reports",
    response_model=None,
    summary="Отчёт дилера (shim на /reports/dealer)",
    description=(
        "Express-совместимый alias на `GET /reports/dealer` с принудительно "
        "выставленной ролью `dealer`. Даты опциональны (ISO-8601 с tz).\n\n"
        "Параметры `?format=xlsx|csv` возвращают бинарный отчёт через "
        "`StreamingResponse` с `Content-Disposition: attachment`."
    ),
    dependencies=[Depends(_reports_access)],
)
async def dealer_reports(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: Annotated[str | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[str | None, Query(alias="dateTo")] = None,
    fmt: Annotated[ExportFormat, Depends(export_format_dep)] = "json",
) -> JSONResponse | StreamingResponse:
    _require_dealer_role(user)
    df = _parse_iso_tz(date_from)
    dt = _parse_iso_tz(date_to)
    if fmt in {"xlsx", "csv"}:
        export_fmt = "excel" if fmt == "xlsx" else "csv"
        try:
            export_result = await handle_export_report(
                ExportReportCommand(
                    actor_id=user["id"],
                    actor_role="dealer",
                    actor_company_id=user.get("company_id"),
                    report_type="dealer",
                    export_format=export_fmt,
                    date_from=df,
                    date_to=dt,
                    filters=None,
                ),
                session,
            )
        except (ServiceError, DomainError) as exc:
            raise _http(exc)
        return StreamingResponse(
            iter([export_result.content]),
            media_type=export_result.mime_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{export_result.filename}"'
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )
    try:
        result = await handle_get_dealer_report(
            GetDealerReportQuery(
                actor_id=user["id"],
                actor_role="dealer",
                dealer_id=None,
                date_from=df,
                date_to=dt,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder({"reports": result}))
