"""Per-leasing-company questionnaire disclosure and required fields."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


# TODO(TZ40): Today this is one overwritten JSONB row keyed by leasing_companies.id.
# TZ40 describes versions (one is_current; no new version for unchanged values),
# companies.id and name/INN snapshots. These UUIDs are not interchangeable;
# reconcile identity and field mappings when designing the future storage change.
# See specs/task_2026-09-30_16-03-41_MSK.md,
# section "Отложенное ТЗ №40 и устранение блокировки дозапросов".
class LeasingQuestionnaireSettings(Base):
    __tablename__ = "leasing_questionnaire_settings"

    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fields: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
