"""HTTP and PostgreSQL contracts for special-equipment colors (Bitrix 22056)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, QueryParams
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import special_equipment_management as commands
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentColor,
    SpecialEquipmentProduct,
)
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio

_MANAGEMENT_COLORS = "/api/v1/admin/special-equipment/colors"
_PUBLIC_PRODUCTS = "/api/v1/special-equipment/products"
_PUBLIC_FACETS = "/api/v1/special-equipment/facets"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _valid_etag(resource_id: UUID, *, version: int = 1) -> str:
    return f'"{resource_id}:{version}:{"a" * 64}"'


def _assert_color_error(
    response: Any,
    *,
    status_code: int,
    code: str,
) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert "detail" in body["error"]
    assert isinstance(body["error"]["field_errors"], list)
    return cast("dict[str, Any]", body["error"])


async def _add_color(
    db_session: AsyncSession,
    *,
    name: str,
    applicability: str = "both",
    is_active: bool = True,
) -> SpecialEquipmentColor:
    suffix = uuid4().hex
    color = SpecialEquipmentColor(
        code=f"color-{suffix}",
        name=f"{name} {suffix}",
        applicability=applicability,
        is_active=is_active,
    )
    db_session.add(color)
    await db_session.flush()
    return color


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_unknown_color_returns_color_not_found_from_real_route(
    client: AsyncClient,
    employee_token: str,
    method: str,
) -> None:
    color_id = uuid4()
    headers = _auth(employee_token)
    request_kwargs: dict[str, Any] = {"headers": headers}
    if method in {"PATCH", "DELETE"}:
        request_kwargs["headers"] = {
            **headers,
            "If-Match": _valid_etag(color_id),
        }
    if method == "PATCH":
        request_kwargs["json"] = {"name": "Несуществующий цвет"}

    response = await client.request(
        method,
        f"{_MANAGEMENT_COLORS}/{color_id}",
        **request_kwargs,
    )

    _assert_color_error(response, status_code=404, code="color_not_found")


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
async def test_color_mutation_without_if_match_returns_428(
    client: AsyncClient,
    employee_token: str,
    method: str,
) -> None:
    request_kwargs: dict[str, Any] = {"headers": _auth(employee_token)}
    if method == "PATCH":
        request_kwargs["json"] = {"name": "Новый цвет"}

    response = await client.request(
        method,
        f"{_MANAGEMENT_COLORS}/{uuid4()}",
        **request_kwargs,
    )

    _assert_color_error(
        response,
        status_code=428,
        code="precondition_required",
    )


@pytest.mark.parametrize(
    "if_match",
    [
        "broken",
        f'W/"{UUID("00000000-0000-0000-0000-000000000001")}:1:{"a" * 64}"',
    ],
)
async def test_color_patch_rejects_malformed_if_match_from_real_route(
    client: AsyncClient,
    employee_token: str,
    if_match: str,
) -> None:
    response = await client.patch(
        f"{_MANAGEMENT_COLORS}/{uuid4()}",
        headers={**_auth(employee_token), "If-Match": if_match},
        json={"name": "Некорректный ETag"},
    )

    _assert_color_error(
        response,
        status_code=400,
        code="malformed_if_match",
    )


async def test_delete_rejects_etag_from_another_color(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    target = await _add_color(db_session, name="Целевой")
    other = await _add_color(db_session, name="Другой")
    other_response = await client.get(
        f"{_MANAGEMENT_COLORS}/{other.id}",
        headers=_auth(employee_token),
    )
    assert other_response.status_code == 200, other_response.text

    response = await client.delete(
        f"{_MANAGEMENT_COLORS}/{target.id}",
        headers={
            **_auth(employee_token),
            "If-Match": other_response.headers["etag"],
        },
    )

    error = _assert_color_error(
        response,
        status_code=409,
        code="etag_resource_mismatch",
    )
    assert error["detail"] == {
        "expected_resource_type": "special-equipment-color"
    }


async def test_delete_rejects_stale_color_etag(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    color = await _add_color(db_session, name="Версионируемый")
    detail = await client.get(
        f"{_MANAGEMENT_COLORS}/{color.id}",
        headers=_auth(employee_token),
    )
    assert detail.status_code == 200, detail.text
    stale_etag = detail.headers["etag"]

    updated = await client.patch(
        f"{_MANAGEMENT_COLORS}/{color.id}",
        headers={**_auth(employee_token), "If-Match": stale_etag},
        json={"name": "Обновлённый версионируемый"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.headers["etag"] != stale_etag

    response = await client.delete(
        f"{_MANAGEMENT_COLORS}/{color.id}",
        headers={**_auth(employee_token), "If-Match": stale_etag},
    )

    _assert_color_error(response, status_code=409, code="stale_etag")


async def _add_product(
    db_session: AsyncSession,
    *,
    modification_id: UUID,
    seller_company_id: UUID,
    code: str,
    body_color_id: UUID | None,
    interior_color_id: UUID | None,
) -> SpecialEquipmentProduct:
    product = SpecialEquipmentProduct(
        code=code,
        slug=code,
        modification_id=modification_id,
        seller_company_id=seller_company_id,
        body_color_id=body_color_id,
        interior_color_id=interior_color_id,
        description=f"Публичное предложение {code}",
        price=Decimal("1000000.00"),
        manufacture_year=2024,
        condition="used",
        vin=None,
        no_vin=True,
        owners_count=1,
        engine_hours=100,
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.flush()
    return product


@pytest.mark.parametrize("color_field", ["body_color_id", "interior_color_id"])
async def test_delete_fk_race_returns_color_in_use_without_counters(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
    color_field: str,
) -> None:
    color = await _add_color(db_session, name="Используемый")
    seller = Company(name=f"Продавец {uuid4().hex}", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="Марка FK race",
        model_name="Модель FK race",
        modification_name="Модификация FK race",
    )
    db_session.add_all([seller, mark, model, modification])
    await db_session.flush()
    color_ids: dict[str, UUID | None] = {
        "body_color_id": None,
        "interior_color_id": None,
    }
    color_ids[color_field] = color.id
    await _add_product(
        db_session,
        modification_id=modification.id,
        seller_company_id=seller.id,
        code=f"fk-race-{color_field}-{uuid4().hex}",
        body_color_id=color_ids["body_color_id"],
        interior_color_id=color_ids["interior_color_id"],
    )
    detail = await client.get(
        f"{_MANAGEMENT_COLORS}/{color.id}",
        headers=_auth(employee_token),
    )
    assert detail.status_code == 200, detail.text
    monkeypatch.setattr(
        commands.repository,
        "color_usage_counts",
        AsyncMock(return_value={"body": 0, "interior": 0}),
    )

    response = await client.delete(
        f"{_MANAGEMENT_COLORS}/{color.id}",
        headers={
            **_auth(employee_token),
            "If-Match": detail.headers["etag"],
        },
    )

    error = _assert_color_error(
        response,
        status_code=409,
        code="color_in_use",
    )
    assert error["detail"] is None


async def _seed_public_color_catalog(
    db_session: AsyncSession,
) -> dict[str, UUID]:
    suffix = uuid4().hex
    seller = Company(name=f"Публичный продавец {suffix}", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name=f"Публичная марка {suffix}",
        model_name=f"Публичная модель {suffix}",
        modification_name=f"Публичная модификация {suffix}",
    )
    body_a = await _add_color(
        db_session,
        name="Белый активный",
        applicability="body",
    )
    body_b = await _add_color(
        db_session,
        name="Синий активный",
        applicability="body",
    )
    body_inactive = await _add_color(
        db_session,
        name="Архивный кузов",
        applicability="body",
        is_active=False,
    )
    interior_x = await _add_color(
        db_session,
        name="Чёрный салон",
        applicability="interior",
    )
    interior_y = await _add_color(
        db_session,
        name="Серый салон",
        applicability="interior",
    )
    db_session.add_all([seller, mark, model, modification])
    await db_session.flush()

    combinations = {
        "body-a-interior-x": (body_a.id, interior_x.id),
        "body-a-interior-y": (body_a.id, interior_y.id),
        "body-b-interior-x": (body_b.id, interior_x.id),
        "body-inactive-interior-x": (body_inactive.id, interior_x.id),
        "without-colors": (None, None),
    }
    for label, (body_color_id, interior_color_id) in combinations.items():
        await _add_product(
            db_session,
            modification_id=modification.id,
            seller_company_id=seller.id,
            code=f"{label}-{suffix}",
            body_color_id=body_color_id,
            interior_color_id=interior_color_id,
        )

    return {
        "body_a": body_a.id,
        "body_b": body_b.id,
        "body_inactive": body_inactive.id,
        "interior_x": interior_x.id,
        "interior_y": interior_y.id,
    }


def _facet_counts(items: list[dict[str, Any]]) -> dict[UUID, int]:
    return {UUID(item["id"]): item["count"] for item in items}


async def test_public_products_show_inactive_color_but_facets_hide_it(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    ids = await _seed_public_color_catalog(db_session)

    response = await client.get(_PUBLIC_PRODUCTS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pagination"]["total"] == 5
    inactive_item = next(
        item
        for item in body["items"]
        if item["body_color"]
        and item["body_color"]["id"] == str(ids["body_inactive"])
    )
    assert inactive_item["body_color"] == {
        "id": str(ids["body_inactive"]),
        "name": inactive_item["body_color"]["name"],
    }
    assert _facet_counts(body["facets"]["body_colors"]) == {
        ids["body_a"]: 2,
        ids["body_b"]: 1,
    }
    assert _facet_counts(body["facets"]["interior_colors"]) == {
        ids["interior_x"]: 3,
        ids["interior_y"]: 1,
    }

    facets = await client.get(_PUBLIC_FACETS)
    assert facets.status_code == 200, facets.text
    assert _facet_counts(facets.json()["body_colors"]) == {
        ids["body_a"]: 2,
        ids["body_b"]: 1,
    }


async def test_public_color_filter_accepts_inactive_unknown_and_repeated_ids(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    ids = await _seed_public_color_catalog(db_session)
    unknown_id = uuid4()

    inactive = await client.get(
        _PUBLIC_PRODUCTS,
        params=[("body_color_id", str(ids["body_inactive"]))],
    )
    assert inactive.status_code == 200, inactive.text
    assert inactive.json()["pagination"]["total"] == 1
    assert inactive.json()["items"][0]["body_color"]["id"] == str(
        ids["body_inactive"]
    )
    assert ids["body_inactive"] not in _facet_counts(
        inactive.json()["facets"]["body_colors"]
    )

    repeated = await client.get(
        _PUBLIC_PRODUCTS,
        params=[
            ("body_color_id", str(unknown_id)),
            ("body_color_id", str(ids["body_a"])),
        ],
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["pagination"]["total"] == 2

    unknown = await client.get(
        _PUBLIC_FACETS,
        params=[("body_color_id", str(unknown_id))],
    )
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["interior_colors"] == []


async def test_public_color_facets_exclude_only_their_own_dimension(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    ids = await _seed_public_color_catalog(db_session)
    params = QueryParams(
        [
            ("body_color_id", str(ids["body_a"])),
            ("interior_color_id", str(ids["interior_x"])),
        ]
    )

    products = await client.get(_PUBLIC_PRODUCTS, params=params)
    facets = await client.get(_PUBLIC_FACETS, params=params)

    assert products.status_code == 200, products.text
    assert products.json()["pagination"]["total"] == 1
    expected_body = {ids["body_a"]: 1, ids["body_b"]: 1}
    expected_interior = {ids["interior_x"]: 1, ids["interior_y"]: 1}
    assert _facet_counts(products.json()["facets"]["body_colors"]) == expected_body
    assert (
        _facet_counts(products.json()["facets"]["interior_colors"])
        == expected_interior
    )
    assert facets.status_code == 200, facets.text
    assert _facet_counts(facets.json()["body_colors"]) == expected_body
    assert _facet_counts(facets.json()["interior_colors"]) == expected_interior
