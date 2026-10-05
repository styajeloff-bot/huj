"""Per-kind CSV row handlers for the async data-import pipeline.

The Taskiq ``data_import.process_rows_batch`` task calls :func:`process_batch`
with a batch of parsed CSV rows for one ``kind``. Each handler parses the row,
upserts into PostgreSQL via :mod:`infrastructure.repositories.bulk_import_repository`
(source of truth) and collects the DWH snapshot payloads to publish to Kafka —
the event-worker then persists them to ClickHouse ``dwh_*`` tables, which is
what the distributor analytics dashboards read.

Layering: application layer — parses + orchestrates only. All ORM/DB-driver
access is delegated to the repository.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.messaging.topics import (
    EXCHANGE_BID_SNAPSHOT,
    EXCHANGE_REQUEST_SNAPSHOT,
    VEHICLE_SNAPSHOT,
)
from infrastructure.repositories import bulk_import_repository as repo
from infrastructure.repositories import warehouse_repository as warehouse_repo

logger = logging.getLogger("carcraft-backend")

CSV_DELIMITER = ";"

# Kinds processed natively by this module (fresh upsert logic). Applications are
# dispatched to existing application-layer helpers from the taskiq task itself.
NATIVE_KINDS = frozenset(
    {
        "vehicles",
        "warehouses",
        "exchange_requests",
        "exchange_bids",
        "distributor_dealer_links",
    }
)


@dataclass
class BatchResult:
    """Outcome of upserting one batch of rows."""

    processed: int = 0
    errors: list[str] = field(default_factory=list)
    # topic -> list of DWH payloads to publish after the DB commit
    dwh_payloads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def add_payload(self, topic: str, payload: dict[str, Any]) -> None:
        self.dwh_payloads.setdefault(topic, []).append(payload)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_csv(data: bytes) -> list[dict[str, str]]:
    """Decode CSV bytes (utf-8-sig) into a list of row dicts."""
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=CSV_DELIMITER)
    return list(reader)


def _uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value.strip())
    except (ValueError, AttributeError):
        return None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    v = value.strip().replace(" ", "")
    if not v:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    v = value.strip().replace(" ", "").replace(",", ".")
    if not v:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        return None


def _bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in ("", "0", "false", "no", "нет")


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _str(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v or None


# ---------------------------------------------------------------------------
# Per-kind upserts
# ---------------------------------------------------------------------------

async def _upsert_vehicle(
    session: AsyncSession, row: dict[str, str], res: BatchResult
) -> None:
    vehicle_id = _uuid(row.get("id"))
    dealer_id = _uuid(row.get("dealer_id"))
    if vehicle_id is None:
        res.errors.append("vehicle: пропущено обязательное поле id")
        return
    if dealer_id is None:
        res.errors.append(f"vehicle {vehicle_id}: пропущено обязательное поле dealer_id")
        return

    base_price = _decimal(row.get("base_price"))
    special_price = _decimal(row.get("special_price"))
    status = _str(row.get("status")) or "available"
    is_available = (
        _bool(row.get("is_available"))
        if row.get("is_available")
        else (status == "available")
    )
    created_at = _dt(row.get("created_at"))
    values: dict[str, Any] = {
        "id": vehicle_id,
        "vin": _str(row.get("vin")),
        "dealer_id": dealer_id,
        "mark_id": _str(row.get("mark_id")),
        "model_id": _str(row.get("model_id")),
        "year": _int(row.get("year")),
        "base_price": base_price,
        "special_price": special_price,
        "color": _str(row.get("color")),
        "status": status,
        "is_available": is_available,
    }
    if created_at is not None:
        values["created_at"] = created_at

    await repo.upsert_vehicle(session, values)

    # Vehicle belongs to a warehouse (warehouse → dealer). dealer_id above is the
    # warehouse's dealer (the seed derives it), kept on the fact row for the
    # distributor analytics scope; the physical link lives in vehicle_warehouses.
    warehouse_id = _uuid(row.get("warehouse_id"))
    if warehouse_id is not None:
        await repo.upsert_vehicle_warehouse(session, vehicle_id, warehouse_id)

    res.add_payload(
        VEHICLE_SNAPSHOT,
        {
            "vehicle_id": str(vehicle_id),
            "vin": values["vin"],
            "dealer_id": str(dealer_id),
            "mark_id": values["mark_id"],
            "model_id": values["model_id"],
            "year": values["year"],
            "base_price": str(base_price) if base_price is not None else None,
            "special_price": str(special_price) if special_price is not None else None,
            "color": values["color"],
            "status": status,
            "is_available": 1 if is_available else 0,
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": (
                created_at.isoformat() if created_at else datetime.now(UTC).isoformat()
            ),
            "_deleted": 0,
        },
    )
    res.processed += 1


def _city_name_from_address(address: str | None) -> str:
    """Best-effort city name: the address prefix before the first comma.

    The seed addresses read ``"<city>, складская площадка №N"``, so the leading
    segment is the city name (e.g. ``"Москва"``)."""
    text = _str(address)
    if not text:
        return "—"
    return text.split(",", 1)[0].strip() or "—"


async def _resolve_city_id(
    session: AsyncSession, row: dict[str, str]
) -> UUID | None:
    """Resolve the warehouse city id.

    Prefers an explicit ``city_id`` (UUID), *ensuring* the referenced city row
    exists first — a warehouse CSV may carry deterministic city ids for cities
    that were never seeded, which would otherwise violate the
    ``warehouses_city_id_fkey`` foreign key. The created city's name is taken
    from a ``city`` column when present, else derived from the address prefix.

    Without an explicit id, falls back to a ``city`` name column, resolving it
    case-insensitively against the ``cities`` table and creating the city when
    it is missing.
    """
    city_id = _uuid(row.get("city_id"))
    if city_id is not None:
        name = _str(row.get("city")) or _city_name_from_address(row.get("address"))
        await warehouse_repo.ensure_city(session, city_id, name)
        return city_id
    city_name = _str(row.get("city"))
    if city_name is None:
        return None
    resolved: UUID | None = await warehouse_repo.resolve_or_create_city_by_name(
        session, city_name
    )
    return resolved


async def _upsert_warehouse(
    session: AsyncSession, row: dict[str, str], res: BatchResult
) -> None:
    warehouse_id = _uuid(row.get("id"))
    if warehouse_id is None:
        res.errors.append("warehouse: пропущено обязательное поле id")
        return
    values: dict[str, Any] = {
        "id": warehouse_id,
        "address": _str(row.get("address")) or "—",
        "brand": _str(row.get("brand")) or "—",
        "city_id": await _resolve_city_id(session, row),
        "dealer_id": _uuid(row.get("dealer_id")),
        "company_id": _uuid(row.get("company_id")),
        "status": _str(row.get("status")) or "active",
    }
    await repo.upsert_warehouse(session, values)
    res.processed += 1


async def _upsert_exchange_request(
    session: AsyncSession, row: dict[str, str], res: BatchResult
) -> None:
    request_id = _uuid(row.get("id"))
    lc_user_id = _uuid(row.get("lc_user_id"))
    vehicle_id = _uuid(row.get("vehicle_id"))
    if request_id is None or lc_user_id is None or vehicle_id is None:
        res.errors.append("exchange_request: требуются поля id, lc_user_id, vehicle_id")
        return

    expiration = _date(row.get("expiration_date"))
    discount_value = _decimal(row.get("discount_value"))
    status = _str(row.get("status")) or "open"
    created_at = _dt(row.get("created_at"))
    quantity = _int(row.get("quantity")) or 1
    values: dict[str, Any] = {
        "id": request_id,
        "lc_user_id": lc_user_id,
        "vehicle_id": vehicle_id,
        "quantity": quantity,
        "expiration_at": datetime.combine(expiration, time(23, 59, 59), ZoneInfo("Europe/Moscow")) if expiration else None,
        "discount_type": _str(row.get("discount_type")),
        "discount_value": discount_value,
        "status": status,
    }
    if created_at is not None:
        values["created_at"] = created_at

    await repo.upsert_exchange_request(session, values)

    res.add_payload(
        EXCHANGE_REQUEST_SNAPSHOT,
        {
            "request_id": str(request_id),
            "lc_user_id": str(lc_user_id),
            "vehicle_id": str(vehicle_id),
            "quantity": quantity,
            # ClickHouse Date columns don't accept ISO strings via this pipeline;
            # the value is preserved in Postgres. (DWH coercion is a follow-up.)
            "expiration_date": None,
            "discount_type": values["discount_type"],
            "discount_value": str(discount_value) if discount_value is not None else None,
            "status": status,
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": (
                created_at.isoformat() if created_at else datetime.now(UTC).isoformat()
            ),
            "_deleted": 0,
        },
    )
    res.processed += 1


async def _upsert_exchange_bid(
    session: AsyncSession, row: dict[str, str], res: BatchResult
) -> None:
    bid_id = _uuid(row.get("id"))
    request_id = _uuid(row.get("request_id"))
    dealer_id = _uuid(row.get("dealer_id"))
    price = _decimal(row.get("price"))
    if bid_id is None or request_id is None or dealer_id is None or price is None:
        res.errors.append("exchange_bid: требуются поля id, request_id, dealer_id, price")
        return

    is_accepted = _bool(row.get("is_accepted"))
    quantity = _int(row.get("quantity")) or 1
    created_at = _dt(row.get("created_at"))
    values: dict[str, Any] = {
        "id": bid_id,
        "request_id": request_id,
        "dealer_id": dealer_id,
        "price": price,
        "is_accepted": is_accepted,
        "quantity": quantity,
        "kp_status": "none",  # NOT NULL column with no applied DB default
    }
    if created_at is not None:
        values["created_at"] = created_at

    await repo.upsert_exchange_bid(session, values)

    res.add_payload(
        EXCHANGE_BID_SNAPSHOT,
        {
            "bid_id": str(bid_id),
            "request_id": str(request_id),
            "dealer_id": str(dealer_id),
            "price": str(price),
            "is_accepted": 1 if is_accepted else 0,
            "quantity": quantity,
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": (
                created_at.isoformat() if created_at else datetime.now(UTC).isoformat()
            ),
            "_deleted": 0,
        },
    )
    res.processed += 1


async def _upsert_link(
    session: AsyncSession, row: dict[str, str], res: BatchResult
) -> None:
    distributor_id = _uuid(row.get("distributor_company_id"))
    dealer_id = _uuid(row.get("dealer_company_id"))
    if distributor_id is None or dealer_id is None:
        res.errors.append(
            "link: требуются поля distributor_company_id, dealer_company_id"
        )
        return
    await repo.upsert_distributor_dealer_link(
        session, distributor_company_id=distributor_id, dealer_company_id=dealer_id
    )
    res.processed += 1


_NATIVE_HANDLERS = {
    "vehicles": _upsert_vehicle,
    "warehouses": _upsert_warehouse,
    "exchange_requests": _upsert_exchange_request,
    "exchange_bids": _upsert_exchange_bid,
    "distributor_dealer_links": _upsert_link,
}


async def process_batch(
    session: AsyncSession, kind: str, rows: list[dict[str, str]]
) -> BatchResult:
    """Upsert a batch of native-kind rows; collect DWH payloads + errors."""
    handler = _NATIVE_HANDLERS.get(kind)
    if handler is None:
        raise ValueError(f"Unknown native import kind: {kind}")
    res = BatchResult()
    for row in rows:
        # Isolate each row in a SAVEPOINT: a failing row (e.g. an FK violation)
        # rolls back only itself, so the rest of the batch still commits instead
        # of the whole transaction aborting with InFailedSQLTransactionError.
        try:
            async with session.begin_nested():
                await handler(session, row, res)
        except Exception as exc:
            res.errors.append(f"{kind}: {exc}")
    return res
