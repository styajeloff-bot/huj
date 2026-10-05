"""The section list of fast deals, its filter dropdowns and one card.

Everything is restricted by the actor's scope on the server first; filters narrow the
visible set and never widen it. What a row reveals depends on the viewer: an invited
leasing company does not learn who else was invited or who was chosen.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import ensure_membership
from application.fast_deals.actor import Actor
from application.fast_deals.card import scope_of, visible_assignees
from application.queries.fast_deals.card import handle_get_fast_deal
from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.values import DealStatus, Role, SourceType
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_list_repository as list_repo

Record = dict[str, Any]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
_MAX_TEXT = 64
# Who may narrow the list by a leasing company or by a dealer (spec §3.1).
_LEASING_FILTER_ROLES = frozenset({Role.DEALER, Role.PLATFORM})
_DEALER_FILTER_ROLES = frozenset({Role.LEASING_COMPANY, Role.DISTRIBUTOR, Role.PLATFORM})
_SOURCE_TYPES = frozenset(item.value for item in SourceType)
_STATUSES = frozenset(item.value for item in DealStatus)


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text[:_MAX_TEXT] if text else None


def _uuid(value: Any, field: str) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise FastDealValidationError("Некорректный идентификатор", field=field) from exc


def _choice(value: Any, allowed: frozenset[str], field: str) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if text not in allowed:
        raise FastDealValidationError("Недопустимое значение фильтра", field=field)
    return text


def clean_filters(actor: Actor, raw: Mapping[str, Any]) -> access_repo.Filters:
    """Known filters only; the leasing-company and dealer filters follow the role.

    A filter that does not belong to the actor's role is dropped: an invited leasing
    company must not probe who else was invited by filtering on a competitor.
    """
    cleaned: access_repo.Filters = {}
    number = _text(raw.get("number"))
    if number:
        cleaned["number"] = number
    inn = _text(raw.get("client_inn"))
    if inn:
        cleaned["client_inn"] = inn
    client = _uuid(raw.get("client_company_id"), "client_company_id")
    if client is not None:
        cleaned["client_company_id"] = client
    leasing = _uuid(raw.get("leasing_company_id"), "leasing_company_id")
    if leasing is not None and actor.role in _LEASING_FILTER_ROLES:
        cleaned["leasing_company_id"] = leasing
    dealer = _uuid(raw.get("dealer_company_id"), "dealer_company_id")
    if dealer is not None and actor.role in _DEALER_FILTER_ROLES:
        cleaned["dealer_company_id"] = dealer
    source = _choice(raw.get("source_type"), _SOURCE_TYPES, "source_type")
    if source:
        cleaned["source_type"] = source
    status = _choice(raw.get("status"), _STATUSES, "status")
    if status:
        cleaned["status"] = status
    return cleaned


def _party_brief(company_id: UUID | None, name: str | None) -> Record | None:
    if company_id is None:
        return None
    return {"id": company_id, "name": name or "", "inn": None}


def list_item(row: Record, assignees: list[Record], actor: Actor) -> Record:
    """One list row (``FastDealListItem``) as this actor may see it."""
    lc_view = actor.role == Role.LEASING_COMPANY
    dd = row["source_type"] == SourceType.DEALER_TO_LEASING
    leasing = _party_brief(row["leasing_company_id"], row["leasing_company_name"])
    invited = row["invited_lc_count"]
    if lc_view:
        # Only its own invitation is visible to a leasing company, and only it can be chosen.
        if row["leasing_company_id"] != actor.company_id:
            leasing = None
        invited = 1 if dd else 0
    return {
        "id": row["id"],
        "display_number": row["display_number"],
        "source_type": row["source_type"],
        "status": row["status"],
        "client": {
            "id": row["client_company_id"],
            "name": row["client_name"],
            "inn": row["client_inn"],
        },
        "initiator_company": _party_brief(
            row["initiator_company_id"], row["initiator_company_name"]
        ),
        "dealer_company": _party_brief(row["dealer_company_id"], row["dealer_company_name"]),
        "leasing_company": leasing,
        "invited_lc_count": invited,
        "vehicle_count": row["vehicle_count"],
        "vehicles_total": row["vehicles_total"],
        "assignees": visible_assignees(
            assignees, row, role=actor.role, company_id=actor.company_id
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": "fast_deal",
    }


async def load_list_items(
    session: AsyncSession,
    actor: Actor,
    *,
    filters: access_repo.Filters,
    limit: int,
    offset: int,
) -> tuple[list[Record], int]:
    """Visible deals newest first as list rows, and the total of all matches."""
    found: tuple[list[Record], int] = await access_repo.list_deals(
        session, scope=scope_of(actor), filters=filters, limit=limit, offset=offset
    )
    rows, total = found
    assignees: dict[Any, list[Record]] = await list_repo.assignees_by_deal(
        session, [row["id"] for row in rows]
    )
    return [list_item(row, assignees.get(row["id"], []), actor) for row in rows], total


async def handle_list_fast_deals(
    actor: Actor,
    filters: Mapping[str, Any],
    page: int,
    page_size: int,
    session: AsyncSession,
) -> Record:
    """``{"items", "total", "page", "page_size"}`` for ``GET /api/v1/fast-deals``."""
    if page < 1:
        raise FastDealValidationError("Номер страницы начинается с 1", field="page")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise FastDealValidationError(
            f"Размер страницы — от 1 до {MAX_PAGE_SIZE}", field="page_size"
        )
    await ensure_membership(session, actor)
    items, total = await load_list_items(
        session,
        actor,
        filters=clean_filters(actor, filters),
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def handle_filter_options(actor: Actor, session: AsyncSession) -> Record:
    """Companies of the actor's visible deals for the filter dropdowns.

    The leasing-company dropdown exists for the dealer and the platform only, the
    dealer dropdown for the others: the repository lists every invited company of a
    visible deal, which an invited leasing company must not see.
    """
    await ensure_membership(session, actor)
    options: Record = await access_repo.filter_options(session, scope=scope_of(actor))
    if actor.role not in _LEASING_FILTER_ROLES:
        options["leasing_companies"] = []
    if actor.role not in _DEALER_FILTER_ROLES:
        options["dealers"] = []
    return options


__all__ = [
    "clean_filters",
    "handle_filter_options",
    "handle_get_fast_deal",
    "handle_list_fast_deals",
    "list_item",
    "load_list_items",
]
