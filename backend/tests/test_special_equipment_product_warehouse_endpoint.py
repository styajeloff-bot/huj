"""Focused contracts for the product warehouse replacement endpoint."""

from typing import Any
from unittest.mock import ANY, AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from application.commands import special_equipment_management as commands
from application.special_equipment_management_etag import (
    special_equipment_management_etag,
)
from domain.special_equipment_management import (
    ProductWarehouseValidationError,
    SpecialEquipmentManagementPreconditionError,
)
from presentation.routers.special_equipment_management import (
    _commit,
    _expected_precondition,
    _http,
    router,
)
from presentation.schemas.special_equipment_management import (
    ProductWarehouseReplaceRequest,
)


def _product(
    *,
    product_id: UUID,
    no_vin: bool,
    lock_version: int = 1,
    sale_status: str = "available",
) -> dict[str, Any]:
    return {
        "id": product_id,
        "lock_version": lock_version,
        "no_vin": no_vin,
        "code": "product",
        "sale_status": sale_status,
        "seller_company_id": None,
    }


def _patchable_product(
    *,
    product_id: UUID,
    no_vin: bool,
    warehouse_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        **_product(product_id=product_id, no_vin=no_vin),
        "warehouse_id": warehouse_id,
        "modification_id": uuid4(),
        "trim_id": None,
        "seller_company_id": None,
        "body_color_id": None,
        "interior_color_id": None,
        "price": 1,
        "vin": None if no_vin else "VIN",
        "condition": "new",
        "owners_count": None,
        "mileage_km": None,
        "engine_hours": None,
        "manufacture_year": 2024,
        "publication_status": "draft",
        "sale_status": "available",
        "category_ids": [],
        "attribute_values": [],
    }


def test_product_warehouse_request_requires_explicit_warehouse_field() -> None:
    with pytest.raises(ValidationError):
        ProductWarehouseReplaceRequest.model_validate({})

    assert ProductWarehouseReplaceRequest(warehouse_id=None).warehouse_id is None


@pytest.mark.asyncio
async def test_product_get_validation_uses_problem_json(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        "/api/v1/admin/special-equipment/products/not-a-uuid",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 422


@pytest.mark.asyncio
async def test_create_no_vin_product_with_warehouse_returns_problem_contract(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_product = AsyncMock(
        side_effect=ProductWarehouseValidationError(
            "Товар без VIN не может быть привязан к складу",
            code="WAREHOUSE_NOT_ALLOWED",
        )
    )
    monkeypatch.setattr(commands, "create_product_idempotent", create_product)

    response = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={
            "Authorization": f"Bearer {employee_token}",
            "Idempotency-Key": "warehouse-contract-create",
        },
        json={
            "code": "no-vin-with-warehouse",
            "modification_id": uuid4(),
            "category_ids": [uuid4()],
            "condition": "new",
            "no_vin": True,
            "warehouse_id": uuid4(),
        },
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "WAREHOUSE_NOT_ALLOWED"
    assert response.json()["status"] == 422
    create_product.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_rejects_explicit_warehouse_for_no_vin_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    current = _patchable_product(product_id=product_id, no_vin=False)
    patch = AsyncMock()
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "patch_entity", patch)
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)

    with pytest.raises(ProductWarehouseValidationError) as raised:
        await commands.patch_entity(
            AsyncMock(),
            entity_type="product",
            entity_id=product_id,
            values={"no_vin": True, "warehouse_id": uuid4()},
            expected_version=1,
            expected_etag=special_equipment_management_etag(current),
        )

    assert raised.value.error_code == "WAREHOUSE_NOT_ALLOWED"
    http_error = _http(raised.value)
    assert http_error.status_code == 422
    assert isinstance(http_error.detail, dict)
    assert http_error.detail["code"] == "WAREHOUSE_NOT_ALLOWED"
    patch.assert_not_awaited()
    replace.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_allows_unrelated_update_of_legacy_vin_product_without_warehouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    current = _patchable_product(product_id=product_id, no_vin=False)
    updated = {**current, "price": 2, "lock_version": 2}
    patch = AsyncMock(return_value=True)
    replace = AsyncMock()
    warehouse_is_active = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "patch_entity", patch)
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)
    monkeypatch.setattr(commands.repository, "warehouse_is_active", warehouse_is_active)
    monkeypatch.setattr(commands.repository, "get_entity", AsyncMock(return_value=updated))
    monkeypatch.setattr(commands.repository, "increment_catalog_revision", AsyncMock())
    monkeypatch.setattr(commands, "_validate_product", AsyncMock())

    result = await commands.patch_entity(
        AsyncMock(),
        entity_type="product",
        entity_id=product_id,
        values={"price": 2},
        expected_version=1,
        expected_etag=special_equipment_management_etag(current),
    )

    assert result == updated
    patch.assert_awaited_once_with(ANY, "product", product_id, {"price": 2})
    warehouse_is_active.assert_not_awaited()
    replace.assert_not_awaited()


