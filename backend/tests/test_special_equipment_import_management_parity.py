"""Regression contracts keeping XLSX import aligned with management writes."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application import special_equipment_import_v2 as import_v2
from domain.special_equipment_import import (
    DATA_SHEET_HEADERS,
    ImportMode,
    error_policy_for_mode,
)
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentProduct,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
)
from infrastructure.models.users import User
from infrastructure.repositories import (
    special_equipment_import_repository as import_repository,
)
from infrastructure.services.special_equipment_xlsx import ParsedWorkbook
from tests.special_equipment_factories import special_equipment_directory


def _catalog_context(
    *,
    sale_status: str = "available",
    published: bool = False,
) -> tuple[dict[str, Any], dict[str, UUID]]:
    ids = {
        "mark": uuid4(),
        "model": uuid4(),
        "modification": uuid4(),
        "category": uuid4(),
        "group": uuid4(),
        "attribute": uuid4(),
        "product": uuid4(),
        "seller": uuid4(),
    }
    publication_status = "published" if published else "draft"
    published_at = datetime(2026, 1, 1, tzinfo=UTC) if published else None
    context: dict[str, Any] = {
        "marks": {
            "mark-1": {
                "id": ids["mark"],
                "code": "mark-1",
                "name": "Марка",
                "slug": "mark-1",
                "is_active": True,
            }
        },
        "models": {
            "model-1": {
                "id": ids["model"],
                "code": "model-1",
                "name": "Модель",
                "slug": "model-1",
                "mark_id": ids["mark"],
                "is_active": True,
            }
        },
        "modifications": {
            "modification-1": {
                "id": ids["modification"],
                "code": "modification-1",
                "name": "Модификация",
                "slug": "modification-1",
                "model_id": ids["model"],
                "year_from": 2020,
                "year_to": 2026,
                "is_active": True,
            }
        },
        "trims": {},
        "categories": {
            "category-1": {
                "id": ids["category"],
                "code": "category-1",
                "name": "Категория",
                "slug": "category-1",
                "usage_metric": "mileage_km",
                "is_attachment_category": False,
                "sort_order": 0,
                "is_active": True,
            }
        },
        "attribute_groups": {
            "main": {
                "id": ids["group"],
                "code": "main",
                "name": "Основные",
                "slug": "main",
                "sort_order": 0,
                "is_active": True,
            }
        },
        "attributes": {
            "power": {
                "id": ids["attribute"],
                "code": "power",
                "name": "Мощность",
                "attribute_group_id": ids["group"],
                "data_type": "number",
                "unit": "л.с.",
                "filter_kind": "range",
                "is_active": True,
            }
        },
        "attribute_options": {},
        "colors": {},
        "products": {
            "product-1": {
                "id": ids["product"],
                "code": "product-1",
                "modification_id": ids["modification"],
                "trim_id": None,
                "seller_company_id": ids["seller"],
                "warehouse_id": None,
                "body_color_id": None,
                "interior_color_id": None,
                "description": "Товар",
                "price": Decimal("100.00"),
                "special_price": None,
                "currency_code": "RUB",
                "manufacture_year": 2025,
                "vin": None,
                "no_vin": True,
                "condition": "new",
                "owners_count": None,
                "mileage_km": None,
                "engine_hours": None,
                "publication_status": publication_status,
                "sale_status": sale_status,
                "published_at": published_at,
                "lock_version": 1,
            }
        },
        "category_relations": set(),
        "modification_categories": {
            (ids["modification"], ids["category"]),
        },
        "_modification_category_details": {
            ids["modification"]: {
                ids["category"]: {"sort_order": 0, "is_primary": True},
            }
        },
        "category_attributes": {},
        "modification_attribute_values": set(),
        "trim_attributes": {},
        "trim_attribute_values": set(),
        "units": {},
        "superstructures": {},
        "superstructure_attributes": {},
        "superstructure_usage_counts": {},
        "product_categories": {(ids["product"], ids["category"])},
        "product_chassis_values": set(),
        "product_superstructure_values": set(),
        "product_attachments": set(),
        "_product_attachment_details": {},
        "companies": {},
        "warehouses": {},
    }
    return context, ids


def _row(sheet: str, **values: Any) -> dict[str, Any]:
    return {
        "_sheet_code": sheet,
        "_row_number": 2,
        "_clear_fields": [],
        **values,
    }


async def _build_plan(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    context: dict[str, Any],
    mode: ImportMode,
    rows: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], import_v2.V2IssueCollector]:
    async def get_context(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return deepcopy(context)

    monkeypatch.setattr(import_v2.repo, "get_v2_import_context", get_context)
    workbook_rows: dict[str, Any] = {family: [] for family in DATA_SHEET_HEADERS}
    workbook_rows.update(rows)
    plan, issues, *_ = await import_v2.build_normalized_plan_v2(
        object(),  # type: ignore[arg-type]
        job={"mode": mode.value},
        workbook=ParsedWorkbook(
            manifest={
                "mode": mode.value,
                "error_policy": error_policy_for_mode(mode).value,
            },
            rows=workbook_rows,
        ),
        plan_spool_dir=tmp_path / f"plan-{uuid4().hex}",
    )
    return plan, issues


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "requested"),
    [
        ("available", "reserved"),
        ("available", "sold"),
        ("reserved", "available"),
        ("sold", "unavailable"),
    ],
)
async def test_import_rejects_commerce_owned_sale_status_transition(
    db_session: AsyncSession,
    current: str,
    requested: str,
) -> None:
    seller = Company(
        name=f"Sale parity seller {uuid4()}",
        company_type="dealer",
        is_active=True,
    )
    mark, model, modification = special_equipment_directory(
        mark_name="Sale parity mark",
        model_name="Sale parity model",
        modification_name="Sale parity modification",
    )
    db_session.add_all([seller, mark, model, modification])
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"sale-parity-{uuid4().hex}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug=f"sale-parity-{uuid4().hex}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        price=Decimal("100.00"),
        publication_status="published",
        sale_status=current,
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()

    result = await import_repository.apply_normalized_plan(
        db_session,
        job_id=uuid4(),
        mode=ImportMode.PATCH.value,
        plan={
            "products": [
                {
                    "id": product.id,
                    "code": product.code,
                    "operation": "SET",
                    "values": {
                        "modification_id": modification.id,
                        "seller_company_id": seller.id,
                        "slug": product.slug,
                        "description": None,
                        "price": Decimal("100.00"),
                        "special_price": None,
                        "currency_code": "RUB",
                        "manufacture_year": None,
                        "vin": None,
                        "no_vin": True,
                        "condition": "new",
                        "owners_count": None,
                        "mileage_km": None,
                        "engine_hours": None,
                        "publication_status": "published",
                        "sale_status": requested,
                        "published_at": product.published_at,
                    },
                    "_sheet_code": "Объявления",
                    "_row_number": 2,
                    "_aggregate_kind": "product",
                    "_aggregate_code": product.code,
                }
            ]
        },
    )
    await db_session.refresh(product)

    assert product.sale_status == current
    assert result["counts"]["updated"] == 0
    assert len(result["rejected_aggregates"]) == 1


@pytest.mark.asyncio
async def test_full_snapshot_rejects_modification_without_any_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context()
    context["products"] = {}
    context["product_categories"] = set()

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.FULL_SNAPSHOT,
        rows={
            "marks": [
                _row(
                    "Марки",
                    operation="SET",
                    code="mark-1",
                    name="Марка",
                    is_active=True,
                )
            ],
            "models": [
                _row(
                    "Модели",
                    operation="SET",
                    code="model-1",
                    name="Модель",
                    mark_code="mark-1",
                    is_active=True,
                )
            ],
            "modifications": [
                _row(
                    "Модификации",
                    operation="SET",
                    code="modification-1",
                    name="Модификация",
                    model_code="model-1",
                    year_from=2020,
                    year_to=2026,
                    is_active=True,
                )
            ],
            "categories": [
                _row(
                    "Категории",
                    operation="SET",
                    code="category-1",
                    name="Категория",
                    usage_metric="mileage_km",
                    is_attachment_category=False,
                    sort_order=0,
                    is_active=True,
                )
            ],
        },
    )

    assert issues.error_count == 1
    assert any("категор" in issue.message.lower() for issue in issues)
    assert list(plan["modifications"]) == []


@pytest.mark.asyncio
async def test_import_rejects_option_for_non_select_attribute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context()

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "attribute_options": [
                _row(
                    "Варианты характеристик",
                    operation="ADD",
                    attribute_code="power",
                    code="turbo",
                    name="Турбо",
                    sort_order=0,
                    is_active=True,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["attribute_options"]) == []


@pytest.mark.asyncio
async def test_import_rejects_modification_value_outside_effective_attributes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context()

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "modification_attribute_values": [
                _row(
                    "Характеристики модификаций",
                    operation="SET",
                    modification_code="modification-1",
                    attribute_code="power",
                    option_code=None,
                    value=250,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["modification_attribute_values"]) == []


@pytest.mark.asyncio
async def test_import_rejects_attribute_type_change_with_stored_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    context["modification_attribute_values"] = {
        (ids["modification"], ids["attribute"]),
    }

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "attributes": [
                _row(
                    "Характеристики",
                    operation="SET",
                    code="power",
                    name="Мощность",
                    group_code="main",
                    data_type="text",
                    filter_kind="search",
                    is_active=True,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["attributes"]) == []


@pytest.mark.asyncio
async def test_import_rejects_attribute_group_deactivation_with_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context()

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "attribute_groups": [
                _row(
                    "Группы характеристик",
                    operation="SET",
                    code="main",
                    name="Основные",
                    sort_order=0,
                    is_active=False,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["attribute_groups"]) == []


@pytest.mark.asyncio
async def test_import_rejects_attribute_deactivation_with_category_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    context["category_attributes"] = {
        (ids["category"], ids["attribute"]): {
            "category_id": ids["category"],
            "attribute_id": ids["attribute"],
            "group_id": ids["group"],
            "is_required": False,
            "is_filterable": True,
            "is_visible": True,
            "sort_order": 0,
        }
    }

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "attributes": [
                _row(
                    "Характеристики",
                    operation="SET",
                    code="power",
                    name="Мощность",
                    group_code="main",
                    data_type="number",
                    filter_kind="range",
                    is_active=False,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["attributes"]) == []


@pytest.mark.asyncio
async def test_import_rejects_referenced_option_deactivation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    option_id = uuid4()
    context["attributes"]["power"]["data_type"] = "select"
    context["attributes"]["power"]["filter_kind"] = "exact"
    context["attribute_options"] = {
        "power:turbo": {
            "id": option_id,
            "attribute_id": ids["attribute"],
            "code": "turbo",
            "name": "Турбо",
            "sort_order": 0,
            "is_active": True,
        }
    }
    value_key = (ids["modification"], ids["attribute"])
    context["modification_attribute_values"] = {value_key}
    context["_modification_attribute_value_details"] = {
        value_key: {"option_id": option_id}
    }

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "attribute_options": [
                _row(
                    "Варианты характеристик",
                    operation="SET",
                    attribute_code="power",
                    code="turbo",
                    name="Турбо",
                    sort_order=0,
                    is_active=False,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["attribute_options"]) == []


@pytest.mark.asyncio
async def test_structural_category_change_revalidates_published_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context(published=True)

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "categories": [
                _row(
                    "Категории",
                    operation="SET",
                    code="category-1",
                    is_active=False,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["categories"]) == []


@pytest.mark.asyncio
async def test_structural_year_range_change_revalidates_published_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context(published=True)

    plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "modifications": [
                _row(
                    "Модификации",
                    operation="SET",
                    code="modification-1",
                    model_code="model-1",
                    year_to=2024,
                )
            ]
        },
    )

    assert issues.error_count == 1
    assert list(plan["modifications"]) == []


@pytest.mark.asyncio
async def test_import_does_not_archive_product_with_active_dependencies(
    db_session: AsyncSession,
) -> None:
    seller = Company(
        name=f"Import parity seller {uuid4()}",
        company_type="dealer",
        is_active=True,
    )
    buyer = Company(
        name=f"Import parity buyer {uuid4()}",
        company_type="other",
        is_active=True,
    )
    user = User(phone=f"+77{uuid4().int % 10**9:09d}", role="client")
    mark, model, modification = special_equipment_directory(
        mark_name="Import parity mark",
        model_name="Import parity model",
        modification_name="Import parity modification",
    )
    db_session.add_all([seller, buyer, user, mark, model, modification])
    await db_session.flush()
    product = SpecialEquipmentProduct(
        code=f"import-parity-{uuid4().hex}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        slug=f"import-parity-{uuid4().hex}",
        condition="new",
        vin=None,
        no_vin=True,
        owners_count=None,
        publication_status="draft",
        sale_status="available",
    )
    application = LeasingApplication(company_id=buyer.id, created_by=user.id)
    db_session.add_all([product, application])
    await db_session.flush()
    db_session.add(
        SpecialEquipmentApplicationItem(
            application_id=application.id,
            product_id=product.id,
            seller_company_id=seller.id,
            item_snapshot={},
            item_status="active",
        )
    )
    await db_session.flush()

    result = await import_repository.apply_normalized_plan(
        db_session,
        job_id=uuid4(),
        mode=ImportMode.PATCH.value,
        plan={
            "products": [
                {
                    "id": product.id,
                    "code": product.code,
                    "operation": "DELETE",
                    "values": {},
                    "_sheet_code": "Объявления",
                    "_row_number": 2,
                    "_aggregate_kind": "product",
                    "_aggregate_code": product.code,
                }
            ]
        },
    )
    await db_session.refresh(product)

    assert product.publication_status == "draft"
    assert result["counts"]["archived"] == 0
    assert len(result["rejected_aggregates"]) == 1


@pytest.mark.asyncio
async def test_apply_rejects_attribute_group_deactivation_with_members(
    db_session: AsyncSession,
) -> None:
    group = SpecialEquipmentAttributeGroup(
        code=f"parity-group-{uuid4().hex}",
        name="Parity group",
        slug=f"parity-group-{uuid4().hex}",
        sort_order=0,
        is_active=True,
    )
    db_session.add(group)
    await db_session.flush()
    attribute = SpecialEquipmentAttribute(
        code=f"parity-attribute-{uuid4().hex}",
        name="Parity attribute",
        attribute_group_id=group.id,
        data_type="number",
        filter_kind="range",
        is_active=True,
    )
    db_session.add(attribute)
    await db_session.flush()

    result = await import_repository.apply_normalized_plan(
        db_session,
        job_id=uuid4(),
        mode=ImportMode.PATCH.value,
        plan={
            "attribute_groups": [
                {
                    "id": group.id,
                    "code": group.code,
                    "operation": "SET",
                    "values": {
                        "name": group.name,
                        "slug": group.slug,
                        "sort_order": group.sort_order,
                        "is_active": False,
                    },
                    "_sheet_code": "Группы характеристик",
                    "_row_number": 2,
                    "_aggregate_kind": "attribute_group",
                    "_aggregate_code": group.code,
                }
            ]
        },
    )
    await db_session.refresh(group)

    assert group.is_active is True
    assert result["counts"]["updated"] == 0
    assert len(result["rejected_aggregates"]) == 1


@pytest.mark.asyncio
async def test_superstructure_name_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context()
    s_id = uuid4()
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Существующая надстройка",
        "is_active": True,
    }

    # 1. DB conflict: another code with duplicate name
    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "superstructures": [
                _row(
                    "Надстройки",
                    operation="ADD",
                    code="s-2",
                    name="  существующая надстройка  ",
                    is_active=True,
                )
            ]
        },
    )
    assert any(
        issue.code == "SUPERSTRUCTURE_NAME_CONFLICT" and issue.column_name == "Название"
        for issue in issues
    )

    # 2. Workbook duplicate name conflict
    _plan2, issues2 = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "superstructures": [
                _row(
                    "Надстройки",
                    operation="ADD",
                    code="s-3",
                    name="Новая надстройка",
                    is_active=True,
                ),
                _row(
                    "Надстройки",
                    operation="ADD",
                    code="s-4",
                    name="НОВАЯ НАДСТРОЙКА",
                    is_active=True,
                ),
            ]
        },
    )
    assert any(
        issue.code == "SUPERSTRUCTURE_NAME_CONFLICT" and issue.column_name == "Название"
        for issue in issues2
    )

    # 3. SET on the same superstructure preserving name does NOT conflict with itself
    _plan3, issues3 = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "superstructures": [
                _row(
                    "Надстройки",
                    operation="SET",
                    code="s-1",
                    name="Существующая надстройка",
                    is_active=True,
                )
            ]
        },
    )
    assert not any(
        issue.code == "SUPERSTRUCTURE_NAME_CONFLICT"
        for issue in issues3
    )


@pytest.mark.asyncio
async def test_kit_superstructure_model_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ids = _catalog_context()
    s_id = uuid4()
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "is_active": True,
    }

    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-1",
                    superstructure_code="s-1",
                    model_code="model-1",
                    # superstructure_model_code is omitted
                    superstructure_name="Кран",
                    superstructure_manufacturer="Завод",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ]
        },
    )
    assert any(
        issue.code == "KIT_SUPERSTRUCTURE_MODEL_REQUIRED"
        for issue in issues
    )


@pytest.mark.asyncio
async def test_kit_chassis_modification_model_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    other_model_id = uuid4()
    other_mod_id = uuid4()
    s_id = uuid4()
    context["models"]["model-2"] = {
        "id": other_model_id,
        "code": "model-2",
        "name": "Модель 2",
        "mark_id": ids["mark"],
        "is_active": True,
    }
    context["modifications"]["mod-2"] = {
        "id": other_mod_id,
        "code": "mod-2",
        "name": "Модификация 2",
        "model_id": other_model_id,
        "is_active": True,
    }
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "model_id": ids["model"],
        "modification_id": None,
        "is_active": True,
    }

    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-1",
                    superstructure_code="s-1",
                    superstructure_model_code="model-1",
                    model_code="model-1",
                    modification_code="mod-2",
                    superstructure_name="Кран",
                    superstructure_manufacturer="Завод",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ]
        },
    )
    assert any(
        issue.code == "KIT_CHASSIS_MODIFICATION_MODEL_MISMATCH"
        for issue in issues
    )


@pytest.mark.asyncio
async def test_kit_superstructure_modification_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    s_id = uuid4()
    other_model_id = uuid4()
    other_mod_id = uuid4()
    context["models"]["model-2"] = {
        "id": other_model_id,
        "code": "model-2",
        "name": "Модель 2",
        "mark_id": ids["mark"],
        "is_active": True,
    }
    context["modifications"]["mod-2"] = {
        "id": other_mod_id,
        "code": "mod-2",
        "name": "Модификация 2",
        "model_id": other_model_id,
        "is_active": True,
    }
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "is_active": True,
    }

    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-1",
                    superstructure_code="s-1",
                    superstructure_model_code="model-1",
                    superstructure_modification_code="mod-2",
                    model_code="model-1",
                    superstructure_name="Кран",
                    superstructure_manufacturer="Завод",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ]
        },
    )
    assert any(
        issue.code == "KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH"
        for issue in issues
    )


@pytest.mark.asyncio
async def test_kit_kind_conflict_and_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    s_id = uuid4()
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "model_id": ids["model"],
        "modification_id": None,
        "is_active": True,
    }

    # Attempting to change an existing ordinary product into a kit
    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="SET",
                    code="product-1",
                    superstructure_code="s-1",
                    model_code="model-1",
                    superstructure_name="Кран",
                    superstructure_manufacturer="Завод",
                )
            ]
        },
    )
    assert any(
        issue.code == "PRODUCT_KIND_IMMUTABLE"
        for issue in issues
    )


@pytest.mark.asyncio
async def test_kit_compatibility_forbidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    s_id = uuid4()
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "model_id": ids["model"],
        "modification_id": None,
        "is_active": True,
    }
    context["products"]["kit-1"] = {
        "id": uuid4(),
        "code": "kit-1",
        "superstructure_id": s_id,
        "model_id": ids["model"],
        "modification_id": None,
        "is_active": True,
    }

    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "product_attachments": [
                _row(
                    "Совместимые надстройки",
                    operation="ADD",
                    product_code="kit-1",
                    attachment_product_code="product-1",
                )
            ]
        },
    )
    assert any(
        issue.code == "KIT_COMPATIBILITY_FORBIDDEN"
        for issue in issues
    )


@pytest.mark.asyncio
async def test_kit_attachment_category_forbidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    s_id = uuid4()
    att_cat_id = uuid4()
    context["categories"]["att-cat"] = {
        "id": att_cat_id,
        "code": "att-cat",
        "name": "Категория надстроек",
        "is_attachment_category": True,
        "is_active": True,
    }
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "model_id": ids["model"],
        "modification_id": None,
        "is_active": True,
    }

    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "product_categories": [
                _row(
                    "Категории объявлений",
                    operation="ADD",
                    product_code="kit-1",
                    category_code="att-cat",
                )
            ],
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-1",
                    superstructure_code="s-1",
                    superstructure_model_code="model-1",
                    model_code="model-1",
                    superstructure_name="Кран",
                    superstructure_manufacturer="Завод",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ],
        },
    )
    assert any(
        issue.code == "KIT_ATTACHMENT_CATEGORY"
        for issue in issues
    )


@pytest.mark.asyncio
async def test_kit_chassis_values_with_modification_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    s_id = uuid4()
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "model_id": ids["model"],
        "modification_id": None,
        "is_active": True,
    }

    # Kit product WITH chassis modification ("modification-1") must NOT have product_chassis_values
    _plan, issues = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-1",
                    superstructure_code="s-1",
                    superstructure_model_code="model-1",
                    model_code="model-1",
                    modification_code="modification-1",
                    superstructure_name="Кран",
                    superstructure_manufacturer="Завод",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ],
            "product_categories": [
                _row(
                    "Категории объявлений",
                    operation="ADD",
                    product_code="kit-1",
                    category_code="category-1",
                )
            ],
            "product_chassis_values": [
                _row(
                    "Характеристики шасси объявлений",
                    operation="ADD",
                    product_code="kit-1",
                    attribute_code="power",
                    value="150",
                )
            ],
        },
    )
    assert any(
        issue.code == "KIT_CHASSIS_VALUES_WITH_MODIFICATION"
        for issue in issues
    ), [f"{i.code}: {i.message}" for i in issues]


@pytest.mark.asyncio
async def test_kit_superstructure_source_conflict_and_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, ids = _catalog_context()
    s_id = uuid4()
    context["superstructures"]["s-1"] = {
        "id": s_id,
        "code": "s-1",
        "name": "Надстройка",
        "is_active": True,
    }
    att_cat_id = uuid4()
    context["categories"]["att-cat"] = {
        "id": att_cat_id,
        "code": "att-cat",
        "name": "Категория надстроек",
        "is_attachment_category": True,
        "is_active": True,
    }

    # 1. Source conflict: both superstructure_source_code and manual superstructure field
    _plan1, issues1 = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-conflict",
                    superstructure_code="s-1",
                    model_code="model-1",
                    superstructure_source_code="source-ad",
                    superstructure_name="Ручное имя",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ]
        },
    )
    assert any(
        issue.code == "KIT_SUPERSTRUCTURE_SOURCE_CONFLICT"
        for issue in issues1
    )

    # 2. Source not found
    _plan2, issues2 = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-missing",
                    superstructure_code="s-1",
                    model_code="model-1",
                    superstructure_source_code="non-existent-source",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ]
        },
    )
    assert any(
        issue.code == "PRODUCT_NOT_FOUND" and issue.column_name == "Код объявления надстройки"
        for issue in issues2
    )

    # 3. Source invalid: source product is in non-attachment category
    source_id = uuid4()
    context["products"]["source-ordinary"] = {
        "id": source_id,
        "code": "source-ordinary",
        "model_id": ids["model"],
        "modification_id": ids["modification"],
        "superstructure_id": None,
        "is_kit": False,
        "publication_status": "draft",
        "is_active": True,
    }
    # Category is category-1 which is NOT attachment category
    context["product_categories_map"] = {source_id: {ids["category"]}}

    _plan3, issues3 = await _build_plan(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        context=context,
        mode=ImportMode.PATCH,
        rows={
            "products": [
                _row(
                    "Объявления",
                    operation="ADD",
                    code="kit-bad-cat",
                    superstructure_code="s-1",
                    model_code="model-1",
                    superstructure_source_code="source-ordinary",
                    condition="new",
                    no_vin=True,
                    publication_status="draft",
                    sale_status="available",
                )
            ]
        },
    )
    assert any(
        issue.code == "KIT_SUPERSTRUCTURE_SOURCE_INVALID"
        for issue in issues3
    )

