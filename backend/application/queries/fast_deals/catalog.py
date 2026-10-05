"""Read-only queries behind the fast deal forms: VIN lookup, stock table, directories.

The scope follows the actor. A dealer searches only the stock of its own warehouses
(the physical owner: warehouse owner, else seller; the right to see a foreign
warehouse does not make its stock "own"). A leasing company searches every published
listing. Nothing is hidden silently: a unit that cannot become a position is
returned together with the reason. Money leaves as exact decimal strings.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from domain.fast_deals.catalog_rules import ensure_selectable, resolve_unit_vin
from domain.fast_deals.errors import (
    FastDealAccessDeniedError,
    FastDealValidationError,
)
from domain.fast_deals.money import wire
from domain.fast_deals.values import VISIBLE_ROLES, Role
from domain.fast_deals.vin import normalize_vin
from infrastructure.repositories import fast_deal_lookup_repository as repo

Record = dict[str, Any]

_NOT_FOUND_OWN_STOCK = "Не найдено на ваших складах"
_NOT_FOUND_PUBLISHED = "Не найдено среди опубликованных объявлений"
_CLAIMED = "Единица зарезервирована или продана"
_NO_OWNER = "У объявления не определён владелец склада или продавец"

# The catalog stores up to 32 symbols and is not narrowed to the 17-symbol rule: the
# lookup finds such a unit and explains why it cannot be registered.
_LOOKUP_VIN = re.compile(r"^[0-9A-Z-]{1,32}$")
_MAX_VIN_FILTER = 32
_MAX_TEXT = 100
_MAX_PAGE_SIZE = 100
_DEFAULT_LIMIT = 500
_MAX_LIMIT = 1000

# Similar models: ranked in Python over a bounded candidate set.
_SIMILAR_DEFAULT = 10
_SIMILAR_MAX = 50
_CANDIDATE_CAP = 1000
_MIN_SIMILARITY = 0.6
_MIN_MATCH_LENGTH = 3
_MAX_FRAGMENT_WORDS = 5
# Cyrillic letters that look like Latin ones: "КС-45717" is typed with either alphabet.
_TO_LATIN = str.maketrans("авеёкмнорстух", "abeekmhopctyx")
_TO_CYRILLIC = str.maketrans("abekmhopctyx", "авекмнорстух")
_WORD = re.compile(r"[0-9a-zа-яё]+")


# --------------------------------------------------------------------------- scope

@dataclass(frozen=True)
class _StockScope:
    own_stock_of: UUID | None  # a dealer's own warehouses; None = all published listings
    not_found: str


def _stock_scope(actor: Actor) -> _StockScope:
    if actor.company_id is None:
        raise FastDealAccessDeniedError("Не выбрана компания")
    if actor.role == Role.DEALER:
        return _StockScope(actor.company_id, _NOT_FOUND_OWN_STOCK)
    if actor.role == Role.LEASING_COMPANY:
        return _StockScope(None, _NOT_FOUND_PUBLISHED)
    raise FastDealAccessDeniedError(
        "Подбор техники доступен дилеру и лизинговой компании"
    )


def _require_roles(actor: Actor, *roles: Role) -> None:
    if actor.role not in roles:
        raise FastDealAccessDeniedError("Справочник недоступен для вашей роли")


# ----------------------------------------------------------------------- parameters

def _text(params: Mapping[str, Any], key: str = "q") -> str | None:
    value = params.get(key)
    if value is None:
        return None
    text = str(value).strip()
    if len(text) > _MAX_TEXT:
        raise FastDealValidationError("Слишком длинный поисковый запрос", field=key)
    return text or None


def _uuid(params: Mapping[str, Any], key: str) -> UUID | None:
    value = params.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise FastDealValidationError("Некорректный идентификатор", field=key) from exc


def _limit(
    params: Mapping[str, Any], *, default: int = _DEFAULT_LIMIT, maximum: int = _MAX_LIMIT
) -> int:
    value = params.get("limit")
    if value is None or value == "":
        return default
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise FastDealValidationError("Некорректный размер выборки", field="limit") from exc
    if not 1 <= limit <= maximum:
        raise FastDealValidationError(
            f"Размер выборки должен быть от 1 до {maximum}", field="limit"
        )
    return limit


def _lookup_vin(value: str | None) -> str:
    vin = normalize_vin(value)
    if not vin:
        raise FastDealValidationError("Укажите VIN", field="vin")
    if not _LOOKUP_VIN.fullmatch(vin):
        raise FastDealValidationError(
            "VIN может содержать до 32 символов: латинские буквы, цифры и дефис",
            field="vin",
        )
    return vin


# ------------------------------------------------------------------------- units

def _requires_manual_vin(row: Record) -> bool:
    """A listing without VIN or «под заказ»: the user types the VIN, nothing is reserved."""
    return bool(row["no_vin"] or not row["vin"] or row["sale_status"] == "on_order")


def _unavailable_reason(row: Record) -> str | None:
    """Why the unit cannot become a position now; ``None`` when it can."""
    claimed = bool(row["claimed"])
    try:
        ensure_selectable(row)
        if not _requires_manual_vin(row):
            resolve_unit_vin(row, None)
    except FastDealValidationError as exc:
        if claimed and row["publication_status"] == "published":
            return _CLAIMED
        return str(exc)
    if claimed:
        return _CLAIMED
    if row["owner_company_id"] is None:
        return _NO_OWNER
    return None


def _present_unit(row: Record) -> Record:
    on_request = bool(row["price_on_request"])
    fixed = row["special_price"] if row["special_price"] is not None else row["price"]
    reason = _unavailable_reason(row)
    return {
        "id": row["id"],
        "code": row["code"],
        "vin": normalize_vin(row["vin"]) or None,
        "requires_manual_vin": _requires_manual_vin(row),
        "condition": row["condition"],
        "manufacture_year": row["manufacture_year"],
        "mileage_km": row["mileage_km"],
        "engine_hours": row["engine_hours"],
        "publication_status": row["publication_status"],
        "sale_status": row["sale_status"],
        # A request-priced listing has no price of its own: the user states it, and
        # ``price_from`` is only an indication, never an agreed price.
        "price_on_request": on_request,
        "base_price": None if on_request else wire(fixed),
        "price": None if on_request else wire(row["price"]),
        "special_price": None if on_request else wire(row["special_price"]),
        "price_from": wire(row["price_from"]) if on_request else None,
        "mark_id": row["mark_id"],
        "mark_name": row["mark_name"],
        "model_id": row["model_id"],
        "model_name": row["model_name"],
        "modification_id": row["modification_id"],
        "modification_name": row["modification_name"],
        "trim_id": row["trim_id"],
        "trim_name": row["trim_name"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "body_color_id": row["body_color_id"],
        "body_color_name": row["body_color_name"],
        "warehouse_id": row["warehouse_id"],
        "warehouse_name": row["warehouse_name"],
        "warehouse_city": row["warehouse_city"],
        "owner_company_id": row["owner_company_id"],
        "owner_company_name": row["owner_company_name"],
        "reserved": bool(row["claimed"]),
        "selectable": reason is None,
        "reason": reason,
    }


async def handle_vin_lookup(actor: Actor, vin: str, session: AsyncSession) -> dict[str, Any]:
    """``{found, product, reserved, reason}`` for one VIN inside the actor's stock.

    ``reserved`` is true when anything holds the unit: a reserved/sold status, an
    active allocation of any source, or a purchase that is not cancelled. A found
    unit that cannot be registered carries the explanation in ``reason``; a missing
    one is reported with the scope-specific message.
    """
    scope = _stock_scope(actor)
    normalized = _lookup_vin(vin)
    row: Record | None = await repo.find_unit_by_vin(
        session, vin=normalized, own_stock_of=scope.own_stock_of
    )
    if row is None:
        return {"found": False, "product": None, "reserved": False, "reason": scope.not_found}
    product = _present_unit(row)
    return {
        "found": True,
        "product": product,
        "reserved": product["reserved"],
        "reason": product["reason"],
    }


async def handle_vehicle_candidates(
    actor: Actor, filters: dict[str, Any], page: int, page_size: int, session: AsyncSession
) -> dict[str, Any]:
    """The stock table for selecting units, filtered by VIN, warehouse, mark, model.

    A dealer sees its own stock, a leasing company every published listing. Reserved,
    sold and (for a dealer) unpublished units stay in the table with ``selectable``
    false and a ``reason``; only archived listings of a dealer are outside the stock.
    """
    scope = _stock_scope(actor)
    if page < 1:
        raise FastDealValidationError("Номер страницы должен быть не меньше 1", field="page")
    if not 1 <= page_size <= _MAX_PAGE_SIZE:
        raise FastDealValidationError(
            f"Размер страницы должен быть от 1 до {_MAX_PAGE_SIZE}", field="page_size"
        )
    vin = normalize_vin(filters.get("vin")) or None
    if vin is not None and len(vin) > _MAX_VIN_FILTER:
        raise FastDealValidationError("VIN слишком длинный", field="vin")
    rows: list[Record]
    total: int
    rows, total = await repo.list_units(
        session,
        own_stock_of=scope.own_stock_of,
        vin=vin,
        warehouse_id=_uuid(filters, "warehouse_id"),
        mark_id=_uuid(filters, "mark_id"),
        model_id=_uuid(filters, "model_id"),
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {
        "items": [_present_unit(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# --------------------------------------------------------------------- similar models

def _fold(text: str) -> str:
    """Lower case, look-alike Cyrillic letters as Latin, letters and digits only."""
    return "".join(ch for ch in text.lower().translate(_TO_LATIN) if ch.isalnum())


def _similarity(typed: str, name: str) -> float:
    left, right = _fold(typed), _fold(name)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= _MIN_MATCH_LENGTH and shorter in longer:
        return 0.85 + 0.15 * len(shorter) / len(longer)
    return SequenceMatcher(None, left, right).ratio()


def _fragments(text: str) -> list[str]:
    """Substrings to look for in model names, in both look-alike alphabets."""
    words = _WORD.findall(text.lower())
    significant = [
        word
        for word in words
        if len(word) >= _MIN_MATCH_LENGTH or any(ch.isdigit() for ch in word)
    ] or words
    fragments: list[str] = []
    for word in significant[:_MAX_FRAGMENT_WORDS]:
        for variant in (word, word.translate(_TO_LATIN), word.translate(_TO_CYRILLIC)):
            if variant not in fragments:
                fragments.append(variant)
    return fragments


async def _similar_models(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    """Catalog models whose name resembles the typed one (``q``), best first.

    Within ``mark_id`` every model of the mark is compared; without it the search
    spans all marks. An item carries ``mark_id``, ``id`` (the model) and
    ``category_id``: choosing it restores the directory chain.
    """
    typed = _text(params)
    limit = _limit(params, default=_SIMILAR_DEFAULT, maximum=_SIMILAR_MAX)
    if typed is None:
        return []
    candidates: list[Record] = await repo.list_model_candidates(
        session,
        mark_id=_uuid(params, "mark_id"),
        fragments=_fragments(typed),
        limit=_CANDIDATE_CAP,
    )
    ranked: list[Record] = []
    for row in candidates:
        score = _similarity(typed, row["name"])
        if score >= _MIN_SIMILARITY:
            ranked.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "mark_id": row["mark_id"],
                    "mark_name": row["mark_name"],
                    "category_id": row["category_id"],
                    "category_name": row["category_name"],
                    "score": round(score * 100),
                }
            )
    ranked.sort(key=lambda item: (-item["score"], item["name"]))
    return ranked[:limit]


# ------------------------------------------------------------------------- lookups

def _coded(rows: list[Record]) -> list[Record]:
    """Code-keyed dictionaries: the code is the identifier (not a UUID)."""
    return [{**row, "id": row["code"]} for row in rows]


async def _leasing_companies(
    actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    _require_roles(actor, Role.DEALER, Role.PLATFORM)
    items: list[Record] = await repo.list_leasing_companies(
        session, q=_text(params), limit=_limit(params)
    )
    return items


async def _dealers(
    actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    _require_roles(actor, Role.LEASING_COMPANY, Role.DISTRIBUTOR, Role.PLATFORM)
    distributor_id: UUID | None = None
    if actor.role == Role.DISTRIBUTOR:
        if actor.company_id is None:
            raise FastDealAccessDeniedError("Не выбрана компания")
        distributor_id = actor.company_id
    items: list[Record] = await repo.list_dealers(
        session,
        q=_text(params),
        limit=_limit(params),
        distributor_company_id=distributor_id,
    )
    return items


async def _warehouses(
    actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    scope = _stock_scope(actor)
    items: list[Record] = await repo.list_warehouses(
        session, own_stock_of=scope.own_stock_of, q=_text(params), limit=_limit(params)
    )
    return items


async def _categories(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    items: list[Record] = await repo.list_categories(
        session, q=_text(params), limit=_limit(params)
    )
    return items


async def _marks(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    items: list[Record] = await repo.list_marks(
        session, q=_text(params), category_id=_uuid(params, "category_id"), limit=_limit(params)
    )
    return items


async def _models(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    items: list[Record] = await repo.list_models(
        session,
        q=_text(params),
        mark_id=_uuid(params, "mark_id"),
        category_id=_uuid(params, "category_id"),
        limit=_limit(params),
    )
    return items


async def _modifications(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    items: list[Record] = await repo.list_modifications(
        session,
        q=_text(params),
        model_id=_uuid(params, "model_id"),
        category_id=_uuid(params, "category_id"),
        limit=_limit(params),
    )
    return items


async def _trims(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    items: list[Record] = await repo.list_trims(
        session,
        q=_text(params),
        modification_id=_uuid(params, "modification_id"),
        limit=_limit(params),
    )
    return items


async def _colors(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    applicability = _text(params, "applicability") or "body"
    if applicability not in ("body", "interior"):
        raise FastDealValidationError("Неизвестное назначение цвета", field="applicability")
    items: list[Record] = await repo.list_colors(
        session, q=_text(params), applicability=applicability, limit=_limit(params)
    )
    return items


async def _equipments(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    rows: list[Record] = await repo.list_equipments(
        session, q=_text(params), limit=_limit(params)
    )
    return _coded(rows)


async def _services(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    rows: list[Record] = await repo.list_services(
        session, q=_text(params), limit=_limit(params)
    )
    return _coded(rows)


async def _purposes(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    rows: list[Record] = await repo.list_purposes(
        session, q=_text(params), limit=_limit(params)
    )
    return _coded(rows)


async def _regions(
    _actor: Actor, params: Mapping[str, Any], session: AsyncSession
) -> list[Record]:
    rows: list[Record] = await repo.list_regions(
        session, q=_text(params), limit=_limit(params)
    )
    return _coded(rows)


_Lookup = Callable[[Actor, Mapping[str, Any], AsyncSession], Awaitable[list[Record]]]

_LOOKUPS: dict[str, _Lookup] = {
    "leasing-companies": _leasing_companies,
    "dealers": _dealers,
    "warehouses": _warehouses,
    "categories": _categories,
    "marks": _marks,
    "models": _models,
    "modifications": _modifications,
    "trims": _trims,
    "colors": _colors,
    "equipments": _equipments,
    "services": _services,
    "purposes": _purposes,
    "regions": _regions,
    "similar-models": _similar_models,
}


async def handle_lookup(
    actor: Actor, kind: str, params: dict[str, Any], session: AsyncSession
) -> dict[str, Any]:
    """``{"items": [...]}`` of one directory.

    Directories (categories, marks, models, modifications, trims, colors, equipments,
    services, purposes, regions, similar-models) are open to every role of the
    section. Company lists are role-scoped: ``leasing-companies`` for a dealer,
    ``dealers`` for a leasing company (a distributor: its own linked dealers).
    ``warehouses`` feeds the stock filter of a dealer or a leasing company.
    Equipment, service, purpose and region items use their code as ``id`` and ``code``.
    """
    if actor.role not in VISIBLE_ROLES:
        raise FastDealAccessDeniedError("Раздел недоступен для вашей роли")
    lookup = _LOOKUPS.get(kind)
    if lookup is None:
        raise FastDealValidationError("Неизвестный справочник", field="kind")
    return {"items": await lookup(actor, params, session)}
