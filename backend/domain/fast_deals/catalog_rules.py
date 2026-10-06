"""Which catalog listings can become a fast deal position, and which can be reserved."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.vin import is_valid_vin, normalize_vin, validate_vin

# A listing of a unit that can be sold: in stock, or "под заказ" (no VIN yet).
SELLABLE_STATUSES = frozenset({"available", "on_order"})


def ensure_selectable(product: Mapping[str, Any]) -> None:
    """Only published, sellable units; a direct product id never bypasses this."""
    if product.get("publication_status") != "published":
        raise FastDealValidationError("Объявление не опубликовано", field="product_id")
    if product.get("sale_status") not in SELLABLE_STATUSES:
        raise FastDealValidationError("Техника недоступна к продаже", field="product_id")


def resolve_unit_vin(product: Mapping[str, Any], manual_vin: str | None) -> tuple[str, bool]:
    """``(vin, entered_manually)`` of a catalog unit.

    A unit with its own VIN keeps it (the user cannot replace it). A listing without
    VIN, or "под заказ", needs a VIN typed by the user; such a position is manual for
    reservation purposes: it never reserves the listing and never marks it sold.
    """
    own = normalize_vin(product.get("vin"))
    if product.get("no_vin") or not own or product.get("sale_status") == "on_order":
        return validate_vin(manual_vin), True
    if manual_vin and normalize_vin(manual_vin) != own:
        raise FastDealValidationError(
            "VIN каталожной единицы нельзя изменить", field="vin"
        )
    if not is_valid_vin(own):
        raise FastDealValidationError(
            "VIN объявления не подходит для регистрации сделки: "
            "нужен VIN из 17 символов без букв I, O, Q. Исправьте VIN в объявлении",
            field="vin",
        )
    return own, False


def is_reservable_unit(
    product: Mapping[str, Any],
    *,
    owner_company_id: UUID | None,
    expected_owner_id: UUID | None,
    vin_entered_manually: bool,
) -> bool:
    """A real catalog unit with its original VIN, free stock and a proven owner.

    The owner is the warehouse owner, or the seller when there is no warehouse. The
    flag is computed by the server and never accepted from the client.
    """
    return bool(
        not vin_entered_manually
        and not product.get("no_vin")
        and product.get("vin")
        and product.get("sale_status") == "available"
        and owner_company_id is not None
        and expected_owner_id is not None
        and owner_company_id == expected_owner_id
    )
