"""HTTP contracts for application-vehicle assignments."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssignApplicationVehicleDealerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dealer_id: UUID


class ApplicationVehicleAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    application_vehicle: dict[str, Any]
