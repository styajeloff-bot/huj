"""HTTP contracts for storefront-scoped cart, favorites, and applications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import CatalogScope
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
)
from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
from infrastructure.models.vehicles import Warehouse
from main import app
from tests.legacy_compat import Vehicle, VehicleWarehouse
from tests.special_equipment_factories import special_equipment_directory

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True, slots=True)
class ScopedCatalog:
    scope: CatalogScope
    in_scope_vehicle: Vehicle
    out_of_scope_vehicle: Vehicle
    in_scope_special_equipment: SpecialEquipmentProduct
    out_of_scope_special_equipment: SpecialEquipmentProduct


@pytest_asyncio.fixture
async def scoped_catalog(db_session: AsyncSession) -> ScopedCatalog:
    selected_warehouse = Warehouse(
        address="Склад витрины",
        brand="FAW",
        status="active",
    )
    other_warehouse = Warehouse(
        address="Другой склад",
        brand="OTHER",
        status="active",
    )
    storefront = Storefront(
        id=uuid4(),
        slug="faw",
        is_default=False,
        is_active=True,
        version=1,
    )
    in_scope_vehicle = Vehicle(status="available", is_available=True)
    out_of_scope_vehicle = Vehicle(status="available", is_available=True)
    seller = Company(name="Scoped special seller", company_type="dealer")
    mark, model, modification = special_equipment_directory(
        mark_name="Scoped commerce mark",
        model_name="Scoped commerce model",
        modification_name="Scoped commerce modification",
    )
    db_session.add_all(
        [
            selected_warehouse,
            other_warehouse,
            storefront,
            in_scope_vehicle,
            out_of_scope_vehicle,
            seller,
            mark,
            model,
            modification,
        ]
    )
    await db_session.flush()
    in_scope_special_equipment = SpecialEquipmentProduct(
        code=f"scoped-commerce-in-{uuid4()}",
        slug=f"scoped-commerce-in-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        warehouse_id=selected_warehouse.id,
        condition="new",
        vin=f"SCIN{str(uuid4().int)[-12:]}",
        no_vin=False,
        price=Decimal("100.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    out_of_scope_special_equipment = SpecialEquipmentProduct(
        code=f"scoped-commerce-out-{uuid4()}",
        slug=f"scoped-commerce-out-{uuid4()}",
        modification_id=modification.id,
        seller_company_id=seller.id,
        warehouse_id=other_warehouse.id,
        condition="new",
        vin=f"SCOUT{str(uuid4().int)[-11:]}",
        no_vin=False,
        price=Decimal("200.00"),
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add_all(
        [
            in_scope_special_equipment,
            out_of_scope_special_equipment,
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            StorefrontWarehouse(
                storefront_id=storefront.id,
                warehouse_id=selected_warehouse.id,
            ),
            VehicleWarehouse(
                vehicle_id=in_scope_vehicle.id,
                warehouse_id=selected_warehouse.id,
            ),
            VehicleWarehouse(
                vehicle_id=out_of_scope_vehicle.id,
                warehouse_id=other_warehouse.id,
            ),
        ]
    )
    await db_session.flush()
    return ScopedCatalog(
        scope=CatalogScope(
            id=storefront.id,
            slug="faw",
            version=1,
            is_default=False,
        ),
        in_scope_vehicle=in_scope_vehicle,
        out_of_scope_vehicle=out_of_scope_vehicle,
        in_scope_special_equipment=in_scope_special_equipment,
        out_of_scope_special_equipment=out_of_scope_special_equipment,
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/storefronts/faw/cart/"),
        ("GET", "/api/v1/storefronts/faw/client/favorites"),
        ("POST", "/api/v1/storefronts/faw/applications"),
        ("POST", "/api/v1/storefronts/faw/commerce/leasing-applications"),
    ],
)
async def test_storefront_commerce_routes_require_authentication(
    client: AsyncClient,
    method: str,
    path: str,
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 401


async def test_storefront_commerce_item_catalog_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"/api/v1/storefronts/faw/commerce/items/special_equipment/{uuid4()}"
    )

    assert response.status_code == 401


async def test_storefront_commerce_routes_document_scope_specific_behavior(
) -> None:
    schema = app.openapi()

    for path, method in (
        (
            "/api/v1/storefronts/{storefront_slug}/commerce/"
            "items/{item_type}/{item_id}",
            "get",
        ),
        (
            "/api/v1/storefronts/{storefront_slug}/commerce/leasing-applications",
            "post",
        ),
    ):
        description = schema["paths"][path][method].get("description")
        assert description
        assert "витрин" in description.casefold()


async def test_storefront_special_equipment_projection_nulls_foreign_detail_url(
    client: AsyncClient,
    client_token: str,
    scoped_catalog: ScopedCatalog,
) -> None:
    headers = _auth(client_token)
    visible = await client.get(
        "/api/v1/storefronts/faw/commerce/items/special_equipment/"
        f"{scoped_catalog.in_scope_special_equipment.id}",
        headers=headers,
    )
    hidden = await client.get(
        "/api/v1/storefronts/faw/commerce/items/special_equipment/"
        f"{scoped_catalog.out_of_scope_special_equipment.id}",
        headers=headers,
    )
    hidden_detail = await client.get(
        "/api/v1/storefronts/faw/special-equipment/products/"
        f"{scoped_catalog.out_of_scope_special_equipment.id}",
    )
    root = await client.get(
        "/api/v1/commerce/items/special_equipment/"
        f"{scoped_catalog.out_of_scope_special_equipment.id}",
        headers=headers,
    )

    assert visible.status_code == 200
    assert visible.json()["item"]["detail_url"].endswith(
        f"/{scoped_catalog.in_scope_special_equipment.slug}"
    )
    assert hidden.status_code == 200
    assert hidden.json()["item"]["detail_url"] is None
    assert hidden_detail.status_code == 404
    assert root.status_code == 200
    assert root.json()["item"]["detail_url"].endswith(
        f"/{scoped_catalog.out_of_scope_special_equipment.slug}"
    )



async def test_storefront_cart_rejects_vehicle_from_another_warehouse(
    client: AsyncClient,
    client_token: str,
    scoped_catalog: ScopedCatalog,
) -> None:
    accepted = await client.post(
        "/api/v1/storefronts/faw/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": scoped_catalog.in_scope_vehicle.id, "quantity": 1},
    )
    rejected = await client.post(
        "/api/v1/storefronts/faw/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": scoped_catalog.out_of_scope_vehicle.id, "quantity": 1},
    )
    root_added = await client.post(
        "/api/v1/cart/",
        headers=_auth(client_token),
        json={"vehicle_id": scoped_catalog.out_of_scope_vehicle.id, "quantity": 1},
    )
    listed = await client.get(
        "/api/v1/storefronts/faw/cart/",
        headers=_auth(client_token),
    )
    root_listed = await client.get(
        "/api/v1/cart/",
        headers=_auth(client_token),
    )

    assert accepted.status_code == 201, accepted.text
    assert rejected.status_code == 404
    assert root_added.status_code == 201, root_added.text
    assert [item["vehicle_id"] for item in listed.json()["items"]] == [
        str(scoped_catalog.in_scope_vehicle.id)
    ]
    assert [item["vehicle_id"] for item in root_listed.json()["items"]] == [
        str(scoped_catalog.out_of_scope_vehicle.id)
    ]


async def test_storefront_favorites_reject_vehicle_from_another_warehouse(
    client: AsyncClient,
    client_token: str,
    scoped_catalog: ScopedCatalog,
) -> None:
    accepted = await client.post(
        "/api/v1/storefronts/faw/client/favorites/"
        f"{scoped_catalog.in_scope_vehicle.id}",
        headers=_auth(client_token),
    )
    rejected = await client.post(
        "/api/v1/storefronts/faw/client/favorites/"
        f"{scoped_catalog.out_of_scope_vehicle.id}",
        headers=_auth(client_token),
    )
    listed = await client.get(
        "/api/v1/storefronts/faw/client/favorites",
        headers=_auth(client_token),
    )

    assert accepted.status_code == 201, accepted.text
    assert rejected.status_code == 404
    assert [item["vehicle_id"] for item in listed.json()["favorites"]] == [
        str(scoped_catalog.in_scope_vehicle.id)
    ]
