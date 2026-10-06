"""Role-scoped card of a deal: the one projection behind every response.

The card is built from the same ``DealContext`` that guards mutations, so what an
actor reads and what the server lets them do come from one resolved party.

Projections (spec §4, §6, §8.1):

* dealer side (the DD initiator, the DL dealer) and the platform: everything, including
  the support data of ``supports_view``;
* leasing company (an invited one in DD, the initiator in DL): the allow-listed
  position, only its own invitation and offer, filtered history and changes, and no
  support data in any field;
* distributor: the deal and its invitations without offers, support requests of its
  own, no private files and no changes of the history.

Money stays ``Decimal`` (the router writes exact strings); only ``etag`` is a string.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import DealContext, etag_for, load_context
from application.fast_deals.actor import Actor
from application.fast_deals.pending_changes import changes_for_card, jsonable_snapshot
from domain.fast_deals.money import money
from domain.fast_deals.projection import (
    deal_snapshot,
    diff_snapshots,
    project_history_event_for_lc,
    project_vehicle_for_lc,
)
from domain.fast_deals.values import (
    RESERVING_STATUSES,
    DealStatus,
    HistoryEvent,
    LcStatus,
    Party,
    Role,
    SourceType,
)
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_list_repository as list_repo
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

# Directory ids that an editing party needs to prefill the form of a position.
_EDITOR_IDS = (
    "product_id", "category_id", "mark_id", "model_id", "modification_id", "trim_id",
    "body_color_id",
)
_VEHICLE_FIELDS = (
    "id", "position", "vehicle_source_type", "vin", "vin_entered_manually", "mark_name",
    "model_name", "modification_name", "trim_name", "category_name", "body_color_name",
    "dealer_company_id", "final_price", "equipments", "services", "purposes", "regions",
    "item_status", "replaced_by_id", "is_reservable", "base_price", "adjustment_type",
    "adjustment_amount", "options_amount", "support_amount",
)
# The only keys taken from ``supports_view``: nothing unexpected reaches the response.
_SUPPORT_VIEW_KEYS = (
    "applied_supports", "support_request", "unaccounted_support", "can_request_support",
    "support_hint",
)
_FINAL_COLUMNS = (
    "final_total_amount", "final_down_payment", "final_down_payment_percent",
    "final_lease_term_months", "final_monthly_payment", "final_total_cost",
    "final_buyout_amount",
)
_OFFER_FIELDS = (
    "id", "down_payment", "down_payment_percent", "lease_term_months", "monthly_payment",
    "total_cost", "buyout_amount", "rate", "markup", "total_interest", "vat_refund",
    "profit_tax_savings", "total_savings", "optional_financial_terms", "pdf_file_id",
    "created_at",
)
_HISTORY_FIELDS = (
    "id", "event_type", "from_status", "to_status", "actor_name", "actor_company_name",
    "reason", "changes", "created_at",
)
_SELECTED = frozenset({LcStatus.SELECTED_BY_DEALER, LcStatus.CONFIRMED})
# DL: the statuses in which the dealer's changes against the sent state matter.
_CHANGE_REVIEW = frozenset(
    {DealStatus.PENDING_DEALER_CONFIRMATION, DealStatus.PENDING_LC_CHANGES_CONFIRMATION}
)
# A distributor keeps the details of its own support requests only: offers, files and
# other business changes of a deal stay out of its history.
_DISTRIBUTOR_DETAILS = frozenset(
    {
        HistoryEvent.SUPPORT_REQUESTED,
        HistoryEvent.SUPPORT_DECIDED,
        HistoryEvent.SUPPORT_ACCOUNTED,
    }
)
_DISTRIBUTOR_HIDDEN = frozenset(
    {
        HistoryEvent.FILE_UPLOADED,
        HistoryEvent.SUPPORT_APPLIED,
        HistoryEvent.SUPPORT_REMOVED,
    }
)


# ------------------------------------------------------------------------- shared helpers

def scope_of(actor: Actor) -> access_repo.Scope:
    """The repository scope of an actor (lists and group lookups)."""
    return access_repo.Scope(
        role=actor.role,
        company_id=actor.company_id,
        user_id=actor.user_id,
        is_company_admin=actor.is_company_admin,
    )


def company_brief(briefs: Mapping[UUID, Record], company_id: UUID | None) -> Record | None:
    """``{id, name, inn}`` of a company, ``None`` when the deal has no such party."""
    if company_id is None:
        return None
    known = briefs.get(company_id)
    if known is None:
        return {"id": company_id, "name": "", "inn": None}
    return {"id": company_id, "name": known["name"], "inn": known["inn"]}


def assignee_company_ids(
    deal: Mapping[str, Any], *, role: str, company_id: UUID | None
) -> set[UUID] | None:
    """Companies whose responsible employees the viewer may see; ``None`` means all.

    An invited leasing company never learns who works on the deal at its competitors,
    and a distributor only needs the dealer's contacts.
    """
    if role == Role.LEASING_COMPANY and deal["source_type"] == SourceType.DEALER_TO_LEASING:
        return {item for item in (deal["initiator_company_id"], company_id) if item is not None}
    if role == Role.DISTRIBUTOR:
        return {item for item in (deal["dealer_company_id"],) if item is not None}
    return None


def assignee_out(assignee: Mapping[str, Any]) -> Record:
    return {
        "company_id": assignee["company_id"],
        "user_id": assignee["user_id"],
        "user_name": assignee.get("user_name"),
        "role": assignee["role"],
    }


def visible_assignees(
    assignees: Iterable[Mapping[str, Any]],
    deal: Mapping[str, Any],
    *,
    role: str,
    company_id: UUID | None,
) -> list[Record]:
    allowed = assignee_company_ids(deal, role=role, company_id=company_id)
    return [
        assignee_out(item)
        for item in assignees
        if allowed is None or item["company_id"] in allowed
    ]


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


# ------------------------------------------------------------------------------ terms

def requested_terms(deal: Record) -> Record:
    """Terms as asked: the dealer's request in DD, the leasing company's in DL.

    ``calc_snapshot`` holds terms only (never support), so every party may see it.
    """
    snapshot: Mapping[str, Any] = deal.get("calc_snapshot") or {}
    down = deal.get("down_payment")
    return {
        "down_payment_mode": deal.get("down_payment_mode"),
        "down_payment": down,
        "down_payment_percent": deal.get("down_payment_percent"),
        "lease_term_months": deal.get("lease_term_months"),
        "monthly_payment": deal.get("monthly_payment"),
        "monthly_payment_is_manual": bool(deal.get("monthly_payment_is_manual")),
        "calculated_monthly_payment": deal.get("calculated_monthly_payment"),
        "buyout_amount": deal.get("buyout_amount"),
        "total_cost": _decimal(snapshot.get("total_cost")),
        "financing_amount": money(deal["vehicles_total"] - down) if down is not None else None,
    }


def blank_terms() -> Record:
    """Terms with nothing in them, for a viewer who must not read the real ones."""
    return {
        "down_payment_mode": None,
        "down_payment": None,
        "down_payment_percent": None,
        "lease_term_months": None,
        "monthly_payment": None,
        "monthly_payment_is_manual": False,
        "calculated_monthly_payment": None,
        "buyout_amount": None,
        "total_cost": None,
        "financing_amount": None,
    }


def final_terms(deal: Record) -> Record | None:
    """Terms fixed at confirmation; ``None`` until they exist."""
    if all(deal.get(name) is None for name in _FINAL_COLUMNS):
        return None
    return {
        "down_payment_mode": None,
        "down_payment": deal.get("final_down_payment"),
        "down_payment_percent": deal.get("final_down_payment_percent"),
        "lease_term_months": deal.get("final_lease_term_months"),
        "monthly_payment": deal.get("final_monthly_payment"),
        "monthly_payment_is_manual": False,
        "calculated_monthly_payment": None,
        "buyout_amount": deal.get("final_buyout_amount"),
        "total_cost": deal.get("final_total_cost"),
        "financing_amount": deal.get("final_total_amount"),
    }


# -------------------------------------------------------------------------- positions

def _vehicle_view(
    vehicle: Record,
    *,
    ctx: DealContext,
    lc_view: bool,
    support_view: Mapping[str, Any] | None,
) -> Record:
    editor = ctx.party in {Party.INITIATOR, Party.DEALER}
    if lc_view:
        view = project_vehicle_for_lc(vehicle)
    else:
        view = {name: vehicle.get(name) for name in _VEHICLE_FIELDS}
        view["reserved"] = bool(vehicle["is_reservable"]) and ctx.status in RESERVING_STATUSES
        if support_view:
            view.update({key: support_view[key] for key in _SUPPORT_VIEW_KEYS if key in support_view})
    if editor:
        view.update({name: vehicle.get(name) for name in _EDITOR_IDS})
    if editor or ctx.party == Party.PLATFORM:
        # A request-priced listing needs an explicit price: the UI offers editing it.
        snapshot: Mapping[str, Any] = vehicle.get("catalog_snapshot") or {}
        view["price_on_request"] = bool(snapshot.get("price_on_request"))
    return view


# ----------------------------------------------------------------- invitations, offers

def _offer_view(offer: Record) -> Record:
    view = {name: offer.get(name) for name in _OFFER_FIELDS}
    view["financing_amount"] = offer["total_amount"]
    return view


def _visible_invitations(ctx: DealContext) -> list[Record]:
    """An invited leasing company sees its own invitation only."""
    if ctx.party == Party.LEASING:
        return [ctx.lc_application] if ctx.lc_application is not None else []
    return list(ctx.lc_applications)


def _invitation_views(
    ctx: DealContext,
    briefs: Mapping[UUID, Record],
    offers: Mapping[UUID, Record],
) -> list[Record]:
    """Invitations of the current cycle as this party may see them."""
    party = ctx.party
    invitations = _visible_invitations(ctx)
    views: list[Record] = []
    for item in invitations:
        offer = offers.get(item["current_offer_id"]) if item["current_offer_id"] else None
        # A refused invitation no longer offers anything to choose; its own company
        # still reads what it sent.
        if offer is not None and item["status"] == LcStatus.REJECTED and party != Party.LEASING:
            offer = None
        if party == Party.DISTRIBUTOR:
            offer = None
        views.append(
            {
                "id": item["id"],
                "leasing_company": company_brief(briefs, item["leasing_company_id"]),
                "status": item["status"],
                "offer": _offer_view(offer) if offer is not None else None,
                "rejection_reason": None if party == Party.DISTRIBUTOR else item["rejection_reason"],
                "selected": item["status"] in _SELECTED,
            }
        )
    return views


# ----------------------------------------------------------------------------- history

def _history_row(
    event: Mapping[str, Any], *, detailed: bool, lc_names: Mapping[UUID, str]
) -> Record:
    row = {name: event.get(name) for name in _HISTORY_FIELDS}
    if detailed:
        application_id = event.get("lc_application_id")
        row["lc_application_id"] = application_id
        row["lc_company_name"] = lc_names.get(application_id) if application_id else None
        row["review_cycle"] = event.get("review_cycle")
        row["deal_version"] = event.get("deal_version")
    return row


def _hidden_from_leasing(
    event: Mapping[str, Any],
    *,
    own_ids: set[UUID],
    first_invited: datetime | None,
    company_id: UUID | None,
) -> bool:
    """Events of another invitation, from before the own one, or another party's files."""
    linked = event.get("lc_application_id")
    if linked is not None and linked not in own_ids:
        return True
    if first_invited is not None and event["created_at"] < first_invited:
        return True
    return bool(
        event["event_type"] == HistoryEvent.FILE_UPLOADED
        and linked is None
        and event.get("actor_company_id") != company_id
    )


