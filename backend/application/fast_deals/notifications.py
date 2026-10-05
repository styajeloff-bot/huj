"""Transactional-outbox notifications of the deal.

Events are appended in the caller's transaction (inbox and e-mail follow after the
commit). Recipients are the party's primary and additional assignees, else its
company administrators; the client is never notified. Deduplication key:
event + deal + version (+ recipient scope).

This module decides *which companies* a fact concerns and *what* may be said; who inside
a company receives it, and whether that person may still read the deal, is decided when
the event is processed (``application.notifications.fast_deal_recipients``).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from application.notifications.events import record_notification_event
from domain.fast_deals.money import wire
from domain.fast_deals.notification_content import (
    Scope,
    clip,
    payload_changes,
    payload_support_request,
    payload_terms,
    payload_vehicles,
)
from domain.fast_deals.values import LcStatus, NotifyEvent, SourceType
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo

logger = logging.getLogger("carcraft-backend")

Record = dict[str, Any]

# Invitations that still have something to answer or to do on the deal.
_LIVE_LC = frozenset(
    {
        LcStatus.PENDING_REVIEW,
        LcStatus.OFFER_SENT,
        LcStatus.SELECTED_BY_DEALER,
        LcStatus.CONFIRMED,
    }
)
_SUPPORT_EVENTS = frozenset({NotifyEvent.SUPPORT_REQUESTED, NotifyEvent.SUPPORT_DECIDED})
# The refusal text of the actor is shown to the counterparty.
_REASON_EVENTS = frozenset(
    {
        NotifyEvent.LC_REJECTED,
        NotifyEvent.REJECTED,
        NotifyEvent.CHANGES_REJECTED,
        NotifyEvent.CANCELLED,
    }
)
# These facts are told without the deal's business data: no client, positions or prices.
_NO_BUSINESS_DATA = frozenset({NotifyEvent.RESET, NotifyEvent.ASSIGNEES_CHANGED})


@dataclass(frozen=True)
class _Audience:
    """Companies one event is addressed to, with what is specific to them."""

    scope: str
    companies: list[UUID]
    suffix: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def notify(
    session: AsyncSession,
    event: str,
    deal: Record,
    actor: Actor,
    *,
    version: int,
    lc_application: Record | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Record one ``fast_deal.*`` event; ``extra`` carries event-specific facts.

    Known ``extra`` keys: ``reason``, ``leasing_company_ids`` (sending to leasing
    companies), ``previous_lc_company_ids`` (reset), ``assignee_company_id`` and
    ``previous_user_ids`` (assignment), ``support_request`` (support events),
    ``changes`` and ``comment`` (dealer changes in DL).

    A fact is recorded once per event, deal version and scope: replaying the same
    command, or the delivery of the event, produces nothing new.
    """
    if event not in NotifyEvent.ALL:
        raise ValueError(f"Unknown fast deal notification event: {event}")
    details = dict(extra or {})
    # The caller may hold a deal read before its own update; the facts must not.
    current: Record = await repo.get_deal(session, deal["id"]) or deal
    audiences = [
        item
        for item in await _audiences(
            session, event, current, actor, lc_application=lc_application, details=details
        )
        if item.companies
    ]
    if not audiences:
        return
    facts = await _facts(
        session, event, current, actor, version=version, details=details,
        lc_application=lc_application,
    )
    for audience in audiences:
        await record_notification_event(
            session,
            event_type=event,
            entity_type="fast_deal",
            entity_id=current["id"],
            aggregate_id=current["id"],
            request_number=current["display_number"],
            actor_user_id=actor.user_id,
            payload=facts
            | audience.extra
            | {
                "scope": audience.scope,
                "target_company_ids": [str(company) for company in audience.companies],
            },
            occurrence_key=_occurrence_key(event, current["id"], version, audience.suffix),
        )


def _occurrence_key(event: str, deal_id: UUID, version: int, suffix: str | None) -> str:
    """``fast_deal.<event>:<deal>:<version>[:<scope>]``; ``event`` has the prefix already."""
    key = f"{event}:{deal_id}:{version}"
    return f"{key}:{suffix}" if suffix else key


# ----------------------------------------------------------------------------- audience

def _present(*companies: Any) -> list[UUID]:
    """Distinct company ids in order; absent ones and ``str`` forms are normalised."""
    result: list[UUID] = []
    for company in companies:
        if company is None:
            continue
        value = company if isinstance(company, UUID) else UUID(str(company))
        if value not in result:
            result.append(value)
    return result


