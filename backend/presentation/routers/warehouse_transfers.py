"""HTTP endpoints for scoped, atomic warehouse vehicle transfers."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.warehouse_transfers import (
    TransferVehiclesCommand,
    handle_transfer_vehicles,
)
from application.queries.warehouse_transfers import (
    ListAvailableWarehousesQuery,
    ListSourceVehiclesQuery,
    handle_list_available_warehouses,
    handle_list_source_vehicles,
)
from domain.services.scopes import VEHICLES_ADMIN
from infrastructure.database import get_db
from presentation.dependencies.auth import (
    get_current_user,
    require_roles,
    require_scopes,
)
from presentation.schemas.warehouse_transfers import (
    AvailableWarehousesResponse,
    SourceVehiclesResponse,
    TransferVehiclesRequest,
    TransferVehiclesResponse,
)

router = APIRouter()
_vehicle_admin = require_scopes(VEHICLES_ADMIN)
_transfer_roles = require_roles("carcraft_employee", "distributor")
_transfer_access = [Depends(_vehicle_admin), Depends(_transfer_roles)]


@router.get(
    "/warehouses",
    response_model=AvailableWarehousesResponse,
    summary="Доступные склады для перемещения",
    description=(
        "Возвращает склады, доступные текущему сотруднику Carcraft или "
        "дистрибьютору, вместе с числом автомобилей. Требует `vehicles:admin`."
    ),
    dependencies=_transfer_access,
)
async def list_available_warehouses(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    result = await handle_list_available_warehouses(
        ListAvailableWarehousesQuery(
            actor_id=user["id"],
            actor_role=user["role"],
            company_id=user.get("company_id"),
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.get(
    "/vehicles",
    response_model=SourceVehiclesResponse,
    summary="Автомобили исходного склада",
    description=(
        "Постранично возвращает автомобили текущего исходного склада и доступные "
        "фасеты фильтров в разрешённом scope. Требует `vehicles:admin`."
    ),
    dependencies=_transfer_access,
)
async def list_source_vehicles(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    source_warehouse_id: UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    vin: str | None = Query(default=None),
    mark_ids: list[str] | None = Query(default=None),
    model_ids: list[str] | None = Query(default=None),
    years: list[int] | None = Query(default=None),
    colors: list[str] | None = Query(default=None),
) -> JSONResponse:
    result = await handle_list_source_vehicles(
        ListSourceVehiclesQuery(
            actor_id=user["id"],
            actor_role=user["role"],
            company_id=user.get("company_id"),
            source_warehouse_id=source_warehouse_id,
            page=page,
            limit=limit,
            vin=vin,
            mark_ids=mark_ids,
            model_ids=model_ids,
            years=years,
            colors=colors,
        ),
        session,
    )
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "",
    status_code=201,
    response_model=TransferVehiclesResponse,
    summary="Переместить автомобили между складами",
    description=(
        "Атомарно переносит выбранные автомобили либо все автомобили по фильтру. "
        "Допускает частичный результат; если не перемещена ни одна позиция, "
        "возвращает 409. Требует `vehicles:admin`."
    ),
    dependencies=_transfer_access,
)
async def transfer_vehicles(
    body: TransferVehiclesRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_transfer_vehicles(
            TransferVehiclesCommand(
                actor_id=user["id"],
                actor_role=user["role"],
                company_id=user.get("company_id"),
                source_warehouse_id=body.source_warehouse_id,
                destination_warehouse_id=body.destination_warehouse_id,
                vehicle_ids=body.vehicle_ids,
                all_filtered=body.all_filtered,
            ),
            session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["message"] = (
        "Автомобили успешно перемещены"
        if result["transferred_count"]
        else "Не удалось переместить автомобили"
    )
    if not result["transferred_count"]:
        return JSONResponse(status_code=409, content=jsonable_encoder(result))

    await session.commit()
    return JSONResponse(status_code=201, content=jsonable_encoder(result))
