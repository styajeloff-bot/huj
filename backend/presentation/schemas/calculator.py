"""Pydantic schemas for the calculator API.

Response shapes keep the Express camelCase keys (``calculation``) where the
frontend depends on them, while top-level wrapper keys use snake_case to
match the rest of the FastAPI surface.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from presentation.schemas.support_summary import ApplicableSupportProgramOut

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


PriceOverride = Annotated[float, Field(ge=0, le=10_000_000_000)]
VehicleQuantity = Annotated[int, Field(ge=1)]


class CalculateRequest(BaseModel):
    total_amount: float = Field(ge=0, le=10_000_000_000)
    additional_amount: float | None = Field(
        default=None,
        ge=0,
        le=10_000_000_000,
        description=(
            "Явная сумма спецтехники и дополнительных опций сверх "
            "авторитетной стоимости автомобилей"
        ),
    )
    down_payment: float = Field(ge=0)
    down_payment_percent: float = Field(ge=0, le=49)
    lease_term_months: int = Field(ge=12, le=84)
    buyout_amount: float | None = Field(default=None, ge=0)
    buyout_percent: float | None = Field(default=None, ge=0, le=5)
    vehicle_ids: list[UUID] | None = None
    vehicle_price_overrides: dict[UUID, PriceOverride] | None = None
    vehicle_quantities: dict[UUID, VehicleQuantity] | None = None
    selected_support: dict[str, list[str]] | None = None

    @model_validator(mode="after")
    def validate_additional_amount(self) -> CalculateRequest:
        if (
            self.additional_amount is not None
            and self.additional_amount > self.total_amount
        ):
            raise ValueError("additional_amount не может превышать total_amount")
        return self


class SupportStatusRequest(BaseModel):
    vehicle_ids: list[UUID] = Field(min_length=1)


class SendCalculationEmailRequest(BaseModel):
    # `EmailStr` would require the optional `email-validator` extra. The regex
    # is intentionally permissive (RFC 5322 superset) — strict validation is
    # the email gateway's job.
    to: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    subject: str = Field(min_length=1, max_length=255)
    text: str | None = Field(default=None, max_length=50_000)
    html: str | None = Field(default=None, max_length=300_000)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SupportStatusItem(BaseModel):
    vehicle_id: str
    has_support: bool
    support_type: str | None = None
    support_params: dict[str, Any] | None = None
    eligible_program_ids: list[UUID]
    applicable_support_programs: list[ApplicableSupportProgramOut] = Field(
        default_factory=list
    )


class SupportStatusResponse(BaseModel):
    items: list[SupportStatusItem]


class CalculationOut(BaseModel):
    """One leasing calculation result. Keys match the Express response."""

    model_config = ConfigDict(populate_by_name=True)

    monthly_payment: int = Field(alias="monthlyPayment")
    monthly_principal_payment: int = Field(alias="monthlyPrincipalPayment")
    monthly_interest_payment: int = Field(alias="monthlyInterestPayment")
    total_cost: int = Field(alias="totalCost")
    total_interest: int = Field(alias="totalInterest")
    markup: int
    markup_percent: float = Field(alias="markupPercent")
    rate: float
    buyout_amount: int = Field(alias="buyoutAmount")
    vat_refund: int = Field(alias="vatRefund")
    profit_tax_savings: int = Field(alias="profitTaxSavings")
    total_savings: int = Field(alias="totalSavings")


class CalculationParametersOut(BaseModel):
    total_amount: int
    down_payment: int
    down_payment_percent: float
    lease_term_months: int
    buyout_amount: int
    buyout_percent: float


class CalculateResponse(BaseModel):
    """Full calculator response.

    Optional fields populated only when ``vehicle_ids`` is non-empty and at
    least one support program applies.
    """

    calculation: CalculationOut
    calculation_parameters: CalculationParametersOut
    support: dict[str, Any] | None = None
    calculation_without_support: dict[str, Any] | None = None
    support_per_program: list[dict[str, Any]] | None = None
    support_per_vehicle: list[dict[str, Any]] | None = None
    eligible_support_program_ids_by_vehicle: list[dict[str, Any]] | None = None
    support_program_details: list[dict[str, Any]] | None = None
    calculations_per_vehicle: list[dict[str, Any]] | None = None


class SendCalculationEmailResponse(BaseModel):
    success: bool
