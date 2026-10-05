"""HTTP schemas for the historical LCA status funnel."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.application_status_funnel import ApplicationFunnelSelectionMode


class ApplicationStatusFunnelRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    status: str
    label: str
    order: int
    events_count: int = Field(serialization_alias="eventsCount")
    end_state_count: int = Field(serialization_alias="endStateCount")


class ApplicationStatusFunnelResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    unit: Literal["lca"]
    timezone: str
    period_from: date = Field(serialization_alias="periodFrom")
    period_to: date = Field(serialization_alias="periodTo")
    selection_mode: ApplicationFunnelSelectionMode = Field(
        serialization_alias="selectionMode"
    )
    history_available_from: date = Field(serialization_alias="historyAvailableFrom")
    selected_count: int = Field(serialization_alias="selectedCount")
    rows: list[ApplicationStatusFunnelRow]


class ApplicationStatusFunnelErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    error_code: str
    history_available_from: date | None = None


class ApplicationStatusFunnelErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: ApplicationStatusFunnelErrorDetail
