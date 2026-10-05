"""Fast deals inside the shared «Мои заявки» lists (spec §3.1).

The ordinary lists of a dealer, a distributor, a leasing company and the platform
stay as they are; this module splices the visible fast deals into them:

* ``kind=application`` — ordinary applications only, ``kind=fast_deal`` — fast deals only;
* without ``kind`` the union is returned, except that a filter of the ORDINARY
  dictionaries (status, application source) leaves the fast deals out: their statuses
  are their own and are never mixed with the application ones;
* sort, page and ``total`` are computed over the union: the newest ``page * limit``
  rows of each source are merged by the sort key of their own list, then sliced. The
  total is the sum of both totals.

Ordinary rows get ``kind='application'``. A fast row is flat (the fields of
``FastDealListItem``) with ``kind='fast_deal'``, ``link_url`` to its own card and a
few keys that ordinary rows also have (``company_id``, ``name``, ``total_amount``),
so a consumer that does not know the kind still shows something sensible. Money in a
fast row is an exact decimal string: the existing routers encode with
``jsonable_encoder``, which would turn a ``Decimal`` into a float.

The client's list is not touched: a client has no access to fast deals.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from application.queries.fast_deals.list_deals import load_list_items
from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.money import wire
from domain.fast_deals.values import VISIBLE_ROLES, Role
from infrastructure.repositories import fast_deal_access_repository as access_repo

Record = dict[str, Any]
SortKey = tuple[datetime, datetime]
OrdinaryFetch = Callable[[int, int], Awaitable[tuple[list[Record], int]]]

KIND_APPLICATION = "application"
KIND_FAST_DEAL = "fast_deal"
KINDS = frozenset({KIND_APPLICATION, KIND_FAST_DEAL})
# Lists whose ordinary side is a dealer's or a distributor's «Мои заявки».
APPLICATION_LIST_ROLES = frozenset({Role.DEALER, Role.DISTRIBUTOR})
# A union page needs the head of both sources; deeper windows are not served.
MAX_MERGE_WINDOW = 2000

_EARLIEST = datetime.min.replace(tzinfo=UTC)
# The platform scope sees every sent deal and never looks at the user.
_PLATFORM_LIST_USER = UUID(int=0)
_SEARCH_LENGTH = 64


def validate_kind(kind: str | None) -> None:
    if kind is not None and kind not in KINDS:
        raise FastDealValidationError("Недопустимый вид заявки", field="kind")


async def resolve_list_actor(
    session: AsyncSession, *, user_id: UUID | None, role: str, company_id: UUID | None
) -> Actor | None:
    """The actor for the fast-deal side of a list, or ``None`` when it has no such side.

    The role must have the section at all (never a client) and a blocked membership
    grants nothing. The administrator flag comes from the current membership, not
    from the request.
    """
    if role not in VISIBLE_ROLES:
        return None
    if role == Role.PLATFORM:
        return Actor(user_id=user_id or _PLATFORM_LIST_USER, role=role, company_id=None)
    if user_id is None or company_id is None:
        return None
    membership: Record | None = await access_repo.get_membership(session, user_id, company_id)
    if membership is not None and not membership["is_active"]:
        return None
    sub_role = membership["sub_role"] if membership is not None else None
    return Actor(user_id=user_id, role=role, company_id=company_id, sub_role=sub_role)


# ------------------------------------------------------------------------ sort keys

def _aware(value: Any) -> datetime:
    if not isinstance(value, datetime):
        return _EARLIEST
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def activity_key(row: Record) -> SortKey:
    """Dealer / distributor list: ``coalesce(updated_at, created_at)``, then ``created_at``."""
    return _aware(row.get("updated_at") or row.get("created_at")), _aware(row.get("created_at"))


def created_key(row: Record) -> SortKey:
    """Admin list (and every fast deal): ``created_at``."""
    created = _aware(row.get("created_at"))
    return created, created


def lc_entry_key(entry: Record) -> SortKey:
    """LC list: the link's activity first, then the application's own times."""
    link: Record = entry.get("link") or {}
    application: Record = entry.get("application") or {}
    primary = (
        link.get("updated_at")
        or link.get("submitted_at")
        or application.get("updated_at")
        or application.get("created_at")
        or link.get("created_at")
    )
    return _aware(primary), _aware(application.get("created_at"))


# --------------------------------------------------------------------------- rows

def union_row(item: Record) -> Record:
    """A fast-deal list item as a row of a shared list."""
    total = wire(item["vehicles_total"])
    return {
        **item,
        "vehicles_total": total,
        "company_id": item["client"]["id"],
        "name": item["client"]["name"],
        "total_amount": total,
        "link_url": f"/workspace/fast-deals/{item['id']}",
    }


def _tag(rows: list[Record]) -> list[Record]:
    for row in rows:
        row["kind"] = KIND_APPLICATION
    return rows


async def _fast_rows(
    session: AsyncSession, actor: Actor, *, search: str | None, limit: int, offset: int
) -> tuple[list[Record], int]:
    filters: access_repo.Filters = {}
    text = (search or "").strip()
    if text:
        # The number carries the client's INN, so it covers a search by INN too.
        filters["number"] = text[:_SEARCH_LENGTH]
    items, total = await load_list_items(
        session, actor, filters=filters, limit=limit, offset=offset
    )
    return [union_row(item) for item in items], total


def _merge(
    ordinary: list[Record], fast: list[Record], ordinary_key: Callable[[Record], SortKey]
) -> list[Record]:
    """Two newest-first lists into one; on a tie the ordinary row comes first."""
    merged: list[Record] = []
    left = right = 0
    while left < len(ordinary) and right < len(fast):
        if ordinary_key(ordinary[left]) >= created_key(fast[right]):
            merged.append(ordinary[left])
            left += 1
        else:
            merged.append(fast[right])
            right += 1
    merged.extend(ordinary[left:])
    merged.extend(fast[right:])
    return merged


async def merged_page(
    session: AsyncSession,
    *,
    actor: Actor | None,
    kind: str | None,
    ordinary_filtered: bool,
    search: str | None,
    page: int,
    limit: int,
    fetch_ordinary: OrdinaryFetch,
    ordinary_key: Callable[[Record], SortKey],
) -> tuple[list[Record], int]:
    """One page of a shared list and its total.

    ``actor`` is ``None`` for a role without fast deals; ``ordinary_filtered`` says that
    a status or source filter of the ordinary dictionaries is set; ``fetch_ordinary``
    returns ``(rows, total)`` of the existing list for ``(page, limit)``.
    """
    validate_kind(kind)
    if kind == KIND_FAST_DEAL:
        if actor is None or ordinary_filtered:
            return [], 0
        return await _fast_rows(
            session, actor, search=search, limit=limit, offset=(page - 1) * limit
        )
    if actor is None or ordinary_filtered or kind == KIND_APPLICATION:
        rows, total = await fetch_ordinary(page, limit)
        return _tag(rows), total

    window = min(page * limit, MAX_MERGE_WINDOW)
    ordinary, ordinary_total = await fetch_ordinary(1, window)
    fast, fast_total = await _fast_rows(session, actor, search=search, limit=window, offset=0)
    merged = _merge(_tag(ordinary), fast, ordinary_key)
    start = (page - 1) * limit
    return merged[start : start + limit], ordinary_total + fast_total
