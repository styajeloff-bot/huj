"""Prepare real, namespace-owned data for the compact vehicle card E2E suite.

Run after scripts/e2e/reset-fixture.sh, with the runner's exported environment:
    cd backend && uv run python ../scripts/e2e/22386/prepare.py
Use --cleanup before the next reset to restore the shared fixture and remove
this suite's additional warehouse/color. No production API response is mocked.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from application.queries.special_equipment import (  # noqa: E402
    GetSpecialEquipmentProductQuery,
    handle_get_product,
)
from domain.special_equipment_management import (  # noqa: E402
    ensure_warehouse_owner_matches_seller,
)
from infrastructure.database import AsyncSessionLocal  # noqa: E402
from infrastructure.models.companies import Company  # noqa: E402
from infrastructure.models.special_equipment import (  # noqa: E402
    SpecialEquipmentAttribute,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentColor,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentProduct,
)
from infrastructure.models.vehicles import Warehouse  # noqa: E402
from infrastructure.settings import settings  # noqa: E402
from scripts.seed_special_equipment_e2e import (  # noqa: E402
    FixtureContext,
    fixture_context,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_context() -> tuple[Path, dict[str, Any], FixtureContext]:
    namespace = os.environ.get("E2E_NAMESPACE", "").strip()
    manifest_name = os.environ.get("E2E_MANIFEST", "").strip()
    require(bool(namespace and manifest_name), "E2E_NAMESPACE and E2E_MANIFEST are required")
    manifest_path = Path(manifest_name)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    context = fixture_context(namespace)
    require(manifest.get("namespace") == namespace, "Fixture namespace does not match E2E_NAMESPACE")
    require(manifest.get("prefix") == context.prefix, "Fixture prefix does not match namespace")
    database = make_url(settings.database_dsn)
    expected_database = os.environ.get("E2E_POSTGRES_DB", "carcraft_e2e")
    require(
        database.database == expected_database
        and "e2e" in expected_database.lower()
        and database.host in {"127.0.0.1", "localhost", "::1", "postgres"},
        "Refusing to prepare compact-card data outside the local E2E database",
    )
    return manifest_path, manifest, context


def product_ref(product: SpecialEquipmentProduct) -> dict[str, str]:
    return {"id": str(product.id), "slug": product.slug, "code": product.code}


def serializable_fields(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        name: str(value) if isinstance(value, (UUID, Decimal)) else value
        for name in fields
        for value in (getattr(row, name),)
    }


async def take_snapshot(
    session: AsyncSession,
    products: dict[str, SpecialEquipmentProduct],
    modification_id: UUID,
    category_id: UUID,
    attributes: dict[str, SpecialEquipmentAttribute],
) -> dict[str, Any]:
    values = []
    for key in ("capacity", "free", "abs", "esp"):
        attribute_id = attributes[key].id
        row = await session.get(
            SpecialEquipmentModificationAttributeValue,
            (modification_id, attribute_id),
        )
        values.append({
            "attribute_id": str(attribute_id),
            "state": None if row is None else serializable_fields(
                row, ("value_number", "value_text", "value_boolean", "option_id")
            ),
        })
    free_rule = await session.get(
        SpecialEquipmentCategoryAttribute, (category_id, attributes["free"].id)
    )
    return {
        "products": [
            {"id": str(product.id), **serializable_fields(
                product, ("warehouse_id", "body_color_id", "sale_status")
            )}
            for product in products.values()
        ],
        "modification_id": str(modification_id),
        "category_id": str(category_id),
        "values": values,
        "free_attribute_id": str(attributes["free"].id),
        "free_rule": None if free_rule is None else serializable_fields(
            free_rule, ("group_id", "is_required", "is_filterable", "is_visible", "sort_order")
        ),
    }


async def prepare_price_on_request_product(
    session: AsyncSession,
    manifest: dict[str, Any],
    context: FixtureContext,
    snapshot: dict[str, Any],
) -> dict[str, str]:
    product = await session.get(SpecialEquipmentProduct, UUID(manifest["products"]["onOrder"]["id"]))
    require(
        product is not None
        and product.code.startswith(context.prefix)
        and product.publication_status == "published"
        and product.sale_status == "on_order",
        "Expected a published, namespace-owned on-order fixture",
    )
    assert product is not None
    snapshot.setdefault("price_on_request_product", {
        "id": str(product.id),
        **serializable_fields(product, ("price", "special_price", "price_on_request", "price_from")),
    })
    # This is seed construction, not a production mutation: public commands
    # intentionally forbid switching the pricing mode after publication.
    # Keep the existing warehouse, availability, price and publication intact.
    product.price_on_request = True
    product.price_from = Decimal("2700000.00")
    await session.flush()
    detail = await handle_get_product(GetSpecialEquipmentProductQuery(product.id), session)
    require(
        detail["price_on_request"] is True
        and detail["price_from"] == "2700000.00"
        and detail["capabilities"]["can_add_to_cart"] is True,
        "Price-on-request fixture must remain available for the cart",
    )
    return product_ref(product)


async def restore_price_on_request_product(
    session: AsyncSession, snapshot: dict[str, Any], context: FixtureContext
) -> None:
    record = snapshot.get("price_on_request_product")
    if record is None:
        return
    product = await session.get(SpecialEquipmentProduct, UUID(record["id"]))
    require(product is not None and product.code.startswith(context.prefix), "Refusing to restore an unowned price fixture")
    assert product is not None
    product.price = Decimal(record["price"]) if record["price"] is not None else None
    product.special_price = Decimal(record["special_price"]) if record["special_price"] is not None else None
    product.price_on_request = record["price_on_request"]
    product.price_from = Decimal(record["price_from"]) if record["price_from"] is not None else None

async def prepare(
    session: AsyncSession, manifest: dict[str, Any], context: FixtureContext
) -> dict[str, Any]:
    products: dict[str, SpecialEquipmentProduct] = {}
    for key in ("representative", "equivalent", "kitWithMod"):
        row = await session.get(SpecialEquipmentProduct, UUID(manifest["products"][key]["id"]))
        require(row is not None and row.code.startswith(context.prefix), f"Missing owned product: {key}")
        assert row is not None
        products[key] = row
    representative = products["representative"]
    equivalent = products["equivalent"]
    require(
        representative.modification_id == equivalent.modification_id
        and representative.seller_company_id == equivalent.seller_company_id,
        "Representative group modification or seller differs",
    )
    seller = await session.get(Company, representative.seller_company_id)
    require(seller is not None and seller.company_type == "dealer", "Expected fixture dealer")
    assert seller is not None
    primary_warehouse = await session.get(Warehouse, context.entity_id("warehouse:catalog"))
    require(primary_warehouse is not None, "Run the shared fixture reset first")
    assert primary_warehouse is not None
    ensure_warehouse_owner_matches_seller(
        company_id=primary_warehouse.owner_company_id,
        dealer_id=primary_warehouse.owner_company_id,
        seller_company_id=representative.seller_company_id,
    )
    secondary_warehouse = await session.merge(Warehouse(
        id=context.entity_id("warehouse:22386-secondary"),
        name=f"{context.prefix} Второй склад 22386",
        owner_company_id=seller.id,
        owner_company_type=seller.company_type,
        address=(f"г. Москва, {context.prefix} Производственно-логистический проезд, "
                 "дом 22386, корпус 2, территория дилерского центра коммерческой техники, "
                 "площадка выдачи автомобилей и склад запасных частей"),
        is_active=True,
    ))
    body_color = await session.merge(SpecialEquipmentColor(
        id=context.entity_id("color:22386-body"),
        code=f"{context.slug_prefix}-22386-body",
        name=f"{context.prefix} Белый",
        applicability="body",
        is_active=True,
    ))
    attributes: dict[str, SpecialEquipmentAttribute] = {}
    for key in ("capacity", "color", "description", "free", "abs", "esp"):
        attribute = await session.get(SpecialEquipmentAttribute, UUID(manifest["attributes"][key]["id"]))
        require(attribute is not None and attribute.code.startswith(context.prefix), f"Missing attribute: {key}")
        assert attribute is not None
        attributes[key] = attribute
    category_id = UUID(manifest["categories"]["leaf"]["id"])
    modification_id = representative.modification_id
    prior = manifest.get("compact_card", {})
    snapshot = prior.get("restore") or await take_snapshot(
        session, products, modification_id, category_id, attributes
    )

    # The same seller must own both warehouses. Seller is part of the public
    # offering fingerprint; warehouse is not. A foreign owner is invalid data.
    representative.warehouse_id = primary_warehouse.id
    equivalent.warehouse_id = secondary_warehouse.id
    representative.body_color_id = body_color.id
    equivalent.body_color_id = body_color.id
    products["kitWithMod"].warehouse_id = secondary_warehouse.id
    for product in (representative, equivalent, products["kitWithMod"]):
        ensure_warehouse_owner_matches_seller(
            company_id=seller.id, dealer_id=seller.id,
            seller_company_id=product.seller_company_id,
        )
    await session.merge(SpecialEquipmentCategoryAttribute(
        category_id=category_id,
        attribute_id=attributes["free"].id,
        group_id=attributes["free"].attribute_group_id,
        is_required=False,
        is_filterable=False,
        is_visible=True,
        sort_order=60,
    ))
    for key, column, value in (
        ("capacity", "value_number", Decimal("0")),
        ("free", "value_text", "6×4"),
        ("abs", "value_boolean", True),
        ("esp", "value_boolean", False),
    ):
        fields = {"value_number": None, "value_text": None, "value_boolean": None, "option_id": None}
        fields[column] = value
        await session.merge(SpecialEquipmentModificationAttributeValue(
            modification_id=modification_id, attribute_id=attributes[key].id, **fields
        ))
    await session.flush()

    detail = await handle_get_product(GetSpecialEquipmentProductQuery(representative.id), session)
    composite = await handle_get_product(GetSpecialEquipmentProductQuery(products["kitWithMod"].id), session)
    expected_order = ("capacity", "free", "color", "description", "abs", "esp")
    expected_ids = [attributes[key].id for key in expected_order]
    require([item["id"] for item in detail["card_attributes"]] == expected_ids, "Expected six ordered public attributes")
    expected_displays = [
        "0 тонн", "6×4", manifest["options"]["white"]["name"],
        f"{context.prefix} магистральное шасси", "Да", "Нет",
    ]
    require(
        [item["display_value"] for item in detail["card_attributes"]] == expected_displays,
        "Unexpected compact-card attribute values",
    )
    expected_stock = sorted([
        {"warehouse_id": str(warehouse.id), "owner_company_name": seller.name,
         "address": warehouse.address, "count": 1}
        for warehouse in (primary_warehouse, secondary_warehouse)
    ], key=lambda row: (row["address"], row["warehouse_id"]))
    actual_stock = [
        {"warehouse_id": str(row["warehouse_id"]), "owner_company_name": row["owner_company_name"],
         "address": row["address"], "count": row["count"]}
        for row in detail["warehouse_stock"]
    ]
    require(actual_stock == expected_stock and detail["available_count"] == 2, "Expected a valid 1+1 stock group")
    require(
        len(composite["warehouse_stock"]) == 1
        and composite["warehouse_stock"][0]["warehouse_id"] == secondary_warehouse.id
        and composite["warehouse_stock"][0]["owner_company_name"] == seller.name
        and composite["warehouse_stock"][0]["count"] == 1,
        "Composite must inherit its base component warehouse",
    )
    public_attributes = [
        {"id": str(item["id"]), **{key: item[key] for key in ("name", "data_type", "value", "display_value")}}
        for item in detail["card_attributes"]
    ]
    return {
        "product": product_ref(representative),
        "equivalent_product": product_ref(equivalent),
        "search": representative.description,
        "warehouses": expected_stock,
        "available_count": 2,
        "attributes": public_attributes,
        "zero_attribute": public_attributes[0],
        "false_attribute": public_attributes[-1],
        "body_color": {"id": str(body_color.id), "name": body_color.name},
        "composite_product": product_ref(products["kitWithMod"]),
        "composite_warehouses": [row for row in expected_stock if row["warehouse_id"] == str(secondary_warehouse.id)],
        "price_on_request_product": await prepare_price_on_request_product(session, manifest, context, snapshot),
        "restore": snapshot,
    }


async def cleanup(
    session: AsyncSession, manifest: dict[str, Any], context: FixtureContext
) -> None:
    snapshot = manifest.get("compact_card", {}).get("restore")
    require(bool(snapshot), "Cleanup requires compact_card.restore from prepare; run it before the shared reset")
    assert snapshot is not None
    await restore_price_on_request_product(session, snapshot, context)
    for record in snapshot["products"]:
        product = await session.get(SpecialEquipmentProduct, UUID(record["id"]))
        require(product is not None and product.code.startswith(context.prefix), "Refusing to restore an unowned product")
        assert product is not None
        product.warehouse_id = UUID(record["warehouse_id"]) if record["warehouse_id"] else None
        product.body_color_id = UUID(record["body_color_id"]) if record["body_color_id"] else None
        product.sale_status = record["sale_status"]
    modification_id = UUID(snapshot["modification_id"])
    for record in snapshot["values"]:
        attribute_id = UUID(record["attribute_id"])
        state = record["state"]
        if state is None:
            await session.execute(sa.delete(SpecialEquipmentModificationAttributeValue).where(
                SpecialEquipmentModificationAttributeValue.modification_id == modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id == attribute_id,
            ))
        else:
            await session.merge(SpecialEquipmentModificationAttributeValue(
                modification_id=modification_id, attribute_id=attribute_id,
                value_number=Decimal(state["value_number"]) if state["value_number"] is not None else None,
                value_text=state["value_text"], value_boolean=state["value_boolean"],
                option_id=UUID(state["option_id"]) if state["option_id"] else None,
            ))
    category_id = UUID(snapshot["category_id"])
    attribute_id = UUID(snapshot["free_attribute_id"])
    rule = snapshot["free_rule"]
    if rule is None:
        await session.execute(sa.delete(SpecialEquipmentCategoryAttribute).where(
            SpecialEquipmentCategoryAttribute.category_id == category_id,
            SpecialEquipmentCategoryAttribute.attribute_id == attribute_id,
        ))
    else:
        await session.merge(SpecialEquipmentCategoryAttribute(
            category_id=category_id, attribute_id=attribute_id,
            **{**rule, "group_id": UUID(rule["group_id"]) if rule["group_id"] else None},
        ))
    await session.flush()
    await session.execute(sa.delete(Warehouse).where(Warehouse.id == context.entity_id("warehouse:22386-secondary")))
    await session.execute(sa.delete(SpecialEquipmentColor).where(SpecialEquipmentColor.id == context.entity_id("color:22386-body")))


async def main(clean: bool) -> None:
    path, manifest, context = load_context()
    async with AsyncSessionLocal() as session, session.begin():
        if clean:
            await cleanup(session, manifest, context)
            manifest.pop("compact_card")
        else:
            manifest["compact_card"] = await prepare(session, manifest, context)
    temporary = path.with_name(f".{path.name}.22386.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    sys.stdout.write("22386 fixture cleaned\n" if clean else "22386 fixture prepared: six attributes, two valid warehouses\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true", help="Restore shared fixture and remove extra warehouse/color")
    asyncio.run(main(parser.parse_args().cleanup))