def test_product_warehouse_endpoint_uses_put_and_if_match() -> None:
    route = next(
        route
        for route in router.routes
        if getattr(route, "path", None) == "/products/{product_id}/warehouse"
    )

    assert isinstance(route, APIRoute)
    assert route.methods == {"PUT"}
    assert any(parameter.name == "if_match" for parameter in route.dependant.header_params)


def test_product_warehouse_precondition_rejects_missing_weak_and_foreign_etags() -> None:
    product_id = uuid4()
    foreign_id = uuid4()

    for raw in (None, 'W/"x"', f'"{foreign_id}:1:{"0" * 64}"'):
        with pytest.raises(HTTPException) as exc_info:
            _expected_precondition(raw, product_id, problem=True)
        assert exc_info.value.status_code in {412, 428}
        assert exc_info.value.headers == {
            "content-type": "application/problem+json"
        }


@pytest.mark.asyncio
async def test_replace_product_warehouse_rejects_stale_etag_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    current = _product(product_id=product_id, no_vin=False)
    stale = _product(product_id=product_id, no_vin=False, lock_version=2)
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)

    with pytest.raises(SpecialEquipmentManagementPreconditionError):
        await commands.replace_product_warehouse(
            AsyncMock(),
            product_id=product_id,
            warehouse_id=uuid4(),
            expected_version=2,
            expected_etag=special_equipment_management_etag(stale),
        )

    replace.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_product_warehouse_enforces_vin_and_active_warehouse_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    current = _product(product_id=product_id, no_vin=False)
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)

    with pytest.raises(ProductWarehouseValidationError) as raised:
        await commands.replace_product_warehouse(
            AsyncMock(),
            product_id=product_id,
            warehouse_id=None,
            expected_version=1,
            expected_etag=special_equipment_management_etag(current),
        )

    assert raised.value.error_code == "WAREHOUSE_REQUIRED"
    replace.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("warehouse_exists", "warehouse_is_active", "expected_code"),
    ((False, False, "WAREHOUSE_NOT_FOUND"), (True, False, "WAREHOUSE_INACTIVE")),
)
async def test_replace_product_warehouse_returns_distinct_warehouse_codes(
    monkeypatch: pytest.MonkeyPatch,
    warehouse_exists: bool,
    warehouse_is_active: bool,
    expected_code: str,
) -> None:
    product_id = uuid4()
    current = _product(product_id=product_id, no_vin=False)
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)
    monkeypatch.setattr(
        commands.repository, "warehouse_exists", AsyncMock(return_value=warehouse_exists)
    )
    monkeypatch.setattr(
        commands.repository,
        "warehouse_is_active",
        AsyncMock(return_value=warehouse_is_active),
    )

    with pytest.raises(ProductWarehouseValidationError) as raised:
        await commands.replace_product_warehouse(
            AsyncMock(),
            product_id=product_id,
            warehouse_id=uuid4(),
            expected_version=1,
            expected_etag=special_equipment_management_etag(current),
        )

    assert raised.value.error_code == expected_code
    http_error = _http(raised.value)
    assert http_error.status_code == 422
    assert http_error.headers == {"content-type": "application/problem+json"}
    assert isinstance(http_error.detail, dict)
    assert http_error.detail["code"] == expected_code
    replace.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_product_warehouse_allows_null_for_no_vin_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    current = _product(product_id=product_id, no_vin=True)
    updated = {**current, "lock_version": 2, "warehouse_id": None}
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)
    monkeypatch.setattr(commands.repository, "get_entity", AsyncMock(return_value=updated))
    monkeypatch.setattr(commands.repository, "increment_catalog_revision", AsyncMock())

    assert (
        await commands.replace_product_warehouse(
            AsyncMock(),
            product_id=product_id,
            warehouse_id=None,
            expected_version=1,
            expected_etag=special_equipment_management_etag(current),
        )
        == updated
    )
    replace.assert_awaited_once_with(
        ANY, product_id=product_id, warehouse_id=None
    )


