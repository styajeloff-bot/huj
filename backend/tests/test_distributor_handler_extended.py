"""Unit tests for Phase 7a G3 distributor handlers.

Covers import preview (dry-run), profile/stats/analytics/filters queries,
model-orders handlers, application-vehicles commands, delete and export.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles import (
    AssignVinCommand,
    handle_assign_vin,
)
from application.commands.distributor.add_vehicle_to_application import (
    AddVehicleToApplicationCommand,
    handle_add_vehicle_to_application,
)
from application.commands.distributor.delete_distributor_vehicle import (
    DeleteDistributorVehicleCommand,
    handle_delete_distributor_vehicle,
)
from application.commands.distributor.preview_import_distributor_vehicles import (
    PreviewImportDistributorVehiclesCommand,
    handle_preview_import_distributor_vehicles,
)
from application.commands.distributor.remove_application_vehicle import (
    RemoveApplicationVehicleCommand,
    handle_remove_application_vehicle,
)
from application.commands.distributor.replace_application_vehicle import (
    ReplaceApplicationVehicleCommand,
    handle_replace_application_vehicle,
)
from application.queries.distributor.export_distributor_vehicles import (
    ExportDistributorVehiclesQuery,
    handle_export_distributor_vehicles,
)
from application.queries.distributor.get_distributor_analytics import (
    GetDistributorAnalyticsQuery,
    handle_get_distributor_analytics,
)
from application.queries.distributor.get_distributor_profile import (
    GetDistributorProfileQuery,
    handle_get_distributor_profile,
)
from application.queries.distributor.get_model_orders_stats import (
    GetModelOrdersStatsQuery,
    handle_get_model_orders_stats,
)
from application.queries.distributor.list_application_vehicles import (
    ListApplicationVehiclesQuery,
    handle_list_application_vehicles,
)
from application.queries.distributor.list_available_vehicles_for_app import (
    ListAvailableVehiclesForAppQuery,
    handle_list_available_vehicles_for_app,
)
from application.queries.distributor.list_distributor_applications_grouped import (
    ListDistributorApplicationsGroupedQuery,
    handle_list_distributor_applications_grouped,
)
from application.queries.distributor.list_distributor_dealers import (
    ListDistributorDealersQuery,
    handle_list_distributor_dealers,
)
from application.queries.distributor.list_distributor_support_programs import (
    ListDistributorSupportProgramsQuery,
    handle_list_distributor_support_programs,
)
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationVehicleNotFoundError,
    BulkImportValidationError,
    DistributorAccessDeniedError,
    ExcelFormatError,
    InvalidExportFormatError,
    UserNotFoundError,
    VehicleNotAvailableError,
    VehicleNotFoundError,
)
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
)
from infrastructure.models.companies import Company, Distributor, DistributorDealerLink
from infrastructure.models.support import SupportProgram
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.services.excel_io import write_workbook
from tests.legacy_compat import (
    CarModel,
    Mark,
    Vehicle,
    VehicleCategory,
    VehicleWarehouse,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


async def _seed_basic(
    db: AsyncSession,
) -> tuple[User, Mark, CarModel, Company, Distributor, Company]:
    company = Company(
        name="Distrib", company_type="distributor", inn="1111111111"
    )
    dealer_company = Company(
        name="Linked Dealer", company_type="dealer", inn="2222222222"
    )
    db.add_all([company, dealer_company])
    await db.flush()

    user = User(
        phone="+76660004500",
        email="d1@t.local",
        name="D1",
        role="distributor",
        is_active=True,
        company_id=company.id,
    )
    db.add(user)
    await db.flush()

    dist = Distributor(company_id=company.id, is_active=True)
    db.add(dist)
    await db.flush()

    db.add(
        DistributorDealerLink(
            distributor_company_id=company.id,
            dealer_company_id=dealer_company.id,
        )
    )
    await db.flush()

    mark = Mark(id="bmw_ext", name="BMW")
    db.add(mark)
    await db.flush()

    category_id = "B (Легковые автомобили)"
    if await db.get(VehicleCategory, category_id) is None:
        db.add(VehicleCategory(id=category_id, parent_id=None))
        await db.flush()

    model = CarModel(id="x5_ext", name="X5", mark_id=mark.id, category=category_id)
    db.add(model)
    await db.flush()

    return user, mark, model, company, dist, dealer_company


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def test_profile_returns_user_and_company(
    db_session: AsyncSession,
) -> None:
    user, _mark, _model, company, _dist, _dealer_company = await _seed_basic(db_session)
    result = await handle_get_distributor_profile(
        GetDistributorProfileQuery(actor_id=user.id, actor_role="distributor"),
        db_session,
    )
    profile = result["profile"]
    assert profile["user"]["id"] == user.id
    assert profile["company"]["id"] == company.id
    assert profile["distributor"] is not None


async def test_profile_rejects_non_distributor() -> None:
    with pytest.raises(DistributorAccessDeniedError):
        await handle_get_distributor_profile(
            GetDistributorProfileQuery(actor_id=uuid4(), actor_role="client"),
            session=None,  # type: ignore[arg-type]
        )


async def test_profile_raises_when_user_missing(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(UserNotFoundError):
        await handle_get_distributor_profile(
            GetDistributorProfileQuery(
                actor_id=uuid4(), actor_role="distributor"
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


async def test_analytics_returns_breakdown(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    db_session.add_all(
        [
            Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id),
            Vehicle(mark_id=mark.id, status="reserved", dealer_id=dealer_company.id),
        ]
    )
    await db_session.flush()

    result = await handle_get_distributor_analytics(
        GetDistributorAnalyticsQuery(
            actor_id=user.id, actor_role="distributor", company_id=company.id
        ),
        db_session,
    )
    analytics = result["analytics"]
    assert analytics["by_status"]["available"] == 1
    assert analytics["by_status"]["reserved"] == 1
    assert any(item["mark"] == "BMW" for item in analytics["by_mark"])


# ---------------------------------------------------------------------------
# Dealers
# ---------------------------------------------------------------------------


async def test_list_dealers_returns_linked_dealer_for_distributor(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    db_session.add(
        Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    )
    await db_session.flush()

    result = await handle_list_distributor_dealers(
        ListDistributorDealersQuery(
            actor_id=user.id, actor_role="distributor", company_id=company.id
        ),
        db_session,
    )
    ids = {d["id"] for d in result["dealers"]}
    assert dealer_company.id in ids


# ---------------------------------------------------------------------------
# Support programs
# ---------------------------------------------------------------------------


async def test_list_support_programs_filters_by_distributor_id(
    db_session: AsyncSession,
) -> None:
    user, _mark, _model, company, _dist, _dealer_company = await _seed_basic(db_session)

    db_session.add(
        SupportProgram(
            name="Prog own",
            distributor_id=company.id,
            support_type="vehicle_discount_dealer_invoice",
            support_params={},
        )
    )
    db_session.add(
        SupportProgram(
            name="Prog foreign",
            distributor_id=None,
            support_type="vehicle_discount_dealer_invoice",
            support_params={},
        )
    )
    await db_session.flush()

    result = await handle_list_distributor_support_programs(
        ListDistributorSupportProgramsQuery(
            actor_id=user.id,
            actor_role="distributor",
            actor_company_id=company.id,
        ),
        db_session,
    )
    names = {p["name"] for p in result["items"]}
    assert "Prog own" in names
    assert "Prog foreign" not in names


async def test_list_support_programs_empty_scope_uses_standard_list_envelope(
    db_session: AsyncSession,
) -> None:
    result = await handle_list_distributor_support_programs(
        ListDistributorSupportProgramsQuery(
            actor_id=uuid4(),
            actor_role="distributor",
            actor_company_id=None,
            page=2,
            limit=5,
        ),
        db_session,
    )

    assert result == {
        "items": [],
        "pagination": {"page": 2, "limit": 5, "total": 0, "pages": 0},
    }


# ---------------------------------------------------------------------------
# Applications grouped
# ---------------------------------------------------------------------------


async def test_applications_grouped_by_status(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    db_session.add(vehicle)
    await db_session.flush()
    warehouse = Warehouse(company_id=company.id, address="Application stock", brand="BMW")
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
    await db_session.flush()

    app1 = LeasingApplication(company_id=company.id, status="active")
    app2 = LeasingApplication(company_id=company.id, status="active")
    db_session.add_all([app1, app2])
    await db_session.flush()
    db_session.add_all(
        [
            ApplicationVehicle(
                application_id=app1.id, vehicle_id=vehicle.id, quantity=1
            ),
            ApplicationVehicle(
                application_id=app2.id, vehicle_id=vehicle.id, quantity=1
            ),
        ]
    )
    await db_session.flush()

    result = await handle_list_distributor_applications_grouped(
        ListDistributorApplicationsGroupedQuery(
            actor_id=user.id, actor_role="distributor", company_id=company.id
        ),
        db_session,
    )
    grouped = result["applications"]
    assert "active" in grouped
    assert "active" in grouped


# ---------------------------------------------------------------------------
# Application vehicles + add/remove/replace
# ---------------------------------------------------------------------------


async def test_add_vehicle_to_application_reserves(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(
        mark_id=mark.id,
        status="available",
        dealer_id=dealer_company.id,
        base_price=Decimal("100000"),
    )
    db_session.add(vehicle)
    await db_session.flush()

    app_row = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()

    result = await handle_add_vehicle_to_application(
        AddVehicleToApplicationCommand(
            actor_id=user.id,
            actor_role="distributor",
            application_id=app_row.id,
            vehicle_id=vehicle.id,
            quantity=1,
            company_id=company.id,
        ),
        db_session,
    )
    assert result["application_id"] == app_row.id
    await db_session.refresh(vehicle)
    assert vehicle.status == "reserved"


async def test_add_vehicle_rejects_unavailable(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(
        mark_id=mark.id, status="sold", dealer_id=dealer_company.id
    )
    db_session.add(vehicle)
    await db_session.flush()

    app_row = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()

    with pytest.raises(VehicleNotAvailableError):
        await handle_add_vehicle_to_application(
            AddVehicleToApplicationCommand(
                actor_id=user.id,
                actor_role="distributor",
                application_id=app_row.id,
                vehicle_id=vehicle.id,
                company_id=company.id,
            ),
            db_session,
        )


async def test_add_vehicle_unknown_application(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    db_session.add(vehicle)
    await db_session.flush()

    with pytest.raises(ApplicationNotFoundError):
        await handle_add_vehicle_to_application(
            AddVehicleToApplicationCommand(
                actor_id=user.id,
                actor_role="distributor",
                application_id=uuid.UUID("a0b1c2d3-e4f5-6789-0123-456789abcdef"),
                vehicle_id=vehicle.id,
                company_id=company.id,
            ),
            db_session,
        )


async def test_remove_application_vehicle_releases_vehicle(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(
        mark_id=mark.id, status="reserved", dealer_id=dealer_company.id
    )
    db_session.add(vehicle)
    await db_session.flush()
    app_row = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    av = ApplicationVehicle(
        application_id=app_row.id, vehicle_id=vehicle.id, quantity=1
    )
    db_session.add(av)
    await db_session.flush()

    await handle_remove_application_vehicle(
        RemoveApplicationVehicleCommand(
            actor_id=user.id,
            actor_role="distributor",
            application_vehicle_id=av.id,
            company_id=company.id,
        ),
        db_session,
    )
    await db_session.refresh(vehicle)
    assert vehicle.status == "available"


async def test_remove_application_vehicle_missing(
    db_session: AsyncSession,
) -> None:
    user, _mark, _model, company, _dist, _dealer_company = await _seed_basic(db_session)
    with pytest.raises(ApplicationVehicleNotFoundError):
        await handle_remove_application_vehicle(
            RemoveApplicationVehicleCommand(
                actor_id=user.id,
                actor_role="distributor",
                application_vehicle_id=uuid4(),
                company_id=company.id,
            ),
            db_session,
        )


async def test_replace_application_vehicle(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    old = Vehicle(mark_id=mark.id, status="reserved", dealer_id=dealer_company.id)
    new = Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    db_session.add_all([old, new])
    await db_session.flush()

    app_row = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    av = ApplicationVehicle(
        application_id=app_row.id, vehicle_id=old.id, quantity=1
    )
    db_session.add(av)
    await db_session.flush()

    await handle_replace_application_vehicle(
        ReplaceApplicationVehicleCommand(
            actor_id=user.id,
            actor_role="distributor",
            application_vehicle_id=av.id,
            new_vehicle_id=new.id,
            company_id=company.id,
        ),
        db_session,
    )
    await db_session.refresh(old)
    await db_session.refresh(new)
    assert old.status == "available"
    assert new.status == "reserved"


# ---------------------------------------------------------------------------
# Delete vehicle
# ---------------------------------------------------------------------------


async def test_delete_vehicle_in_scope(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(
        mark_id=mark.id, status="available", dealer_id=dealer_company.id
    )
    db_session.add(vehicle)
    await db_session.flush()
    vid = vehicle.id

    result = await handle_delete_distributor_vehicle(
        DeleteDistributorVehicleCommand(
            vehicle_id=vid, actor_id=user.id, actor_role="distributor", company_id=company.id
        ),
        db_session,
    )
    assert result["id"] == vid


async def test_delete_vehicle_missing(
    db_session: AsyncSession,
) -> None:
    user, _mark, _model, company, _dist, _dealer_company = await _seed_basic(db_session)
    with pytest.raises(VehicleNotFoundError):
        await handle_delete_distributor_vehicle(
            DeleteDistributorVehicleCommand(
                vehicle_id=uuid4(),
                actor_id=user.id,
                actor_role="distributor",
                company_id=company.id,
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Model orders
# ---------------------------------------------------------------------------


async def test_model_orders_stats(
    db_session: AsyncSession,
) -> None:
    user, _mark, _model, _company, _dist, _dealer_company = await _seed_basic(db_session)
    result = await handle_get_model_orders_stats(
        GetModelOrdersStatsQuery(
            actor_id=user.id, actor_role="distributor"
        ),
        db_session,
    )
    stats = result["stats"]
    assert "pending" in stats
    assert "assigned" in stats


async def test_assign_vin_to_model_order(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    db_session.add(vehicle)
    await db_session.flush()
    app_row = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    av = ApplicationVehicle(
        application_id=app_row.id,
        vehicle_id=vehicle.id,
        quantity=1,
        is_model_order=True,
    )
    db_session.add(av)
    await db_session.flush()

    result = await handle_assign_vin(
        AssignVinCommand(
            application_vehicle_id=av.id,
            actor_id=user.id,
            actor_role="distributor",
            actor_company_id=company.id,
            vin="WBA123456789ABCD",
        ),
        db_session,
    )
    assert result["order"]["vin"] == "WBA123456789ABCD"


# ---------------------------------------------------------------------------
# Application vehicles listing + available for app
# ---------------------------------------------------------------------------


async def test_list_application_vehicles_scoped(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    vehicle = Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    db_session.add(vehicle)
    await db_session.flush()
    warehouse = Warehouse(company_id=company.id, address="Application stock", brand="BMW")
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
    await db_session.flush()
    app_row = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    db_session.add(
        ApplicationVehicle(
            application_id=app_row.id, vehicle_id=vehicle.id, quantity=1
        )
    )
    await db_session.flush()

    result = await handle_list_application_vehicles(
        ListApplicationVehiclesQuery(
            actor_id=user.id,
            actor_role="distributor",
            application_id=app_row.id,
            company_id=company.id,
        ),
        db_session,
    )
    assert len(result["vehicles"]) == 1


async def test_available_vehicles_excludes_reserved(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, company, _dist, dealer_company = await _seed_basic(db_session)
    db_session.add_all(
        [
            Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id),
            Vehicle(mark_id=mark.id, status="reserved", dealer_id=dealer_company.id),
        ]
    )
    await db_session.flush()
    result = await handle_list_available_vehicles_for_app(
        ListAvailableVehiclesForAppQuery(
            actor_id=user.id, actor_role="distributor", company_id=company.id
        ),
        db_session,
    )
    statuses = {v["status"] for v in result["vehicles"]}
    assert statuses == {"available"}


# ---------------------------------------------------------------------------
# Import preview
# ---------------------------------------------------------------------------


async def test_preview_import_returns_sample(
    db_session: AsyncSession,
) -> None:
    headers = ["VIN", "Марка", "Модель", "Год", "Базовая цена"]
    rows = [
        ["PREVIEWVIN01", "BMW", "X5", 2024, 5000000],
        ["PREVIEWVIN02", "BMW", "X5", 2024, 5200000],
        ["", "Ford", "Focus", 2020, 800000],
    ]
    file_bytes = await write_workbook(headers, rows)

    result = await handle_preview_import_distributor_vehicles(
        PreviewImportDistributorVehiclesCommand(
            actor_id=uuid4(),
            actor_role="carcraft_employee",
            file_bytes=file_bytes,
        ),
        db_session,
    )
    assert result["total_rows"] == 3
    assert result["vehicles_count"] == 2
    assert result["rows_without_vin"] == 1
    assert len(result["sample_data"]) == 3


async def test_preview_import_rejects_empty() -> None:
    with pytest.raises(ExcelFormatError):
        await handle_preview_import_distributor_vehicles(
            PreviewImportDistributorVehiclesCommand(
                actor_id=uuid4(),
                actor_role="carcraft_employee",
                file_bytes=b"",
            ),
            session=None,  # type: ignore[arg-type]
        )


async def test_preview_import_rejects_oversized() -> None:
    huge = b"\x00" * (10 * 1024 * 1024 + 1)
    with pytest.raises(BulkImportValidationError):
        await handle_preview_import_distributor_vehicles(
            PreviewImportDistributorVehiclesCommand(
                actor_id=uuid4(),
                actor_role="carcraft_employee",
                file_bytes=huge,
            ),
            session=None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


async def test_export_xlsx_produces_bytes(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, _company, _dist, dealer_company = await _seed_basic(db_session)
    db_session.add(
        Vehicle(
            mark_id=mark.id,
            status="available",
            dealer_id=dealer_company.id,
            base_price=Decimal("1000"),
        )
    )
    await db_session.flush()

    result = await handle_export_distributor_vehicles(
        ExportDistributorVehiclesQuery(
            actor_id=user.id,
            actor_role="distributor",
            export_format="xlsx",
        ),
        db_session,
    )
    assert isinstance(result["content"], bytes)
    assert len(result["content"]) > 0
    assert result["mime_type"].startswith("application/vnd.")
    assert result["filename"].endswith(".xlsx")


async def test_export_csv_produces_bytes(
    db_session: AsyncSession,
) -> None:
    user, mark, _model, _company, _dist, dealer_company = await _seed_basic(db_session)
    db_session.add(
        Vehicle(mark_id=mark.id, status="available", dealer_id=dealer_company.id)
    )
    await db_session.flush()

    result = await handle_export_distributor_vehicles(
        ExportDistributorVehiclesQuery(
            actor_id=user.id,
            actor_role="distributor",
            export_format="csv",
        ),
        db_session,
    )
    assert result["mime_type"].startswith("text/csv")
    assert result["filename"].endswith(".csv")


async def test_export_rejects_unknown_format(
    db_session: AsyncSession,
) -> None:
    user, _mark, _model, _company, _dist, _dealer_company = await _seed_basic(db_session)
    with pytest.raises(InvalidExportFormatError):
        await handle_export_distributor_vehicles(
            ExportDistributorVehiclesQuery(
                actor_id=user.id,
                actor_role="distributor",
                export_format="pdf",
            ),
            db_session,
        )
