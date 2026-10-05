from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.application_create_idempotency import (
    begin_application_create,
    finish_application_create,
)
from application.commands.applications.update_items import (
    ApplicationItemUpdate,
    UpdateApplicationItemsCommand,
    handle_update_application_items,
)
from application.errors import domain_to_http
from domain.errors import DomainError
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from presentation.schemas.applications import (
    ApplicationSpecialEquipmentItem,
    ApplicationVehicleItem,
)

pytestmark = pytest.mark.asyncio


async def test_application_item_response_contract_includes_optional_flow_fields() -> None:
    common = {
        "id": uuid4(),
        "item_id": uuid4(),
        "title": "Тестовая позиция",
        "leasing_purpose": None,
        "regions": [],
        "region": None,
        "comment": "Комментарий к позиции",
    }

    vehicle = ApplicationVehicleItem.model_validate({"type": "vehicle", **common})
    equipment = ApplicationSpecialEquipmentItem.model_validate(
        {"type": "special_equipment", "snapshot": {}, **common}
    )

    assert vehicle.regions == []
    assert equipment.leasing_purpose is None


async def test_application_create_idempotency_replays_and_rejects_mismatch(
    db_session: AsyncSession,
) -> None:
    endpoint = "POST /api/v1/applications"
    key = str(uuid4())
    payload = {"company_id": str(uuid4()), "vehicles": []}

    assert await begin_application_create(
        db_session, endpoint=endpoint, key=key, payload=payload
    ) is None
    response = {"application_id": str(uuid4()), "status": "active"}
    await finish_application_create(
        db_session, endpoint=endpoint, key=key, result=response
    )
    assert await begin_application_create(
        db_session, endpoint=endpoint, key=key, payload=payload
    ) == response

    with pytest.raises(DomainError) as exc_info:
        await begin_application_create(
            db_session,
            endpoint=endpoint,
            key=key,
            payload={"company_id": str(uuid4()), "vehicles": []},
        )
    assert domain_to_http(exc_info.value).status_code == 409
    assert str(exc_info.value) == "Idempotency-Key уже используется с другим payload"


async def test_update_items_is_partial_and_accepts_empty_values(
    db_session: AsyncSession,
) -> None:
    company = Company(name=f"Компания {uuid4()}", company_type="other")
    db_session.add(company)
    await db_session.flush()
    application = LeasingApplication(company_id=company.id, status="active")
    db_session.add(application)
    await db_session.flush()
    line = ApplicationVehicle(
        application_id=application.id,
        modification_id=f"model-{uuid4()}",
        quantity=1,
        leasing_purpose=None,
        regions=[],
        comment="Старый комментарий",
    )
    db_session.add(line)
    await db_session.flush()

    result = await handle_update_application_items(
        UpdateApplicationItemsCommand(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
            items=[
                ApplicationItemUpdate(
                    line_id=line.id,
                    kind="vehicle",
                    leasing_purpose=None,
                    regions=[],
                    comment="Новый комментарий",
                )
            ],
        ),
        db_session,
    )
    assert result["ok"] is True
    assert result["items"] == [
        {
            "line_id": line.id,
            "kind": "vehicle",
            "leasing_purpose": None,
            "regions": [],
            "region": None,
            "comment": "Новый комментарий",
        }
    ]
    assert line.comment == "Новый комментарий"

    empty_result = await handle_update_application_items(
        UpdateApplicationItemsCommand(
            application_id=application.id,
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
            items=[],
        ),
        db_session,
    )
    assert empty_result == {"ok": True, "items": []}
