"""Transactional persistence primitives for administrative company-type changes."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationDealerDistributionRequest,
    ApplicationVehicleDealerDistribution,
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingCompanyDocumentRequirement,
)
from infrastructure.models.companies import (
    Company,
    Distributor,
    DistributorBrand,
    DistributorDealerLink,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.contractors import LeasingCompanyContractor
from infrastructure.models.documents import Document, DocumentLeasingCompanyApproval
from infrastructure.models.monetization import (
    condition_requests as monetization_condition_requests,
)
from infrastructure.models.monetization import (
    deals as monetization_deals,
)
from infrastructure.models.monetization import (
    programs as monetization_programs,
)
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.support import (
    DealerGroup,
    SupportProgramDistributor,
    SupportProgramLeasingCompany,
)
from infrastructure.models.vehicles import Warehouse
from infrastructure.repository_timing import timed_repository


class TypeTransitionBlocker(TypedDict):
    code: str
    count: int


def _extension_dict(row: LeasingCompany | Distributor | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"id": row.id, "company_id": row.company_id, "is_active": row.is_active}


@timed_repository
async def lock_company_type_transition_state(
    session: AsyncSession, company_id: UUID
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None] | None:
    """Lock the base company and both extension rows before deciding a transition."""
    company = await session.scalar(
        sa.select(Company).where(Company.id == company_id).with_for_update()
    )
    if company is None:
        return None
    leasing = await session.scalar(
        sa.select(LeasingCompany)
        .where(LeasingCompany.company_id == company_id)
        .with_for_update()
    )
    distributor = await session.scalar(
        sa.select(Distributor)
        .where(Distributor.company_id == company_id)
        .with_for_update()
    )
    return (
        {"id": company.id, "company_type": company.company_type},
        _extension_dict(leasing),
        _extension_dict(distributor),
    )


async def _count_rows(session: AsyncSession, statement: sa.Select[Any]) -> int:
    """Count dependencies without loading or disclosing dependency records."""
    count = await session.scalar(
        sa.select(sa.func.count()).select_from(statement.subquery())
    )
    return int(count or 0)


@timed_repository
async def list_type_transition_blockers(
    session: AsyncSession,
    *,
    company_id: UUID,
    current_type: str,
    leasing_extension_id: UUID | None,
) -> list[TypeTransitionBlocker]:
    """Return conservative dependency codes and aggregate counts for a role exit.

    The company row is already locked by the caller.  We intentionally retain
    all subtype/history rows and reject a role exit whenever a known consumer
    could become semantically orphaned.
    """
    blocker_counts: dict[str, int] = {}
    if current_type == "leasing_company" and leasing_extension_id is not None:
        checks: tuple[tuple[str, sa.Select[Any]], ...] = (
            (
                "leasing_applications",
                sa.select(LeasingCompanyApplication.id).where(
                    LeasingCompanyApplication.leasing_company_id == leasing_extension_id
                ),
            ),
            (
                "leasing_documents",
                sa.select(DocumentLeasingCompanyApproval.id).where(
                    DocumentLeasingCompanyApproval.leasing_company_id
                    == leasing_extension_id
                ),
            ),
            (
                "leasing_document_requirements",
                sa.select(LeasingCompanyDocumentRequirement.id).where(
                    LeasingCompanyDocumentRequirement.leasing_company_id
                    == leasing_extension_id
                ),
            ),
            (
                "leasing_company_users",
                sa.select(LeasingCompanyUser.id).where(
                    LeasingCompanyUser.leasing_company_id == leasing_extension_id
                ),
            ),
            (
                "monetization",
                sa.select(monetization_programs.c.id).where(
                    monetization_programs.c.leasing_company_id == leasing_extension_id
                ),
            ),
            (
                "monetization",
                sa.select(monetization_deals.c.id).where(
                    monetization_deals.c.leasing_company_id == leasing_extension_id
                ),
            ),
            (
                "monetization",
                sa.select(monetization_condition_requests.c.id).where(
                    monetization_condition_requests.c.leasing_company_id
                    == leasing_extension_id
                ),
            ),
            (
                "leasing_contractors",
                sa.select(LeasingCompanyContractor.id).where(
                    LeasingCompanyContractor.leasing_company_id == leasing_extension_id
                ),
            ),
            (
                "leasing_support_programs",
                sa.select(SupportProgramLeasingCompany.leasing_company_id).where(
                    SupportProgramLeasingCompany.leasing_company_id
                    == leasing_extension_id
                ),
            ),
            (
                "company_documents",
                sa.select(Document.id).where(Document.company_id == company_id),
            ),
        )
    elif current_type == "distributor":
        checks = (
            (
                "distributor_brands",
                sa.select(DistributorBrand.id).where(
                    DistributorBrand.distributor_company_id == company_id
                ),
            ),
            (
                "distributor_dealer_links",
                sa.select(DistributorDealerLink.dealer_company_id).where(
                    DistributorDealerLink.distributor_company_id == company_id
                ),
            ),
            (
                "dealer_groups",
                sa.select(DealerGroup.id).where(
                    DealerGroup.distributor_company_id == company_id
                ),
            ),
            (
                "distributor_warehouses",
                sa.select(Warehouse.id).where(
                    Warehouse.owner_company_id == company_id,
                    Warehouse.owner_company_type == current_type,
                ),
            ),
            (
                "dealer_distribution_requests",
                sa.select(ApplicationDealerDistributionRequest.id).where(
                    ApplicationDealerDistributionRequest.distributor_company_id
                    == company_id
                ),
            ),
            (
                "monetization",
                sa.select(monetization_programs.c.id).where(
                    monetization_programs.c.distributor_company_id == company_id
                ),
            ),
            (
                "monetization",
                sa.select(monetization_deals.c.id).where(
                    monetization_deals.c.distributor_company_id == company_id
                ),
            ),
            (
                "distributor_support_programs",
                sa.select(SupportProgramDistributor.distributor_id).where(
                    SupportProgramDistributor.distributor_id == company_id
                ),
            ),
        )
    elif current_type == "dealer":
        checks = (
            (
                "distributor_dealer_links",
                sa.select(DistributorDealerLink.distributor_company_id).where(
                    DistributorDealerLink.dealer_company_id == company_id
                ),
            ),
            (
                "dealer_applications",
                sa.select(LeasingApplication.id).where(
                    LeasingApplication.dealer_company_id == company_id
                ),
            ),
            (
                "dealer_inventory",
                sa.select(SpecialEquipmentProduct.id).where(
                    SpecialEquipmentProduct.seller_company_id == company_id
                ),
            ),
            (
                "dealer_warehouses",
                sa.select(Warehouse.id).where(
                    Warehouse.owner_company_id == company_id,
                    Warehouse.owner_company_type == current_type,
                ),
            ),
            (
                "dealer_distributions",
                sa.select(ApplicationVehicleDealerDistribution.id).where(
                    ApplicationVehicleDealerDistribution.dealer_company_id == company_id
                ),
            ),
        )
    else:
        checks = ()

    for category, statement in checks:
        count = await _count_rows(session, statement)
        if count:
            blocker_counts[category] = blocker_counts.get(category, 0) + count
    return [
        {"code": category, "count": count}
        for category, count in blocker_counts.items()
    ]


@timed_repository
async def apply_company_type_transition(
    session: AsyncSession,
    *,
    company_id: UUID,
    target_type: str,
    leaving_type: str | None,
    target_extension: dict[str, Any] | None,
) -> None:
    """Create/reactivate the target, deactivate the old subtype, and update the base row.

    The caller locks the company and both subtype rows before invoking this
    function.  An inactive target row is therefore the historical subtype from
    a prior safe exit and must be reactivated rather than replaced.
    """
    now = datetime.now(UTC)
    if target_type == "leasing_company" and target_extension is None:
        session.add(LeasingCompany(company_id=company_id, is_active=True))
        await session.flush()
    elif (
        target_type == "leasing_company"
        and target_extension is not None
        and target_extension.get("is_active") is not True
    ):
        await session.execute(
            sa.update(LeasingCompany)
            .where(LeasingCompany.id == target_extension["id"])
            .values(is_active=True, updated_at=now)
        )
    elif target_type == "distributor" and target_extension is None:
        session.add(Distributor(company_id=company_id, is_active=True))
        await session.flush()
    elif (
        target_type == "distributor"
        and target_extension is not None
        and target_extension.get("is_active") is not True
    ):
        await session.execute(
            sa.update(Distributor)
            .where(Distributor.id == target_extension["id"])
            .values(is_active=True, updated_at=now)
        )

    if leaving_type == "leasing_company":
        await session.execute(
            sa.update(LeasingCompany)
            .where(LeasingCompany.company_id == company_id)
            .values(is_active=False, updated_at=now)
        )
    elif leaving_type == "distributor":
        await session.execute(
            sa.update(Distributor)
            .where(Distributor.company_id == company_id)
            .values(is_active=False, updated_at=now)
        )

    await session.execute(
        sa.update(Company)
        .where(Company.id == company_id)
        .values(company_type=target_type, updated_at=now)
    )
    await session.flush()
