"""Responsible employees of a party: one primary and at most one additional.

Only the administrator of a party's own company assigns that party's employees: the
initiator side, an invited or selected leasing company, or the DL dealer of the part.
It is an administrative exception, allowed in every status including ``confirmed`` and
``cancelled``: nothing but the assignees changes there, and the change is audited and
notified. The platform, a distributor and the counterparty never assign.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import notifications
from application.fast_deals.access import DealContext, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import FastDealAccessDeniedError, FastDealValidationError
from domain.fast_deals.values import AssigneeRole, HistoryEvent, NotifyEvent, Party
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]


@dataclass
class SetAssigneesCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    primary_user_id: UUID
    additional_user_id: UUID | None = None


def _by_role(assignees: list[Record]) -> dict[str, Record]:
    return {str(item["role"]): item for item in assignees}


def _user_of(item: Record | None) -> UUID | None:
    user_id: UUID | None = item["user_id"] if item is not None else None
    return user_id


def _display_name(item: Record | None) -> str | None:
    if item is None:
        return None
    return str(item.get("user_name") or item.get("user_email") or "Без имени")


async def _validate_users(
    session: AsyncSession, company_id: UUID, cmd: SetAssigneesCommand
) -> None:
    if cmd.additional_user_id is not None and cmd.additional_user_id == cmd.primary_user_id:
        raise FastDealValidationError(
            "Основной и дополнительный ответственные должны быть разными сотрудниками",
            field="additional_user_id",
        )
    requested = [cmd.primary_user_id]
    if cmd.additional_user_id is not None:
        requested.append(cmd.additional_user_id)
    members: set[UUID] = await access_repo.active_member_ids(session, company_id, requested)
    if cmd.primary_user_id not in members:
        raise FastDealValidationError(
            "Основной ответственный должен быть активным сотрудником вашей компании",
            field="primary_user_id",
        )
    if cmd.additional_user_id is not None and cmd.additional_user_id not in members:
        raise FastDealValidationError(
            "Дополнительный ответственный должен быть активным сотрудником вашей компании",
            field="additional_user_id",
        )


def _changes(before: dict[str, Record], after: dict[str, Record]) -> Record:
    """``primary`` / ``additional`` before and after, by employee name."""
    changes: Record = {}
    for role in (AssigneeRole.PRIMARY.value, AssigneeRole.ADDITIONAL.value):
        old, new = before.get(role), after.get(role)
        if _user_of(old) != _user_of(new):
            changes[role] = {"before": _display_name(old), "after": _display_name(new)}
    return changes


async def handle_set_assignees(cmd: SetAssigneesCommand, session: AsyncSession) -> dict[str, Any]:
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    company_id = _assigning_company(ctx)
    await _validate_users(session, company_id, cmd)

    current = _by_role([item for item in ctx.assignees if item["company_id"] == company_id])
    if (
        _user_of(current.get(AssigneeRole.PRIMARY.value)) == cmd.primary_user_id
        and _user_of(current.get(AssigneeRole.ADDITIONAL.value)) == cmd.additional_user_id
    ):
        # Nothing to change: no version bump, no history, no notification.
        return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}

    before_rows, after_rows = await access_repo.replace_company_assignees(
        session,
        deal_id=ctx.deal_id,
        company_id=company_id,
        primary_user_id=cmd.primary_user_id,
        additional_user_id=cmd.additional_user_id,
        assigned_by=cmd.actor.user_id,
    )
    before, after = _by_role(before_rows), _by_role(after_rows)
    own = ctx.lc_application
    version = await bump_and_log(
        session,
        ctx.deal,
        cmd.actor,
        HistoryEvent.ASSIGNEES_CHANGED,
        changes=_changes(before, after),
        lc_application_id=own["id"] if ctx.party == Party.LEASING and own else None,
    )
    fresh: Record | None = await repo.get_deal(session, ctx.deal_id)
    assert fresh is not None
    await notifications.notify(
        session,
        NotifyEvent.ASSIGNEES_CHANGED,
        fresh,
        cmd.actor,
        version=version,
        lc_application=own,
        extra={
            "assignee_company_id": company_id,
            "previous_user_ids": [item["user_id"] for item in before_rows],
            "user_ids": [item["user_id"] for item in after_rows],
        },
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


def _assigning_company(ctx: DealContext) -> UUID:
    """The actor's own party company, for an administrator of a participating party."""
    company_id = ctx.actor.company_id
    if company_id is None or Action.ASSIGN_EMPLOYEES not in ctx.actions():
        raise FastDealAccessDeniedError(
            "Ответственных назначает администратор компании, участвующей в сделке"
        )
    return company_id