def _other_side(deal: Record, company: UUID | None, live: list[UUID]) -> list[UUID]:
    """The counterparty of ``company``: the initiator's partners, or the initiator."""
    if company != deal["initiator_company_id"]:
        return _present(deal["initiator_company_id"])
    if deal["source_type"] == SourceType.LEASING_TO_DEALER:
        return _present(deal["dealer_company_id"])
    return live


def _invitation(
    lc_application: Record | None, invitations: list[Record], actor: Actor
) -> Record | None:
    """The invitation a fact is about, as it is stored now."""
    if lc_application is not None:
        stored = next((item for item in invitations if item["id"] == lc_application["id"]), None)
        return stored or lc_application
    return next(
        (item for item in invitations if item["leasing_company_id"] == actor.company_id), None
    )


async def _offer_terms(session: AsyncSession, offer_id: UUID | None) -> dict[str, Any]:
    offer: Record | None = await repo.get_offer(session, offer_id) if offer_id else None
    return {"terms": payload_terms(offer)} if offer else {}


async def _audiences(
    session: AsyncSession,
    event: str,
    deal: Record,
    actor: Actor,
    *,
    lc_application: Record | None,
    details: dict[str, Any],
) -> list[_Audience]:
    invitations: list[Record] = await repo.list_lc_applications(session, deal["id"])
    live = _present(
        *(item["leasing_company_id"] for item in invitations if item["status"] in _LIVE_LC)
    )
    initiator, dealer = deal["initiator_company_id"], deal["dealer_company_id"]

    if event == NotifyEvent.SENT:
        if deal["source_type"] == SourceType.DEALER_TO_LEASING:
            invited = _present(*(details.get("leasing_company_ids") or live))
            return [_Audience(Scope.INVITED_LCS, invited)]
        return [_Audience(Scope.DEALER, _present(dealer))]
    if event == NotifyEvent.OFFER_SENT:
        offer = _invitation(lc_application, invitations, actor)
        terms = await _offer_terms(session, offer["current_offer_id"] if offer else None)
        return [_Audience(Scope.INITIATOR, _present(initiator), extra=terms)]
    if event in {NotifyEvent.OFFER_SELECTED, NotifyEvent.SELECTION_WITHDRAWN}:
        return await _selection_audiences(
            session, event, deal, invitations, _invitation(lc_application, invitations, actor)
        )
    if event in {
        NotifyEvent.LC_REJECTED,
        NotifyEvent.REJECTED,
        NotifyEvent.CHANGES_SENT,
        NotifyEvent.CHANGES_ACCEPTED,
        NotifyEvent.CHANGES_REJECTED,
    }:
        return [_Audience(Scope.COUNTERPARTY, _other_side(deal, actor.company_id, live))]
    return await _closing_audiences(session, event, deal, actor, live=live, details=details)


async def _closing_audiences(
    session: AsyncSession,
    event: str,
    deal: Record,
    actor: Actor,
    *,
    live: list[UUID],
    details: dict[str, Any],
) -> list[_Audience]:
    """Facts about the whole deal, its parties, its assignees and its support."""
    initiator, dealer = deal["initiator_company_id"], deal["dealer_company_id"]
    if event == NotifyEvent.RESET:
        previous = _present(*details.get("previous_lc_company_ids", ()))
        return [_Audience(Scope.PREVIOUS_LCS, previous)]
    if event == NotifyEvent.CONFIRMED:
        distributor = await access_repo.distributor_of_dealer(session, dealer) if dealer else None
        parties = _present(initiator, dealer, deal["leasing_company_id"], distributor)
        return [_Audience(Scope.ALL_PARTIES, parties)]
    if event == NotifyEvent.CANCELLED:
        # A draft that never left its initiator concerns nobody else.
        sent = deal["sent_at"] is not None
        parties = _present(initiator, *_other_side(deal, initiator, live)) if sent else []
        return [_Audience(Scope.ALL_PARTIES, parties)]
    if event == NotifyEvent.ASSIGNEES_CHANGED:
        company = details.get("assignee_company_id") or actor.company_id
        return [_Audience(Scope.ASSIGNMENT, _present(company), suffix=str(company))]
    request = details.get("support_request") or {}
    suffix = str(request["id"]) if request.get("id") else None
    if event == NotifyEvent.SUPPORT_REQUESTED:
        distributor = request.get("distributor_company_id")
        if not distributor:
            logger.warning("fast_deal_support_request_without_distributor")
        return [_Audience(Scope.DISTRIBUTOR, _present(distributor), suffix=suffix)]
    # SUPPORT_DECIDED: the dealer side of the deal (DD: the initiator, DL: the dealer).
    return [_Audience(Scope.DEALER, _present(dealer), suffix=suffix)]


