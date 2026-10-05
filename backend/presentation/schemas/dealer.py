"""Pydantic schemas for the dealer cabinet API (Phase 5 E3 + Phase 7a G4)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InviteClientRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phone: str = Field(min_length=5, max_length=32)
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class InviteClientResponse(BaseModel):
    success: bool = True
    message: str
    created_user: bool


# ---------------------------------------------------------------------------
# G4 — Dealer profile / clients / inventory / reports
# ---------------------------------------------------------------------------


class DealerUserOut(BaseModel):
    id: str
    phone: str | None = None
    email: str | None = None
    name: str | None = None
    role: str | None = None
    company_id: str | None = None
    is_active: bool | None = None
    last_login: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DealerCompanyOut(BaseModel):
    id: str
    name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    company_type: str | None = None


class DealerSalesStats(BaseModel):
    total_clients: int = 0
    total_sales: int = 0
    total_revenue: float = 0.0
    total_applications: int = 0
    conversion_rate: float = 0.0


class DealerProfileResponse(BaseModel):
    profile: DealerUserOut
    company: DealerCompanyOut | None = None
    stats: DealerSalesStats


class UpdateDealerProfileRequest(BaseModel):
    """Partial update of the dealer user + their company."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None
    dealership_name: str | None = Field(
        default=None,
        description="Название юрлица дилера (пишется в companies.name).",
        max_length=500,
    )
    contact_person: str | None = None
    phone: str | None = Field(
        default=None,
        description="Контактный телефон компании.",
        max_length=50,
    )
    inn: str | None = None
    kpp: str | None = None
    address: str | None = Field(
        default=None,
        description="Юридический адрес компании.",
        max_length=1000,
    )
    description: str | None = None
    working_hours: dict[str, Any] | None = None
    notification_settings: dict[str, Any] | None = None


class DealerClientOut(BaseModel):
    id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    last_login: datetime | None = None
    created_at: datetime | None = None
    applications_count: int = 0
    total_amount: float = 0.0


class DealerClientsPagination(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class DealerClientsResponse(BaseModel):
    clients: list[DealerClientOut]
    pagination: DealerClientsPagination

