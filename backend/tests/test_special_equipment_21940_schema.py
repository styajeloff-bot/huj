"""Schema contracts introduced for Bitrix task 21940."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models import Base
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)

FASTAPI_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_083 = (
    FASTAPI_ROOT
    / "alembic"
    / "versions"
    / "083_special_equipment_catalog_enhancements.py"
)
MIGRATION_085 = (
    FASTAPI_ROOT
    / "alembic"
    / "versions"
    / "085_special_equipment_management_completion.py"
)


def _check_sql(table: sa.Table, name: str) -> str:
    constraint = next(
        item
        for item in table.constraints
        if isinstance(item, sa.CheckConstraint) and item.name == name
    )
    return " ".join(str(constraint.sqltext).split())


def test_attribute_groups_have_default_and_nullable_category_override() -> None:
    attributes = Base.metadata.tables["special_equipment_attributes"]
    category_attributes = Base.metadata.tables[
        "special_equipment_category_attributes"
    ]

    default_group = attributes.c.attribute_group_id
    assert default_group.nullable is True
    assert getattr(default_group.type, "as_uuid", False) is True
    assert {foreign_key.target_fullname for foreign_key in default_group.foreign_keys} == {
        "special_equipment_attribute_groups.id"
    }
    assert category_attributes.c.group_id.nullable is True
    assert "idx_special_equipment_attributes_group" in {
        index.name for index in attributes.indexes
    }


def test_modification_categories_are_ordered_with_at_most_one_primary() -> None:
    categories = Base.metadata.tables["special_equipment_modification_categories"]

    assert categories.c.sort_order.nullable is False
    assert categories.c.is_primary.nullable is False
    assert _check_sql(categories, "ck_se_modification_categories_sort_order") == (
        "sort_order >= 0"
    )
    assert "uq_se_modification_categories_order" in {
        constraint.name
        for constraint in categories.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    primary_index = next(
        index
        for index in categories.indexes
        if index.name == "uq_se_modification_categories_primary"
    )
    assert primary_index.unique is True
    assert str(primary_index.dialect_options["postgresql"]["where"]) == "is_primary"


def test_product_owner_vin_and_on_order_constraints_match_contract() -> None:
    products = Base.metadata.tables["special_equipment_products"]

    assert products.c.owners_count.nullable is True
    assert products.c.no_vin.nullable is False
    constraint_names = {constraint.name for constraint in products.constraints}
    assert "ck_special_equipment_products_owners_count_nonnegative" in constraint_names
    assert "ck_special_equipment_products_owners_count_positive" not in constraint_names
    assert "owners_count >= 0" in _check_sql(
        products, "ck_special_equipment_products_condition_owners"
    )
    assert "char_length(vin) <= 17" in _check_sql(
        products, "ck_special_equipment_products_vin_choice"
    )
    assert "'on_order'" in _check_sql(
        products, "ck_special_equipment_products_sale_status"
    )
    assert "price > 0" in _check_sql(
        products, "ck_special_equipment_products_on_order_price"
    )

    for name in (
        "ck_special_equipment_products_owners_count_nonnegative",
        "ck_special_equipment_products_condition_owners",
        "ck_special_equipment_products_vin_choice",
    ):
        constraint = next(item for item in products.constraints if item.name == name)
        assert constraint.dialect_options["postgresql"]["not_valid"] is True


def test_text_search_and_public_availability_have_supporting_indexes() -> None:
    attributes = Base.metadata.tables["special_equipment_attributes"]
    marks = Base.metadata.tables["special_equipment_marks"]
    models = Base.metadata.tables["special_equipment_models"]
    modifications = Base.metadata.tables["special_equipment_modifications"]
    values = Base.metadata.tables[
        "special_equipment_modification_attribute_values"
    ]
    products = Base.metadata.tables["special_equipment_products"]
    orders = Base.metadata.tables["special_equipment_purchase_orders"]

    assert _check_sql(
        attributes, "ck_special_equipment_attributes_search_text"
    ) == "filter_kind IS DISTINCT FROM 'search' OR NOT (data_type IS DISTINCT FROM 'text')"

    assert "idx_se_marks_name_search" in {index.name for index in marks.indexes}
    assert "idx_se_models_name_search" in {
        index.name for index in models.indexes
    }
    assert "idx_se_modifications_name_search" in {
        index.name for index in modifications.indexes
    }
    assert "idx_se_modification_attribute_values_text_search" in {
        index.name for index in values.indexes
    }
    assert "idx_se_products_public_availability" in {
        index.name for index in products.indexes
    }
    assert "idx_se_products_description_search" in {
        index.name for index in products.indexes
    }
    category_updated = next(
        index
        for index in Base.metadata.tables["special_equipment_categories"].indexes
        if index.name == "idx_se_categories_updated_desc"
    )
    assert [str(expression) for expression in category_updated.expressions] == [
        "GREATEST(created_at, updated_at) DESC",
        "id DESC",
    ]
    live_seller_index = next(
        index for index in orders.indexes if index.name == "idx_se_orders_live_seller"
    )
    assert "'preordered'" in str(
        live_seller_index.dialect_options["postgresql"]["where"]
    )


def test_migration_083_invalidates_unfinished_pre_v4_import_previews() -> None:
    migration = MIGRATION_083.read_text(encoding="utf-8")

    assert "UPDATE special_equipment_import_jobs" in migration
    assert "normalized_artifact_key IS NOT NULL" in migration
    assert "applied_revision IS NULL" in migration
    assert "status IN ('preview_ready', 'applying')" in migration
    assert "SET status = 'preview_stale'" in migration
    assert "error_code = 'PREVIEW_STALE'" in migration


def test_migration_083_preserves_existing_rows_and_extends_commerce_states() -> None:
    migration = MIGRATION_083.read_text(encoding="utf-8")
    payments = Base.metadata.tables["special_equipment_payments"]

    assert 'revision: str = "083"' in migration
    assert 'down_revision: str | None = "082"' in migration
    assert "SET no_vin = (vin IS NULL)" in migration
    assert migration.count("postgresql_not_valid=True") == 4
    assert migration.count('"ck_special_equipment_attributes_search_text"') == 2
    assert "normalization_state" not in migration
    assert "purchase_type IN ('reservation', 'preorder', 'full_purchase', 'leasing')" in migration
    assert "'reservation', 'preorder', 'full_purchase'" in _check_sql(
        payments, "ck_special_equipment_payment_type"
    )
    assert migration.count('"ck_special_equipment_payment_type"') == 4
    assert "'preordered', 'cancellation_requested'" in migration
    assert "purchase_type <> 'preorder' AND status IN" in migration
    assert "Cannot downgrade 083 while on-order products or preorder orders exist" in migration


def test_migration_085_weakens_used_owner_checks_and_adds_category_sort_index() -> None:
    migration = MIGRATION_085.read_text(encoding="utf-8")

    assert 'revision: str = "085"' in migration
    assert 'down_revision: str | None = "084"' in migration
    assert "idx_se_categories_updated_desc" in migration
    assert "GREATEST(created_at, updated_at) DESC" in migration
    assert "owners_count IS NULL OR owners_count >= 0" in migration
    assert "owners_count IS NOT NULL AND owners_count >= 0" in migration
    assert (
        "drop_owner_constraint_name=_POSITIVE_OWNER_CONSTRAINT" in migration
    )
    assert (
        "create_owner_constraint_name=_NONNEGATIVE_OWNER_CONSTRAINT"
        in migration
    )
    assert (
        "drop_owner_constraint_name=_NONNEGATIVE_OWNER_CONSTRAINT"
        in migration
    )
    assert (
        "create_owner_constraint_name=_POSITIVE_OWNER_CONSTRAINT" in migration
    )


async def _persist_modification(session: AsyncSession) -> SpecialEquipmentModification:
    suffix = uuid4().hex
    mark_id, model_id, modification_id = uuid4(), uuid4(), uuid4()
    mark = SpecialEquipmentMark(
        id=mark_id,
        code=f"schema-mark-{suffix}",
        name=f"Schema mark {suffix}",
        slug=f"schema-mark-{suffix}",
    )
    model = SpecialEquipmentModel(
        id=model_id,
        mark_id=mark_id,
        code=f"schema-model-{suffix}",
        name=f"Schema model {suffix}",
        slug=f"schema-model-{suffix}",
    )
    modification = SpecialEquipmentModification(
        id=modification_id,
        model_id=model_id,
        code=f"schema-modification-{suffix}",
        name=f"Schema modification {suffix}",
        slug=f"schema-modification-{suffix}",
    )
    session.add_all((mark, model, modification))
    await session.flush()
    return modification


@pytest.mark.asyncio
async def test_fresh_products_enforce_owner_and_vin_contract(
    db_session: AsyncSession,
) -> None:
    modification = await _persist_modification(db_session)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SpecialEquipmentProduct(
                    code=f"missing-owners-{uuid4().hex}",
                    slug=f"missing-owners-{uuid4().hex}",
                    modification_id=modification.id,
                    condition="used",
                    owners_count=None,
                    engine_hours=1,
                    no_vin=True,
                )
            )
            await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SpecialEquipmentProduct(
                    code=f"long-vin-{uuid4().hex}",
                    slug=f"long-vin-{uuid4().hex}",
                    modification_id=modification.id,
                    condition="new",
                    owners_count=None,
                    no_vin=False,
                    vin="123456789012345678",
                )
            )
            await db_session.flush()

    valid = SpecialEquipmentProduct(
        code=f"valid-contract-{uuid4().hex}",
        slug=f"valid-contract-{uuid4().hex}",
        modification_id=modification.id,
        condition="used",
        owners_count=0,
        engine_hours=1,
        no_vin=True,
    )
    db_session.add(valid)
    await db_session.flush()
    assert valid.id is not None
