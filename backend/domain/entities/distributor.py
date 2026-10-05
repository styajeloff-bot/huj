"""Distributor domain entity — scope resolution for distributor users.

A distributor is a User with role ``distributor`` whose ``company_id``
points at a Company of type ``distributor``. Runtime distributor scope is
resolved by the application layer from ``distributor_dealer_links`` and
stored here as linked dealer company ids. A deliberately empty linked scope
means the distributor sees and writes nothing, not an unscoped fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from domain.errors import DistributorAccessDeniedError


@dataclass(frozen=True)
class DistributorScope:
    """Resolved authorization scope for a distributor-side request.

    Attributes:
        actor_id: the user id from the JWT.
        actor_role: the user role from the JWT.
        company_id: the company id (for Phase 5, dealer_id references companies.id).
        is_employee: True when the actor is a carcraft employee — they see
            every distributor's data and bypass scope filters.
        owned_dealer_ids: the dealer_ids (company_ids) whose vehicles this actor "owns".
            For a distributor user this is ``{company_id}``; for an employee
            this is left empty (no filter applied).
    """

    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    is_employee: bool = False
    owned_dealer_ids: tuple[UUID, ...] = ()

    @classmethod
    def for_actor(
        cls,
        *,
        actor_id: UUID,
        actor_role: str,
        company_id: UUID | str | None = None,
        owned_dealer_ids: tuple[UUID, ...] | None = None,
    ) -> DistributorScope:
        """Resolve the scope for the actor.

        Raises ``DistributorAccessDeniedError`` for any role other than
        ``distributor`` or ``carcraft_employee``.

        ``company_id`` may arrive as a string from the JWT payload; it is
        coerced to ``UUID`` here so ``owned_dealer_ids`` comparisons work
        correctly against UUID-typed database columns.

        When ``owned_dealer_ids`` is provided for a distributor role it
        overrides the default self-reference fallback.
        """
        cid: UUID | None = None
        if isinstance(company_id, str) and company_id:
            cid = UUID(company_id)
        elif isinstance(company_id, UUID):
            cid = company_id

        if actor_role == "carcraft_employee":
            return cls(
                actor_id=actor_id,
                actor_role=actor_role,
                is_employee=True,
                owned_dealer_ids=(),
                company_id=cid,
            )
        if actor_role == "distributor":
            if owned_dealer_ids is not None:
                dealers = owned_dealer_ids
            else:
                dealers = (cid,) if cid else (actor_id,)
            return cls(
                actor_id=actor_id,
                actor_role=actor_role,
                is_employee=False,
                owned_dealer_ids=dealers,
                company_id=cid,
            )
        raise DistributorAccessDeniedError()

    def dealer_filter(self) -> list[UUID] | None:
        """Return the dealer_ids to filter by, or None for "no filter"."""
        if self.is_employee:
            return None
        if not self.owned_dealer_ids:
            # Defensive: a non-employee with no owned dealers means we'd
            # otherwise leak everything. Return an empty list so callers
            # can force an impossible filter.
            return []
        return list(self.owned_dealer_ids)

    def ensure_can_write(self, target_dealer_id: UUID | None) -> None:
        """Authorize a write whose target row has ``target_dealer_id``.

        Employees may write anything; a distributor may only write rows
        bound to one of their owned dealer ids (or unbound rows that we
        are about to bind to themselves — caller responsibility).
        """
        if self.is_employee:
            return
        if target_dealer_id is None:
            return  # caller will set dealer_id = self.actor_id
        if target_dealer_id in self.owned_dealer_ids:
            return
        raise DistributorAccessDeniedError(
            "Автомобиль не принадлежит данному распределителю"
        )

    def ensure_can_write_any(self) -> None:
        """Authorize a write when no specific target row is known yet.

        Used for bulk operations where individual rows will be checked later.
        """
        if self.is_employee:
            return
        if not self.owned_dealer_ids:
            raise DistributorAccessDeniedError(
                "Нет привязанных дилеров для выполнения операции"
            )

    def coerce_dealer_id_for_write(
        self, requested_dealer_id: UUID | None
    ) -> UUID | None:
        """Resolve the dealer_id to write to a new/updated row.

        Employees keep whatever they sent. Distributors may write to an
        explicitly requested linked dealer. If no dealer is requested, the
        operation can default only when exactly one linked dealer exists.
        """
        if self.is_employee:
            return requested_dealer_id
        if requested_dealer_id is not None:
            self.ensure_can_write(requested_dealer_id)
            return requested_dealer_id
        if len(self.owned_dealer_ids) == 1:
            return self.owned_dealer_ids[0]
        if not self.owned_dealer_ids:
            raise DistributorAccessDeniedError(
                "Нет привязанных дилеров для выполнения операции"
            )
        raise DistributorAccessDeniedError(
            "Укажите дилера для операции распределителя"
        )
