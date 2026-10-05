"""Unit tests for distributor command handlers (B3).

These tests focus on the row-level validation logic of the bulk-import
command, which is the core of the new B3 surface and the most error-prone
piece. CRUD handlers are exercised end-to-end via the integration suite.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.distributor.bulk_import_distributor_vehicles import (
    BulkImportDistributorVehiclesCommand,
    handle_bulk_import_distributor_vehicles,
)
from domain.errors import (
    BulkImportValidationError,
    DistributorAccessDeniedError,
    ExcelFormatError,
)
from infrastructure.services.excel_io import write_workbook
from tests.legacy_compat import CarModel, Mark, Vehicle, VehicleCategory

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_catalog(session: AsyncSession) -> tuple[Mark, CarModel]:
    category_id = "B (Легковые автомобили)"
    if await session.get(VehicleCategory, category_id) is None:
        session.add(VehicleCategory(id=category_id, parent_id=None))
        await session.flush()
    mark = Mark(id="bmw_b3", name="BMW")
    session.add(mark)
    await session.flush()
    model = CarModel(id="x5_b3", name="X5", mark_id=mark.id, category=category_id)
    session.add(model)
    await session.flush()
    return mark, model


async def _build_xlsx(rows: list[dict[str, object]]) -> bytes:
    headers = [
        "VIN",
        "Марка",
        "Модель",
        "Год",
        "Цвет",
        "Базовая цена",
        "Цена со скидкой",
        "Статус",
    ]
    body = [
        [
            r.get("VIN", ""),
            r.get("Марка", ""),
            r.get("Модель", ""),
            r.get("Год", ""),
            r.get("Цвет", ""),
            r.get("Базовая цена", ""),
            r.get("Цена со скидкой", ""),
            r.get("Статус", ""),
        ]
        for r in rows
    ]
    return await write_workbook(headers, body, sheet_name="Vehicles")


def _employee_cmd(file_bytes: bytes) -> BulkImportDistributorVehiclesCommand:
    return BulkImportDistributorVehiclesCommand(
        actor_id=uuid4(),
        actor_role="carcraft_employee",
        file_bytes=file_bytes,
        filename="vehicles.xlsx",
    )


# ---------------------------------------------------------------------------
# Bulk-import: golden + partial success
# ---------------------------------------------------------------------------


async def test_bulk_import_happy_path(db_session: AsyncSession) -> None:
    await _seed_catalog(db_session)
    file_bytes = await _build_xlsx(
        [
            {
                "VIN": "BULKVIN0000001",
                "Марка": "BMW",
                "Модель": "X5",
                "Год": 2024,
                "Цвет": "Белый",
                "Базовая цена": 5000000,
                "Статус": "В наличии",
            },
            {
                "VIN": "BULKVIN0000002",
                "Марка": "BMW",
                "Модель": "X5",
                "Год": 2024,
                "Цвет": "Чёрный",
                "Базовая цена": 5500000,
                "Статус": "Доступен",
            },
        ]
    )
    result = await handle_bulk_import_distributor_vehicles(
        _employee_cmd(file_bytes), db_session
    )
    assert result["imported"] == 2
    assert result["total_rows"] == 2
    assert result["errors"] == []


async def test_bulk_import_collects_row_errors(
    db_session: AsyncSession,
) -> None:
    await _seed_catalog(db_session)
    file_bytes = await _build_xlsx(
        [
            {  # 1: ok
                "VIN": "GOODVIN000001",
                "Марка": "BMW",
                "Модель": "X5",
                "Базовая цена": 1000000,
            },
            {  # 2: missing VIN
                "Марка": "BMW",
                "Модель": "X5",
                "Базовая цена": 1000000,
            },
            {  # 3: unknown mark
                "VIN": "BADMARKVIN001",
                "Марка": "Tesla",
                "Модель": "Model S",
                "Базовая цена": 1000000,
            },
            {  # 4: ok
                "VIN": "GOODVIN000002",
                "Марка": "BMW",
                "Модель": "X5",
                "Базовая цена": 1100000,
            },
            {  # 5: duplicate of row 1's VIN inside file
                "VIN": "GOODVIN000001",
                "Марка": "BMW",
                "Модель": "X5",
                "Базовая цена": 1200000,
            },
        ]
    )
    result = await handle_bulk_import_distributor_vehicles(
        _employee_cmd(file_bytes), db_session
    )
    assert result["imported"] == 2
    assert result["total_rows"] == 5
    rows = {e["row"]: e for e in result["errors"]}
    assert set(rows.keys()) == {3, 4, 6}  # 1-indexed + header offset
    # Row 3 (file row "2") missing VIN.
    assert "VIN" in rows[3]["reason"]
    # Row 4 (file row "3") unknown mark.
    assert "BMW" not in rows[4]["reason"] or "Марка" in rows[4]["reason"] or "не найдена" in rows[4]["reason"]
    # Row 6 (file row "5") duplicate inside file.
    assert "Дублирующийся" in rows[6]["reason"]


async def test_bulk_import_blocks_existing_vin(
    db_session: AsyncSession,
) -> None:
    await _seed_catalog(db_session)
    db_session.add(Vehicle(vin="EXISTVIN00001", status="available"))
    await db_session.flush()

    file_bytes = await _build_xlsx(
        [
            {
                "VIN": "EXISTVIN00001",
                "Марка": "BMW",
                "Модель": "X5",
                "Базовая цена": 1000000,
            }
        ]
    )
    result = await handle_bulk_import_distributor_vehicles(
        _employee_cmd(file_bytes), db_session
    )
    assert result["imported"] == 0
    assert len(result["errors"]) == 1
    assert "уже существует" in result["errors"][0]["reason"]


async def test_bulk_import_rejects_empty_file() -> None:
    with pytest.raises(ExcelFormatError):
        await handle_bulk_import_distributor_vehicles(
            _employee_cmd(b""),
            session=None,  # type: ignore[arg-type]
        )


async def test_bulk_import_rejects_non_distributor_role() -> None:
    cmd = BulkImportDistributorVehiclesCommand(
        actor_id=uuid4(),
        actor_role="dealer",
        file_bytes=b"x",
    )
    with pytest.raises(DistributorAccessDeniedError):
        await handle_bulk_import_distributor_vehicles(
            cmd, session=None  # type: ignore[arg-type]
        )


async def test_bulk_import_rejects_oversize_file(
    db_session: AsyncSession,
) -> None:
    huge = b"\x00" * (10 * 1024 * 1024 + 1)  # 10MB + 1 byte
    with pytest.raises(BulkImportValidationError):
        await handle_bulk_import_distributor_vehicles(
            _employee_cmd(huge), db_session
        )
