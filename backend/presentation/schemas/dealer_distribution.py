"""Quantity distribution request with optimistic remaining-quantity checks."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class DealerDistributionItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_vehicle_id: UUID
    quantity: StrictInt = Field(gt=0)
    expected_unassigned_quantity: StrictInt = Field(ge=0)


class DealerDistributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    dealer_id: UUID
    items: list[DealerDistributionItemRequest] = Field(min_length=1, max_length=200)


class DealerDistributionResponse(BaseModel):
    application_vehicle_ids: list[UUID]
