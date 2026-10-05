"""Warehouse read-scope resolution for employee, distributor and dealer actors."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope


async def resolve_warehouse_dealer_filter(
    session: AsyncSession,
    *,
    actor_id: UUID,
    actor_role: str,
    company_id: UUID | None,
) -> list[UUID] | None:
    """Return company ids visible to an actor reading warehouses.

    ``None`` means unfiltered employee access, while an empty list denies all
    rows. Distributors retain their linked-dealer scope; dealers are limited to
    the company from their access token.
    """

    if actor_role == "carcraft_employee":
        return None
    if actor_role == "dealer":
        return [company_id] if company_id is not None else []
    if actor_role == "distributor":
        if company_id is None:
            return []
        scope = await resolve_distributor_scope(
            session,
            actor_id=actor_id,
            actor_role=actor_role,
            company_id=company_id,
        )
        dealer_filter = scope.dealer_filter() or []
        return list(dict.fromkeys((company_id, *dealer_filter)))
    return []
