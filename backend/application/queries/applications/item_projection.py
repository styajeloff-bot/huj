"""Normalized read model for vehicle and special-equipment application lines."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from application.special_equipment_urls import special_equipment_detail_url
from domain.commerce import CommerceItemType
from domain.leasing_purposes import selected_purposes

_VEHICLE_IMAGE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")
_VEHICLE_HISTORY_STATUSES = {
    "not_confirmed": "rejected",
}
_INTERNAL_GROUPING_SNAPSHOT_KEYS = frozenset(
    {
        "composite_product_id",
        "is_base",
        "group_id",
        "parent_group_id",
        "item_role",
    }
)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _quantity(value: Any) -> int:
    quantity = int(value) if value is not None else 1
    return quantity if quantity > 0 else 1


def _correction_amount(
    *, correction_type: Any, value: Any, catalog_price: Decimal | None
) -> Decimal | None:
    correction_value = _decimal(value)
    if correction_type is None or correction_value is None or catalog_price is None:
        return None
    kind = str(correction_type)
    if kind in {"rubles_off", "rubles_up"}:
        amount = correction_value
    elif kind in {"percent_off", "percent_up"}:
        amount = catalog_price * correction_value / Decimal("100")
    elif kind == "fixed_price":
        amount = catalog_price - correction_value
    else:
        return None
    return max(amount, Decimal("0")).quantize(Decimal("0.01"))


def _effective_vehicle_total(row: dict[str, Any], quantity: int) -> Decimal | None:
    unit_price = _decimal(row.get("unit_price"))
    stored_total = _decimal(row.get("total_price"))
    calculated = unit_price * quantity if unit_price is not None else None
    # ``total_price`` includes persisted additional equipment and services;
    # recomputing it from the base unit price would silently drop those costs.
    if stored_total is not None and stored_total != 0:
        return stored_total
    if calculated is not None and calculated != 0:
        return calculated
    return calculated if calculated is not None else stored_total


def _first_vehicle_image_url(raw_images: Any) -> str | None:
    if not isinstance(raw_images, list) or not raw_images:
        return None
    first = raw_images[0]
    filename: Any
    if isinstance(first, str):
        filename = first
    elif isinstance(first, dict):
        filename = first.get("filename")
    else:
        return None
    if not isinstance(filename, str) or not _VEHICLE_IMAGE_FILENAME.fullmatch(
        filename
    ):
        return None
    return f"/api/v1/cars/images/{filename}"


def _vehicle_title(row: dict[str, Any]) -> str:
    mark = (
        row.get("mark_name")
        or row.get("fallback_mark_name")
        or row.get("mark_cyrillic_name")
        or row.get("mark_cyrillic")
        or row.get("fallback_mark_cyrillic_name")
    )
    model = (
        row.get("model_name")
        or row.get("fallback_model_name")
        or row.get("model_cyrillic_name")
        or row.get("model_cyrillic")
        or row.get("fallback_model_cyrillic_name")
    )
    modification = (
        row.get("complectation_name")
        or row.get("group_name")
        or row.get("modification_name")
        or row.get("fallback_modification_name")
    )
    title = " ".join(str(part).strip() for part in (mark, model, modification) if part)
    return title or "Автомобиль"


def project_vehicle_item(row: dict[str, Any]) -> dict[str, Any]:
    """Map one ``application_vehicles`` row to the common wire contract."""

    quantity = _quantity(row.get("quantity"))
    raw_status_value = row.get("status") or row.get("car_status")
    raw_status = str(raw_status_value) if raw_status_value is not None else None
    public_status = (
        (_VEHICLE_HISTORY_STATUSES.get(raw_status) or raw_status)
        if raw_status is not None
        else None
    )
    unit_price = _decimal(row.get("unit_price"))
    current_catalog_price = _decimal(
        row.get("catalog_price_from") or row.get("fallback_catalog_price_from")
    )
    catalog_price = (
        unit_price
        if unit_price is not None and unit_price > 0
        else current_catalog_price
    )
    final_price = _decimal(row.get("final_price"))
    if final_price is None:
        final_price = catalog_price
    discount_amount = _correction_amount(
        correction_type=row.get("discount_type"),
        value=row.get("discount_value"),
        catalog_price=catalog_price,
    )
    markup_amount = _correction_amount(
        correction_type=row.get("markup_type"),
        value=row.get("markup_value"),
        catalog_price=catalog_price,
    )
    return {
        "type": CommerceItemType.VEHICLE.value,
        "id": row["id"],
        "item_id": row.get("vehicle_id"),
        "title": _vehicle_title(row),
        "image_url": _first_vehicle_image_url(row.get("images")),
        "detail_url": (
            f"/cars/{row['vehicle_id']}" if row.get("vehicle_id") else None
        ),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": _effective_vehicle_total(row, quantity),
        "catalog_price": catalog_price,
        "discount_type": row.get("discount_type"),
        "discount_value": _decimal(row.get("discount_value")),
        "discount_amount": discount_amount,
        "markup_type": row.get("markup_type"),
        "markup_value": _decimal(row.get("markup_value")),
        "markup_amount": markup_amount,
        "final_price": final_price,
        "show_catalog_price": bool(
            row.get("discount_show_catalog_price", True)
        )
        and bool(row.get("markup_show_catalog_price", True)),
        "comment": row.get("comment"),
        "dealer_comment": row.get("dealer_comment"),
        "leasing_purpose": row.get("leasing_purpose"),
        "leasing_purposes": selected_purposes(row.get("leasing_purposes"), row.get("leasing_purpose")),
        "regions": row.get("regions") or [],
        "region": (row.get("regions") or [None])[0],
        "currency_code": "RUB",
        "status": public_status,
        "snapshot": None,
    }


def _snapshot(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("item_snapshot")
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key not in _INTERNAL_GROUPING_SNAPSHOT_KEYS
    }


def _special_equipment_title(
    row: dict[str, Any], snapshot: dict[str, Any]
) -> str:
    from domain.special_equipment_kits import kit_title

    mark = snapshot.get("mark") or row.get("mark_name")
    model = snapshot.get("model") or row.get("model_name")
    modification = snapshot.get("modification") or row.get("modification_name")
    superstructure_name = (
        snapshot.get("superstructure_name")
        or row.get("superstructure_name")
    )
    if superstructure_name and mark and model:
        return kit_title(
            superstructure_name=str(superstructure_name),
            chassis_mark_name=str(mark),
            chassis_model_name=str(model),
        )
    title = " ".join(
        str(part).strip()
        for part in (mark, model, modification)
        if part
    )
    return title or "Спецтехника"


def project_special_equipment_group(
    group_rows: list[dict[str, Any]],
    *,
    for_leasing_company: bool = False,
) -> dict[str, Any]:
    """Map a group of special-equipment lines to a single position."""
    if not group_rows:
        raise ValueError("group_rows must not be empty")

    first_row = group_rows[0]
    group_id = first_row.get("group_id")
    quantity = len(group_rows)
    snapshot = _snapshot(first_row)
    image_id = first_row.get("primary_image_id")
    unit_price = _decimal(first_row.get("unit_price"))
    total_price: Decimal | None
    if unit_price is not None:
        total_price = unit_price * quantity
    else:
        stored_total = _decimal(first_row.get("total_price"))
        total_price = (
            stored_total
            if stored_total is not None and stored_total > 0
            else None
        )

    detail_product_id = first_row.get("detail_product_id")
    detail_product_slug = first_row.get("detail_product_slug")

    raw_overstock = max(
        (int(r.get("overstock_requested_quantity") or 0) for r in group_rows),
        default=0,
    )
    overstock_requested_quantity = 0 if for_leasing_company else raw_overstock

    product_ids = [
        r["product_id"] for r in group_rows if r.get("product_id") is not None
    ]
    item_id = group_id if group_id is not None else first_row["product_id"]

    raw_regions: Any = next(
        (r.get("regions") for r in group_rows if r.get("regions")),
        [],
    )
    regions: list[str] = (
        [str(item) for item in raw_regions]
        if isinstance(raw_regions, list)
        else []
    )
    region: str | None = regions[0] if regions else None
    leasing_purpose = next(
        (r.get("leasing_purpose") for r in group_rows if r.get("leasing_purpose")),
        None,
    )
    comment = next(
        (r.get("comment") for r in group_rows if r.get("comment")),
        None,
    )

    return {
        "type": CommerceItemType.SPECIAL_EQUIPMENT.value,
        "id": first_row["id"],
        "item_id": item_id,
        "product_ids": product_ids,
        "seller_company_id": first_row.get("seller_company_id"),
        "title": _special_equipment_title(first_row, snapshot),
        "image_url": (
            f"/api/v1/special-equipment/images/{image_id}/content"
            if image_id
            else None
        ),
        "detail_url": special_equipment_detail_url(
            detail_product_id,
            detail_product_slug,
        ),
        "quantity": quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "currency_code": first_row.get("currency_code") or "RUB",
        "status": first_row.get("status") or first_row.get("item_status"),
        "item_role": first_row.get("item_role") or "offer",
        "snapshot": snapshot,
        "price_on_request": snapshot.get("price_on_request") is True,
        "price_status": first_row.get("price_status") or "none",
        "price_set_by": first_row.get("price_set_by"),
        "price_set_at": first_row.get("price_set_at"),
        "comment": comment,
        "leasing_purpose": leasing_purpose,
        "leasing_purposes": list(dict.fromkeys(value for row in group_rows for value in selected_purposes(row.get("leasing_purposes"), row.get("leasing_purpose")))),
        "regions": regions,
        "region": region,
        "overstock_requested_quantity": overstock_requested_quantity,
    }


def project_special_equipment_item(
    row: dict[str, Any],
    *,
    for_leasing_company: bool = False,
) -> dict[str, Any]:
    """Map one special-equipment line using its immutable snapshot."""
    return project_special_equipment_group([row], for_leasing_company=for_leasing_company)


def group_application_items(
    application_ids: list[UUID],
    *,
    vehicle_rows: list[dict[str, Any]],
    special_equipment_rows: list[dict[str, Any]],
    actor_role: str | None = None,
    for_leasing_company: bool = False,
) -> dict[UUID, list[dict[str, Any]]]:
    """Build deterministic, discriminated item arrays for many applications."""

    is_lc = for_leasing_company or actor_role == "leasing_company"
    grouped: dict[UUID, list[dict[str, Any]]] = {
        application_id: [] for application_id in application_ids
    }
    se_by_app_and_product = {
        (row["application_id"], row["product_id"])
        for row in special_equipment_rows
        if row.get("product_id")
    }
    se_by_app_and_id = {
        (row["application_id"], row["id"])
        for row in special_equipment_rows
        if row.get("id")
    }
    for row in vehicle_rows:
        app_id = row["application_id"]
        prod_id = row.get("product_id") or row.get("vehicle_id")
        row_id = row.get("id")
        if (app_id, prod_id) in se_by_app_and_product or (app_id, row_id) in se_by_app_and_id:
            continue
        grouped.setdefault(app_id, []).append(
            project_vehicle_item(row)
        )

    se_by_app: dict[UUID, list[dict[str, Any]]] = {}
    for row in special_equipment_rows:
        se_by_app.setdefault(row["application_id"], []).append(row)

    for app_id, rows in se_by_app.items():
        if app_id not in grouped:
            grouped[app_id] = []
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in rows:
            group_id = row.get("group_id")
            key: tuple[Any, ...]
            if group_id is None:
                key = ("legacy", row.get("id") or object())
            else:
                item_role = row.get("item_role") or "offer"
                status = row.get("status") or row.get("item_status") or "active"
                if item_role == "component":
                    key = ("component", group_id, row.get("product_id"), status)
                else:
                    key = ("grouped", group_id, item_role, status)
            groups.setdefault(key, []).append(row)

        for group_rows in groups.values():
            grouped[app_id].append(
                project_special_equipment_group(group_rows, for_leasing_company=is_lc)
            )

    return grouped


__all__ = [
    "group_application_items",
    "project_special_equipment_group",
    "project_special_equipment_item",
    "project_vehicle_item",
]