async def _selection_audiences(
    session: AsyncSession,
    event: str,
    deal: Record,
    invitations: list[Record],
    chosen: Record | None,
) -> list[_Audience]:
    """The chosen leasing company, and the others merely informed (never its terms)."""
    chosen_company = chosen["leasing_company_id"] if chosen else deal["leasing_company_id"]
    others = _present(
        *(
            item["leasing_company_id"]
            for item in invitations
            if item["status"] != LcStatus.REJECTED
            and item["leasing_company_id"] != chosen_company
        )
    )
    audiences: list[_Audience] = []
    if chosen_company:
        terms: dict[str, Any] = {}
        if event == NotifyEvent.OFFER_SELECTED:
            offer_id = (chosen or {}).get("current_offer_id") or deal["final_offer_id"]
            terms = await _offer_terms(session, offer_id)
        audiences.append(_Audience(Scope.SELECTED_LC, _present(chosen_company), "selected", terms))
    audiences.append(_Audience(Scope.OTHER_LCS, others, "others"))
    return audiences


# ------------------------------------------------------------------------------- facts

async def _company_names(session: AsyncSession, companies: Iterable[Any]) -> dict[UUID, str]:
    ids = _present(*companies)
    briefs: dict[UUID, Record] = await access_repo.company_briefs(session, ids)
    return {company: brief["name"] for company, brief in briefs.items()}


async def _facts(
    session: AsyncSession,
    event: str,
    deal: Record,
    actor: Actor,
    *,
    version: int,
    details: dict[str, Any],
    lc_application: Record | None,
) -> dict[str, Any]:
    """The part of the payload that every addressee of the event shares."""
    facts: dict[str, Any] = {
        "source_type": deal["source_type"],
        "deal_status": deal["status"],
        "deal_version": version,
        "review_cycle": deal["review_cycle"],
    }
    assignee_company = details.get("assignee_company_id") or actor.company_id
    names = await _company_names(
        session,
        [
            actor.company_id,
            None if event in _NO_BUSINESS_DATA else deal["client_company_id"],
            assignee_company if event == NotifyEvent.ASSIGNEES_CHANGED else None,
        ],
    )
    facts["actor_company_name"] = names.get(actor.company_id) if actor.company_id else None
    if event == NotifyEvent.ASSIGNEES_CHANGED:
        facts |= await _assignment_facts(
            session, deal, names.get(UUID(str(assignee_company))), assignee_company, details
        )
        return facts
    if event == NotifyEvent.RESET:
        return facts
    facts["client_name"] = names.get(deal["client_company_id"])
    vehicles: list[Record] = await repo.list_vehicles(session, deal["id"])
    if event in _SUPPORT_EVENTS:
        facts["support_request"] = payload_support_request(
            details.get("support_request") or {}, vehicles
        )
        return facts
    final = event in {NotifyEvent.CONFIRMED, NotifyEvent.CHANGES_ACCEPTED}
    total = deal["confirmed_amount"] if final and deal["confirmed_amount"] else deal["vehicles_total"]
    facts |= {
        "vehicles": payload_vehicles(vehicles),
        "vehicles_count": len(vehicles),
        "vehicles_total": wire(total),
    }
    if event == NotifyEvent.SENT:
        facts["terms"] = payload_terms(deal)
    elif final:
        facts["terms"] = payload_terms(deal, prefix="final_")
    if event in _REASON_EVENTS:
        facts["reason"] = _reason(event, deal, details, lc_application)
    if event == NotifyEvent.CHANGES_SENT:
        facts["changes"] = payload_changes(details.get("changes") or [])
        facts["comment"] = clip(details.get("comment"))
    return facts


def _reason(
    event: str, deal: Record, details: dict[str, Any], lc_application: Record | None
) -> str | None:
    """The refusal text given by the actor; the stored one when the caller sent none."""
    if text := clip(details.get("reason")):
        return text
    if event == NotifyEvent.LC_REJECTED:
        return clip((lc_application or {}).get("rejection_reason"))
    return clip(deal.get("status_reason"))


async def _assignment_facts(
    session: AsyncSession,
    deal: Record,
    company_name: str | None,
    company: Any,
    details: dict[str, Any],
) -> dict[str, Any]:
    """Who is assigned now (names for the administrators) and who just lost the deal."""
    rows: list[Record] = await access_repo.list_assignees(session, deal["id"])
    return {
        "assignee_company_id": str(company),
        "assignee_company_name": company_name,
        "assignees": [
            {"user_id": str(row["user_id"]), "role": row["role"], "name": row["user_name"]}
            for row in rows
            if str(row["company_id"]) == str(company)
        ],
        "previous_user_ids": [str(item) for item in details.get("previous_user_ids") or []],
    }
