"""Contract tests for the explicit Bitrix 21808 E2E catalog fixture."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentMark,
    SpecialEquipmentProduct,
)
from scripts import seed_special_equipment_e2e_21808 as fixture_script
from scripts.seed_special_equipment_e2e_21808 import (
    E2E_PREFIX,
    seed_special_equipment_e2e_21808,
)


async def _count_prefixed(session: AsyncSession, model: type, field: str) -> int:
    column = getattr(model, field)
    return int(
        (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(model)
                .where(column.startswith(E2E_PREFIX))
            )
        ).scalar_one()
    )


def test_cli_rejects_execution_without_explicit_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fail_if_called() -> SimpleNamespace:
        nonlocal called
        called = True
        return SimpleNamespace(counts={})

    monkeypatch.setattr(fixture_script, "_apply_fixture", fail_if_called)

    with pytest.raises(SystemExit) as exc_info:
        fixture_script.main([])

    assert exc_info.value.code == 2
    assert called is False


def test_cli_accepts_apply_and_runs_fixture_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def apply_once() -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return SimpleNamespace(counts={"products": 3})

    monkeypatch.setattr(fixture_script, "_apply_fixture", apply_once)

    assert fixture_script.main(["--apply"]) == 0
    assert calls == 1


async def test_apply_fixture_rolls_back_everything_when_seed_fails(
    _engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_code = f"{E2E_PREFIX}_ATOMIC_ROLLBACK_SENTINEL"
    session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async def fail_after_flush(session: AsyncSession) -> None:
        session.add(
            SpecialEquipmentCategory(
                code=sentinel_code,
                name="Должно быть откачено",
                slug="e2e-21808-atomic-rollback-sentinel",
                usage_metric="mileage_km",
                sort_order=21808,
            )
        )
        await session.flush()
        raise RuntimeError("forced fixture failure")

    monkeypatch.setattr(fixture_script, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        fixture_script,
        "seed_special_equipment_e2e_21808",
        fail_after_flush,
    )

    with pytest.raises(RuntimeError, match="forced fixture failure"):
        await fixture_script._apply_fixture()

    async with session_factory() as verification_session:
        persisted = await verification_session.scalar(
            sa.select(sa.func.count())
            .select_from(SpecialEquipmentCategory)
            .where(SpecialEquipmentCategory.code == sentinel_code)
        )

    assert persisted == 0


async def test_fixture_is_repeatable_and_preserves_unowned_rows(
    db_session: AsyncSession,
) -> None:
    unowned = SpecialEquipmentCategory(
        code="operator-owned-category",
        name="Категория оператора",
        slug="operator-owned-category",
        usage_metric="mileage_km",
        sort_order=99,
    )
    db_session.add(unowned)
    await db_session.flush()

    first = await seed_special_equipment_e2e_21808(db_session)
    first_counts = {
        "categories": await _count_prefixed(
            db_session, SpecialEquipmentCategory, "code"
        ),
        "marks": await _count_prefixed(db_session, SpecialEquipmentMark, "code"),
        "attributes": await _count_prefixed(
            db_session, SpecialEquipmentAttribute, "code"
        ),
        "products": await _count_prefixed(db_session, SpecialEquipmentProduct, "code"),
    }
    fixture_mark = await db_session.get(SpecialEquipmentMark, first.mark_ids["faw"])
    assert fixture_mark is not None
    fixture_mark.name = "временно изменено оператором"
    await db_session.flush()

    second = await seed_special_equipment_e2e_21808(db_session)
    second_counts = {
        "categories": await _count_prefixed(
            db_session, SpecialEquipmentCategory, "code"
        ),
        "marks": await _count_prefixed(db_session, SpecialEquipmentMark, "code"),
        "attributes": await _count_prefixed(
            db_session, SpecialEquipmentAttribute, "code"
        ),
        "products": await _count_prefixed(db_session, SpecialEquipmentProduct, "code"),
    }

    assert first == second
    await db_session.refresh(fixture_mark)
    assert fixture_mark.name == f"{E2E_PREFIX} FAW"
    assert (
        first_counts
        == second_counts
        == {
            "categories": 4,
            "marks": 2,
            "attributes": 3,
            "products": 3,
        }
    )
    assert await db_session.get(SpecialEquipmentCategory, unowned.id) is unowned
    assert unowned.name == "Категория оператора"


async def test_fixture_contains_dag_filters_and_usage_examples(
    db_session: AsyncSession,
) -> None:
    summary = await seed_special_equipment_e2e_21808(db_session)

    shared_child_parent_count = int(
        (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(SpecialEquipmentCategoryRelation)
                .where(
                    SpecialEquipmentCategoryRelation.child_id
                    == summary.category_ids["shared_cranes"]
                )
            )
        ).scalar_one()
    )
    attributes = (
        await db_session.execute(
            sa.select(
                SpecialEquipmentAttribute.code,
                SpecialEquipmentAttribute.data_type,
                SpecialEquipmentAttribute.filter_kind,
            ).where(SpecialEquipmentAttribute.code.startswith(E2E_PREFIX))
        )
    ).all()
    products = (
        await db_session.execute(
            sa.select(
                SpecialEquipmentProduct.code,
                SpecialEquipmentProduct.condition,
                SpecialEquipmentProduct.owners_count,
                SpecialEquipmentProduct.no_vin,
                SpecialEquipmentProduct.vin,
                SpecialEquipmentProduct.mileage_km,
                SpecialEquipmentProduct.engine_hours,
                SpecialEquipmentProduct.publication_status,
            )
            .where(SpecialEquipmentProduct.code.startswith(E2E_PREFIX))
            .order_by(SpecialEquipmentProduct.code)
        )
    ).all()

    assert shared_child_parent_count == 2
    assert {(row.data_type, row.filter_kind) for row in attributes} == {
        ("number", "range"),
        ("select", "exact"),
    }
    assert [
        (
            row.condition,
            row.owners_count,
            row.no_vin,
            row.vin,
            row.mileage_km,
            row.engine_hours,
        )
        for row in products
    ] == [
        ("new", None, False, "E2E21808NEWCRANE0", None, None),
        ("used", 1, False, "E2E21808USEDCRANE", None, 1840),
        ("used", 2, False, "E2E21808USEDTRUCK", 126000, None),
    ]
    assert all(row.vin is None or len(row.vin) <= 17 for row in products)
    assert {row.publication_status for row in products} == {"published"}


async def test_fixture_drives_public_dag_and_category_specific_filters(
    db_session: AsyncSession,
    client: AsyncClient,
) -> None:
    summary = await seed_special_equipment_e2e_21808(db_session)

    lifting_path = await client.get(
        "/api/v1/special-equipment/categories/resolve",
        params={"path": "e2e-21808-lifting/e2e-21808-cranes"},
    )
    construction_path = await client.get(
        "/api/v1/special-equipment/categories/resolve",
        params={"path": "e2e-21808-construction/e2e-21808-cranes"},
    )
    listing = await client.get(
        "/api/v1/special-equipment/products",
        params=[
            (
                "category_path",
                "e2e-21808-lifting/e2e-21808-cranes",
            ),
            ("condition", "used"),
            ("engine_hours_min", "1800"),
            (
                "attribute",
                f"{summary.attribute_ids['engine_power']}:gte:200",
            ),
            (
                "attribute",
                f"{summary.attribute_ids['drive']}:eq:{E2E_PREFIX}_OPTION_DRIVE_6X6",
            ),
        ],
    )

    assert lifting_path.status_code == 200, lifting_path.text
    assert construction_path.status_code == 200, construction_path.text
    assert [item["code"] for item in lifting_path.json()["items"]] == [
        f"{E2E_PREFIX}_CATEGORY_LIFTING",
        f"{E2E_PREFIX}_CATEGORY_CRANES",
    ]
    assert [item["code"] for item in construction_path.json()["items"]] == [
        f"{E2E_PREFIX}_CATEGORY_CONSTRUCTION",
        f"{E2E_PREFIX}_CATEGORY_CRANES",
    ]
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["code"] == f"{E2E_PREFIX}_PRODUCT_02_USED_CRANE"
    assert body["facets"]["usage"]["metric"] == "engine_hours"
    facet_codes = {
        attribute["code"]
        for group in body["facets"]["attribute_groups"]
        for attribute in group["attributes"]
    }
    assert facet_codes == {
        f"{E2E_PREFIX}_ATTRIBUTE_ENGINE_POWER",
        f"{E2E_PREFIX}_ATTRIBUTE_DRIVE",
        f"{E2E_PREFIX}_ATTRIBUTE_BOOM_LENGTH",
    }


async def test_fixture_drives_truck_listing_and_truck_only_facets(
    db_session: AsyncSession,
    client: AsyncClient,
) -> None:
    summary = await seed_special_equipment_e2e_21808(db_session)
    truck_path = "e2e-21808-trucks"
    listing = await client.get(
        "/api/v1/special-equipment/products",
        params=[
            ("category_path", truck_path),
            ("condition", "used"),
            ("mileage_min", "120000"),
            (
                "attribute",
                f"{summary.attribute_ids['engine_power']}:gte:400",
            ),
            (
                "attribute",
                f"{summary.attribute_ids['drive']}:eq:{E2E_PREFIX}_OPTION_DRIVE_6X4",
            ),
        ],
    )
    facets = await client.get(
        "/api/v1/special-equipment/facets",
        params=[
            ("category_path", truck_path),
            ("condition", "used"),
            ("mileage_min", "120000"),
        ],
    )

    assert listing.status_code == 200, listing.text
    listing_body = listing.json()
    assert listing_body["pagination"]["total"] == 1
    assert listing_body["items"][0]["code"] == (
        f"{E2E_PREFIX}_PRODUCT_03_USED_TRUCK"
    )
    assert listing_body["items"][0]["mileage_km"] == 126000
    assert listing_body["items"][0]["engine_hours"] is None
    assert listing_body["facets"]["usage"] == {
        "metric": "mileage_km",
        "min": 126000,
        "max": 126000,
    }

    assert facets.status_code == 200, facets.text
    facets_body = facets.json()
    assert facets_body["usage"] == {
        "metric": "mileage_km",
        "min": 126000,
        "max": 126000,
    }
    listing_facet_codes = {
        attribute["code"]
        for group in listing_body["facets"]["attribute_groups"]
        for attribute in group["attributes"]
    }
    standalone_facet_codes = {
        attribute["code"]
        for group in facets_body["attribute_groups"]
        for attribute in group["attributes"]
    }
    expected_codes = {
        f"{E2E_PREFIX}_ATTRIBUTE_ENGINE_POWER",
        f"{E2E_PREFIX}_ATTRIBUTE_DRIVE",
    }
    assert listing_facet_codes == expected_codes
    assert standalone_facet_codes == expected_codes
    assert f"{E2E_PREFIX}_ATTRIBUTE_BOOM_LENGTH" not in listing_facet_codes
    assert f"{E2E_PREFIX}_ATTRIBUTE_BOOM_LENGTH" not in standalone_facet_codes
