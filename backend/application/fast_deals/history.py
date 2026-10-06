"""Audit trail and the single version bump of one command."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]


async def bump_and_log(
    session: AsyncSession,
    deal: Record,
    actor: Actor,
    event_type: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    changes: Record | None = None,
    lc_application_id: UUID | None = None,
    review_cycle: int | None = None,
    version: int | None = None,
) -> int:
    """Advance the parent version once per command and record the event.

    A command with several events passes the version returned by the first call to
    the rest, so all of them describe the same resulting version.
    """
    if version is None:
        version = await repo.bump_version(session, deal["id"])
    await repo.append_history(
        session,
        deal_id=deal["id"],
        event_type=event_type,
        actor_user_id=actor.user_id,
        actor_company_id=actor.company_id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        changes=changes,
        lc_application_id=lc_application_id,
        deal_version=version,
        review_cycle=review_cycle if review_cycle is not None else deal.get("review_cycle"),
    )
    return version


def field_changes(before: Record, after: Record, fields: tuple[str, ...]) -> Record:
    """Flat ``{field: {before, after}}`` for the fields that really changed."""
    changed: Record = {}
    for name in fields:
        if before.get(name) != after.get(name):
            changed[name] = {"before": _plain(before.get(name)), "after": _plain(after.get(name))}
    return changed


def _plain(value: Any) -> Any:
    """History is JSON: money and ids become strings, exactly."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    return value
