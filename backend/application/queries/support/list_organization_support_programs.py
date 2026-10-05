"""List support programs visible to the current dealer or leasing company."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import support_repository as repo

_ORGANIZATION_PROGRAM_FIELDS = frozenset(
    {
        "id",
        "name",
        "mark_id",
        "mark_ids",
        "mark_name",
        "model_id",
        "model_ids",
        "model_name",
        "complectation_ids",
        "vin",
        "vins",
        "support_type",
        "support_params",
        "production_year_from",
        "production_year_to",
        "production_date_from",
        "production_date_to",
        "delivery_date_from",
        "delivery_date_to",
        "starts_at",
        "ends_at",
        "is_active",
        "is_compatible",
        "status",
        "show_to_leasing_company",
        "show_to_client",
        "comment",
        "compensation_templates",
        "created_at",
        "updated_at",
    }
)
_ORGANIZATION_COMPENSATION_FIELDS = frozenset(
    {
        "payer",
        "recipient",
        "calculation_base",
        "value_type",
        "value",
        "min_amount",
        "max_amount",
        "min_percent",
        "max_percent",
        "payment_schedule_type",
        "payment_schedule_period",
        "payment_schedule_value",
        "comment",
    }
)
_ORGANIZATION_SUPPORT_PARAM_FIELDS = frozenset(
    {
        "value_type",
        "value",
        "min_amount",
        "max_amount",
        "min_percent",
        "max_percent",
        "compensation_period_months",
        "start_month",
    }
)


def _organization_compensation_projection(
    template: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in template.items()
        if key in _ORGANIZATION_COMPENSATION_FIELDS
    }


def _organization_support_params_projection(
    support_params: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in support_params.items()
        if key in _ORGANIZATION_SUPPORT_PARAM_FIELDS
    }


def _organization_program_projection(program: dict[str, Any]) -> dict[str, Any]:
    """Return the stable read projection without organization relations.

    The allowlist is intentional: a relation added to the repository's admin
    representation cannot silently become visible through the organization API.
    Neutral values preserve the existing frontend ``SupportProgram`` shape.
    """

    projected = {
        key: value
        for key, value in program.items()
        if key in _ORGANIZATION_PROGRAM_FIELDS
    }
    projected.update(
        {
            "dealer_group_id": None,
            "dealer_group_ids": [],
            "dealer_groups": [],
            "distributor_id": None,
            "distributor_ids": [],
            "distributor_name": None,
            "distributors": [],
            "leasing_company_ids": [],
            "leasing_companies": [],
            "compatible_support_ids": [],
            "bill_of_lading": None,
            "support_params": _organization_support_params_projection(
                program.get("support_params") or {}
            ),
            "compensation_templates": [
                _organization_compensation_projection(template)
                for template in program.get("compensation_templates") or []
            ],
        }
    )
    return projected


@dataclass(frozen=True)
class ListOrganizationSupportProgramsQuery:
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None
    page: int = 1
    limit: int = 20
    search: str | None = None
    mark_id: str | None = None
    model_id: str | None = None
    is_active: bool | None = None


def _empty_result(query: ListOrganizationSupportProgramsQuery) -> dict[str, Any]:
    return {
        "items": [],
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": 0,
            "pages": 0,
        },
    }


async def handle_list_organization_support_programs(
    query: ListOrganizationSupportProgramsQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.actor_role == "dealer" and query.actor_company_id is None:
        return _empty_result(query)
    if (
        query.actor_role == "leasing_company"
        and query.actor_leasing_company_id is None
    ):
        return _empty_result(query)

    items, total = await repo.list_programs(
        session,
        page=query.page,
        limit=query.limit,
        search=query.search,
        mark_id=query.mark_id,
        model_id=query.model_id,
        is_active=query.is_active,
        visible_dealer_company_id=(
            query.actor_company_id if query.actor_role == "dealer" else None
        ),
        visible_leasing_company_id=(
            query.actor_leasing_company_id
            if query.actor_role == "leasing_company"
            else None
        ),
    )
    items = [_organization_program_projection(item) for item in items]
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "items": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }


__all__ = [
    "ListOrganizationSupportProgramsQuery",
    "handle_list_organization_support_programs",
]
