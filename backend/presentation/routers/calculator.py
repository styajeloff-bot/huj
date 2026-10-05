"""Calculator routes — leasing math, support-status, history, send-email."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.calculator import (
    CalculateCommand,
    SendCalculationEmailCommand,
    handle_calculate,
    handle_send_calculation_email,
)
from application.errors import ServiceError, domain_to_http
from application.queries.calculator import (
    GetSupportStatusQuery,
    handle_get_support_status,
)
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.dependencies.auth import (
    get_current_user_optional,
)
from presentation.schemas.calculator import (
    CalculateRequest,
    CalculateResponse,
    SendCalculationEmailRequest,
    SendCalculationEmailResponse,
    SupportStatusRequest,
    SupportStatusResponse,
)

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _normalize_selected_support(
    raw: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    if not raw:
        return {}
    out: dict[str, list[str]] = {}
    for key, value in raw.items():
        out[str(key)] = [str(pid) for pid in value if pid is not None]
    return out


@router.post(
    "/calculate",
    response_model=CalculateResponse,
    summary="Рассчитать лизинг",
    description=(
        "Возвращает ежемесячный платёж, итоговую сумму и налоговую экономию "
        "по заданным параметрам. Если переданы `vehicle_ids` и для них "
        "передайте `additional_amount` как сумму спецтехники и опций, чтобы "
        "сложить её с актуальными ценами автомобилей. Поле необязательно для "
        "обратной совместимости. Если для автомобилей "
        "доступны программы поддержки — дополнительно возвращает блоки "
        "`support`, `calculation_without_support`, `support_per_program`, "
        "`support_per_vehicle`, `calculations_per_vehicle`. "
        "Если пользователь авторизован — расчёт сохраняется в историю."
    ),
)
async def calculate(
    body: CalculateRequest,
    user: Annotated[dict[str, Any] | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    cmd = CalculateCommand(
        total_amount=body.total_amount,
        additional_amount=body.additional_amount,
        down_payment=body.down_payment,
        down_payment_percent=body.down_payment_percent,
        lease_term_months=body.lease_term_months,
        buyout_amount=body.buyout_amount or 0.0,
        buyout_percent=body.buyout_percent,
        vehicle_ids=list(body.vehicle_ids or []),
        vehicle_price_overrides=dict(body.vehicle_price_overrides or {}),
        vehicle_quantities=dict(body.vehicle_quantities or {}),
        selected_support=_normalize_selected_support(body.selected_support),
        user=user,
    )
    try:
        result = await handle_calculate(cmd, session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result.response))


@router.post(
    "/support-status",
    response_model=SupportStatusResponse,
    summary="Поддержка по списку ТС",
    description=(
        "Возвращает по каждому переданному `vehicle_id` флаг наличия "
        "программы поддержки и список её идентификаторов "
        "(`eligible_program_ids`). Авторизация необязательна."
    ),
)
async def support_status(
    body: SupportStatusRequest,
    _user: Annotated[dict[str, Any] | None, Depends(get_current_user_optional)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    items = await handle_get_support_status(
        GetSupportStatusQuery(vehicle_ids=list(body.vehicle_ids), user=_user),
        session,
    )
    return JSONResponse(content=jsonable_encoder({"items": items}))


@router.post(
    "/send-calculation-email",
    response_model=SendCalculationEmailResponse,
    summary="Отправить расчёт на email",
    description=(
        "Отправляет произвольное письмо с заранее свёрстанным расчётом. "
        "Авторизация необязательна, но ограничено через rate-limiter "
        "на уровне инфраструктуры."
    ),
)
async def send_calculation_email(
    body: SendCalculationEmailRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        await handle_send_calculation_email(
            SendCalculationEmailCommand(
                to=body.to,
                subject=body.subject,
                text=body.text,
                html=body.html,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(content={"success": True})
