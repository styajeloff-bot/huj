"""Focused unit and HTTP-contract tests for the unified commerce facade."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from application.commands.purchases import PayRemainingCommand, handle_pay_remaining
from application.commerce import (
    CommerceFacade,
    CommerceLeasingApplicationLineCommand,
    CreateCommerceLeasingApplicationBatchCommand,
    CreateCommerceLeasingApplicationCommand,
    CreateCommerceOrderCommand,
    CreateCommercePaymentCommand,
    SpecialEquipmentCommerceAdapter,
    VehicleCommerceAdapter,
)
from application.errors import ServiceError
from application.special_equipment_checkout import (
    AllocatedCartLine,
    AllocatedComponent,
    CheckoutAllocation,
)
from domain.commerce import CommerceItemRef, CommerceItemType, CommerceOrderRef
from domain.entities.purchase_order import PurchaseOrder
from domain.errors import PaymentNotFoundError
from domain.special_equipment_commerce import ProductCommerceState
from domain.storefronts import CatalogScope
from infrastructure.database import get_db
from presentation.routers import commerce as router_module
from presentation.routers.commerce import router
from presentation.schemas.commerce import (
    CreateCommerceLeasingApplicationRequest,
    CreateCommerceOrderRequest,
)
from presentation.schemas.special_equipment_commerce import CommerceProductCard

pytestmark = pytest.mark.asyncio


async def test_special_equipment_commerce_card_declares_nullable_detail_url() -> None:
    field = CommerceProductCard.model_json_schema()["properties"]["detail_url"]

    assert {item.get("type") for item in field["anyOf"]} == {"string", "null"}


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _normalized_order(
    item_type: str = "vehicle",
    *,
    order_id: UUID | None = None,
    item_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "id": order_id or uuid4(),
        "item": {"type": item_type, "id": item_id or uuid4()},
        "item_snapshot": {
            "title": "КамАЗ 43118",
            "subtitle": None,
            "image_url": "/api/v1/cars/images/test.webp",
            "manufacturer": "КамАЗ",
            "model": "43118",
            "modification": None,
            "year": 2025,
        },
        "purchase_type": "reservation",
        "status": "reserved",
        "total_price": Decimal("10000000.00"),
        "paid_amount": Decimal("1000000.00"),
        "remaining_amount": Decimal("9000000.00"),
        "currency_code": "RUB",
        "leasing_application_id": None,
        "down_payment_percent": Decimal("10.00"),
        "hold_expires_at": None,
        "cancellation_reason": None,
        "cancellation_requested_at": None,
        "cancelled_at": None,
        "created_at": datetime(2026, 7, 20, tzinfo=UTC),
        "updated_at": datetime(2026, 7, 20, tzinfo=UTC),
    }


async def test_vehicle_item_projection_uses_fastapi_image_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vehicle_id = uuid4()

    async def get_vehicle(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "vehicle_id": vehicle_id,
            "mark_name": "КамАЗ",
            "model_name": "43118",
            "group_name": "6x6",
            "vehicle_year": 2025,
            "effective_price": Decimal("10000000.00"),
            "status": "available",
            "images": ["vehicle.webp"],
            "engine_type": "diesel",
            "horse_power": "300",
        }

    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.get_product",
        get_vehicle,
    )
    item = await VehicleCommerceAdapter().get_item(vehicle_id, object())  # type: ignore[arg-type]

    assert item["ref"] == {"type": "vehicle", "id": vehicle_id}
    assert item["detail_url"] == f"/special-equipment/products/{vehicle_id}"
    assert item["image_url"] == "/api/v1/cars/images/vehicle.webp"
    assert item["facts"] == [
        {"label": "Двигатель", "value": "diesel"},
        {"label": "Мощность", "value": "300"},
    ]


async def test_special_item_projection_never_exposes_storage_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    image_id = uuid4()

    async def get_product(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": product_id,
            "slug": "amkodor-352c",
            "mark_name": "Амкодор",
            "model_name": "352C",
            "modification_name": "Погрузчик",
            "manufacture_year": 2026,
            "price": Decimal("12500000.00"),
            "currency_code": "RUB",
            "publication_status": "published",
            "sale_status": "available",
            "primary_image_id": image_id,
        }

    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.get_product",
        get_product,
    )
    item = await SpecialEquipmentCommerceAdapter().get_item(
        product_id, object()  # type: ignore[arg-type]
    )

    assert item["ref"] == {"type": "special_equipment", "id": product_id}
    assert item["image_url"] == (
        f"/api/v1/special-equipment/images/{image_id}/content"
    )
    assert item["detail_url"] == (
        f"/special-equipment/products/{product_id}/amkodor-352c"
    )
    assert "s3" not in item["image_url"].lower()


@pytest.mark.parametrize(
    ("publication_status", "sale_status", "slug"),
    [
        ("draft", "available", "amkodor-352c"),
        ("published", "sold", "amkodor-352c"),
        ("published", "available", None),
    ],
)
async def test_special_item_projection_omits_unavailable_detail_target(
    monkeypatch: pytest.MonkeyPatch,
    publication_status: str,
    sale_status: str,
    slug: str | None,
) -> None:
    product_id = uuid4()

    async def get_product(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": product_id,
            "slug": slug,
            "publication_status": publication_status,
            "sale_status": sale_status,
            "currency_code": "RUB",
        }

    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.get_product",
        get_product,
    )

    item = await SpecialEquipmentCommerceAdapter().get_item(
        product_id, object()  # type: ignore[arg-type]
    )

    assert item["detail_url"] is None


async def test_special_item_projection_omits_detail_target_outside_storefront(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()
    scope = CatalogScope(id=uuid4(), slug="faw", version=1, is_default=False)

    async def get_product(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": product_id,
            "slug": "amkodor-352c",
            "warehouse_id": uuid4(),
            "publication_status": "published",
            "sale_status": "available",
            "currency_code": "RUB",
        }

    async def visible(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.get_product",
        get_product,
    )
    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.product_visible_in_scope",
        visible,
    )

    item = await SpecialEquipmentCommerceAdapter().get_item(
        product_id,
        object(),  # type: ignore[arg-type]
        scope=scope,
    )

    assert item["detail_url"] is None


async def test_unpriced_available_special_item_remains_leasable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()

    async def get_product(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": product_id,
            "slug": "amkodor-352c",
            "mark_name": "Амкодор",
            "model_name": "352C",
            "modification_name": "Погрузчик",
            "manufacture_year": 2026,
            "price": None,
            "currency_code": "RUB",
            "publication_status": "published",
            "sale_status": "available",
            "primary_image_id": None,
        }

    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.get_product",
        get_product,
    )

    item = await SpecialEquipmentCommerceAdapter().get_item(
        product_id, object()  # type: ignore[arg-type]
    )

    assert item["price"] is None
    assert item["capabilities"] == {
        "can_lease": True,
        "can_buy": False,
        "can_preorder": False,
    }


async def test_on_order_special_item_projection_allows_leasing_and_preorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = uuid4()

    async def get_product(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": product_id,
            "slug": "amkodor-352c",
            "mark_name": "Амкодор",
            "model_name": "352C",
            "modification_name": "Погрузчик",
            "manufacture_year": 2026,
            "price": Decimal("12500000.00"),
            "currency_code": "RUB",
            "publication_status": "published",
            "sale_status": "on_order",
            "primary_image_id": None,
        }

    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.get_product",
        get_product,
    )

    item = await SpecialEquipmentCommerceAdapter().get_item(
        product_id, object()  # type: ignore[arg-type]
    )

    assert item["availability"] == "on_order"
    assert item["capabilities"] == {
        "can_lease": True,
        "can_buy": False,
        "can_preorder": True,
    }


async def test_facade_dispatches_only_by_explicit_discriminator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    product_id = uuid4()
    calls: list[str] = []

    async def vehicle_get(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("vehicle")
        return {"kind": "vehicle"}

    async def special_get(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("special")
        return {"kind": "special"}

    monkeypatch.setattr(facade.adapter(CommerceItemType.VEHICLE), "get_item", vehicle_get)
    monkeypatch.setattr(
        facade.adapter(CommerceItemType.SPECIAL_EQUIPMENT),
        "get_item",
        special_get,
    )

    result = await facade.get_item(
        CommerceItemRef(CommerceItemType.SPECIAL_EQUIPMENT, product_id),
        object(),  # type: ignore[arg-type]
    )

    assert result == {"kind": "special"}
    assert calls == ["special"]


async def test_create_order_schema_rejects_ambiguous_or_numeric_reference() -> None:
    with pytest.raises(ValueError):
        CreateCommerceOrderRequest.model_validate(
            {
                "item": {"id": str(uuid4())},
                "purchase_type": "reservation",
                "payment_method": "card",
            }
        )
    for payment_method in ("card", "sbp"):
        with pytest.raises(ValueError, match="Пакетное оформление"):
            CreateCommerceOrderRequest.model_validate(
                {
                    "item": {"type": "vehicle", "id": str(uuid4())},
                    "quantity": 2,
                    "purchase_type": "reservation",
                    "payment_method": payment_method,
                }
            )
    special_quantity = CreateCommerceOrderRequest.model_validate(
        {
            "item": {"type": "special_equipment", "id": str(uuid4())},
            "quantity": 2,
            "cart_item_ids": [str(uuid4())],
            "purchase_type": "reservation",
            "payment_method": "card",
        }
    )
    assert special_quantity.quantity == 2
    with pytest.raises(ValueError, match="Безналичный перевод для автомобиля"):
        CreateCommerceOrderRequest.model_validate(
            {
                "item": {"type": "vehicle", "id": str(uuid4())},
                "purchase_type": "reservation",
                "payment_method": "bank_transfer",
            }
        )
    with pytest.raises(ValueError, match="только для reservation или preorder"):
        CreateCommerceOrderRequest.model_validate(
            {
                "item": {"type": "special_equipment", "id": str(uuid4())},
                "purchase_type": "full_purchase",
                "payment_method": "card",
                "down_payment_percent": "10.00",
            }
        )
    preorder = CreateCommerceOrderRequest.model_validate(
        {
            "item": {"type": "special_equipment", "id": str(uuid4())},
            "purchase_type": "preorder",
            "payment_method": "card",
            "down_payment_percent": "10.00",
        }
    )
    assert preorder.purchase_type == "preorder"
    with pytest.raises(ValueError, match="только для спецтехники"):
        CreateCommerceOrderRequest.model_validate(
            {
                "item": {"type": "vehicle", "id": str(uuid4())},
                "purchase_type": "preorder",
                "payment_method": "card",
                "down_payment_percent": "10.00",
            }
        )
    with pytest.raises(ValueError):
        CreateCommerceOrderRequest.model_validate(
            {
                "item": {"type": "vehicle", "id": 123},
                "purchase_type": "reservation",
                "payment_method": "card",
            }
        )


async def test_mixed_leasing_schema_matches_calculator_boundaries() -> None:
    base = {
        "items": [
            {
                "item": {
                    "type": "special_equipment",
                    "id": str(uuid4()),
                }
            }
        ],
        "company_id": str(uuid4()),
        "source_type": "platform",
    }

    minimum = CreateCommerceLeasingApplicationRequest.model_validate(
        {**base, "down_payment_percent": "0", "lease_term_months": 12}
    )
    maximum = CreateCommerceLeasingApplicationRequest.model_validate(
        {**base, "down_payment_percent": "49", "lease_term_months": 84}
    )
    assert minimum.down_payment_percent == Decimal("0")
    assert minimum.lease_term_months == 12
    assert maximum.down_payment_percent == Decimal("49")
    assert maximum.lease_term_months == 84

    calculation = CreateCommerceLeasingApplicationRequest.model_validate(
        {
            **base,
            "calculation": {
                "total_amount": "15300000.00",
                "monthly_payment": "401234.56",
                "markup": "1140000.00",
                "selected_support": {},
            },
        }
    )
    assert calculation.calculation is not None
    assert calculation.calculation.total_amount == Decimal("15300000.00")
    assert calculation.calculation.markup == Decimal("1140000.00")

    with pytest.raises(ValueError):
        CreateCommerceLeasingApplicationRequest.model_validate(
            {
                **base,
                "calculation": {
                    "total_amount": "15300000.00",
                    "nested": {},
                },
            }
        )

    for invalid in (
        {**base, "down_payment_percent": "50", "lease_term_months": 12},
        {**base, "down_payment_percent": "0", "lease_term_months": 11},
        {**base, "down_payment_percent": "0", "lease_term_months": 85},
    ):
        with pytest.raises(ValueError):
            CreateCommerceLeasingApplicationRequest.model_validate(invalid)


async def test_http_create_order_keeps_unified_envelope_and_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    item_id = uuid4()
    order = _normalized_order(item_id=item_id)
    payment_id = uuid4()
    captured: list[CreateCommerceOrderCommand] = []

    async def create_order(
        command: CreateCommerceOrderCommand, _session: Any
    ) -> dict[str, Any]:
        captured.append(command)
        return {
            "orders": [order],
            "payments": [
                {
                    "id": payment_id,
                    "order": {"type": "vehicle", "id": order["id"]},
                    "payment_type": "reservation",
                    "amount": Decimal("1000000.00"),
                    "status": "pending_payment",
                    "payment_method": "card",
                    "error_message": None,
                    "fiscal_status": None,
                    "expires_at": None,
                    "paid_at": None,
                    "created_at": datetime(2026, 7, 20, tzinfo=UTC),
                    "updated_at": datetime(2026, 7, 20, tzinfo=UTC),
                    "receipt_content_url": None,
                }
            ],
            "replayed": False,
        }

    monkeypatch.setattr(router_module.commerce_facade, "create_order", create_order)
    session = _Session()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/commerce")

    async def actor() -> dict[str, Any]:
        return {"id": user_id, "role": "client", "company_id": None}

    async def db() -> AsyncIterator[Any]:
        yield session

    app.dependency_overrides[router_module._write] = actor
    app.dependency_overrides[get_db] = db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/commerce/orders",
            headers={"Idempotency-Key": "checkout-123456"},
            json={
                "item": {"type": "vehicle", "id": str(item_id)},
                "purchase_type": "reservation",
                "payment_method": "card",
                "down_payment_percent": "10.00",
            },
        )

    assert response.status_code == 201
    assert response.headers["location"] == (
        f"/api/v1/commerce/orders/vehicle/{order['id']}"
    )
    assert response.json()["orders"][0]["item"] == {
        "type": "vehicle",
        "id": str(item_id),
    }
    assert response.json()["payments"][0]["amount"] == "1000000.00"
    assert response.json()["payments"][0]["order"] == {
        "type": "vehicle",
        "id": str(order["id"]),
    }
    assert session.commits == 1
    assert captured[0].item == CommerceItemRef(CommerceItemType.VEHICLE, item_id)
    assert captured[0].down_payment_percent == Decimal("10.00")


async def test_dealer_company_payload_becomes_special_application_client_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dealer_company_id = uuid4()
    selected_dealer_company_id = uuid4()
    client_company_id = uuid4()
    product_id = uuid4()
    application_id = uuid4()
    line_id = uuid4()
    observed: dict[str, Any] = {}

    async def create_or_get_company(
        _session: Any, payload: dict[str, Any]
    ) -> dict[str, Any]:
        observed["company_payload"] = payload
        return {
            "id": client_company_id,
            "name": payload["name"],
            "inn": payload["inn"],
        }

    async def create_special_application(command: Any, _session: Any) -> dict[str, Any]:
        observed["special_command"] = command
        return {
            "application_id": application_id,
            "item_id": line_id,
            "status": "active",
            "item_status": "active",
        }

    monkeypatch.setattr(
        "application.commerce.company_registration_repository.create_or_get_company",
        create_or_get_company,
    )
    monkeypatch.setattr(
        "application.commerce.create_special_equipment_leasing_application",
        create_special_application,
    )

    item = CommerceItemRef(CommerceItemType.SPECIAL_EQUIPMENT, product_id)
    result = await SpecialEquipmentCommerceAdapter().create_leasing_application(
        CreateCommerceLeasingApplicationCommand(
            source_type="platform",
            user_id=uuid4(),
            actor_role="dealer",
            actor_company_id=dealer_company_id,
            item=item,
            # The checkout sends the selected/own dealer company together with
            # a DaData client-company payload. The payload must win, exactly as
            # in the existing vehicle application flow.
            company_id=selected_dealer_company_id,
            company={"name": "ООО Клиент", "inn": "7716010001"},
            leasing_purpose="other",
            leasing_purpose_comment="  Доставка на удалённые объекты  ",
        ),
        object(),  # type: ignore[arg-type]
    )

    special_command = observed["special_command"]
    assert observed["company_payload"]["inn"] == "7716010001"
    assert special_command.company_id == client_company_id
    assert special_command.actor_role == "dealer"
    assert special_command.allow_dealer_client_company is True
    assert special_command.leasing_purpose == "Доставка на удалённые объекты"
    assert result == {
        "application_id": application_id,
        "item": item.as_dict(),
        "line_id": line_id,
        "status": "active",
    }


async def test_vehicle_application_preserves_other_purpose_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vehicle_id = uuid4()
    application_id = uuid4()
    captured: dict[str, Any] = {}
    adapter = VehicleCommerceAdapter()

    async def get_item(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"price": Decimal("5000000.00")}

    async def create_draft(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {"application_id": application_id, "status": "active"}

    monkeypatch.setattr(adapter, "get_item", get_item)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)

    result = await adapter.create_leasing_application(
        CreateCommerceLeasingApplicationCommand(
            source_type="platform",
            user_id=uuid4(),
            actor_role="client",
            actor_company_id=None,
            item=CommerceItemRef(CommerceItemType.VEHICLE, vehicle_id),
            company_id=uuid4(),
            leasing_purpose="other",
            leasing_purpose_comment="  Перевозка выставочного стенда  ",
        ),
        object(),  # type: ignore[arg-type]
    )

    assert captured["command"].vehicles[0].leasing_purpose == (
        "Перевозка выставочного стенда"
    )
    assert result == {
        "application_id": application_id,
        "item": {"type": "vehicle", "id": vehicle_id},
        "line_id": None,
        "status": "active",
    }


async def test_special_schedule_receipt_uses_unified_proxy_and_order_reference() -> None:
    order_id = uuid4()
    payment_id = uuid4()
    row = SpecialEquipmentCommerceAdapter().normalize_schedule_item(
        {
            "id": uuid4(),
            "purchase_order_id": order_id,
            "payment_number": 1,
            "due_date": "2026-08-20",
            "amount": Decimal("100000.00"),
            "payment_id": payment_id,
            "is_paid": True,
            "receipt_content_url": (
                f"/api/v1/special-equipment/purchase-orders/{order_id}/payments/"
                f"{payment_id}/receipt/content"
            ),
            "can_pay": False,
        }
    )

    assert row["order"] == {"type": "special_equipment", "id": order_id}
    assert row["receipt_content_url"] == (
        f"/api/v1/commerce/orders/special_equipment/{order_id}/payments/"
        f"{payment_id}/receipt/content"
    )


async def test_special_order_adapter_routes_only_canonical_server_cart_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    product_id = uuid4()
    cart_item_ids = (uuid4(), uuid4())
    order_id = uuid4()
    captured: dict[str, Any] = {}

    async def create_order(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {
            "order": {
                "id": order_id,
                "product_id": product_id,
                "item_snapshot": {},
                "purchase_type": "reservation",
                "status": "payment_pending",
                "total_price": Decimal("100.00"),
                "paid_amount": Decimal("0.00"),
                "remaining_amount": Decimal("100.00"),
                "currency_code": "RUB",
            },
            "payment": None,
            "replayed": False,
        }

    monkeypatch.setattr("application.commerce.create_special_equipment_order", create_order)

    result = await SpecialEquipmentCommerceAdapter().create_order(
        CreateCommerceOrderCommand(
            user_id=user_id,
            item=CommerceItemRef(CommerceItemType.SPECIAL_EQUIPMENT, product_id),
            purchase_type="reservation",
            payment_method="bank_transfer",
            idempotency_key="canonical-cart-order",
            quantity=2,
            cart_item_ids=cart_item_ids,
        ),
        object(),  # type: ignore[arg-type]
    )

    command = captured["command"]
    assert command.cart_item_ids == cart_item_ids
    assert command.product_id == product_id
    assert command.quantity == 2
    assert result["orders"][0]["id"] == order_id


async def test_special_order_adapter_rejects_missing_canonical_cart_ids() -> None:
    with pytest.raises(ServiceError, match="серверной корзины") as raised:
        await SpecialEquipmentCommerceAdapter().create_order(
            CreateCommerceOrderCommand(
                user_id=uuid4(),
                item=CommerceItemRef(CommerceItemType.SPECIAL_EQUIPMENT, uuid4()),
                purchase_type="reservation",
                payment_method="bank_transfer",
                idempotency_key="missing-cart-order",
            ),
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 422


async def test_special_order_adapter_consumes_every_paginated_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_ids = [uuid4(), uuid4(), uuid4()]
    observed_pages: list[tuple[int, int]] = []

    async def list_orders(
        _user_id: UUID,
        _session: Any,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        observed_pages.append((page, page_size))
        index = page - 1
        return {
            "items": [
                {
                    "id": order_ids[index],
                    "product_id": uuid4(),
                    "item_snapshot": {},
                    "purchase_type": "reservation",
                    "status": "reserved",
                    "total_price": Decimal("100.00"),
                    "paid_amount": Decimal("10.00"),
                    "remaining_amount": Decimal("90.00"),
                    "currency_code": "RUB",
                }
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": 3,
                "pages": 3,
            },
        }

    monkeypatch.setattr("application.commerce.list_special_equipment_orders", list_orders)

    result = await SpecialEquipmentCommerceAdapter().list_orders(
        uuid4(), object()  # type: ignore[arg-type]
    )

    assert [row["id"] for row in result] == order_ids
    assert observed_pages == [(1, 100), (2, 100), (3, 100)]


async def test_vehicle_unified_payment_rejects_legacy_immediate_bank_transfer() -> None:
    with pytest.raises(ServiceError, match="Безналичный перевод") as raised:
        await VehicleCommerceAdapter().create_payment(
            CreateCommercePaymentCommand(
                user_id=uuid4(),
                order=CommerceOrderRef(CommerceItemType.VEHICLE, uuid4()),
                scope="remaining",
                payment_method="bank_transfer",
                idempotency_key="payment-bank-transfer",
            ),
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 422


async def test_vehicle_order_rejects_duplicate_provider_payment_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    vehicle_id = uuid4()
    order_id = uuid4()
    legacy_called = False

    async def lock_vehicle(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": vehicle_id, "status": "reserved", "complectation_id": None}

    async def find_order(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": order_id}

    async def list_payments(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": uuid4(), "status": "pending_payment"}]

    async def legacy_create(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal legacy_called
        legacy_called = True
        return {}

    async def lock_idempotency(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def find_idempotency(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "application.commerce.purchase_repository.lock_vehicle_commerce_idempotency",
        lock_idempotency,
    )
    monkeypatch.setattr(
        "application.commerce.purchase_repository.find_vehicle_commerce_payment_by_idempotency",
        find_idempotency,
    )

    monkeypatch.setattr(
        "application.commerce.purchase_repository.get_vehicle_for_update",
        lock_vehicle,
    )
    monkeypatch.setattr(
        "application.commerce.purchase_repository.find_active_order_by_vehicle_and_user",
        find_order,
    )
    monkeypatch.setattr(
        "application.commerce.purchase_repository.get_payments_by_order_id",
        list_payments,
    )
    monkeypatch.setattr(
        "application.commerce.handle_create_purchase_orders",
        legacy_create,
    )

    with pytest.raises(ServiceError, match="уже выполняется платёж") as raised:
        await VehicleCommerceAdapter().create_order(
            CreateCommerceOrderCommand(
                user_id=user_id,
                item=CommerceItemRef(CommerceItemType.VEHICLE, vehicle_id),
                purchase_type="reservation",
                payment_method="card",
                idempotency_key="duplicate-checkout",
            ),
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 409
    assert legacy_called is False


async def test_vehicle_order_lock_rejects_second_active_follow_up_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    order_id = uuid4()
    vehicle_id = uuid4()

    async def get_lock_route(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": order_id, "user_id": user_id, "vehicle_id": vehicle_id}

    async def lock_vehicle(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": vehicle_id, "status": "reserved"}

    async def lock_order(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "id": order_id,
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "purchase_type": "reservation",
            "status": "reserved",
            "total_price": Decimal("10000000.00"),
            "paid_amount": Decimal("1000000.00"),
            "remaining_amount": Decimal("9000000.00"),
        }

    async def list_payments(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": uuid4(), "status": "processing"}]

    monkeypatch.setattr(
        "application.commands.purchases.repo.get_order_lock_route",
        get_lock_route,
    )
    monkeypatch.setattr(
        "application.commands.purchases.repo.get_vehicle_for_update",
        lock_vehicle,
    )
    monkeypatch.setattr(
        "application.commands.purchases.repo.get_order_for_update",
        lock_order,
    )
    monkeypatch.setattr(
        "application.commands.purchases.repo.get_payments_by_order_id",
        list_payments,
    )

    with pytest.raises(ServiceError, match="уже выполняется платёж") as raised:
        await handle_pay_remaining(
            PayRemainingCommand(
                user_id=user_id,
                order_id=order_id,
                payment_method="card",
            ),
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 409


async def test_vehicle_payment_status_validates_order_then_delegates_legacy_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    order_id = uuid4()
    payment_id = uuid4()
    adapter = VehicleCommerceAdapter()
    calls: list[str] = []

    async def get_order(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("owned_order")
        return _normalized_order(order_id=order_id)

    async def get_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append("payment")
        return {
            "id": payment_id,
            "purchase_order_id": order_id,
            "payment_type": "reservation",
            "amount": Decimal("1000000.00"),
            "status": "completed" if calls.count("payment") > 1 else "pending_payment",
            "payment_method": "card",
        }

    async def sync_status(query: Any, _session: Any) -> object:
        calls.append(f"legacy_sync:{query.payment_id}")
        return object()

    monkeypatch.setattr(adapter, "get_order", get_order)
    monkeypatch.setattr(
        "application.commerce.purchase_repository.get_payment_by_id",
        get_payment,
    )
    monkeypatch.setattr("application.commerce.handle_get_payment_status", sync_status)

    result = await adapter.get_payment_status(
        user_id, order_id, payment_id, object()  # type: ignore[arg-type]
    )

    assert calls == [
        "owned_order",
        "payment",
        f"legacy_sync:{payment_id}",
        "payment",
    ]
    assert result["status"] == "completed"
    assert result["order"] == {"type": "vehicle", "id": order_id}


async def test_vehicle_payment_status_rejects_payment_from_another_order_before_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    adapter = VehicleCommerceAdapter()
    legacy_called = False

    async def get_order(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return _normalized_order(order_id=order_id)

    async def get_payment(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"id": uuid4(), "purchase_order_id": uuid4()}

    async def sync_status(*_args: Any, **_kwargs: Any) -> object:
        nonlocal legacy_called
        legacy_called = True
        return object()

    monkeypatch.setattr(adapter, "get_order", get_order)
    monkeypatch.setattr(
        "application.commerce.purchase_repository.get_payment_by_id",
        get_payment,
    )
    monkeypatch.setattr("application.commerce.handle_get_payment_status", sync_status)

    with pytest.raises(PaymentNotFoundError):
        await adapter.get_payment_status(
            uuid4(), order_id, uuid4(), object()  # type: ignore[arg-type]
        )

    assert legacy_called is False


async def test_vehicle_reservation_money_rounds_half_up() -> None:
    payment, paid, remaining, _status, _payment_type = PurchaseOrder.compute_amounts(
        "reservation",
        Decimal("100.05"),
        True,
        10,
    )

    assert payment == Decimal("10.01")
    assert paid == Decimal("0.00")
    assert remaining == Decimal("100.05")


async def test_batch_leasing_rejects_zero_custom_price_before_catalog_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    prepare_called = False

    async def prepare(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal prepare_called
        prepare_called = True
        return object()

    monkeypatch.setattr(facade, "_prepare_leasing_batch", prepare)
    command = CreateCommerceLeasingApplicationBatchCommand(
        source_type="platform",
        user_id=uuid4(),
        actor_role="carcraft_employee",
        actor_company_id=None,
        company_id=uuid4(),
        items=[
            CommerceLeasingApplicationLineCommand(
                item=CommerceItemRef(CommerceItemType.VEHICLE, uuid4()),
                custom_price=Decimal("0.00"),
            )
        ],
    )

    with pytest.raises(ServiceError, match="больше нуля") as raised:
        await facade.create_leasing_application(
            command,
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 422
    assert prepare_called is False


async def test_batch_leasing_accepts_support_discount_against_calculator_base_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    vehicle_id = uuid4()
    application_id = uuid4()
    line_id = uuid4()
    line = CommerceLeasingApplicationLineCommand(
        item=CommerceItemRef(CommerceItemType.VEHICLE, vehicle_id),
    )
    captured: dict[str, Any] = {}
    scope = CatalogScope(
        id=uuid4(),
        slug="faw",
        version=7,
        is_default=False,
    )

    async def prepare(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            vehicles=[
                (
                    line,
                    SimpleNamespace(custom_price=Decimal("4400000.00")),
                )
            ],
            special_equipment=[],
            total_amount=Decimal("4400000.00"),
        )

    async def calculate(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            response={
                "support": {"base_total": "4400000.00"},
                "calculation_parameters": {
                    "total_amount": "3900000.00",
                    "down_payment": "780000.00",
                    "down_payment_percent": 20,
                    "lease_term_months": 36,
                },
                "calculation": {
                    "monthlyPayment": "125000.00",
                    "totalCost": "4500000.00",
                    "markup": "600000.00",
                    "rate": "12.00",
                    "totalInterest": "600000.00",
                    "buyoutAmount": "0.00",
                    "vatRefund": "650000.00",
                    "profitTaxSavings": "120000.00",
                    "totalSavings": "770000.00",
                },
            }
        )

    async def create_draft(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {
            "application_id": application_id,
            "vehicle_line_ids": [line_id],
            "special_equipment_line_ids": [],
            "status": "active",
        }

    monkeypatch.setattr(facade, "_prepare_leasing_batch", prepare)
    monkeypatch.setattr("application.commerce.handle_calculate", calculate)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)

    result = await facade.create_leasing_application(
        CreateCommerceLeasingApplicationBatchCommand(
            source_type="platform",
            user_id=uuid4(),
            actor_role="carcraft_employee",
            actor_company_id=None,
            company_id=uuid4(),
            down_payment_percent=Decimal("20"),
            lease_term_months=36,
            calculation={"total_amount": "4400000.00"},
            items=[line],
            scope=scope,
        ),
        object(),  # type: ignore[arg-type]
    )

    assert result == {
        "application_id": application_id,
        "items": [
            {
                "item": {"type": "vehicle", "id": vehicle_id},
                "line_id": line_id,
                "quantity": 1,
            }
        ],
        "status": "active",
    }
    assert captured["command"].calculation["total_amount"] == Decimal("4400000.00")
    assert captured["command"].calculation["monthly_payment"] == "125000.00"
    assert captured["command"].scope == scope


async def test_custom_storefront_batch_allows_special_equipment_catalog_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    prepare_called = False

    async def prepare(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal prepare_called
        prepare_called = True
        raise RuntimeError("special-equipment catalog reached")

    monkeypatch.setattr(facade, "_prepare_leasing_batch", prepare)
    command = CreateCommerceLeasingApplicationBatchCommand(
        source_type="platform",
        user_id=uuid4(),
        actor_role="client",
        actor_company_id=None,
        company_id=uuid4(),
        items=[
            CommerceLeasingApplicationLineCommand(
                item=CommerceItemRef(
                    CommerceItemType.SPECIAL_EQUIPMENT,
                    uuid4(),
                ),
            )
        ],
        scope=CatalogScope(
            id=uuid4(),
            slug="faw",
            version=1,
            is_default=False,
        ),
    )

    with pytest.raises(RuntimeError, match="special-equipment catalog reached"):
        await facade.create_leasing_application(
            command,
            object(),  # type: ignore[arg-type]
        )

    assert prepare_called is True


@pytest.mark.parametrize(
    "calculator_response",
    [
        pytest.param(
            {
                "support": {"base_total": "100.006"},
                "calculation_parameters": {
                    "total_amount": "90.00",
                    "down_payment": "18.00",
                    "down_payment_percent": 20,
                    "lease_term_months": 36,
                },
                "calculation": {},
            },
            id="support-base-total",
        ),
        pytest.param(
            {
                "calculation_parameters": {
                    "total_amount": 200,
                    "down_payment": 20,
                    "down_payment_percent": 20,
                    "lease_term_months": 36,
                },
                "calculation": {},
            },
            id="calculator-total",
        ),
    ],
)
async def test_batch_leasing_rejects_calculation_base_total_drift_before_persist(
    monkeypatch: pytest.MonkeyPatch,
    calculator_response: dict[str, Any],
) -> None:
    facade = CommerceFacade()
    draft_called = False

    async def prepare(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(
            vehicles=[],
            special_equipment=[],
            total_amount=Decimal("100.00"),
        )

    async def calculate(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(response=calculator_response)

    async def create_draft(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal draft_called
        draft_called = True
        return {}

    monkeypatch.setattr(facade, "_prepare_leasing_batch", prepare)
    monkeypatch.setattr("application.commerce.handle_calculate", calculate)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)
    command = CreateCommerceLeasingApplicationBatchCommand(
        source_type="platform",
        user_id=uuid4(),
        actor_role="carcraft_employee",
        actor_company_id=None,
        company_id=uuid4(),
        down_payment_percent=Decimal("20"),
        lease_term_months=36,
        calculation={"total_amount": "100.00"},
        items=[
            CommerceLeasingApplicationLineCommand(
                item=CommerceItemRef(CommerceItemType.VEHICLE, uuid4()),
            )
        ],
    )

    with pytest.raises(ServiceError, match="не соответствует") as raised:
        await facade.create_leasing_application(
            command,
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 409
    assert draft_called is False


async def test_unified_leasing_persists_concrete_composite_application_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    user_id = uuid4()
    company_id = uuid4()
    seller_id = uuid4()
    representative_id = uuid4()
    cart_item_id = uuid4()
    component_ids = (uuid4(), uuid4())
    application_id = uuid4()
    concrete = {
        "id": representative_id,
        "seller_company_id": seller_id,
        "price": Decimal("100.00"),
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    component_rows = {
        component_id: {**concrete, "id": component_id, "price": Decimal("0.00")}
        for component_id in component_ids
    }
    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_id,
                representative_id=representative_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(concrete,),
            ),
        ),
        components=tuple(
            AllocatedComponent(
                source_cart_item_id=cart_item_id,
                composite_product_id=representative_id,
                component_product_id=component_id,
                position=position,
                is_base=position == 0,
            )
            for position, component_id in enumerate(component_ids)
        ),
    )
    captured: dict[str, Any] = {}

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, product_id: UUID, **_kwargs: Any
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        row = concrete if product_id == representative_id else component_rows[product_id]
        return row, ProductCommerceState.from_dict(row)

    async def create_draft(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {
            "application_id": application_id,
            "vehicle_line_ids": [],
            "special_equipment_line_ids": [uuid4(), uuid4(), uuid4()],
            "status": "active",
        }

    async def delete_cart(*_args: Any, **_kwargs: Any) -> int:
        return 1

    monkeypatch.setattr("application.commerce.allocate_cart_items", allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", load_product)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)
    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.delete_cart_items_by_ids",
        delete_cart,
    )

    result = await facade.create_leasing_application(
        CreateCommerceLeasingApplicationBatchCommand(
            source_type="platform",
            user_id=user_id,
            actor_role="client",
            actor_company_id=None,
            company_id=company_id,
            items=[
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        representative_id,
                    ),
                    cart_item_ids=(cart_item_id,),
                )
            ],
        ),
        object(),  # type: ignore[arg-type]
    )

    entries = captured["command"].special_equipment_items
    assert [entry.product_id for entry in entries] == [
        representative_id,
        *component_ids,
    ]
    assert [entry.item_role for entry in entries] == ["offer", "component", "component"]
    assert entries[0].source_cart_item_id == cart_item_id
    assert all(entry.group_id == cart_item_id for entry in entries)
    assert len(result["items"]) == 1
    assert result["items"][0]["item"]["id"] == representative_id


async def test_mixed_unified_leasing_uses_server_cart_quantity_above_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    user_id = uuid4()
    vehicle_id = uuid4()
    representative_id = uuid4()
    second_product_id = uuid4()
    cart_item_id = uuid4()
    seller_id = uuid4()
    company_id = uuid4()
    products = {
        product_id: {
            "id": product_id,
            "seller_company_id": seller_id,
            "price": Decimal("100.00"),
            "currency_code": "RUB",
            "publication_status": "published",
            "sale_status": "available",
            "condition": "new",
            "no_vin": True,
            "lock_version": 1,
        }
        for product_id in (representative_id, second_product_id)
    }
    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_id,
                representative_id=representative_id,
                parent_cart_item_id=None,
                quantity=2,
                products=(products[representative_id], products[second_product_id]),
            ),
        ),
        components=(),
    )
    captured: dict[str, Any] = {}

    async def prepare_vehicle(*_args: Any, **_kwargs: Any) -> tuple[Any, Decimal]:
        return SimpleNamespace(custom_price=Decimal("50.00")), Decimal("50.00")

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, product_id: UUID
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        row = products[product_id]
        return row, ProductCommerceState.from_dict(row)

    async def create_draft(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {
            "application_id": uuid4(),
            "vehicle_line_ids": [uuid4()],
            "special_equipment_line_ids": [uuid4(), uuid4()],
            "status": "active",
        }

    async def delete_cart(*_args: Any, **_kwargs: Any) -> int:
        return 1

    monkeypatch.setattr(facade, "_prepare_vehicle_line", prepare_vehicle)
    monkeypatch.setattr("application.commerce.allocate_cart_items", allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", load_product)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)
    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.delete_cart_items_by_ids",
        delete_cart,
    )

    result = await facade.create_leasing_application(
        CreateCommerceLeasingApplicationBatchCommand(
            source_type="platform",
            user_id=user_id,
            actor_role="client",
            actor_company_id=None,
            company_id=company_id,
            items=[
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(CommerceItemType.VEHICLE, vehicle_id),
                ),
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        representative_id,
                    ),
                    quantity=2,
                    cart_item_ids=(cart_item_id,),
                ),
            ],
        ),
        object(),  # type: ignore[arg-type]
    )

    assert [item.product_id for item in captured["command"].special_equipment_items] == [
        representative_id,
        second_product_id,
    ]
    assert [line["quantity"] for line in result["items"]] == [1, 2]


async def test_mixed_unified_leasing_rejects_unknown_special_price_before_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    user_id = uuid4()
    vehicle_id = uuid4()
    product_id = uuid4()
    cart_item_id = uuid4()
    seller_id = uuid4()
    company_id = uuid4()
    product = {
        "id": product_id,
        "seller_company_id": seller_id,
        "price": None,
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_id,
                representative_id=product_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product,),
            ),
        ),
        components=(),
    )
    captured: dict[str, Any] = {}

    async def prepare_vehicle(*_args: Any, **_kwargs: Any) -> tuple[Any, Decimal]:
        return SimpleNamespace(custom_price=Decimal("50.00")), Decimal("50.00")

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, _product_id: UUID
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        return product, ProductCommerceState.from_dict(product)

    async def create_draft(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {
            "application_id": uuid4(),
            "vehicle_line_ids": [uuid4()],
            "special_equipment_line_ids": [uuid4()],
            "status": "active",
        }

    async def delete_cart(*_args: Any, **_kwargs: Any) -> int:
        return 1

    async def calculate(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("calculator must not run without a known asset total")

    monkeypatch.setattr(facade, "_prepare_vehicle_line", prepare_vehicle)
    monkeypatch.setattr("application.commerce.allocate_cart_items", allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", load_product)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)
    monkeypatch.setattr("application.commerce.handle_calculate", calculate)
    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.delete_cart_items_by_ids",
        delete_cart,
    )

    with pytest.raises(ServiceError) as raised:
        await facade.create_leasing_application(
            CreateCommerceLeasingApplicationBatchCommand(
                source_type="platform",
                user_id=user_id,
                actor_role="client",
                actor_company_id=None,
                company_id=company_id,
                down_payment_percent=Decimal("10.00"),
                lease_term_months=36,
                calculation={"total_amount": None},
                items=[
                    CommerceLeasingApplicationLineCommand(
                        item=CommerceItemRef(CommerceItemType.VEHICLE, vehicle_id),
                    ),
                    CommerceLeasingApplicationLineCommand(
                        item=CommerceItemRef(
                            CommerceItemType.SPECIAL_EQUIPMENT,
                            product_id,
                        ),
                        cart_item_ids=(cart_item_id,),
                    ),
                ],
            ),
            object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 422
    assert "command" not in captured


async def test_unified_leasing_rejects_paid_options_for_unknown_special_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    product_id = uuid4()
    cart_item_id = uuid4()
    seller_id = uuid4()
    product = {
        "id": product_id,
        "seller_company_id": seller_id,
        "price": None,
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_id,
                representative_id=product_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product,),
            ),
        ),
        components=(),
    )

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, _product_id: UUID
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        return product, ProductCommerceState.from_dict(product)

    monkeypatch.setattr("application.commerce.allocate_cart_items", allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", load_product)

    with pytest.raises(ServiceError, match="других платных позиций") as raised:
        await facade._prepare_special_lines(
            [
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        product_id,
                    ),
                    cart_item_ids=(cart_item_id,),
                    equipments=[{"name": "Дополнительное оборудование", "price": "1.00"}],
                )
            ],
            user_id=uuid4(),
            actor_role="client",
            session=object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 422


async def test_special_equipment_leasing_allows_multiple_sellers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    user_id = uuid4()
    company_id = uuid4()
    seller_1 = uuid4()
    seller_2 = uuid4()
    product_1_id = uuid4()
    product_2_id = uuid4()
    cart_item_1_id = uuid4()
    cart_item_2_id = uuid4()

    product_1 = {
        "id": product_1_id,
        "seller_company_id": seller_1,
        "price": Decimal("5000000.00"),
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    product_2 = {
        "id": product_2_id,
        "seller_company_id": seller_2,
        "price": Decimal("7000000.00"),
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    products = {product_1_id: product_1, product_2_id: product_2}

    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_1_id,
                representative_id=product_1_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product_1,),
            ),
            AllocatedCartLine(
                cart_item_id=cart_item_2_id,
                representative_id=product_2_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product_2,),
            ),
        ),
        components=(),
    )

    captured: dict[str, Any] = {}

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, product_id: UUID, **_kwargs: Any
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        row = products[product_id]
        return row, ProductCommerceState.from_dict(row)

    async def create_draft(command: Any, _session: Any) -> dict[str, Any]:
        captured["command"] = command
        return {
            "application_id": uuid4(),
            "vehicle_line_ids": [],
            "special_equipment_line_ids": [uuid4(), uuid4()],
            "status": "active",
        }

    async def delete_cart(*_args: Any, **_kwargs: Any) -> int:
        return 2

    monkeypatch.setattr("application.commerce.allocate_cart_items", allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", load_product)
    monkeypatch.setattr("application.commerce.handle_create_draft", create_draft)
    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.delete_cart_items_by_ids",
        delete_cart,
    )

    result = await facade.create_leasing_application(
        CreateCommerceLeasingApplicationBatchCommand(
            source_type="platform",
            user_id=user_id,
            actor_role="client",
            actor_company_id=None,
            company_id=company_id,
            items=[
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        product_1_id,
                    ),
                    cart_item_ids=(cart_item_1_id,),
                ),
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        product_2_id,
                    ),
                    cart_item_ids=(cart_item_2_id,),
                ),
            ],
        ),
        object(),  # type: ignore[arg-type]
    )

    assert result["application_id"] is not None
    se_items = captured["command"].special_equipment_items
    assert len(se_items) == 2
    assert {item.seller_company_id for item in se_items} == {seller_1, seller_2}


async def test_special_equipment_leasing_rejects_mixed_currencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = CommerceFacade()
    product_1_id = uuid4()
    product_2_id = uuid4()
    cart_item_1_id = uuid4()
    cart_item_2_id = uuid4()

    product_1 = {
        "id": product_1_id,
        "seller_company_id": uuid4(),
        "price": Decimal("5000000.00"),
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    product_2 = {
        "id": product_2_id,
        "seller_company_id": uuid4(),
        "price": Decimal("70000.00"),
        "currency_code": "USD",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    products = {product_1_id: product_1, product_2_id: product_2}

    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_1_id,
                representative_id=product_1_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product_1,),
            ),
            AllocatedCartLine(
                cart_item_id=cart_item_2_id,
                representative_id=product_2_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product_2,),
            ),
        ),
        components=(),
    )

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, product_id: UUID, **_kwargs: Any
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        row = products[product_id]
        return row, ProductCommerceState.from_dict(row)

    monkeypatch.setattr("application.commerce.allocate_cart_items", allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", load_product)

    with pytest.raises(ServiceError, match="разных валютах") as raised:
        await facade._prepare_special_lines(
            [
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        product_1_id,
                    ),
                    cart_item_ids=(cart_item_1_id,),
                ),
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(
                        CommerceItemType.SPECIAL_EQUIPMENT,
                        product_2_id,
                    ),
                    cart_item_ids=(cart_item_2_id,),
                ),
            ],
            user_id=uuid4(),
            actor_role="client",
            session=object(),  # type: ignore[arg-type]
        )

    assert raised.value.status_code == 422


async def test_special_equipment_commerce_create_cart_leasing_allows_multiple_sellers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.special_equipment_commerce import (
        CreateLeasingApplicationCommand,
        create_leasing_application,
    )

    user_id = uuid4()
    company_id = uuid4()
    seller_1 = uuid4()
    seller_2 = uuid4()
    product_1_id = uuid4()
    product_2_id = uuid4()
    cart_item_1_id = uuid4()
    cart_item_2_id = uuid4()

    product_1 = {
        "id": product_1_id,
        "seller_company_id": seller_1,
        "price": Decimal("5000000.00"),
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    product_2 = {
        "id": product_2_id,
        "seller_company_id": seller_2,
        "price": Decimal("7000000.00"),
        "currency_code": "RUB",
        "publication_status": "published",
        "sale_status": "available",
        "condition": "new",
        "no_vin": True,
        "lock_version": 1,
    }
    products = {product_1_id: product_1, product_2_id: product_2}

    allocation = CheckoutAllocation(
        cart_lines=(
            AllocatedCartLine(
                cart_item_id=cart_item_1_id,
                representative_id=product_1_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product_1,),
            ),
            AllocatedCartLine(
                cart_item_id=cart_item_2_id,
                representative_id=product_2_id,
                parent_cart_item_id=None,
                quantity=1,
                products=(product_2,),
            ),
        ),
        components=(),
    )

    captured_kwargs: dict[str, Any] = {}

    async def allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return allocation

    async def load_product(
        _session: Any, product_id: UUID, **_kwargs: Any
    ) -> tuple[dict[str, Any], ProductCommerceState]:
        row = products[product_id]
        return row, ProductCommerceState.from_dict(row)

    async def normalize_purpose(_purpose: Any, _session: Any) -> str | None:
        return None

    async def compute_fin(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"total_amount": Decimal("12000000.00")}

    async def create_from_items(
        _session: Any, **kwargs: Any
    ) -> dict[str, Any]:
        captured_kwargs.update(kwargs)
        return {
            "application_id": uuid4(),
            "source_type": "platform",
            "item_id": uuid4(),
            "product_id": product_1_id,
            "item_ids": [uuid4(), uuid4()],
            "product_ids": [product_1_id, product_2_id],
            "status": "active",
            "item_status": "active",
        }

    async def delete_cart(*_args: Any, **_kwargs: Any) -> int:
        return 2

    async def is_linked(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(
        "application.special_equipment_commerce.company_repo.is_user_linked_to_company",
        is_linked,
    )
    monkeypatch.setattr(
        "application.special_equipment_commerce.allocate_cart_items",
        allocate,
    )
    monkeypatch.setattr(
        "application.special_equipment_commerce._load_product",
        load_product,
    )
    monkeypatch.setattr(
        "application.special_equipment_commerce._normalize_leasing_purpose",
        normalize_purpose,
    )
    monkeypatch.setattr(
        "application.special_equipment_commerce.compute_canonical_application_calculation",
        compute_fin,
    )
    monkeypatch.setattr(
        "application.special_equipment_commerce.repo.create_leasing_application_from_items",
        create_from_items,
    )
    async def assign_display_number(*_args: Any, **_kwargs: Any) -> str:
        return "7701234567-300926-001"

    monkeypatch.setattr(
        "application.special_equipment_commerce.assign_display_number_if_missing",
        assign_display_number,
    )
    monkeypatch.setattr(
        "application.special_equipment_commerce.repo.delete_cart_items_by_ids",
        delete_cart,
    )

    result = await create_leasing_application(
        CreateLeasingApplicationCommand(
            user_id=user_id,
            source_type="platform",
            company_id=company_id,
            cart_item_ids=(cart_item_1_id, cart_item_2_id),
            down_payment_percent=Decimal("20"),
            lease_term_months=36,
        ),
        object(),  # type: ignore[arg-type]
    )

    assert result["application_id"] is not None
    assert result["display_number"] == "7701234567-300926-001"
    assert captured_kwargs["dealer_company_id"] is None
    assert len(captured_kwargs["item_entries"]) == 2
    assert {e["seller_company_id"] for e in captured_kwargs["item_entries"]} == {
        seller_1,
        seller_2,
    }

