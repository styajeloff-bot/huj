"""Pydantic schemas for the distributor analytics dashboard."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Widget types (match frontend analytics.ts)
# ---------------------------------------------------------------------------


class KpiWidget(BaseModel):
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
    dashed: bool = False


class DonutSlice(BaseModel):
    label: str
    value: int | float
    color: str


class BarChartSeries(BaseModel):
    name: str
    color: str
    data: list[int | float]


class BarChartData(BaseModel):
    labels: list[str]
    datasets: list[BarChartSeries]


class ComboChartData(BaseModel):
    labels: list[str]
    barDatasets: list[BarChartSeries]
    lineDataset: LineChartSeries | None = None


class Pagination(BaseModel):
    total: int
    page: int
    limit: int
    pages: int


class PaginatedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]]
    pagination: Pagination


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------


class DistributorAnalyticsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_from: date | None = None
    period_to: date | None = None
    cities: list[str] | None = None
    marks: list[str] | None = None
    models: list[str] | None = None
    dealers: list[UUID] | None = None
    statuses: list[str] | None = None


DistributorTab = Literal[
    "warehouse",
    "applications",
    "exchange",
    "financials",
    "sales-dc",
    "sales-dc-regions",
    "team",
]


class DistributorAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab: str
    filters_applied: DistributorAnalyticsFilters
    widgets: dict[str, Any]
