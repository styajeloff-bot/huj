"""Dry-run of the xlsx import — returns parsed row sample without writes.

Mirrors Express' ``/vehicles/import-preview``: collect totals + a sample
of the first ~10 rows with basic hasVin flag so the UI can show a
confirmation before the actual import runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import (
    BulkImportValidationError,
    ExcelFormatError,
)
from infrastructure.services.excel_io import read_workbook

_MAX_FILE_BYTES: int = 10 * 1024 * 1024


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return str(row[key]).strip()
    return ""


def _parse_float(value: str) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


@dataclass
class PreviewImportDistributorVehiclesCommand:
    actor_id: UUID
    actor_role: str
    file_bytes: bytes
    filename: str | None = None
    sheet_name: str | None = None


async def handle_preview_import_distributor_vehicles(
    cmd: PreviewImportDistributorVehiclesCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id,
        actor_role=cmd.actor_role,
    )
    if not cmd.file_bytes:
        raise ExcelFormatError("Файл не загружен")
    if len(cmd.file_bytes) > _MAX_FILE_BYTES:
        raise BulkImportValidationError(
            "Размер файла превышает 10 МБ"
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

    warnings: list[str] = []
    rows_without_vin = 0
    unique_marks: set[str] = set()
    unique_models: set[str] = set()
    sample_data: list[dict[str, Any]] = []
    vehicles_count = 0

    for index, row in enumerate(rows):
        vin = _pick(row, "VIN", "vin")
        mark = _pick(row, "Марка", "mark")
        model = _pick(row, "Модель", "model")
        generation = _pick(row, "Поколение", "generation")
        price_raw = _pick(
            row, "Базовая цена", "base_price", "price"
        )
        special_price_raw = _pick(row, "Специальная цена", "special_price")
        price = _parse_float(price_raw)
        special_price = _parse_float(special_price_raw)

        if not vin:
            rows_without_vin += 1
        else:
            vehicles_count += 1
            if mark:
                unique_marks.add(mark)
            if model:
                unique_models.add(model)

        if index < 10:
            sample_data.append(
                {
                    "vin": vin or "(отсутствует)",
                    "mark": mark,
                    "model": model,
                    "generation": generation,
                    "price": price,
                    "special_price": special_price,
                    "has_vin": bool(vin),
                }
            )

    if rows_without_vin > 0:
        warnings.append(
            f"{rows_without_vin} строк без VIN будут пропущены"
        )

    return {
        "total_rows": len(rows),
        "vehicles_count": vehicles_count,
        "rows_without_vin": rows_without_vin,
        "unique_marks": len(unique_marks),
        "unique_models": len(unique_models),
        "sample_data": sample_data,
        "errors": [],
        "warnings": warnings,
    }