def _hidden_from_others(party: Party, kind: str, *, before_sending: bool) -> bool:
    if party == Party.DEALER:
        return before_sending or kind == HistoryEvent.SPLIT
    if party == Party.PLATFORM:
        return kind == HistoryEvent.FILE_UPLOADED
    if party == Party.DISTRIBUTOR:
        return before_sending or kind in _DISTRIBUTOR_HIDDEN
    return False


def _history(
    ctx: DealContext,
    events: list[Record],
    invitations: list[Record],
    lc_names: Mapping[UUID, str],
) -> list[Record]:
    """History for this party, oldest first.

    A leasing company sees neither support events nor values, nothing that belongs to
    another invitation (their names and offers), and nothing from before its own
    invitation. A DL dealer starts at the sending and never learns about the split. A
    distributor reads only the support requests of its own with their details.
    """
    actor, party = ctx.actor, ctx.party
    lc_view = actor.role == Role.LEASING_COMPANY
    own_ids = {item["id"] for item in invitations if item["leasing_company_id"] == actor.company_id}
    first_invited = min(
        (item["created_at"] for item in invitations if item["id"] in own_ids), default=None
    )
    sent_index = next(
        (index for index, event in enumerate(events) if event["event_type"] == HistoryEvent.SENT),
        0,
    )
    rows: list[Record] = []
    for index, original in enumerate(events):
        event: Mapping[str, Any] = original
        if party == Party.LEASING:
            if _hidden_from_leasing(
                original, own_ids=own_ids, first_invited=first_invited, company_id=actor.company_id
            ):
                continue
        elif _hidden_from_others(
            party, original["event_type"], before_sending=index < sent_index
        ):
            continue
        if party == Party.DISTRIBUTOR and original["event_type"] not in _DISTRIBUTOR_DETAILS:
            # Refusal texts of the parties stay between them; a cancellation is public.
            keep = original["event_type"] == HistoryEvent.CANCELLED
            event = {**original, "changes": None, "reason": original.get("reason") if keep else None}
        if lc_view:
            projected = project_history_event_for_lc(event)
            if projected is None:
                continue
            event = projected
        rows.append(_history_row(event, detailed=not lc_view, lc_names=lc_names))
    return rows


