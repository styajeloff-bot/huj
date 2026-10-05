
"""Internal conditions use registered taxonomy even when no vehicle is in stock."""
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.legacy_compat import (
    CarModel,
    Configuration,
    Generation,
    Mark,
    Modification,
    VehicleCategory,
)

PATH = "/api/v1/monetization/lookups/catalog"


@pytest_asyncio.fixture
async def db_session(_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async with _engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint",
        ) as session:
            yield session
        await transaction.rollback()


@pytest_asyncio.fixture
async def taxonomy(db_session: AsyncSession) -> None:
    db_session.add(VehicleCategory(id="B (Легковые автомобили)"))
    await db_session.flush()
    # Equal display names have different supplier IDs; neither has stock.
    db_session.add_all([
        Mark(id="mon-mark-a", name="Sollers"),
        Mark(id="mon-mark-b", name="Sollers"),
        Mark(id="mon-mark-other", name="UAZ"),
    ])
    await db_session.flush()
    for suffix, name, mark_id in (
        ("a", "Atlant", "mon-mark-a"),
        ("b", "SF5", "mon-mark-b"),
        ("other", "Patriot", "mon-mark-other"),
    ):
        db_session.add(CarModel(id=f"mon-model-{suffix}", name=name, mark_id=mark_id))
        await db_session.flush()
        db_session.add(Generation(id=f"mon-gen-{suffix}", model_id=f"mon-model-{suffix}"))
        await db_session.flush()
        db_session.add(Configuration(
            id=f"mon-conf-{suffix}", configuration_name=name, generation_id=f"mon-gen-{suffix}",
        ))
        await db_session.flush()
        # Multiple modifications with the same trim form a single option.
        for number in (1, 2):
            db_session.add(Modification(
                complectation_id=f"mon-mod-{suffix}-{number}",
                configuration_id=f"mon-conf-{suffix}", group_name="Комфорт",
            ))
    await db_session.commit()


async def test_catalog_without_stock_and_cascade_filters(
    client: AsyncClient, employee_token: str, taxonomy: None,
) -> None:
    headers = {"Authorization": f"Bearer {employee_token}"}
    public = await client.get("/api/v1/cars/facets", params={"fields": "marks"})
    assert public.status_code == 200
    assert public.json()["marks"] == []
    marks = await client.get(PATH, params={"fields": "marks"}, headers=headers)
    assert marks.status_code == 200, marks.text
    assert marks.json() == {"marks": [
        {"id": "mon-mark-a", "ids": ["mon-mark-a", "mon-mark-b"], "name": "Sollers"},
        {"id": "mon-mark-other", "ids": ["mon-mark-other"], "name": "UAZ"},
    ]}
    models = await client.get(PATH, params={
        "fields": "models", "mark_id": "mon-mark-a,mon-mark-b",
    }, headers=headers)
    assert models.status_code == 200, models.text
    assert models.json() == {"models": [
        {"id": "mon-model-a", "name": "Atlant"}, {"id": "mon-model-b", "name": "SF5"},
    ]}
    trims = await client.get(PATH, params={
        "fields": "trims", "mark_id": "mon-mark-a,mon-mark-b", "model_id": "mon-model-b",
    }, headers=headers)
    assert trims.status_code == 200, trims.text
    assert trims.json() == {"trims": [
        {"id": "mon-conf-b_Комфорт", "name": "SF5", "trim_name": "Комфорт"},
    ]}
    wrong_parent = await client.get(PATH, params={
        "fields": "trims", "mark_id": "mon-mark-a", "model_id": "mon-model-b",
    }, headers=headers)
    assert wrong_parent.status_code == 200
    assert wrong_parent.json() == {"trims": []}


@pytest.mark.parametrize("params", [
    {"fields": "models"}, {"fields": "trims", "mark_id": "mon-mark-a"},
])
async def test_children_require_parent_selection(
    client: AsyncClient, employee_token: str, taxonomy: None, params: dict[str, str],
) -> None:
    response = await client.get(PATH, params=params, headers={"Authorization": f"Bearer {employee_token}"})
    assert response.status_code == 200
    assert response.json() == {params["fields"]: []}


async def test_catalog_is_internal(client: AsyncClient, client_token: str) -> None:
    anonymous = await client.get(PATH, params={"fields": "marks"})
    assert anonymous.status_code == 401
    customer = await client.get(PATH, params={"fields": "marks"}, headers={"Authorization": f"Bearer {client_token}"})
    assert customer.status_code == 403


async def test_empty_registered_catalog_returns_empty_list(
    client: AsyncClient, employee_token: str,
) -> None:
    response = await client.get(PATH, params={"fields": "marks"},
                                headers={"Authorization": f"Bearer {employee_token}"})
    assert response.status_code == 200
    assert response.json() == {"marks": []}
