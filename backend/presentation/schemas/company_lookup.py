"""HTTP schemas for company lookup."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyInfoResponse(BaseModel):
    name: str
    full_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    phone: str | None = None
    email: str | None = None
    foundation_date: str | None = None
    employee_count: int | None = None
    business_activity: str | None = None
    manager_name: str | None = None
    entity_type: str | None = None


class CompanySearchResponse(BaseModel):
    items: list[CompanyInfoResponse] = Field(default_factory=list)
