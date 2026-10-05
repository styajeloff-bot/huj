"""Dealer-only actions over leasing-application special-equipment rows."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.dealer_application_pricing import (
    SetDealerApplicationItemPriceCommand,
    handle_set_dealer_application_item_price,
)
from domain.special_equipment_application_pricing import (
    RequestedPriceWorkflowError,
)
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.schemas.applications import (
    DealerApplicationItemPriceError,
    DealerApplicationItemPriceRequest,
    DealerApplicationItemPriceResponse,
)

router = APIRouter()

_dealer_only = require_roles("dealer")
_ERROR_STATUS = {
    "NOT_APPLICATION_DEALER": 403,
    "APPLICATION_NOT_FOUND": 404,
    "ITEM_NOT_FOUND": 404,
    "ITEM_APPLICATION_MISMATCH": 404,
    "APPLICATION_NOT_ACTIVE": 409,
    "LEASING_COMPANY_ALREADY_ASSIGNED": 409,
    "PRICE_NOT_POSITIVE": 422,
    "ITEM_NOT_PRICE_ON_REQUEST": 422,
}


@router.patch(
    "/{application_id}/items/{item_id}/price",
    response_model=DealerApplicationItemPriceResponse,
    responses={
        status: {"model": DealerApplicationItemPriceError}
        for status in (403, 404, 409, 422)
    },
    summary="[dealer] Выставить стоимость позиции",
    description=(
        "Дилер устанавливает либо повторно изменяет точную стоимость своей "
        "позиции спецтехники с режимом «Цена по запросу». Операция доступна "
        "до назначения лизинговой компании и атомарно обновляет позицию, "
        "общую сумму заявки и журнал изменений."
    ),
)
async def set_application_item_price(
    application_id: UUID,
    item_id: UUID,
    body: DealerApplicationItemPriceRequest,
    user: Annotated[dict[str, Any], Depends(_dealer_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_set_dealer_application_item_price(
            SetDealerApplicationItemPriceCommand(
                application_id=application_id,
                item_id=item_id,
                actor_id=UUID(str(user["id"])),
                actor_company_id=(
                    UUID(str(user["company_id"]))
                    if user.get("company_id") is not None
                    else None
                ),
                agreed_price=body.agreed_price,
                source="dealer_ui",
            ),
            session,
        )
    except RequestedPriceWorkflowError as exc:
        return JSONResponse(
            status_code=_ERROR_STATUS[exc.code],
            content={"error_code": exc.code, "message": str(exc)},
        )
    await session.commit()
    payload = dict(result)
    payload["agreed_price"] = str(payload["agreed_price"])
    payload["application_total_amount"] = str(
        payload["application_total_amount"]
    )
    DealerApplicationItemPriceResponse.model_validate(payload)
    return JSONResponse(content=jsonable_encoder(payload))


__all__ = ["router"]
