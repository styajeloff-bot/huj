"""Admin routes for /api/v1/admin/application-vehicles.

Phase 13 R13c — the VIN assign / list-available-VIN endpoints moved to
``/api/v1/application-vehicles/{id}`` (see
``presentation/routers/application_vehicles.py``). What remains here is
the admin-only vehicle↔dealer assignment helper.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles import (
    AssignVehicleCommand,
    handle_assign_vehicle,
)
from application.errors import ServiceError, domain_to_http
from domain.errors import DomainError
from domain.services.scopes import FEATURED_ADMIN
from infrastructure.database import get_db
from presentation.dependencies.auth import get_current_user, require_scopes
from presentation.schemas.application_vehicles import (
    AssignVehicleRequest,
    AssignVehicleResponse,
)

router = APIRouter()

_authorized = require_scopes(FEATURED_ADMIN)


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.put(
    "/application-vehicles/{application_vehicle_id}/assign",
    response_model=AssignVehicleResponse,
    summary="[admin] Назначить дилера автомобилю заявки",
    description=(
        "Передаёт vehicle_id строки на указанного dealer_id. Запись "
        "application_vehicles должна уже иметь связанный vehicle_id."
    ),
    dependencies=[Depends(_authorized)],
)
async def assign_vehicle(
    application_vehicle_id: UUID,
    body: AssignVehicleRequest,
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_assign_vehicle(
            AssignVehicleCommand(
                application_vehicle_id=application_vehicle_id,
                actor_id=user["id"],
                dealer_id=body.dealer_id,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