def _status_reason(ctx: DealContext) -> str | None:
    """Refusal or cancellation text as this party may read it.

    A DD deal is refused with the text of the last leasing company that answered: its
    competitors read their own reason only, and a distributor reads no refusal at all.
    """
    reason: str | None = ctx.deal["status_reason"]
    if ctx.party == Party.DISTRIBUTOR:
        return reason if ctx.status == DealStatus.CANCELLED else None
    if ctx.party == Party.LEASING and ctx.status == DealStatus.REJECTED:
        own = ctx.lc_application
        refused = own is not None and own["status"] == LcStatus.REJECTED
        return own["rejection_reason"] if own is not None and refused else None
    return reason


# ------------------------------------------------------------------------ pending changes

def _pending_changes(ctx: DealContext, *, lc_view: bool) -> list[dict[str, Any]]:
    """DL: what the dealer changed against the state the leasing company sent."""
    deal = ctx.deal
    sent: Mapping[str, Any] | None = deal.get("sent_snapshot")
    if ctx.is_dd or ctx.status not in _CHANGE_REVIEW or sent is None:
        return []
    changes = diff_snapshots(sent, jsonable_snapshot(deal_snapshot(ctx.vehicles)))
    return changes_for_card(changes, leasing_view=lc_view)


# ------------------------------------------------------------------------------- card

