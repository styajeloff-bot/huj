"""Export vehicles in scope as bytes (xlsx/csv)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import InvalidExportFormatError
from infrastructure.repositories import distributor_repository as repo
from infrastructure.services.excel_io import write_workbook

_EXPORT_HEADERS: tuple[str, ...] = (
    "VIN",
    "Марка",
    "Модель",
    "Год",
    "Цвет",
    "Базовая цена",
    "Специальная цена",
    "Цена со скидкой",
    "Статус",
    "Дата добавления",
)


@dataclass
class ExportDistributorVehiclesQuery:
    actor_id: UUID
    actor_role: str
    export_format: str = "xlsx"  # xlsx | csv
    status: str | None = None
    search: str | None = None


def _build_rows(items: list[dict[str, Any]]) -> list[list[Any]]:
    result: list[list[Any]] = []
    for v in items:
        created = v.get("created_at")
        created_str = (
            created.strftime("%Y-%m-%d")
            if isinstance(created, datetime)
            else ""
        )
        base = v.get("base_price")
        discount = v.get("discount_price")
        special = v.get("special_price")
        result.append(
            [
                v.get("vin") or "",
                v.get("mark_name") or "",
                v.get("model_name") or "",
                v.get("year") or "",
                v.get("color") or "",
                str(base) if base is not None else "",
                str(special) if special is not None else "",
                str(discount) if discount is not None else "",
                v.get("status") or "",
                created_str,
            ]
        )
    return result


async def handle_export_distributor_vehicles(
    query: ExportDistributorVehiclesQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role
    )
    export_format = query.export_format.lower()
    if export_format not in {"xlsx", "csv"}:
        raise InvalidExportFormatError(query.export_format)

    items = await repo.list_vehicles_for_export(
        session,
        dealer_filter=scope.dealer_filter(),
        status=query.status,
        search=query.search,
    )
    rows = _build_rows(items)

    if export_format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(_EXPORT_HEADERS)
        writer.writerows(rows)
        content = buf.getvalue().encode("utf-8-sig")
        mime_type = "text/csv; charset=utf-8"
        filename = (
            f"vehicles_export_{datetime.now(UTC).strftime('%Y-%m-%d')}.csv"
        )
    else:
        content = await write_workbook(
            list(_EXPORT_HEADERS), rows, sheet_name="Автомобили"
        )
        mime_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        filename = (
            f"vehicles_export_{datetime.now(UTC).strftime('%Y-%m-%d')}.xlsx"
        )

    return {
        "content": content,
        "filename": filename,
        "mime_type": mime_type,
        "row_count": len(rows),
    }
