"""Client profile domain entity.

Aggregates the user-side view of:
  * basic ``users`` row fields (name, email, phone),
  * one-to-one ``client_profiles`` extension row fields
    (passport, INN, KPP, OGRN, addresses, notification settings, ...).

Invariants:
  * Saved-calculation / favorite / profile rows are owned by a specific user
    — every mutation must call :meth:`ensure_owned_by`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import Any
from uuid import UUID

from domain.errors import AccessDeniedError

# Allowed values for the ``client_type`` column. Mirrors the Joi validator
# in ``express/routes/client.js`` and keeps the FastAPI schema layer in sync
# without leaking presentation concerns into the domain.
CLIENT_TYPES: frozenset[str] = frozenset(
    {"individual", "entrepreneur", "legal"}
)


@dataclass
class ClientProfile:
    """Aggregate root for the client profile + linked user identity.

    Field set deliberately mirrors a JOIN of ``users`` + ``client_profiles``.
    Hydrate via :meth:`from_dict` from the repository's flat dict; missing
    keys default to ``None`` so the same dataclass works for users that have
    no ``client_profiles`` row yet.
    """

    # --- users.* ---
    user_id: UUID = field(default_factory=uuid.uuid4)
    phone: str | None = None
    email: str | None = None
    name: str | None = None
    role: str | None = None
    company_id: UUID | None = None
    is_active: bool | None = None
    phone_verified: bool | None = None

    # --- client_profiles.* ---
    profile_id: UUID | None = None
    client_type: str | None = None
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientProfile:
        """Hydrate from a repository dict, ignoring unknown keys."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    def ensure_owned_by(self, user_id: UUID) -> None:
        """Raise AccessDeniedError if ``user_id`` doesn't match the profile owner."""
        if self.user_id != user_id:
            raise AccessDeniedError("Нет доступа к данному профилю")


@dataclass(frozen=True)
class SavedCalculation:
    """Saved leasing calculation row owned by a specific user."""

    id: UUID
    user_id: UUID
    name: str
    params: dict[str, Any]
    calculation: dict[str, Any]
    created_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SavedCalculation:
        return cls(
            id=data["id"] if isinstance(data["id"], UUID) else UUID(str(data["id"])),
            user_id=data["user_id"] if isinstance(data["user_id"], UUID) else UUID(str(data["user_id"])),
            name=str(data["name"]),
            params=dict(data.get("params") or {}),
            calculation=dict(data.get("calculation") or {}),
            created_at=data.get("created_at"),
        )

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.user_id != user_id:
            raise AccessDeniedError("Нет доступа к данному расчёту")


@dataclass(frozen=True)
class Favorite:
    """A single ``user_favorites`` row."""

    id: UUID
    user_id: UUID
    vehicle_id: UUID
    added_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Favorite:
        return cls(
            id=data["id"] if isinstance(data["id"], UUID) else UUID(str(data["id"])),
            user_id=data["user_id"] if isinstance(data["user_id"], UUID) else UUID(str(data["user_id"])),
            vehicle_id=data["vehicle_id"] if isinstance(data["vehicle_id"], UUID) else UUID(str(data["vehicle_id"])),
            added_at=data.get("added_at"),
        )

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.user_id != user_id:
            raise AccessDeniedError("Нет доступа к избранному другого пользователя")


def normalize_profile_field(value: Any) -> Any:
    """Express-parity: empty string in profile fields is treated as ``NULL``."""
    if value == "":
        return None
    return value
