"""Pydantic schemas for the LC analytics dashboard."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LkDashboardFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_from: date | None = None
    period_to: date | None = None
    statuses: list[str] | None = None
    dealers: list[UUID] | None = None
    marks: list[str] | None = None


LkDashboardTab = Literal[
    "overview",
    "applications",
    "proposals",
    "financials",
]


class LkDashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab: LkDashboardTab = "overview"
    filters: LkDashboardFilters = LkDashboardFilters()
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class KpiCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | float | None = None
    delta: int | float | None = None
    delta_percent: float | None = None
    period_comparison: str | None = None


class TimeSeriesPoint(BaseModel):
    x: str
    y: int | float


class LineChartSeries(BaseModel):
    name: str
    color: str
    data: list[TimeSeriesPoint]


class BarChartSeries(BaseModel):
    name: str
    color: str
    data: list[int | float]


class BarChartData(BaseModel):
    labels: list[str]
    datasets: list[BarChartSeries]


class DonutSlice(BaseModel):
    label: str
    value: int | float
    color: str


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int


class PaginatedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]]
    pagination: Pagination


class LkDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab: str = "overview"
    filters_applied: LkDashboardFilters
    widgets: dict[str, Any]


class ExportQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab: LkDashboardTab = "overview"
    format: Literal["csv"] = "csv"
    period_from: date | None = None
    period_to: date | None = None
    statuses: list[str] | None = None
    dealers: list[UUID] | None = None
    marks: list[str] | None = None
    limit: int = Field(default=1000, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)
