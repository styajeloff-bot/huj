"""Addressees of fast deal facts: a party's assignees, else its administrators.

The event names the addressed companies; who inside a company is decided here, at
processing time and again before every e-mail. A person who may not read the deal over
HTTP (``access.resolve_party``) is never an addressee. Two facts are told to people who
no longer have the card by design — the review cycle that was closed by a reset and a
removed assignee — and those are checked against the deal's parties instead.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import resolve_party
from application.fast_deals.actor import Actor
from domain.events.notifications import NotificationEvent
from domain.fast_deals.notification_content import Relation, Scope
from domain.fast_deals.values import Party
from domain.notification_policy import POLICIES
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo
from infrastructure.repositories import notification_recipients_repository as users

Record = dict[str, Any]


async def resolve_fast_deal_recipients(
    session: AsyncSession,
    event: NotificationEvent,
    *,
    user_id: UUID | None = None,
    company_id: UUID | None = None,
) -> list[Record]:
    """Current addressees of one event; ``user_id``/``company_id`` narrow it to a recheck."""
    deal: Record | None = await repo.get_deal(session, event.entity_id)
    if deal is None:
        return []
    payload = event.payload
    targets = {UUID(str(item)) for item in payload["target_company_ids"]}
    if company_id is not None:
        targets &= {company_id}
    if not targets:
        return []
    invitations: list[Record] = await repo.list_lc_applications(
        session, deal["id"], current_cycle_only=False
    )
    current = [item for item in invitations if item["archived_at"] is None]
    assignees: list[Record] = await access_repo.list_assignees(session, deal["id"])
    assigned = {
        company: await _active_assignees(session, company, assignees) for company in targets
    }
    candidates: list[Record] = await users.candidate_contexts(
        session, company_ids=targets, user_id=user_id
    )
    roles = POLICIES[event.event_type].roles
    scope = payload["scope"]
    recipients: dict[UUID, Record] = {}
    for candidate in sorted(
        candidates, key=lambda item: (str(item["user_id"]), str(item.get("company_id")))
    ):
        if candidate["role"] not in roles or candidate["user_id"] == event.actor_user_id:
            continue
        if scope == Scope.ASSIGNMENT:
            relation = _assignment_relation(candidate, payload)
            addressed = relation is not None
        else:
            relation = None
            addressed = _is_addressed(candidate, assigned[candidate["company_id"]])
        if not addressed or not await _may_be_told(
            session, candidate, deal, scope=scope, relation=relation,
            invitations=invitations, current=current, assignees=assignees,
        ):
            continue
        recipients.setdefault(
            candidate["user_id"],
            candidate
            | {
                "leasing_company_id": None,
                "storefront_slug": None,
                "fast_deal_relation": relation,
            },
        )
    return list(recipients.values())


async def _active_assignees(
    session: AsyncSession, company: UUID, assignees: list[Record]
) -> set[UUID]:
    ids = [item["user_id"] for item in assignees if item["company_id"] == company]
    found: set[UUID] = await access_repo.active_member_ids(session, company, ids)
    return found


def _is_addressed(candidate: Record, assigned: set[UUID]) -> bool:
    """Assignees of the party; until someone is assigned, its administrators."""
    if assigned:
        return bool(candidate["user_id"] in assigned)
    return bool(candidate.get("sub_role") == "administrator")


def _assignment_relation(candidate: Record, payload: dict[str, Any]) -> str | None:
    """Assigned users, administrators and the people who were just removed."""
    user = str(candidate["user_id"])
    for item in payload.get("assignees") or []:
        if str(item.get("user_id")) == user:
            role = item.get("role")
            return role if role in {Relation.PRIMARY, Relation.ADDITIONAL} else None
    if candidate.get("sub_role") == "administrator":
        return Relation.ADMINISTRATOR
    if user in {str(item) for item in payload.get("previous_user_ids") or []}:
        return Relation.REMOVED
    return None


async def _may_be_told(
    session: AsyncSession,
    candidate: Record,
    deal: Record,
    *,
    scope: str,
    relation: str | None,
    invitations: list[Record],
    current: list[Record],
    assignees: list[Record],
) -> bool:
    company = candidate["company_id"]
    membership: Record | None = await access_repo.get_membership(
        session, candidate["user_id"], company
    )
    if membership is not None and not membership["is_active"]:
        return False
    if scope == Scope.PREVIOUS_LCS or relation == Relation.REMOVED:
        parties = {deal["initiator_company_id"], deal["dealer_company_id"]}
        parties.update(item["leasing_company_id"] for item in invitations)
        return company in parties
    actor = Actor(
        user_id=candidate["user_id"],
        role=candidate["role"],
        company_id=company,
        sub_role=candidate.get("sub_role"),
    )
    party, _ = await resolve_party(session, actor, deal, current, assignees)
    return party != Party.NONE
