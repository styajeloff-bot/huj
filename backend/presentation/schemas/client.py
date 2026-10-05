"""HTTP schemas for /api/v1/client/* (profile, favorites, saved calculations)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ClientType = Literal["individual", "entrepreneur", "legal"]


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class ClientProfileResponse(BaseModel):
    """Joined view of users + client_profiles. Profile-side keys may be ``None``."""

    user_id: str
    phone: str | None = None
    email: str | None = None
    name: str | None = None
    role: str | None = None
    company_id: str | None = None
    is_active: bool | None = None
    phone_verified: bool | None = None

    profile_id: str | None = None
    client_type: ClientType | None = None
    passport_series: str | None = None
    passport_issued_date: date | None = None
    passport_issued_by: str | None = None
    company_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    address: str | None = None
    birth_date: date | None = None
    notification_settings: dict[str, Any] | None = None
    two_factor_enabled: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UpdateClientProfileRequest(BaseModel):
    """Partial update; only the keys actually present are changed."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None
    birth_date: date | None = None
    client_type: ClientType | None = None
    passport_series: str | None = None
    passport_issued_date: date | None = None
    passport_issued_by: str | None = None
    company_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    address: str | None = None
    notification_settings: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Saved calculations
# ---------------------------------------------------------------------------


class SavedCalculationOut(BaseModel):
    id: str
    user_id: str
    name: str
    params: dict[str, Any]
    calculation: dict[str, Any]
    created_at: datetime | None = None


class SavedCalculationsListResponse(BaseModel):
    calculations: list[SavedCalculationOut]


class SaveCalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    params: dict[str, Any]
    calculation: dict[str, Any]


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


class FavoriteVehicleOut(BaseModel):
    id: str
    product_id: str
    vehicle_id: str | None = None
    added_at: datetime | None = None
    base_price: float | None = None
    discount_price: float | None = None
    year: int | None = None
    color: str | None = None
    vin: str | None = None
    mark_id: str | None = None
    model_id: str | None = None
    complectation_id: str | None = None
    images: dict[str, Any] | list[Any] | None = None


class FavoritesListResponse(BaseModel):
    favorites: list[FavoriteVehicleOut]


class FavoriteAddedResponse(BaseModel):
    id: str
    user_id: str
    product_id: str
    vehicle_id: str | None = None
    added_at: datetime | None = None


class BulkRemoveFavoritesResponse(BaseModel):
    removed: int

