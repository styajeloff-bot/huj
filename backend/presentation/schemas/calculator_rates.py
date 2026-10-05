from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Percent = Annotated[float, Field(ge=0, le=100)]


class CalculatorRateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date_from: date
    date_to: date | None = None
    key_rate: Percent
    surcharge: Percent
    vat_rate: Percent
    profit_tax_rate: Percent


class CalculatorRatePatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date_from: date | None = None
    date_to: date | None = None
    key_rate: Percent | None = None
    surcharge: Percent | None = None
    vat_rate: Percent | None = None
    profit_tax_rate: Percent | None = None


class CalculatorRateOut(BaseModel):
    id: UUID
    date_from: date
    date_to: date | None
    is_current: bool
    key_rate: float
    surcharge: float
    vat_rate: float
    profit_tax_rate: float


class CalculatorRateListResponse(BaseModel):
    items: list[CalculatorRateOut]


class CalculatorRateResponse(BaseModel):
    calculator_rate: CalculatorRateOut
