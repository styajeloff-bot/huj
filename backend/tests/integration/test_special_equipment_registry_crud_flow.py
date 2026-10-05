"""Management routing contract for corrected catalog resources."""

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import special_equipment_management as commands
from domain.special_equipment_management import (
    SpecialEquipmentManagementPreconditionError,
)
from infrastructure.models.users import User
from infrastructure.repositories import (
    special_equipment_import_repository as import_repository,
)
from infrastructure.repositories import (
    special_equipment_management_repository as management_repository,
)
from presentation.routers.special_equipment_management import router


def test_management_router_exposes_corrected_resources_without_manufacturers() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin/special-equipment")
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/admin/special-equipment/marks" in paths
    assert "/api/v1/admin/special-equipment/models" in paths
    assert "/api/v1/admin/special-equipment/modifications" in paths
    assert "/api/v1/admin/special-equipment/attribute-groups" in paths
    assert "/api/v1/admin/special-equipment/categories/{entity_id}/parents" in paths
    assert "/api/v1/admin/special-equipment/categories/{category_id}/image" in paths
    assert "/api/v1/admin/special-equipment/products/{product_id}/images" in paths
    assert "/api/v1/admin/special-equipment/manufacturers" not in paths


async def test_management_create_receipt_is_stored_and_replayed(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    actor_id = employee_user.id
    revision_before = await import_repository.get_catalog_revision(db_session)
    first = await commands.create_entity_idempotent(
        db_session,
        actor_id=actor_id,
        idempotency_key="create-mark-once",
        request_hash="a" * 64,
        entity_type="mark",
        values={"code": "once", "name": "Один раз", "is_active": True},
    )
    revision_after_create = await import_repository.get_catalog_revision(db_session)
    changed = await commands.patch_entity(
        db_session,
        entity_type="mark",
        entity_id=first["id"],
        values={"name": "Изменённое имя"},
        expected_version=first["lock_version"],
    )
    revision_after_change = await import_repository.get_catalog_revision(db_session)
    replay = await commands.create_entity_idempotent(
        db_session,
        actor_id=actor_id,
        idempotency_key="create-mark-once",
        request_hash="a" * 64,
        entity_type="mark",
        values={"code": "once", "name": "Один раз", "is_active": True},
    )
    receipt = await management_repository.get_mutation_receipt(
        db_session, actor_id, "create-mark-once"
    )
    revision_after_replay = await import_repository.get_catalog_revision(db_session)

    assert replay == first
    assert changed["name"] == "Изменённое имя"
    assert changed["lock_version"] == first["lock_version"] + 1
    assert revision_after_create == revision_before + 1
    assert revision_after_change == revision_after_create + 1
    assert revision_after_replay == revision_after_change
    assert receipt == {
        "request_hash": "a" * 64,
        "resource_type": "mark",
        "resource_id": first["id"],
        "response_snapshot": first,
    }


async def test_failed_management_precondition_does_not_advance_catalog_revision(
    db_session: AsyncSession,
) -> None:
    mark = await commands.create_entity(
        db_session,
        entity_type="mark",
        values={"code": "revision-guard", "name": "Ревизия", "is_active": True},
    )
    revision_before = await import_repository.get_catalog_revision(db_session)

    with pytest.raises(SpecialEquipmentManagementPreconditionError):
        await commands.patch_entity(
            db_session,
            entity_type="mark",
            entity_id=mark["id"],
            values={"name": "Не должно сохраниться"},
            expected_version=mark["lock_version"] + 1,
        )

    assert await import_repository.get_catalog_revision(db_session) == revision_before


async def test_nested_catalog_relations_and_product_gallery_are_live(
    db_session: AsyncSession,
) -> None:
    mark = await commands.create_entity(
        db_session,
        entity_type="mark",
        values={"code": "mark", "name": "Марка", "is_active": True},
    )
    model = await commands.create_entity(
        db_session,
        entity_type="model",
        values={
            "code": "model",
            "name": "Модель",
            "mark_id": mark["id"],
            "is_active": True,
        },
    )
    group = await commands.create_entity(
        db_session,
        entity_type="attribute_group",
        values={
            "code": "engine",
            "name": "Двигатель",
            "sort_order": 0,
            "is_active": True,
        },
    )
    attribute = await commands.create_entity(
        db_session,
        entity_type="attribute",
        values={
            "code": "drive",
            "name": "Привод",
            "data_type": "select",
            "unit": None,
            "filter_kind": "exact",
            "is_active": True,
            "options": [
                {
                    "id": None,
                    "code": "awd",
                    "name": "Полный",
                    "sort_order": 0,
                    "is_active": True,
                }
            ],
        },
    )
    category = await commands.create_entity(
        db_session,
        entity_type="category",
        values={
            "code": "cranes",
            "name": "Краны",
            "usage_metric": "engine_hours",
            "sort_order": 0,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": [
                {
                    "attribute_id": attribute["id"],
                    "group_id": group["id"],
                    "is_required": True,
                    "is_filterable": True,
                    "is_visible": True,
                    "sort_order": 0,
                }
            ],
        },
    )
    secondary_category = await commands.create_entity(
        db_session,
        entity_type="category",
        values={
            "code": "lifting-equipment",
            "name": "Подъёмная техника",
            "usage_metric": "engine_hours",
            "sort_order": 1,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": [],
        },
    )
    option = attribute["options"][0]
    modification = await commands.create_entity(
        db_session,
        entity_type="modification",
        values={
            "code": "modification",
            "name": "Модификация",
            "model_id": model["id"],
            "year_from": 2020,
            "year_to": 2026,
            "is_active": True,
            "category_ids": [category["id"], secondary_category["id"]],
            "attribute_values": [
                {
                    "attribute_id": attribute["id"],
                    "option_id": option["id"],
                    "value": None,
                }
            ],
        },
    )
    product = await commands.create_entity(
        db_session,
        entity_type="product",
        values={
            "code": "offer",
            "modification_id": modification["id"],
            "seller_company_id": None,
            "description": None,
            "price": None,
            "currency_code": "RUB",
            "manufacture_year": 2024,
            "vin": None,
            "no_vin": True,
            "condition": "used",
            "owners_count": 1,
            "mileage_km": None,
            "engine_hours": 100,
            "publication_status": "draft",
            "sale_status": "unavailable",
            "category_ids": [category["id"]],
        },
    )

    assert category["attribute_links"][0]["attribute_name"] == "Привод"
    assert model["mark"]["id"] == mark["id"]
    assert modification["model"]["mark"]["id"] == mark["id"]
    assert modification["category_ids"] == [
        category["id"],
        secondary_category["id"],
    ]
    assert modification["attribute_values"][0]["option_id"] == option["id"]
    assert product["modification"]["id"] == modification["id"]
    assert product["categories"][0]["id"] == category["id"]

    storage_key = f"special-equipment/registry/products/{product['id']}/one.webp"
    await commands.reserve_media_upload(db_session, storage_key)
    image_result = await commands.add_product_image(
        db_session,
        product_id=product["id"],
        expected_version=product["lock_version"],
        storage_key=storage_key,
        alt_text="Кран",
    )
    assert image_result["image"]["is_primary"] is True
    assert image_result["product"]["images"][0]["alt_text"] == "Кран"

    reordered = await commands.update_product_image(
        db_session,
        product_id=product["id"],
        image_id=image_result["image"]["id"],
        expected_version=image_result["product"]["lock_version"],
        values={"sort_order": 0},
    )
    assert reordered["image"]["alt_text"] == "Кран"
