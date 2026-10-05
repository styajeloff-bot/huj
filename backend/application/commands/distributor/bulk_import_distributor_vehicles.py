"""Bulk import vehicles from an Excel file uploaded by a distributor.

Workflow:
1. Parse the .xlsx via ``infrastructure.services.excel_io.read_workbook``.
2. Walk every row and validate it row-by-row using the ``Vehicle`` domain
   entity. Bad rows are collected in ``errors`` with their row number and a
   reason; the rest of the file is still processed (partial-success).
3. Resolve ``mark`` / ``model`` / ``generation`` text to FK ids — unknown
   values fail the row.
4. Reject duplicate VINs — both within the file and against the existing
   inventory (a dup against any other row that the importer just inserted
   in this same file is also blocked).
5. Insert the surviving rows in a single batch via the repository.

Synchronous code path. The brief allows up to ~5000 rows; bigger files
must raise ``BulkImportValidationError`` (HTTP 413).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.entities.vehicle import Vehicle
from domain.errors import (
    BulkImportValidationError,
    DomainError,
    ExcelFormatError,
)
from infrastructure.repositories import distributor_repository as repo
from infrastructure.services.excel_io import read_workbook

MAX_ROWS_SYNC: int = 5000
MAX_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MiB

# Excel header → vehicle attribute mapping. Cyrillic + ascii aliases are
# both accepted (matches Express). The first matching key wins.
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "vin": ("VIN", "vin"),
    "mark_name": ("Марка", "mark", "mark_name"),
    "model_name": ("Модель", "model", "model_name"),
    "generation_name": ("Поколение", "generation"),
    "year": ("Год", "year"),
    "color": ("Цвет", "color"),
    "color_inter": ("Цвет салона", "color_inter"),
    "base_price": ("Базовая цена", "base_price", "price"),
    "special_price": ("Специальная цена", "special_price"),
    "discount_price": ("Цена со скидкой", "discount_price"),
    "status": ("Статус", "status"),
}

# Russian status names → canonical status enum values.
_STATUS_TRANSLATIONS: dict[str, str] = {
    "В наличии": "available",
    "Доступен": "available",
    "Зарезервировано": "reserved",
    "Зарезервирован": "reserved",
    "Продано": "sold",
    "Продан": "sold",
}


@dataclass
class BulkImportRowError:
    """Per-row import failure (row number is 1-indexed, header excluded)."""

    row: int
    reason: str
    vin: str | None = None


@dataclass
class BulkImportDistributorVehiclesCommand:
    actor_id: UUID
    actor_role: str
    file_bytes: bytes
    company_id: UUID | None = None
    filename: str | None = None
    sheet_name: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _resolve_field(
    row: dict[str, Any], aliases: tuple[str, ...]
) -> Any:
    for alias in aliases:
        if alias in row:
            value = row[alias]
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return value
    return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    return str(value).strip() or None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _normalize_status(raw: Any) -> str | None:
    s = _to_str(raw)
    if s is None:
        return None
    if s in _STATUS_TRANSLATIONS:
        return _STATUS_TRANSLATIONS[s]
    s_lower = s.lower()
    if s_lower in {"available", "reserved", "sold"}:
        return s_lower
    return s  # surface to ensure_valid() so it raises a domain error


async def _build_vehicle_from_row(
    session: AsyncSession,
    row: dict[str, Any],
    *,
    dealer_id: UUID | None,
) -> tuple[dict[str, Any], str | None]:
    """Resolve a parsed xlsx row into a vehicle insert payload + the VIN.

    Raises ``DomainError`` (typically ``InvalidVehicleError``,
    ``MarkNotFoundError`` or ``ModelNotFoundError``) on validation failure.
    """
    from domain.errors import (
        InvalidVehicleError,
        MarkNotFoundError,
        ModelNotFoundError,
    )

    vin = _to_str(_resolve_field(row, _HEADER_ALIASES["vin"]))
    if not vin:
        raise InvalidVehicleError("VIN обязателен")

    mark_name = _to_str(_resolve_field(row, _HEADER_ALIASES["mark_name"]))
    model_name = _to_str(_resolve_field(row, _HEADER_ALIASES["model_name"]))
    if not mark_name:
        raise InvalidVehicleError("Марка обязательна")
    if not model_name:
        raise InvalidVehicleError("Модель обязательна")

    mark_id = await repo.find_mark_id_by_name(session, mark_name)
    if not mark_id:
        raise MarkNotFoundError(mark_name)
    model_id = await repo.find_model_id_by_name(
        session, name=model_name, mark_id=mark_id
    )
    if not model_id:
        raise ModelNotFoundError(model_name)

    generation_name = _to_str(
        _resolve_field(row, _HEADER_ALIASES["generation_name"])
    )
    generation_id: str | None = None
    if generation_name:
        generation_id = await repo.find_generation_id_by_name(
            session, name=generation_name, model_id=model_id
        )

    year = _to_int(_resolve_field(row, _HEADER_ALIASES["year"]))
    color = _to_str(_resolve_field(row, _HEADER_ALIASES["color"]))
    color_inter = _to_str(
        _resolve_field(row, _HEADER_ALIASES["color_inter"])
    )
    base_price = _to_decimal(
        _resolve_field(row, _HEADER_ALIASES["base_price"])
    )
    discount_price = _to_decimal(
        _resolve_field(row, _HEADER_ALIASES["discount_price"])
    )
    special_price = _to_decimal(
        _resolve_field(row, _HEADER_ALIASES["special_price"])
    )
    status = _normalize_status(_resolve_field(row, _HEADER_ALIASES["status"]))

    entity = Vehicle(
        vehicle_id=None,
        vin=vin,
        dealer_id=dealer_id,
        mark_id=mark_id,
        model_id=model_id,
        generation_id=generation_id,
        year=year,
        base_price=base_price,
        special_price=special_price,
        discount_price=discount_price,
        color=color,
        color_inter=color_inter,
        status=status or "available",
        is_available=True,
    )
    entity.ensure_valid()

    payload = {
        "vin": entity.vin,
        "dealer_id": entity.dealer_id,
        "mark_id": entity.mark_id,
        "model_id": entity.model_id,
        "generation_id": entity.generation_id,
        "year": entity.year,
        "base_price": entity.base_price,
        "special_price": entity.special_price,
        "discount_price": entity.discount_price,
        "color": entity.color,
        "color_inter": entity.color_inter,
        "status": entity.status,
        "is_available": entity.is_available,
    }
    return payload, entity.vin


async def handle_bulk_import_distributor_vehicles(
    cmd: BulkImportDistributorVehiclesCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )

    if not cmd.file_bytes:
        raise ExcelFormatError("Файл не загружен")
    if len(cmd.file_bytes) > MAX_FILE_BYTES:
        raise BulkImportValidationError(
            "Размер файла превышает 10 МБ — используйте фоновый импорт"
        )

    try:
        _, rows = await read_workbook(
            cmd.file_bytes, sheet_name=cmd.sheet_name, header=True
        )
    except Exception as exc:
        raise ExcelFormatError(
            f"Не удалось прочитать Excel-файл: {exc}"
        ) from exc

    if not rows:
        raise ExcelFormatError("Файл не содержит данных")

    if len(rows) > MAX_ROWS_SYNC:
        raise BulkImportValidationError(
            f"В файле {len(rows)} строк — больше {MAX_ROWS_SYNC} "
            "поддерживаются только в фоновом режиме"
        )

    # The "owner" dealer_id for newly-imported rows: distributor →
    # themselves; employee → unset (NULL) unless the file carries an
    # explicit dealer_id, which we currently do not parse.
    dealer_id = scope.coerce_dealer_id_for_write(None)

    errors: list[dict[str, Any]] = []
    seen_vins: set[str] = set()
    payloads: list[dict[str, Any]] = []

    # Pre-fetch existing VINs for the candidate set in a single round-trip.
    candidate_vins: list[str] = []
    for row in rows:
        v = _to_str(_resolve_field(row, _HEADER_ALIASES["vin"]))
        if v:
            candidate_vins.append(v)
    existing = await repo.existing_vins(session, candidate_vins)

    for index, raw_row in enumerate(rows, start=2):
        # +2: row 1 is the header, openpyxl rows are 1-indexed.
        try:
            payload, vin = await _build_vehicle_from_row(
                session, raw_row, dealer_id=dealer_id
            )
        except DomainError as exc:
            errors.append(
                {
                    "row": index,
                    "reason": str(exc),
                    "vin": _to_str(
                        _resolve_field(raw_row, _HEADER_ALIASES["vin"])
                    ),
                }
            )
            continue

        if vin is None:
            errors.append({"row": index, "reason": "VIN обязателен", "vin": None})
            continue
        if vin in seen_vins:
            errors.append(
                {
                    "row": index,
                    "reason": "Дублирующийся VIN внутри файла",
                    "vin": vin,
                }
            )
            continue
        if vin in existing:
            errors.append(
                {
                    "row": index,
                    "reason": "VIN уже существует в каталоге",
                    "vin": vin,
                }
            )
            continue

        seen_vins.add(vin)
        payloads.append(payload)

    imported = await repo.bulk_create_vehicles(session, payloads=payloads)
    return {
        "imported": imported,
        "total_rows": len(rows),
        "errors": errors,
    }
