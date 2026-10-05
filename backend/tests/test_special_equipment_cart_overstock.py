"""Tests for special equipment cart overstock, color, and privacy rules."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.errors import ServiceError
from application.notifications.events import NotificationEvent
from application.notifications.templates import build_inbox
from application.queries.applications.item_projection import (
    group_application_items,
    project_special_equipment_item,
)
from application.special_equipment_checkout import (
    AllocatedCartLine,
    CheckoutAllocation,
    CheckoutAllocationError,
    allocate_cart_items,
)
from application.special_equipment_commerce import (
    PatchCartItemCommand,
    ProductCommerceState,
    PutCartItemCommand,
    _product_card,
    patch_cart_item,
    put_cart_item,
)
from domain.commerce import CommerceItemRef, CommerceItemType
from domain.notification_policy import notification_data


def test_product_card_body_color() -> None:
    color_id = uuid4()
    row_with_color = {
        "id": uuid4(),
        "slug": "faw-j7",
        "publication_status": "published",
        "sale_status": "available",
        "price": Decimal("2881000"),
        "base_price": Decimal("4031000"),
        "special_price": Decimal("2881000"),
        "currency_code": "RUB",
        "mark_id": uuid4(),
        "mark_name": "FAW",
        "model_id": uuid4(),
        "model_name": "J7",
        "modification_id": uuid4(),
        "modification_name": "4x2",
        "manufacture_year": 2025,
        "body_color_id": color_id,
        "body_color_name": "Белый",
    }
    card = _product_card(row_with_color, detail_url_allowed=False)
    assert card["body_color"] == {"id": color_id, "name": "Белый"}
    assert card["manufacture_year"] == 2025

    row_without_color = {**row_with_color, "body_color_id": None, "body_color_name": None}
    card_no_color = _product_card(row_without_color, detail_url_allowed=False)
    assert card_no_color["body_color"] is None


@pytest.mark.asyncio
async def test_put_cart_item_quantity_validation() -> None:
    session = AsyncMock()
    with pytest.raises(ServiceError) as exc_info:
        await put_cart_item(
            PutCartItemCommand(
                user_id=uuid4(),
                product_id=uuid4(),
                quantity=0,
            ),
            session,
        )
    assert exc_info.value.code == "CART_QUANTITY_OUT_OF_RANGE"
    assert exc_info.value.status_code == 422

    with pytest.raises(ServiceError) as exc_info_max:
        await put_cart_item(
            PutCartItemCommand(
                user_id=uuid4(),
                product_id=uuid4(),
                quantity=1001,
            ),
            session,
        )
    assert exc_info_max.value.code == "CART_QUANTITY_OUT_OF_RANGE"
    assert exc_info_max.value.status_code == 422


@pytest.mark.asyncio
async def test_put_cart_item_attachment_overstock_blocked() -> None:
    session = AsyncMock()
    with pytest.raises(ServiceError) as exc_info:
        await put_cart_item(
            PutCartItemCommand(
                user_id=uuid4(),
                product_id=uuid4(),
                quantity=5,
                allow_overstock=True,
                parent_item_id=uuid4(),
            ),
            session,
        )
    assert exc_info.value.code == "OVERSTOCK_NOT_ALLOWED_FOR_ATTACHMENT"
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_put_cart_item_availability_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    product_id = uuid4()
    user_id = uuid4()
    session = AsyncMock()

    dummy_state = ProductCommerceState(
        id=product_id,
        publication_status="published",
        sale_status="available",
        price=Decimal("1000000"),
        price_from=None,
        price_on_request=False,
        seller_company_id=uuid4(),
        currency_code="RUB",
        mark_name="FAW",
        model_name="J7",
        modification_name="4x2",
        manufacture_year=2025,
        vin="VIN12345",
    )

    async def mock_load_product(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], ProductCommerceState]:
        return {"id": product_id, "slug": "test"}, dummy_state

    monkeypatch.setattr("application.special_equipment_commerce._load_product", mock_load_product)

    # 1. available = 2, requested = 5, allow_overstock = False -> 409
    async def mock_avail_2(*_args: Any, **_kwargs: Any) -> int:
        return 2

    monkeypatch.setattr("application.special_equipment_commerce.available_count_for_representative", mock_avail_2)

    with pytest.raises(CheckoutAllocationError) as exc:
        await put_cart_item(
            PutCartItemCommand(user_id=user_id, product_id=product_id, quantity=5, allow_overstock=False),
            session,
        )
    assert exc.value.code == "INSUFFICIENT_EQUIVALENT_PRODUCTS"

    # 2. available = 2, requested = 5, allow_overstock = True -> succeeds
    async def mock_repo_put(*_args: Any, **kwargs: Any) -> tuple[dict[str, Any], bool]:
        assert kwargs["allow_overstock"] is True
        return {"id": uuid4(), "allow_overstock": True, "quantity": 5}, True

    async def mock_visible(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr("application.special_equipment_commerce.repo.put_cart_item", mock_repo_put)
    monkeypatch.setattr("application.special_equipment_commerce.repo.product_visible_in_scope", mock_visible)

    result = await put_cart_item(
        PutCartItemCommand(user_id=user_id, product_id=product_id, quantity=5, allow_overstock=True),
        session,
    )
    assert result["created"] is True
    assert result["cart_item"]["allow_overstock"] is True

    # 3. available = 0, requested = 5, allow_overstock = True -> 409
    async def mock_avail_0(*_args: Any, **_kwargs: Any) -> int:
        return 0

    monkeypatch.setattr("application.special_equipment_commerce.available_count_for_representative", mock_avail_0)

    with pytest.raises(CheckoutAllocationError) as exc_0:
        await put_cart_item(
            PutCartItemCommand(user_id=user_id, product_id=product_id, quantity=5, allow_overstock=True),
            session,
        )
    assert exc_0.value.code == "INSUFFICIENT_EQUIVALENT_PRODUCTS"


@pytest.mark.asyncio
async def test_patch_cart_item_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    cart_item_id = uuid4()
    user_id = uuid4()
    product_id = uuid4()
    session = AsyncMock()

    current_item = {
        "id": cart_item_id,
        "user_id": user_id,
        "product_id": product_id,
        "quantity": 5,
        "allow_overstock": True,
        "parent_item_id": None,
    }

    async def mock_get_cart_item(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return current_item

    monkeypatch.setattr("application.special_equipment_commerce.repo.get_cart_item", mock_get_cart_item)

    # 1. quantity = 1001 -> 422 CART_QUANTITY_OUT_OF_RANGE
    with pytest.raises(ServiceError) as exc_max:
        await patch_cart_item(
            PatchCartItemCommand(user_id=user_id, cart_item_id=cart_item_id, actor_role="client", changes={"quantity": 1001}),
            session,
        )
    assert exc_max.value.code == "CART_QUANTITY_OUT_OF_RANGE"

    # 2. allow_overstock on attachment -> 422 OVERSTOCK_NOT_ALLOWED_FOR_ATTACHMENT
    with pytest.raises(ServiceError) as exc_att:
        await patch_cart_item(
            PatchCartItemCommand(
                user_id=user_id,
                cart_item_id=cart_item_id,
                actor_role="client",
                changes={"allow_overstock": True, "parent_item_id": uuid4()},
            ),
            session,
        )
    assert exc_att.value.code == "OVERSTOCK_NOT_ALLOWED_FOR_ATTACHMENT"

    # 3. Disabling overstock clamps quantity to max(1, available)
    async def mock_avail_2(*_args: Any, **_kwargs: Any) -> int:
        return 2

    patched_changes: dict[str, Any] = {}

    async def mock_repo_patch(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        patched_changes.update(kwargs["changes"])
        return {**current_item, **kwargs["changes"]}

    monkeypatch.setattr("application.special_equipment_commerce.available_count_for_representative", mock_avail_2)
    monkeypatch.setattr("application.special_equipment_commerce.repo.patch_cart_item", mock_repo_patch)

    res = await patch_cart_item(
        PatchCartItemCommand(
            user_id=user_id,
            cart_item_id=cart_item_id,
            actor_role="client",
            changes={"allow_overstock": False},
        ),
        session,
    )
    assert patched_changes["allow_overstock"] is False
    assert patched_changes["quantity"] == 2
    assert res["quantity"] == 2


@pytest.mark.asyncio
async def test_allocate_cart_items_overstock_and_purchase_blockage(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    user_id = uuid4()
    item_id = uuid4()
    product_rep_id = uuid4()
    p1 = {"id": uuid4(), "price": Decimal("2000000"), "publication_status": "published", "sale_status": "available"}
    p2 = {"id": uuid4(), "price": Decimal("2000000"), "publication_status": "published", "sale_status": "available"}

    cart_row = {
        "id": item_id,
        "user_id": user_id,
        "product_id": product_rep_id,
        "quantity": 5,
        "allow_overstock": True,
        "parent_item_id": None,
        "custom_price": None,
        "equipments": [],
        "services": [],
    }

    async def mock_get_cart(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [cart_row]

    async def mock_lock(*_args: Any, **_kwargs: Any) -> None:
        pass

    async def mock_group(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "available_count": 2,
            "_physical_ids": (p1["id"], p2["id"]),
        }

    async def mock_list_products(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [p1, p2]

    async def mock_lock_products(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [p1, p2]

    monkeypatch.setattr("application.special_equipment_checkout.commerce_repository.get_cart_items_for_checkout", mock_get_cart)
    monkeypatch.setattr("application.special_equipment_checkout.commerce_repository.lock_offering_allocation", mock_lock)
    monkeypatch.setattr("application.special_equipment_checkout._group_for_representative", mock_group)
    monkeypatch.setattr("application.special_equipment_checkout.catalog_repository.list_products_by_ids", mock_list_products)
    monkeypatch.setattr("application.special_equipment_checkout.commerce_repository.lock_products", mock_lock_products)

    # 1. Purchase (allow_overstock=False): raises OVERSTOCK_NOT_ALLOWED_FOR_PURCHASE
    with pytest.raises(CheckoutAllocationError) as exc_purchase:
        await allocate_cart_items(
            session,
            user_id=user_id,
            cart_item_ids=(item_id,),
            allow_on_order=False,
            allow_overstock=False,
        )
    assert exc_purchase.value.code == "OVERSTOCK_NOT_ALLOWED_FOR_PURCHASE"

    # 2. Leasing (allow_overstock=True): allocates billable=2, overstock_quantity=3
    allocation = await allocate_cart_items(
        session,
        user_id=user_id,
        cart_item_ids=(item_id,),
        allow_on_order=True,
        allow_overstock=True,
    )
    assert len(allocation.cart_lines) == 1
    line = allocation.cart_lines[0]
    assert line.quantity == 2
    assert line.overstock_quantity == 3
    assert len(line.products) == 2


@pytest.mark.asyncio
async def test_commerce_leasing_application_records_overstock_on_first_offer(monkeypatch: pytest.MonkeyPatch) -> None:
    from application.commerce import (
        CommerceFacade,
        CommerceLeasingApplicationLineCommand,
        CreateCommerceLeasingApplicationBatchCommand,
    )

    facade = CommerceFacade()
    user_id = uuid4()
    company_id = uuid4()
    rep_id = uuid4()
    cart_item_id = uuid4()
    p1 = {"id": uuid4(), "price": Decimal("2881000")}
    p2 = {"id": uuid4(), "price": Decimal("2881000")}

    allocated_line = AllocatedCartLine(
        cart_item_id=cart_item_id,
        representative_id=rep_id,
        parent_cart_item_id=None,
        quantity=2,
        products=(p1, p2),
        overstock_quantity=3,
        custom_price=None,
    )
    mock_allocation = CheckoutAllocation(
        cart_lines=(allocated_line,),
        components=(),
    )

    async def mock_allocate(*_args: Any, **_kwargs: Any) -> CheckoutAllocation:
        return mock_allocation

    seller_id = uuid4()

    async def mock_load_prod(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], ProductCommerceState]:
        return {}, ProductCommerceState(
            id=uuid4(),
            publication_status="published",
            sale_status="available",
            price=Decimal("2881000"),
            price_from=None,
            price_on_request=False,
            seller_company_id=seller_id,
            currency_code="RUB",
            mark_name="FAW",
            model_name="J7",
            modification_name="4x2",
            manufacture_year=2025,
            vin="VIN123",
        )

    captured: dict[str, Any] = {}

    async def mock_create_draft(cmd: Any, _session: Any) -> dict[str, Any]:
        captured["cmd"] = cmd
        return {
            "application_id": uuid4(),
            "vehicle_line_ids": [],
            "special_equipment_line_ids": [uuid4(), uuid4()],
            "status": "active",
        }

    async def mock_delete_cart(*_args: Any, **_kwargs: Any) -> int:
        return 1

    monkeypatch.setattr("application.commerce.allocate_cart_items", mock_allocate)
    monkeypatch.setattr("application.commerce._load_special_equipment_product", mock_load_prod)
    monkeypatch.setattr("application.commerce.handle_create_draft", mock_create_draft)
    monkeypatch.setattr(
        "application.commerce.special_equipment_commerce_repository.delete_cart_items_by_ids",
        mock_delete_cart,
    )

    await facade.create_leasing_application(
        CreateCommerceLeasingApplicationBatchCommand(
            source_type="platform",
            user_id=user_id,
            actor_role="client",
            actor_company_id=None,
            company_id=company_id,
            items=[
                CommerceLeasingApplicationLineCommand(
                    item=CommerceItemRef(CommerceItemType.SPECIAL_EQUIPMENT, rep_id),
                    cart_item_ids=(cart_item_id,),
                    quantity=5,  # 2 billable + 3 overstock
                )
            ],
        ),
        AsyncMock(),
    )

    draft_items = captured["cmd"].special_equipment_items
    assert len(draft_items) == 2
    assert draft_items[0].overstock_requested_quantity == 3
    assert draft_items[1].overstock_requested_quantity == 0


def test_privacy_scoping_overstock_hidden_for_leasing_company() -> None:
    app_id = uuid4()
    se_row = {
        "id": uuid4(),
        "application_id": app_id,
        "product_id": uuid4(),
        "unit_price": Decimal("2881000"),
        "total_price": Decimal("2881000"),
        "item_role": "offer",
        "item_status": "active",
        "overstock_requested_quantity": 3,
        "item_snapshot": {
            "mark": "FAW",
            "model": "J7",
            "modification": "4x2",
        },
    }

    # Direct projection
    client_proj = project_special_equipment_item(se_row, for_leasing_company=False)
    assert client_proj["overstock_requested_quantity"] == 3

    lc_proj = project_special_equipment_item(se_row, for_leasing_company=True)
    assert lc_proj["overstock_requested_quantity"] == 0

    # Grouped projection by role
    dealer_grouped = group_application_items(
        [app_id],
        vehicle_rows=[],
        special_equipment_rows=[se_row],
        actor_role="dealer",
    )
    assert dealer_grouped[app_id][0]["overstock_requested_quantity"] == 3

    lc_grouped = group_application_items(
        [app_id],
        vehicle_rows=[],
        special_equipment_rows=[se_row],
        actor_role="leasing_company",
    )
    assert lc_grouped[app_id][0]["overstock_requested_quantity"] == 0


def test_dealer_notification_contains_overstock_note() -> None:
    app_id = uuid4()
    event_with_overstock = NotificationEvent(
        event_id=uuid4(),
        aggregate_id=app_id,
        application_id=app_id,
        event_type="leasing.application_created",
        entity_type="leasing_application",
        entity_id=app_id,
        request_number="42",
        occurred_at=datetime.now(UTC),
        changed_fields=["status"],
        previous_values={},
        new_values={"status": "active"},
        payload={
            "overstock_items": [
                {
                    "quantity": 3,
                    "name": "FAW J7 4x2",
                    "mark": "FAW",
                    "model": "J7",
                    "modification": "4x2",
                }
            ]
        },
    )

    dealer_recipient = {"user_id": uuid4(), "role": "dealer"}
    employee_recipient = {"user_id": uuid4(), "role": "carcraft_employee"}

    # Notification data extracts overstock_items for dealer
    dealer_data = notification_data(event_with_overstock, "dealer")
    assert "overstock_items" in dealer_data
    assert dealer_data["overstock_items"][0]["quantity"] == 3

    # But not for employee
    employee_data = notification_data(event_with_overstock, "carcraft_employee")
    assert "overstock_items" not in employee_data

    # build_inbox produces overstock note for dealer
    dealer_inbox = build_inbox(event_with_overstock, dealer_recipient)
    assert "Клиент запросил сверх наличия: 3 шт. по позиции «FAW J7 4x2». Эти единицы не включены в заявку." in dealer_inbox["message"]

    # employee does not receive overstock note
    employee_inbox = build_inbox(event_with_overstock, employee_recipient)
    assert "сверх наличия" not in employee_inbox["message"]

    # When no overstock items exist, message is standard
    event_no_overstock = NotificationEvent(
        event_id=uuid4(),
        aggregate_id=app_id,
        application_id=app_id,
        event_type="leasing.application_created",
        entity_type="leasing_application",
        entity_id=app_id,
        request_number="42",
        occurred_at=datetime.now(UTC),
        changed_fields=["status"],
        previous_values={},
        new_values={"status": "active"},
        payload={},
    )
    dealer_standard_inbox = build_inbox(event_no_overstock, dealer_recipient)
    assert "сверх наличия" not in dealer_standard_inbox["message"]
