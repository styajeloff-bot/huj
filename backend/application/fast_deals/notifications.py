"""Transactional-outbox notifications of the deal (implemented by the notifications owner).

Events are appended in the caller's transaction (inbox and e-mail follow after the
commit). Recipients are the party's primary and additional assignees, else its
company administrators; the client is never notified. Deduplication key:
event + deal + version (+ recipient scope).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor

Record = dict[str, Any]


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

    Known ``extra`` keys: ``reason``, ``previous_lc_company_ids`` (reset),
    ``assignee_company_id`` (assignment), ``support_request`` (support events),
    ``changes`` (dealer changes in DL).
    """
    raise NotImplementedError