async def _group_deals(session: AsyncSession, ctx: DealContext) -> list[Record]:
    group_id = ctx.deal["group_id"]
    if ctx.is_dd or group_id is None or ctx.party not in {Party.INITIATOR, Party.PLATFORM}:
        return []
    rows: list[Record] = await list_repo.list_group_deals(
        session, group_id=group_id, scope=scope_of(ctx.actor)
    )
    return [
        {
            "id": row["id"],
            "display_number": row["display_number"],
            "status": row["status"],
            "dealer_company": (
                None
                if row["dealer_company_id"] is None
                else {
                    "id": row["dealer_company_id"],
                    "name": row["dealer_company_name"],
                    "inn": row["dealer_company_inn"],
                }
            ),
            "vehicles_total": row["vehicles_total"],
            "vehicle_count": row["vehicle_count"],
            "is_current": row["id"] == ctx.deal_id,
        }
        for row in rows
    ]


async def build_card(session: AsyncSession, actor: Actor, deal_id: UUID) -> Record:
    """The card as the actor may see it: projection, ``allowed_actions``, ``etag``.

    Raises ``FastDealNotFoundError`` when the actor may not see the deal.
    """
    # Imported lazily: both modules build on the same access layer as this one.
    from application.fast_deals import file_access, supports_view

    ctx = await load_context(session, actor, deal_id, lock=False)
    deal, party = ctx.deal, ctx.party
    lc_view = actor.role == Role.LEASING_COMPANY

    invitations: list[Record] = (
        await repo.list_lc_applications(session, deal["id"], current_cycle_only=False)
        if ctx.is_dd
        else []
    )
    if lc_view:
        invitations = [item for item in invitations if item["leasing_company_id"] == actor.company_id]
    company_ids = {deal["client_company_id"], deal["initiator_company_id"]}
    company_ids.update(
        item
        for item in (deal["dealer_company_id"], deal["leasing_company_id"])
        if item is not None
    )
    company_ids.update(item["leasing_company_id"] for item in invitations)
    briefs: dict[UUID, Record] = await access_repo.company_briefs(session, list(company_ids))

    offer_rows: list[Record] = await repo.list_offers(
        session, [item["id"] for item in _visible_invitations(ctx)]
    )
    offers = {item["id"]: item for item in offer_rows}

    support_views: dict[UUID, dict[str, Any]] = (
        {} if lc_view else await supports_view.build_vehicle_support_views(session, ctx)
    )
    vehicles = [
        _vehicle_view(item, ctx=ctx, lc_view=lc_view, support_view=support_views.get(item["id"]))
        for item in ctx.vehicles
    ]

    events: list[Record] = await repo.list_history(session, deal["id"])
    lc_names = {
        item["id"]: briefs[item["leasing_company_id"]]["name"]
        for item in invitations
        if item["leasing_company_id"] in briefs
    }
    # A distributor sees a draft only to decide a support request addressed to it: it
    # reads the deal data and its own request, never files, invitations or terms.
    draft_for_distributor = party == Party.DISTRIBUTOR and ctx.status == DealStatus.DRAFT
    files: list[Record] = (
        [] if draft_for_distributor else await file_access.load_visible_files(session, ctx)
    )

    facts: dict[str, Any] = {}
    if not lc_view and party in {Party.INITIATOR, Party.DEALER, Party.DISTRIBUTOR}:
        facts = await supports_view.support_action_facts(session, ctx)

    client = company_brief(briefs, deal["client_company_id"]) or {}
    client["kpp"] = (briefs.get(deal["client_company_id"]) or {}).get("kpp")
    leasing_company = company_brief(briefs, deal["leasing_company_id"])
    if party == Party.LEASING and deal["leasing_company_id"] != actor.company_id:
        # The chosen competitor stays unnamed for the others.
        leasing_company = None
    # A distributor reads requested terms; the final ones of DD copy the chosen offer.
    # An invited leasing company that was not chosen must not read the chosen offer's terms.
    unchosen = (
        party == Party.LEASING
        and (ctx.lc_application is None or ctx.lc_application["status"] not in _SELECTED)
    )
    hide_final = draft_for_distributor or (party == Party.DISTRIBUTOR and ctx.is_dd) or unchosen
    shows_group = party in {Party.INITIATOR, Party.PLATFORM}

    return {
        "id": deal["id"],
        "display_number": deal["display_number"],
        "source_type": deal["source_type"],
        "status": deal["status"],
        "version": deal["version"],
        "etag": etag_for(deal),
        "review_cycle": deal["review_cycle"],
        "group_id": deal["group_id"] if shows_group else None,
        "client": client,
        "client_phone": deal["client_phone"],
        "initiator_company": company_brief(briefs, deal["initiator_company_id"]),
        "dealer_company": company_brief(briefs, deal["dealer_company_id"]),
        "leasing_company": leasing_company,
        "requested_terms": blank_terms() if draft_for_distributor else requested_terms(deal),
        "final_terms": None if hide_final else final_terms(deal),
        "vehicles_total": deal["vehicles_total"],
        "confirmed_amount": deal["confirmed_amount"],
        "has_pending_changes": bool(deal["has_pending_changes"]),
        "pending_changes": _pending_changes(ctx, lc_view=lc_view),
        "status_reason": _status_reason(ctx),
        "vehicles": vehicles,
        "lc_applications": [] if draft_for_distributor else _invitation_views(ctx, briefs, offers),
        "group_deals": await _group_deals(session, ctx),
        "files": files,
        "assignees": visible_assignees(
            ctx.assignees, deal, role=actor.role, company_id=actor.company_id
        ),
        "history": _history(ctx, events, invitations, lc_names),
        "allowed_actions": [action.value for action in ctx.actions(**facts)],
        "party": party.value,
        "sent_at": deal["sent_at"],
        "confirmed_at": deal["confirmed_at"],
        "created_at": deal["created_at"],
        "updated_at": deal["updated_at"],
    }
