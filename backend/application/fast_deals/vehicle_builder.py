"""Construction and validation of fast deal positions, options and their audit diffs.

A position is one physical unit with a VIN (no quantity). It comes from a catalog
unit (``product``) or is typed in by hand (``manual``). Everything derived from the
catalog (names, owner, base price, reservability) is computed here on the server and
never accepted from the client; free text never creates a directory row. These
helpers only read: the commands persist the result.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.pricing import priced_columns
from domain.fast_deals import catalog_rules, pricing
from domain.fast_deals.errors import FastDealConflictError, FastDealValidationError
from domain.fast_deals.money import ZERO, money, nonnegative_money, wire
from domain.fast_deals.values import ItemStatus, Party, SourceType, VehicleSource
from domain.fast_deals.vin import normalize_vin, validate_vin
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_catalog_repository as catalog_repo

Record = dict[str, Any]

_PRODUCT_FIELDS = frozenset({"vehicle_source_type", "product_id", "vin", "price"})
_DEALER_MANUAL_FIELDS = frozenset(
    {
        "vehicle_source_type", "category_id", "mark_id", "model_id", "modification_id",
        "trim_id", "mark_name", "model_name", "vin", "price", "body_color_id",
        "dealer_company_id",
    }
)
_LEASING_MANUAL_FIELDS = frozenset(
    {
        "vehicle_source_type", "mark_name", "model_name", "modification_name", "trim_name",
        "body_color_name", "vin", "price", "category_id", "dealer_company_id",
    }
)
# What a position may be edited with, by who edits and what the position is.
_PRODUCT_PATCH_FIELDS = frozenset({"vin", "price"})
_DEALER_MANUAL_PATCH_FIELDS = frozenset(
    {
        "vin", "price", "category_id", "mark_id", "model_id", "modification_id", "mark_name",
        "model_name", "body_color_id",
    }
)
_LEASING_MANUAL_PATCH_FIELDS = frozenset(
    {
        "vin", "price", "category_id", "mark_name", "model_name", "modification_name",
        "body_color_name", "dealer_company_id",
    }
)
# The dealer of a DL deal may correct the text data and the price of manual positions.
_DL_DEALER_PATCH_FIELDS = frozenset(
    {"vin", "price", "mark_name", "model_name", "modification_name", "body_color_name"}
)
_CHAIN_FIELDS = frozenset(
    {"mark_id", "model_id", "modification_id", "trim_id", "mark_name", "model_name"}
)

# Fields of a position written to the audit trail when they change. A leasing
# company sees only the allow-listed ones (``domain.fast_deals.projection``).
LOGGED_FIELDS = (
    "mark_name", "model_name", "modification_name", "trim_name", "category_name",
    "body_color_name", "vin", "dealer_company_id", "base_price", "adjustment_type",
    "adjustment_amount", "equipments", "services", "purposes", "regions", "final_price",
)
_ADDED_FIELDS = (
    "mark_name", "model_name", "modification_name", "vin", "base_price", "final_price",
)


# -------------------------------------------------------------------------- primitives

def _uuid(value: Any, field: str) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise FastDealValidationError("Некорректный идентификатор", field=field) from exc


def _required_uuid(value: Any, field: str, message: str) -> UUID:
    result = _uuid(value, field)
    if result is None:
        raise FastDealValidationError(message, field=field)
    return result


def _text(value: Any, field: str, *, limit: int = 255) -> str | None:
    text = "" if value is None else str(value).strip()
    if len(text) > limit:
        raise FastDealValidationError(f"Не более {limit} символов", field=field)
    return text or None


def _required_text(value: Any, field: str, message: str) -> str:
    text = _text(value, field)
    if text is None:
        raise FastDealValidationError(message, field=field)
    return text


def _string(value: Any) -> str | None:
    return None if value is None else str(value)


def _node_snapshot(node_id: Any, name: str | None) -> Record | None:
    if node_id is None and name is None:
        return None
    return {"id": _string(node_id), "name": name}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _reject_unsupported(body: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    """A field that does not apply to this kind of position is an error, not ignored."""
    for name, value in body.items():
        if value is not None and name not in allowed:
            raise FastDealValidationError(
                f"Поле «{name}» не используется для {where}", field=name
            )


def duplicate_unit_error(vin: str, message: str) -> FastDealConflictError:
    """409 that names the VIN; the global handler reads ``vin`` from the error."""
    error = FastDealConflictError(message)
    error.vin = vin  # type: ignore[attr-defined]
    return error


def ensure_unique_unit(
    existing: Iterable[Mapping[str, Any]],
    *,
    vin: str,
    product_id: UUID | None,
    exclude_id: UUID | None = None,
) -> None:
    """One catalog unit and one VIN appear at most once among the active positions."""
    for item in existing:
        if item["id"] == exclude_id or item["item_status"] != ItemStatus.ACTIVE:
            continue
        if product_id is not None and item.get("product_id") == product_id:
            raise duplicate_unit_error(vin, "Эта единица техники уже добавлена в сделку")
        if normalize_vin(item["vin"]) == vin:
            raise duplicate_unit_error(vin, f"Техника с VIN {vin} уже есть в сделке")


def ensure_dealer_fits(deal: Mapping[str, Any], dealer_company_id: UUID | None, field: str) -> None:
    """After the DL split a deal belongs to one dealer: only its own units may be added."""
    if deal["source_type"] != SourceType.LEASING_TO_DEALER or deal.get("group_id") is None:
        return
    if dealer_company_id != deal["dealer_company_id"]:
        raise FastDealValidationError(
            "После отправки в сделку можно добавить технику только того же дилера",
            field=field,
        )


async def require_active_dealer(
    session: AsyncSession, company_id: UUID, *, field: str, message: str
) -> None:
    brief = (await access_repo.company_briefs(session, [company_id])).get(company_id)
    if brief is None or brief["company_type"] != "dealer" or not brief["is_active"]:
        raise FastDealValidationError(message, field=field)


# ------------------------------------------------------------------- directory chain

async def _node(
    session: AsyncSession, kind: catalog_repo.NodeKind, node_id: UUID, *, field: str
) -> Record:
    node: Record | None = await catalog_repo.get_directory_node(session, kind, node_id)
    if node is None:
        raise FastDealValidationError("Значение не найдено в справочнике", field=field)
    if not node["is_active"]:
        raise FastDealValidationError("Значение справочника отключено", field=field)
    return node


async def resolve_dealer_chain(
    session: AsyncSession,
    *,
    mark_id: UUID | None,
    model_id: UUID | None,
    modification_id: UUID | None,
    trim_id: UUID | None,
    mark_name: str | None,
    model_name: str | None,
) -> Record:
    """Directory chain of a dealer's manual position, checked for consistency.

    mark → model → optional modification → optional trim, every level belonging to the
    previous one. Without a mark ("Нет марки") the mark and the model are text; without
    a model ("Нет модели") the model is text. Names always come from the directory.
    """
    chain: Record = {
        "mark_id": None, "mark_name": None, "model_id": None, "model_name": None,
        "modification_id": None, "modification_name": None, "trim_id": None, "trim_name": None,
    }
    if mark_id is None:
        if model_id is not None or modification_id is not None or trim_id is not None:
            raise FastDealValidationError("Сначала выберите марку", field="mark_id")
        chain["mark_name"] = _required_text(
            mark_name, "mark_name", "Укажите марку или выберите её из справочника"
        )
        chain["model_name"] = _required_text(model_name, "model_name", "Укажите модель")
        return chain
    mark = await _node(session, "mark", mark_id, field="mark_id")
    chain.update(mark_id=mark["id"], mark_name=mark["name"])
    if model_id is None:
        if modification_id is not None or trim_id is not None:
            raise FastDealValidationError("Сначала выберите модель", field="model_id")
        chain["model_name"] = _required_text(
            model_name, "model_name", "Укажите модель или выберите её из справочника"
        )
        return chain
    model = await _node(session, "model", model_id, field="model_id")
    if model["parent_id"] != mark["id"]:
        raise FastDealValidationError("Модель не относится к выбранной марке", field="model_id")
    chain.update(model_id=model["id"], model_name=model["name"])
    if modification_id is None:
        if trim_id is not None:
            raise FastDealValidationError("Сначала выберите модификацию", field="modification_id")
        return chain
    modification = await _node(session, "modification", modification_id, field="modification_id")
    if modification["parent_id"] != model["id"]:
        raise FastDealValidationError(
            "Модификация не относится к выбранной модели", field="modification_id"
        )
    chain.update(modification_id=modification["id"], modification_name=modification["name"])
    if trim_id is None:
        return chain
    trim = await _node(session, "trim", trim_id, field="trim_id")
    if trim["parent_id"] != modification["id"]:
        raise FastDealValidationError(
            "Комплектация не относится к выбранной модификации", field="trim_id"
        )
    chain.update(trim_id=trim["id"], trim_name=trim["name"])
    return chain


async def _body_color(session: AsyncSession, color_id: UUID | None) -> Record:
    if color_id is None:
        return {"body_color_id": None, "body_color_name": None}
    color = await _node(session, "color", color_id, field="body_color_id")
    if color["applicability"] not in {"body", "both"}:
        raise FastDealValidationError(
            "Этот цвет нельзя использовать для кузова", field="body_color_id"
        )
    return {"body_color_id": color["id"], "body_color_name": color["name"]}


async def _category(session: AsyncSession, category_id: UUID) -> Record:
    category = await _node(session, "category", category_id, field="category_id")
    return {"category_id": category["id"], "category_name": category["name"]}


# --------------------------------------------------------------------------- snapshots

def _product_snapshot(product: Mapping[str, Any], agreed_price: Decimal) -> Record:
    """Catalog values as they were when the unit was added: names, ids and prices."""
    return {
        "source": VehicleSource.PRODUCT.value,
        "captured_at": _now_iso(),
        "product_id": _string(product["id"]),
        "code": product["code"],
        "vin": product["vin"],
        "no_vin": bool(product["no_vin"]),
        "condition": product["condition"],
        "manufacture_year": product["manufacture_year"],
        "price": wire(product["price"]),
        "special_price": wire(product["special_price"]),
        "price_on_request": bool(product["price_on_request"]),
        "price_from": wire(product["price_from"]),
        "agreed_price": wire(agreed_price),
        "sale_status": product["sale_status"],
        "publication_status": product["publication_status"],
        "seller_company_id": _string(product["seller_company_id"]),
        "owner_company_id": _string(product["owner_company_id"]),
        "warehouse": _node_snapshot(product["warehouse_id"], product["warehouse_name"]),
        "mark": _node_snapshot(product["mark_id"], product["mark_name"]),
        "model": _node_snapshot(product["model_id"], product["model_name"]),
        "modification": _node_snapshot(product["modification_id"], product["modification_name"]),
        "trim": _node_snapshot(product["trim_id"], product["trim_name"]),
        "category": _node_snapshot(product["category_id"], product["category_name"]),
        "body_color": _node_snapshot(product["body_color_id"], product["body_color_name"]),
    }


def manual_snapshot(values: Mapping[str, Any]) -> Record:
    """Independent image of a manual position: it never links to the catalog by itself."""
    return {
        "source": VehicleSource.MANUAL.value,
        "captured_at": _now_iso(),
        "vin": values["vin"],
        "base_price": wire(values["base_price"]),
        "dealer_company_id": _string(values.get("dealer_company_id")),
        "mark": _node_snapshot(values.get("mark_id"), values.get("mark_name")),
        "model": _node_snapshot(values.get("model_id"), values.get("model_name")),
        "modification": _node_snapshot(
            values.get("modification_id"), values.get("modification_name")
        ),
        "trim": _node_snapshot(values.get("trim_id"), values.get("trim_name")),
        "category": _node_snapshot(values.get("category_id"), values.get("category_name")),
        "body_color": _node_snapshot(
            values.get("body_color_id"), values.get("body_color_name")
        ),
    }


# --------------------------------------------------------------------- new positions

def _catalog_base_price(product: Mapping[str, Any], explicit: Any) -> Decimal:
    """``special_price`` else ``price``; a request-priced unit takes the stated price."""
    on_request = bool(product["price_on_request"])
    base = pricing.base_price_for_catalog_unit(
        price=product["price"],
        special_price=product["special_price"],
        price_on_request=on_request,
        explicit_price=explicit,
    )
    if not on_request and explicit is not None and money(explicit, field="price") != base:
        raise FastDealValidationError(
            "Цена каталожной единицы задаётся каталогом: скидку или наценку укажите отдельно",
            field="price",
        )
    return base


async def _product_position(
    session: AsyncSession, deal: Mapping[str, Any], body: Mapping[str, Any]
) -> Record:
    _reject_unsupported(body, _PRODUCT_FIELDS, "каталожной позиции")
    dd = deal["source_type"] == SourceType.DEALER_TO_LEASING
    product_id = _required_uuid(body.get("product_id"), "product_id", "Выберите технику")
    product: Record | None = await catalog_repo.get_product(session, product_id)
    initiator = deal["initiator_company_id"]
    # A foreign or unpublished listing is indistinguishable from a missing one.
    if product is None or (
        product["owner_company_id"] != initiator if dd else product["publication_status"] != "published"
    ):
        raise FastDealValidationError(
            "Не найдено на ваших складах" if dd else "Объявление не найдено", field="product_id"
        )
    catalog_rules.ensure_selectable(product)
    vin, entered_manually = catalog_rules.resolve_unit_vin(product, body.get("vin"))
    base_price = _catalog_base_price(product, body.get("price"))
    owner = product["owner_company_id"]
    if dd:
        dealer_id = initiator
    else:
        if owner is None:
            raise FastDealValidationError(
                "Не удалось определить дилера: у техники нет владельца", field="product_id"
            )
        await require_active_dealer(
            session, owner, field="product_id",
            message="Владелец техники не является действующим дилером",
        )
        dealer_id = owner
    if not product["mark_name"] or not product["model_name"]:
        raise FastDealValidationError(
            "У объявления не заполнены марка и модель", field="product_id"
        )
    return {
        "vehicle_source_type": VehicleSource.PRODUCT.value,
        "product_id": product["id"],
        "mark_id": product["mark_id"],
        "mark_name": product["mark_name"],
        "model_id": product["model_id"],
        "model_name": product["model_name"],
        "modification_id": product["modification_id"],
        "modification_name": product["modification_name"],
        "trim_id": product["trim_id"],
        "trim_name": product["trim_name"],
        "category_id": product["category_id"],
        "category_name": product["category_name"],
        "body_color_id": product["body_color_id"],
        "body_color_name": product["body_color_name"],
        "vin": vin,
        "vin_entered_manually": entered_manually,
        "is_reservable": catalog_rules.is_reservable_unit(
            product,
            owner_company_id=owner,
            expected_owner_id=dealer_id,
            vin_entered_manually=entered_manually,
        ),
        "warehouse_id": product["warehouse_id"],
        "dealer_company_id": dealer_id,
        "base_price": base_price,
        "catalog_snapshot": _product_snapshot(product, base_price),
    }


async def _dealer_manual_position(
    session: AsyncSession, deal: Mapping[str, Any], body: Mapping[str, Any]
) -> Record:
    """DD manual position: directory chain or text fallbacks, the dealer is the initiator."""
    _reject_unsupported(body, _DEALER_MANUAL_FIELDS, "ручной позиции дилера")
    initiator = deal["initiator_company_id"]
    explicit_dealer = _uuid(body.get("dealer_company_id"), "dealer_company_id")
    if explicit_dealer not in (None, initiator):
        raise FastDealValidationError(
            "В этой сделке дилер — компания-инициатор", field="dealer_company_id"
        )
    chain = await resolve_dealer_chain(
        session,
        mark_id=_uuid(body.get("mark_id"), "mark_id"),
        model_id=_uuid(body.get("model_id"), "model_id"),
        modification_id=_uuid(body.get("modification_id"), "modification_id"),
        trim_id=_uuid(body.get("trim_id"), "trim_id"),
        mark_name=body.get("mark_name"),
        model_name=body.get("model_name"),
    )
    category = await _category(
        session, _required_uuid(body.get("category_id"), "category_id", "Выберите категорию")
    )
    color = await _body_color(session, _uuid(body.get("body_color_id"), "body_color_id"))
    values: Record = {
        "vehicle_source_type": VehicleSource.MANUAL.value,
        "product_id": None,
        "body_color_name": None,
        **chain,
        **category,
        **color,
        "vin": validate_vin(body.get("vin")),
        "vin_entered_manually": True,
        "is_reservable": False,
        "warehouse_id": None,
        "dealer_company_id": initiator,
        "base_price": pricing.manual_base_price(body.get("price")),
    }
    values["catalog_snapshot"] = manual_snapshot(values)
    return values


async def _leasing_manual_position(
    session: AsyncSession, deal: Mapping[str, Any], body: Mapping[str, Any]
) -> Record:
    """DL manual position: text data, a directory category and an explicit dealer."""
    _reject_unsupported(body, _LEASING_MANUAL_FIELDS, "ручной позиции лизинговой компании")
    dealer_id = _required_uuid(
        body.get("dealer_company_id"), "dealer_company_id", "Выберите дилера"
    )
    await require_active_dealer(
        session, dealer_id, field="dealer_company_id", message="Выберите действующего дилера"
    )
    category = await _category(
        session, _required_uuid(body.get("category_id"), "category_id", "Выберите категорию")
    )
    values: Record = {
        "vehicle_source_type": VehicleSource.MANUAL.value,
        "product_id": None,
        "mark_id": None,
        "mark_name": _required_text(body.get("mark_name"), "mark_name", "Укажите марку"),
        "model_id": None,
        "model_name": _required_text(body.get("model_name"), "model_name", "Укажите модель"),
        "modification_id": None,
        "modification_name": _text(body.get("modification_name"), "modification_name"),
        "trim_id": None,
        "trim_name": _text(body.get("trim_name"), "trim_name"),
        "body_color_id": None,
        "body_color_name": _text(body.get("body_color_name"), "body_color_name"),
        **category,
        "vin": validate_vin(body.get("vin")),
        "vin_entered_manually": True,
        "is_reservable": False,
        "warehouse_id": None,
        "dealer_company_id": dealer_id,
        "base_price": pricing.manual_base_price(body.get("price")),
    }
    values["catalog_snapshot"] = manual_snapshot(values)
    return values


async def build_position(
    session: AsyncSession,
    deal: Mapping[str, Any],
    body: Mapping[str, Any],
    *,
    created_by: UUID,
    existing: Sequence[Mapping[str, Any]],
    position: int,
) -> Record:
    """Insert values of a new position of ``deal``; nothing is written.

    ``existing`` are the active positions that the new unit must not duplicate.
    Raises ``FastDealValidationError`` (field-level) or ``FastDealConflictError``
    (a duplicate unit or VIN, with ``vin``).
    """
    kind = body.get("vehicle_source_type")
    dd = deal["source_type"] == SourceType.DEALER_TO_LEASING
    if kind == VehicleSource.PRODUCT:
        parts = await _product_position(session, deal, body)
        dealer_field = "product_id"
    elif kind == VehicleSource.MANUAL:
        parts = await (
            _dealer_manual_position(session, deal, body)
            if dd
            else _leasing_manual_position(session, deal, body)
        )
        dealer_field = "dealer_company_id"
    else:
        raise FastDealValidationError(
            "Укажите вид позиции: каталожная или ручная", field="vehicle_source_type"
        )
    ensure_dealer_fits(deal, parts["dealer_company_id"], dealer_field)
    ensure_unique_unit(existing, vin=parts["vin"], product_id=parts["product_id"])
    return {
        "fast_deal_id": deal["id"],
        "position": position,
        "item_status": ItemStatus.ACTIVE.value,
        "equipments": [],
        "services": [],
        "purposes": [],
        "regions": [],
        "adjustment_type": None,
        "adjustment_amount": None,
        "support_amount": ZERO,
        "options_amount": ZERO,
        # Repriced by ``refresh_deal_totals`` right after the insert.
        "final_price": parts["base_price"],
        "created_by": created_by,
        **parts,
    }


# --------------------------------------------------------------------- edited positions

async def patch_columns(
    session: AsyncSession,
    *,
    deal: Mapping[str, Any],
    vehicle: Mapping[str, Any],
    fields: Mapping[str, Any],
    party: Party,
    existing: Sequence[Mapping[str, Any]],
) -> Record:
    """Changed columns of a position for the sent ``fields``; empty when nothing changes.

    A catalog unit keeps its catalog data: only a VIN typed by hand and the agreed
    price of a request-priced listing can be edited. The directory chain of a dealer's
    manual position is replaced as a unit when any of its fields is sent. The dealer of
    a DL deal may correct the text data and the price of manual positions only.
    """
    allowed = _patch_allowed(vehicle, deal, party)
    for name in fields:
        if name not in allowed:
            raise FastDealValidationError(
                f"Поле «{name}» нельзя изменить у этой позиции", field=name
            )
    updates: Record = {}
    if "vin" in fields:
        vin = validate_vin(fields["vin"])
        ensure_unique_unit(existing, vin=vin, product_id=None, exclude_id=vehicle["id"])
        updates["vin"] = vin
    if "price" in fields:
        updates["base_price"] = pricing.manual_base_price(fields["price"])
    if _CHAIN_FIELDS & fields.keys():
        updates.update(
            await resolve_dealer_chain(
                session,
                mark_id=_uuid(fields.get("mark_id"), "mark_id"),
                model_id=_uuid(fields.get("model_id"), "model_id"),
                modification_id=_uuid(fields.get("modification_id"), "modification_id"),
                trim_id=None,
                mark_name=fields.get("mark_name"),
                model_name=fields.get("model_name"),
            )
        )
    elif vehicle["vehicle_source_type"] == VehicleSource.MANUAL:
        _merge_text_fields(updates, fields)
    if "category_id" in fields:
        updates.update(
            await _category(
                session,
                _required_uuid(fields["category_id"], "category_id", "Категорию нельзя очистить"),
            )
        )
    if "body_color_id" in fields:
        updates.update(await _body_color(session, _uuid(fields["body_color_id"], "body_color_id")))
    if "dealer_company_id" in fields:
        dealer_id = _required_uuid(
            fields["dealer_company_id"], "dealer_company_id", "Выберите дилера"
        )
        await require_active_dealer(
            session, dealer_id, field="dealer_company_id", message="Выберите действующего дилера"
        )
        ensure_dealer_fits(deal, dealer_id, "dealer_company_id")
        updates["dealer_company_id"] = dealer_id
    changed = {name: value for name, value in updates.items() if vehicle.get(name) != value}
    if not changed:
        return {}
    if vehicle["vehicle_source_type"] == VehicleSource.MANUAL:
        changed["catalog_snapshot"] = manual_snapshot({**vehicle, **changed})
    return changed


def _merge_text_fields(updates: Record, fields: Mapping[str, Any]) -> None:
    """Text fields of a leasing company's manual position (and the DL dealer's edits)."""
    for name, message in (
        ("mark_name", "Укажите марку"),
        ("model_name", "Укажите модель"),
    ):
        if name in fields:
            updates[name] = _required_text(fields[name], name, message)
    for name in ("modification_name", "body_color_name"):
        if name in fields:
            updates[name] = _text(fields[name], name)


def _patch_allowed(
    vehicle: Mapping[str, Any], deal: Mapping[str, Any], party: Party
) -> frozenset[str]:
    manual = vehicle["vehicle_source_type"] == VehicleSource.MANUAL
    if party == Party.DEALER:
        return _DL_DEALER_PATCH_FIELDS if manual else frozenset()
    if not manual:
        allowed = set()
        if vehicle["vin_entered_manually"]:
            allowed.add("vin")
        if (vehicle.get("catalog_snapshot") or {}).get("price_on_request"):
            allowed.add("price")
        return frozenset(allowed) & _PRODUCT_PATCH_FIELDS
    if deal["source_type"] == SourceType.DEALER_TO_LEASING:
        return _DEALER_MANUAL_PATCH_FIELDS
    return _LEASING_MANUAL_PATCH_FIELDS


# ------------------------------------------------------------------------------ options

async def _option_items(
    session: AsyncSession,
    items: Sequence[Mapping[str, Any]],
    *,
    field: str,
    lookup: Callable[[AsyncSession, list[str]], Awaitable[dict[str, str]]],
) -> list[Record]:
    codes: list[str] = []
    for item in items:
        code = _required_text(item.get("code"), field, "Укажите код элемента справочника")
        if code in codes:
            raise FastDealValidationError(f"Элемент «{code}» выбран дважды", field=field)
        codes.append(code)
    names = await lookup(session, codes)
    result: list[Record] = []
    for item, code in zip(items, codes, strict=True):
        if code not in names:
            raise FastDealValidationError(
                f"Элемент «{code}» не найден в справочнике или отключён", field=field
            )
        price = item.get("price")
        result.append(
            {
                "code": code,
                "name": names[code],
                "price": wire(nonnegative_money(ZERO if price is None else price, field=field)),
                "comment": _text(item.get("comment"), field, limit=500),
            }
        )
    return result


async def _dictionary_values(
    session: AsyncSession,
    values: Iterable[Any],
    *,
    field: str,
    lookup: Callable[[AsyncSession, list[str]], Awaitable[set[str]]],
) -> list[str]:
    unique: list[str] = []
    for raw in values:
        value = _required_text(raw, field, "Пустое значение справочника")
        if value not in unique:
            unique.append(value)
    unknown = sorted(unique_value for unique_value in unique if unique_value not in await lookup(session, unique))
    if unknown:
        raise FastDealValidationError(
            f"Неизвестные значения справочника: {', '.join(unknown)}", field=field
        )
    return unique


async def normalize_options(
    session: AsyncSession,
    *,
    equipments: Sequence[Mapping[str, Any]],
    services: Sequence[Mapping[str, Any]],
    purposes: Sequence[str],
    regions: Sequence[str],
) -> Record:
    """The complete option set of a position as it is stored.

    Equipment and services are checked against the active dictionaries and stored as
    ``{code, name, price (exact string), comment}``; purposes and regions are stored as
    their dictionary names, without repeats.
    """
    return {
        "equipments": await _option_items(
            session, equipments, field="equipments", lookup=catalog_repo.equipment_names
        ),
        "services": await _option_items(
            session, services, field="services", lookup=catalog_repo.service_names
        ),
        "purposes": await _dictionary_values(
            session, purposes, field="purposes", lookup=catalog_repo.purpose_names
        ),
        "regions": await _dictionary_values(
            session, regions, field="regions", lookup=catalog_repo.region_names
        ),
    }


# ----------------------------------------------------------------------- audit diffs

def _plain(value: Any) -> Any:
    """History is JSON: money and ids become exact strings."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def vehicle_changes(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    fields: Iterable[str] = LOGGED_FIELDS,
) -> Record:
    """Flat ``{"vehicle.<id>.<field>": {before, after}}`` for the fields that changed."""
    changes: Record = {}
    for name in fields:
        old, new = _plain(before.get(name)), _plain(after.get(name))
        if old != new:
            changes[f"vehicle.{after['id']}.{name}"] = {"before": old, "after": new}
    return changes


def added_changes(vehicle: Mapping[str, Any]) -> Record:
    """A new position as audit changes: identity and price, nothing before."""
    changes: Record = {
        f"vehicle.{vehicle['id']}.item_status": {"before": None, "after": vehicle["item_status"]}
    }
    for name in _ADDED_FIELDS:
        value = _plain(vehicle.get(name))
        if value is not None:
            changes[f"vehicle.{vehicle['id']}.{name}"] = {"before": None, "after": value}
    return changes


def removed_changes(vehicle: Mapping[str, Any], status: str) -> Record:
    """A position that left the deal (``removed`` or ``replaced``), with its last VIN."""
    return {
        f"vehicle.{vehicle['id']}.item_status": {"before": vehicle["item_status"], "after": status},
        f"vehicle.{vehicle['id']}.vin": {"before": vehicle["vin"], "after": None},
    }