@pytest.mark.asyncio
async def test_replace_product_warehouse_only_replaces_link_and_returns_new_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    warehouse_id = uuid4()
    current = _product(product_id=product_id, no_vin=False)
    updated = {**current, "lock_version": 2, "warehouse_id": warehouse_id}
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "warehouse_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(commands.repository, "warehouse_is_active", AsyncMock(return_value=True))
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)
    validate_assignment = AsyncMock()
    monkeypatch.setattr(commands, "_validate_product_warehouse", validate_assignment)
    monkeypatch.setattr(commands.repository, "get_entity", AsyncMock(return_value=updated))
    monkeypatch.setattr(commands.repository, "increment_catalog_revision", AsyncMock())

    result = await commands.replace_product_warehouse(
        AsyncMock(),
        product_id=product_id,
        warehouse_id=warehouse_id,
        expected_version=1,
        expected_etag=special_equipment_management_etag(current),
    )

    assert result == updated
    replace.assert_awaited_once_with(
        ANY, product_id=product_id, warehouse_id=warehouse_id
    )
    validate_assignment.assert_awaited_once_with(
        ANY,
        no_vin=False,
        sale_status="available",
        warehouse_id=warehouse_id,
        seller_company_id=None,
    )


@pytest.mark.asyncio
async def test_replace_product_warehouse_allows_null_for_on_order_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    current = _product(product_id=product_id, no_vin=False, sale_status="on_order")
    updated = {**current, "lock_version": 2, "warehouse_id": None}
    replace = AsyncMock()
    monkeypatch.setattr(commands.repository, "lock_catalog_for_mutation", AsyncMock())
    monkeypatch.setattr(commands.repository, "lock_entity", AsyncMock(return_value=current))
    monkeypatch.setattr(commands.repository, "replace_product_warehouse", replace)
    monkeypatch.setattr(commands.repository, "get_entity", AsyncMock(return_value=updated))
    monkeypatch.setattr(commands.repository, "increment_catalog_revision", AsyncMock())

    result = await commands.replace_product_warehouse(
        AsyncMock(),
        product_id=product_id,
        warehouse_id=None,
        expected_version=1,
        expected_etag=special_equipment_management_etag(current),
    )

    assert result == updated
    replace.assert_awaited_once_with(
        ANY, product_id=product_id, warehouse_id=None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint_name", "expected_code"),
    (
        ("fk_se_products_warehouse", "WAREHOUSE_NOT_FOUND"),
        ("trg_se_product_warehouse_active", "WAREHOUSE_INACTIVE"),
        ("trg_se_product_warehouse_no_vin", "WAREHOUSE_NOT_ALLOWED"),
        ("trg_se_product_warehouse_required", "WAREHOUSE_REQUIRED"),
    ),
)
async def test_commit_maps_warehouse_race_backstops_to_problem_details(
    constraint_name: str,
    expected_code: str,
) -> None:
    class DatabaseOriginError(Exception):
        def __init__(self) -> None:
            self.sqlstate = "23503"
            self.constraint_name = constraint_name

    async def operation() -> None:
        raise IntegrityError(
            "UPDATE special_equipment_products", {}, DatabaseOriginError()
        )

    session = AsyncMock()
    with pytest.raises(HTTPException) as raised:
        await _commit(session, operation())

    assert raised.value.status_code == 422
    assert isinstance(raised.value.detail, dict)
    assert raised.value.detail["code"] == expected_code
    assert raised.value.headers == {"content-type": "application/problem+json"}
    session.rollback.assert_awaited_once()
