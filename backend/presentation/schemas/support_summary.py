"""Shared read-model for a support program applicable to one vehicle."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicableSupportProgramOut(BaseModel):
    vehicle_id: UUID
    id: UUID
    name: str
    support_type: str
    support_params: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    support_amount: int
    base_price: int
    display_price: int
    is_compatible: bool = False
    compatible_support_ids: list[UUID] = Field(default_factory=list)
    bill_of_lading: dict[str, Any] | None = None
