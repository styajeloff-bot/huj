"""Validated per-leasing-company questionnaire field settings."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class QuestionnaireFieldSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(min_length=1, max_length=100)
    enabled: StrictBool
    required: StrictBool


class QuestionnaireFieldSettingOut(QuestionnaireFieldSetting):
    label: str
    required_available: bool
    required_unavailable_reason: str | None


class QuestionnaireSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[QuestionnaireFieldSetting] = Field(max_length=200)


class QuestionnaireSettingsResponse(BaseModel):
    leasing_company_id: UUID
    fields: list[QuestionnaireFieldSettingOut]
