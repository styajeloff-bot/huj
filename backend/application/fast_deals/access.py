"""Visibility, locking and optimistic versioning of one deal for one actor.

Every command loads its deal through ``load_context``: parent lock first, then the
``If-Match`` check, then the visibility check. A deal the actor may not see is
reported as not found, without any detail about the client or a VIN.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from domain.fast_deals.actions import (
    Action,
    ActionContext,
    allowed_actions,
    require_action,
)
from domain.fast_deals.errors import (
    FastDealAccessDeniedError,
    FastDealNotFoundError,
    FastDealStateError,
    FastDealVersionConflictError,
    FastDealVersionRequiredError,
)
from domain.fast_deals.values import (
    DealStatus,
    ItemStatus,
    LcStatus,
    Party,
    Role,
    SourceType,
)
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

_ETAG = re.compile(r'^(?:W/)?"?([0-9a-fA-F-]{36}):(\d+)"?$')


def etag_for(deal: Record) -> str:
    """Strong validator bound to the deal: ``"<deal id>:<version>"``."""
    return f'"{deal["id"]}:{deal["version"]}"'


def parse_if_match(header: str | None, deal_id: UUID) -> int:
    """Version from ``If-Match``; 428 when absent, 412 when it names another deal."""
    if header is None or not header.strip():
        raise FastDealVersionRequiredError
    match = _ETAG.match(header.strip())
    if match is None:
        raise FastDealVersionConflictError("Некорректный заголовок If-Match")
    if UUID(match.group(1)) != deal_id:
        raise FastDealVersionConflictError
    return int(match.group(2))


@dataclass
class DealContext:
    """A locked deal with what the rules need about the actor."""

    actor: Actor
    deal: Record
    party: Party
    vehicles: list[Record]  # active positions
    lc_applications: list[Record]  # invitations of the current cycle
    lc_application: Record | None  # the actor's own invitation (leasing company, DD)
    assignees: list[Record] = field(default_factory=list)

    @property
    def deal_id(self) -> UUID:
        return self.deal["id"]  # type: ignore[no-any-return]

    @property
    def is_dd(self) -> bool:
        return bool(self.deal["source_type"] == SourceType.DEALER_TO_LEASING)

    @property
    def status(self) -> DealStatus:
        return DealStatus(self.deal["status"])

    def actions(self, **facts: Any) -> list[Action]:
        """Allowed actions of this actor; extra facts refine support-related ones."""
        return allowed_actions(
            self.deal,
            ActionContext(
                party=self.party,
                is_company_admin=self.actor.is_company_admin,
                lc_application=self.lc_application,
                lc_applications=self.lc_applications,
                active_vehicles=len(self.vehicles),
                **facts,
            ),
        )

    def require(self, action: Action, message: str | None = None, **facts: Any) -> None:
        """403/409 unless the server allows this action to this actor right now."""
        actions = self.actions(**facts)
        if action in actions:
            return
        if self.party in {Party.PLATFORM, Party.NONE}:
            raise FastDealAccessDeniedError
        raise FastDealStateError(message or "Действие недоступно в текущем состоянии сделки")

    def require_initiator(self) -> None:
        if self.party != Party.INITIATOR:
            raise FastDealAccessDeniedError("Действие доступно только инициатору сделки")


async def resolve_party(
    session: AsyncSession,
    actor: Actor,
    deal: Record,
    lc_applications: list[Record],
    assignees: list[Record],
) -> tuple[Party, Record | None]:
    """Mirror of ``fast_deal_access_repository.scope_clause`` for one loaded deal."""
    sent = deal["sent_at"] is not None and deal["status"] != DealStatus.DRAFT
    company = actor.company_id
    if actor.is_platform:
        return (Party.PLATFORM if sent else Party.NONE), None
    if company is None:
        return Party.NONE, None
    own_or_assigned = (
        actor.is_company_admin
        or deal["created_by"] == actor.user_id
        or _is_assigned(assignees, actor.user_id, company)
    )
    assigned_or_admin = actor.is_company_admin or _is_assigned(assignees, actor.user_id, company)
    dd = deal["source_type"] == SourceType.DEALER_TO_LEASING
    initiator = deal["initiator_company_id"] == company

    party, own = Party.NONE, None
    if actor.role == Role.DEALER:
        if dd and initiator and own_or_assigned:
            party = Party.INITIATOR
        elif not dd and deal["dealer_company_id"] == company and sent and assigned_or_admin:
            party = Party.DEALER
    elif actor.role == Role.LEASING_COMPANY:
        if not dd and initiator and own_or_assigned:
            party = Party.INITIATOR
        elif dd and deal["status"] != DealStatus.DRAFT and assigned_or_admin:
            own = next(
                (
                    item
                    for item in lc_applications
                    if item["leasing_company_id"] == company and item["archived_at"] is None
                ),
                None,
            )
            party = Party.LEASING if own is not None else Party.NONE
    elif actor.role == Role.DISTRIBUTOR:
        dealer = deal["dealer_company_id"]
        if (
            sent
            and dealer is not None
            and await access_repo.distributor_of_dealer(session, dealer) == company
        ):
            party = Party.DISTRIBUTOR
    return party, own


def _is_assigned(assignees: list[Record], user_id: UUID, company_id: UUID) -> bool:
    return any(
        item["user_id"] == user_id and item["company_id"] == company_id for item in assignees
    )


async def ensure_membership(session: AsyncSession, actor: Actor) -> None:
    """A blocked membership grants nothing, whatever the token still says."""
    if actor.is_platform or actor.company_id is None:
        return
    membership = await access_repo.get_membership(session, actor.user_id, actor.company_id)
    if membership is not None and not membership["is_active"]:
        raise FastDealAccessDeniedError("Ваш доступ к компании отключён")


async def load_context(
    session: AsyncSession,
    actor: Actor,
    deal_id: UUID,
    *,
    if_match: str | None = None,
    mutation: bool = False,
    lock: bool = True,
) -> DealContext:
    """Lock the deal, then check visibility, then (for a mutation) the version.

    Visibility comes first so that a stranger learns nothing, not even whether a
    version header was needed. ``if_match`` is the raw ``If-Match`` header: required
    (428) and compared (412) for every mutation, ignored for reads.
    """
    await ensure_membership(session, actor)
    deal = await repo.get_deal(session, deal_id, lock=lock)
    if deal is None:
        raise FastDealNotFoundError
    lc_applications = await repo.list_lc_applications(session, deal_id)
    assignees = await access_repo.list_assignees(session, deal_id)
    party, own_application = await resolve_party(session, actor, deal, lc_applications, assignees)
    if party == Party.NONE:
        # The same answer for a foreign and for a missing deal.
        raise FastDealNotFoundError
    if mutation and deal["version"] != parse_if_match(if_match, deal_id):
        raise FastDealVersionConflictError
    vehicles = await repo.list_vehicles(session, deal_id)
    return DealContext(
        actor=actor,
        deal=deal,
        party=party,
        vehicles=vehicles,
        lc_applications=lc_applications,
        lc_application=own_application,
        assignees=assignees,
    )


async def load_for_mutation(
    session: AsyncSession, actor: Actor, deal_id: UUID | None, if_match: str | None
) -> DealContext:
    """Entry of every mutating command: the parent id may come from a child URL.

    A missing child resolves to ``None`` and is reported as a missing deal.
    """
    if deal_id is None:
        raise FastDealNotFoundError
    return await load_context(session, actor, deal_id, if_match=if_match, mutation=True)


def active_vehicle(ctx: DealContext, vehicle_id: UUID) -> Record:
    """A position of this deal that is still active, else a safe not-found."""
    for item in ctx.vehicles:
        if item["id"] == vehicle_id and item["item_status"] == ItemStatus.ACTIVE:
            return item
    raise FastDealNotFoundError("Позиция не найдена")


def invitation(ctx: DealContext, lc_application_id: UUID) -> Record:
    """An invitation of the current cycle visible to the actor."""
    for item in ctx.lc_applications:
        if item["id"] != lc_application_id:
            continue
        if ctx.party == Party.LEASING and (
            ctx.lc_application is None or ctx.lc_application["id"] != lc_application_id
        ):
            break
        return item
    raise FastDealNotFoundError("Приглашение не найдено")


def current_offers_exist(ctx: DealContext) -> bool:
    return any(
        item["status"] == LcStatus.OFFER_SENT and item["current_offer_id"]
        for item in ctx.lc_applications
    )


__all__ = [
    "DealContext",
    "active_vehicle",
    "current_offers_exist",
    "ensure_membership",
    "etag_for",
    "invitation",
    "load_context",
    "load_for_mutation",
    "parse_if_match",
    "require_action",
    "resolve_party",
]
