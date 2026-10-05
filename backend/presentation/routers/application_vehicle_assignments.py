"""Root-level contract for assigning a dealer to an application vehicle."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles import (
    AssignApplicationVehicleDealerCommand,
    handle_assign_application_vehicle_dealer,
)
from application.errors import ServiceError
from domain.errors import DomainError
from infrastructure.database import get_db
from presentation.assignment_errors import assignment_error_response
from presentation.dependencies.auth import get_current_user, require_roles
from presentation.schemas.application_vehicle_assignments import (
    ApplicationVehicleAssignmentResponse,
    AssignApplicationVehicleDealerRequest,
)

router = APIRouter()
_distributor_only = require_roles("distributor")


@router.put(
    "/{application_id}/{car_id}/diler",
    response_model=ApplicationVehicleAssignmentResponse,
    deprecated=True,
    summary="[distributor] Устаревшее назначение дилера автомобиля",
    description=(
        "Возвращает 409. Для назначения используйте POST "
        "/api/v1/applications/{application_id}/dealer-distributions "
        "с количеством, ожидаемым остатком и request_id."
    ),
    dependencies=[Depends(_distributor_only)],
)
async def assign_application_vehicle_dealer(
    application_id: UUID,
    car_id: UUID,
    body: AssignApplicationVehicleDealerRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_assign_application_vehicle_dealer(
            AssignApplicationVehicleDealerCommand(
                application_id=application_id,
                application_vehicle_id=car_id,
                dealer_id=body.dealer_id,
                actor_id=user["id"],
                actor_role=str(user.get("role") or ""),
                actor_company_id=user.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        return assignment_error_response(exc)
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))
