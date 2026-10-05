from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.calculator_rates import (
    CreateCalculatorRateCommand,
    PatchCalculatorRateCommand,
    handle_create_calculator_rate,
    handle_patch_calculator_rate,
)
from application.errors import ServiceError
from application.queries.calculator_rates import (
    GetCalculatorRateQuery,
    ListCalculatorRatesQuery,
    handle_get_calculator_rate,
    handle_list_calculator_rates,
)
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.schemas.calculator_rates import (
    CalculatorRateCreateRequest,
    CalculatorRateListResponse,
    CalculatorRatePatchRequest,
    CalculatorRateResponse,
)

router = APIRouter()

_employee_only = require_roles("carcraft_employee")


def _http(exc: ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/calculator-rates",
    response_model=CalculatorRateListResponse,
    summary="[admin] Список ставок калькулятора",
    description="Возвращает исторические ставки лизингового калькулятора.",
    dependencies=[Depends(_employee_only)],
)
async def list_calculator_rates(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_calculator_rates(
        ListCalculatorRatesQuery(),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/calculator-rates",
    status_code=201,
    response_model=CalculatorRateResponse,
    summary="[admin] Создать ставку калькулятора",
    description="Создает историческую строку ставок без пересечения периодов.",
    dependencies=[Depends(_employee_only)],
)
async def create_calculator_rate(
    body: CalculatorRateCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_create_calculator_rate(
            CreateCalculatorRateCommand(
                date_from=body.date_from,
                date_to=body.date_to,
                key_rate=body.key_rate,
                surcharge=body.surcharge,
                vat_rate=body.vat_rate,
                profit_tax_rate=body.profit_tax_rate,
            ),
            session,
        )
    except ServiceError as exc:
        raise _http(exc)
    await session.commit()
    rate = cast("dict[str, object]", result["calculator_rate"])
    return JSONResponse(
        content=jsonable_encoder(result),
        status_code=201,
        headers={"Location": f"/api/v1/admin/calculator-rates/{rate['id']}"},
    )


@router.get(
    "/calculator-rates/{rate_id}",
    response_model=CalculatorRateResponse,
    summary="[admin] Ставка калькулятора по id",
    description="Возвращает одну историческую строку ставок калькулятора.",
    dependencies=[Depends(_employee_only)],
)
async def get_calculator_rate(
    rate_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_calculator_rate(
            GetCalculatorRateQuery(rate_id=rate_id),
            session,
        )
    except ServiceError as exc:
        raise _http(exc)
    return JSONResponse(content=jsonable_encoder(result))


@router.patch(
    "/calculator-rates/{rate_id}",
    response_model=CalculatorRateResponse,
    summary="[admin] Обновить ставку калькулятора",
    description="Частично обновляет историческую строку ставок калькулятора.",
    dependencies=[Depends(_employee_only)],
)
async def patch_calculator_rate(
    rate_id: UUID,
    body: CalculatorRatePatchRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_patch_calculator_rate(
            PatchCalculatorRateCommand(
                rate_id=rate_id,
                values=body.model_dump(exclude_unset=True),
            ),
            session,
        )
    except ServiceError as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
