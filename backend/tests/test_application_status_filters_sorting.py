from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications.list_applications import (
    ListApplicationsQuery,
    handle_list_applications,
)
from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
from infrastructure.models.applications import LeasingCompanyApplication as LcaModel
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import distributor_repository as distributor_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


async def _company(db_session: AsyncSession, name: str, company_type: str = "other") -> Company:
    company = Company(name=name, company_type=company_type)
    db_session.add(company)
    await db_session.flush()
    return company


async def _leasing_company(db_session: AsyncSession, company: Company) -> LeasingCompany:
    lc = LeasingCompany(company_id=company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


async def _application(
    db_session: AsyncSession,
    *,
    company: Company,
    status: str,
    created_at: datetime,
    updated_at: datetime | None = None,
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=company.id,
        name=f"Applicant {status}",
        email=f"{status}@test.local",
        status=status,
        created_at=created_at,
        updated_at=updated_at or created_at,
    )
    db_session.add(app)
    await db_session.flush()
    return app


async def _attach_vehicle(
    db_session: AsyncSession,
    *,
    app: LeasingApplication,
    dealer: Company,
    vin: str,
) -> None:
    vehicle = Vehicle(vin=vin, dealer_id=dealer.id, status="available", is_available=True)
    db_session.add(vehicle)
    await db_session.flush()
    db_session.add(ApplicationVehicle(application_id=app.id, vehicle_id=vehicle.id))


async def test_lc_all_statuses_are_sorted_by_activity_before_pagination(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session, "LC applicant")
    lc_company = await _company(db_session, "LC", "leasing_company")
    lc = await _leasing_company(db_session, lc_company)
    base = datetime(2026, 6, 19, tzinfo=UTC)

    old_statuses = [
        "documents_required",
        "deal",
        "rejected_prescoring",
        "approved_scoring",
        "approved_final",
    ]
    for index, status in enumerate(old_statuses):
        app = await _application(
            db_session,
            company=company,
            status="active",
            created_at=base - timedelta(days=10 + index),
        )
        db_session.add(
            LcaModel(
                id=UUID(f"ffffffff-ffff-ffff-ffff-ffffffffff{index:02x}"),
                application_id=app.id,
                leasing_company_id=lc.id,
                status=status,
                created_at=base - timedelta(days=10 + index),
                updated_at=base - timedelta(days=10 + index),
            )
        )

    fresh_submitted = await _application(
        db_session,
        company=company,
        status="active",
        created_at=base + timedelta(hours=1),
    )
    db_session.add(
        LcaModel(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            application_id=fresh_submitted.id,
            leasing_company_id=lc.id,
            status="submitted",
            created_at=base + timedelta(hours=1),
            updated_at=base + timedelta(hours=1),
        )
    )

    fresh_review = await _application(
        db_session,
        company=company,
        status="active",
        created_at=base + timedelta(hours=2),
    )
    db_session.add(
        LcaModel(
            id=UUID("00000000-0000-0000-0000-000000000002"),
            application_id=fresh_review.id,
            leasing_company_id=lc.id,
            status="under_review",
            created_at=base + timedelta(hours=2),
            updated_at=base + timedelta(hours=2),
        )
    )
    await db_session.flush()

    rows = await lca_repo.list_applications_for_lc(
        db_session,
        leasing_company_id=lc.id,
        status=None,
        limit=2,
        offset=0,
    )

    assert [row["link"]["status"] for row in rows] == ["under_review", "submitted"]


async def test_lc_status_filter_still_filters_before_pagination(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session, "LC applicant filter")
    lc_company = await _company(db_session, "LC filter", "leasing_company")
    lc = await _leasing_company(db_session, lc_company)
    base = datetime(2026, 6, 19, tzinfo=UTC)

    for status, hours in [("submitted", 1), ("under_review", 2), ("under_review", 3)]:
        app = await _application(
            db_session,
            company=company,
            status="active",
            created_at=base + timedelta(hours=hours),
        )
        db_session.add(
            LcaModel(
                application_id=app.id,
                leasing_company_id=lc.id,
                status=status,
                created_at=base + timedelta(hours=hours),
                updated_at=base + timedelta(hours=hours),
            )
        )
    await db_session.flush()

    rows = await lca_repo.list_applications_for_lc(
        db_session,
        leasing_company_id=lc.id,
        status="under_review",
        limit=10,
        offset=0,
    )

    assert [row["link"]["status"] for row in rows] == ["under_review", "under_review"]
    assert rows[0]["application"]["created_at"] > rows[1]["application"]["created_at"]


async def test_client_applications_status_query_filters_before_pagination(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session, "Client company")
    user = User(
        phone="+766****2161",
        email="client21616@test.local",
        name="Client 21616",
        role="client",
        is_active=True,
        company_id=company.id,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    base = datetime(2026, 6, 19, tzinfo=UTC)
    await _application(db_session, company=company, status="active", created_at=base)
    rejected = await _application(
        db_session,
        company=company,
        status="rejected",
        created_at=base + timedelta(hours=1),
    )
    await db_session.flush()

    result = await handle_list_applications(
        ListApplicationsQuery(
            actor_id=user.id,
            actor_role="client",
            actor_company_id=company.id,
            page=1,
            limit=10,
            status="rejected",
        ),
        db_session,
    )

    assert [item["id"] for item in result["applications"]] == [rejected.id]


async def test_distributor_all_statuses_are_unfiltered_and_newest_first(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session, "Distributor app company")
    dealer = await _company(db_session, "Dealer", "dealer")
    base = datetime(2026, 6, 19, tzinfo=UTC)

    old = await _application(
        db_session,
        company=company,
        status="active",
        created_at=base - timedelta(days=1),
    )
    new = await _application(
        db_session,
        company=company,
        status="issued",
        created_at=base + timedelta(hours=1),
    )
    await _attach_vehicle(db_session, app=old, dealer=dealer, vin="VIN21616000000001")
    await _attach_vehicle(db_session, app=new, dealer=dealer, vin="VIN21616000000002")
    await db_session.flush()

    items, total = await distributor_repo.list_distributor_applications(
        db_session,
        dealer_filter=None,
        status=None,
        page=1,
        limit=10,
    )

    assert total == 2
    assert [item["status"] for item in items] == ["issued", "active"]

    filtered, filtered_total = await distributor_repo.list_distributor_applications(
        db_session,
        dealer_filter=None,
        status="active",
        page=1,
        limit=10,
    )
    assert filtered_total == 1
    assert [item["status"] for item in filtered] == ["active"]


async def test_distributor_grouped_applications_are_newest_first_across_statuses(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session, "Distributor grouped company")
    dealer = await _company(db_session, "Grouped dealer", "dealer")
    base = datetime(2026, 6, 19, tzinfo=UTC)

    recently_updated = await _application(
        db_session,
        company=company,
        status="active",
        created_at=base - timedelta(days=2),
        updated_at=base + timedelta(hours=2),
    )
    recently_created = await _application(
        db_session,
        company=company,
        status="issued",
        created_at=base + timedelta(hours=1),
        updated_at=base + timedelta(hours=1),
    )
    await _attach_vehicle(db_session, app=recently_updated, dealer=dealer, vin="VIN21616000000003")
    await _attach_vehicle(db_session, app=recently_created, dealer=dealer, vin="VIN21616000000004")
    await db_session.flush()

    grouped, total = await distributor_repo.list_distributor_applications_grouped(
        db_session,
        dealer_filter=None,
        page=1,
        limit=10,
    )

    flattened = [item for bucket in grouped.values() for item in bucket]
    assert total == 2
    assert [item["id"] for item in flattened] == [recently_updated.id, recently_created.id]
    assert flattened[0]["updated_at"] == recently_updated.updated_at
