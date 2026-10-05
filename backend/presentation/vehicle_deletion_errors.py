"""Flat error responses shared by vehicle and warehouse deletion endpoints."""
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from application.commands.vehicles.admin_deletion import VehicleDeletionError


def vehicle_deletion_error(exc: VehicleDeletionError) -> JSONResponse:
    body: dict[str, Any] = {"code": exc.code, "error": str(exc), "deleted": False}
    if exc.blocking_reasons is not None:
        body["blocking_reasons"] = exc.blocking_reasons
    return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(body))
