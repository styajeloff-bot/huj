"""Distributor scope resolution helper for application layer handlers.

Centralises the ``owned_dealer_ids`` lookup so every distributor-scoped
handler does not repeat the same repository boilerplate.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.distributor import DistributorScope
from infrastructure.repositories import distributor_dealer_repository as repo


async def resolve_distributor_scope(
    session: AsyncSession,
    *,
    actor_id: UUID,
    actor_role: str,
    company_id: UUID | None = None,
) -> DistributorScope:
    """Build a ``DistributorScope`` pre-populated with linked dealer ids.

    For ``carcraft_employee`` this is a no-op (no dealer filtering).
    For ``distributor`` we query the ``distributor_dealer_links`` table and
    pass the ids into ``DistributorScope.for_actor``.
    """
    if actor_role == "distributor" and company_id is not None:
        ids = await repo.get_linked_dealer_ids(session, company_id)
        return DistributorScope.for_actor(
            actor_id=actor_id,
            actor_role=actor_role,
            company_id=company_id,
            owned_dealer_ids=tuple(ids) if ids else (),
        )
    return DistributorScope.for_actor(
        actor_id=actor_id,
        actor_role=actor_role,
        company_id=company_id,
    )


async def resolve_distributor_application_dealer_filter(
    session: AsyncSession,
    *,
    actor_id: UUID,
    actor_role: str,
    company_id: UUID | None,
) -> list[UUID] | None:
    """Company scope retained for special equipment and legacy ancillary reads.

    Vehicle application reads additionally pass the active distributor company
    to the repository: its warehouse/group/brand predicate is authoritative and
    deliberately does not grant vehicle visibility from this linked-id list.
    """

    scope = await resolve_distributor_scope(
        session,
        actor_id=actor_id,
        actor_role=actor_role,
        company_id=company_id,
    )
    dealer_filter = scope.dealer_filter()
    if dealer_filter is None or company_id is None:
        return dealer_filter
    return list(dict.fromkeys((company_id, *dealer_filter)))
