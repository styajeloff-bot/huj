"""Project application transport lines into their single questionnaire."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.leasing_purposes import selected_purposes
from infrastructure.models.applications import (
    ApplicationQuestionnaire,
    ApplicationVehicle,
    LeasingApplication,
)


async def lock_purpose_application(session: AsyncSession, application_id: UUID) -> None:
    """Acquire the shared parent-first mutation lock before touching transport rows."""
    await session.execute(sa.select(LeasingApplication.id).where(
        LeasingApplication.id == application_id,
    ).with_for_update())


async def sync_vehicle_purchase_purpose(session: AsyncSession, application_id: UUID) -> None:
    await lock_purpose_application(session, application_id)
    await session.flush()
    lines = (await session.execute(sa.select(
        ApplicationVehicle.id, ApplicationVehicle.leasing_purposes, ApplicationVehicle.leasing_purpose,
    ).where(
        ApplicationVehicle.application_id == application_id,
        ApplicationVehicle.car_status.not_in(("removed", "replaced", "rejected")),
    ).order_by(ApplicationVehicle.id))).all()
    await session.execute(insert(ApplicationQuestionnaire).values(application_id=application_id).on_conflict_do_nothing(index_elements=["application_id"]))
    questionnaire = (await session.execute(sa.select(ApplicationQuestionnaire).where(
        ApplicationQuestionnaire.application_id == application_id,
    ).with_for_update())).scalar_one()
    purpose_projection = {"vehicles": [
        {"vehicle_id": str(line.id), "purposes": selected_purposes(line.leasing_purposes, line.leasing_purpose)}
        for line in lines
    ]}
    if questionnaire.vehicle_purchase_purpose != purpose_projection:
        questionnaire.vehicle_purchase_purpose = purpose_projection
        cast("Any", questionnaire).updated_at = datetime.now(UTC)
    await session.flush()
