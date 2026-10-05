"""Dealer group CRUD commands."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.dealer_group import DealerGroup
from domain.errors import (
    DealerGroupAlreadyExistsError,
    DealerGroupNotFoundError,
    DealerNotFoundError,
    DistributorNotFoundError,
    InvalidDealerGroupError,
)
from infrastructure.repositories import dealer_group_repository as repo
from infrastructure.repositories import distributor_dealer_repository as dist_repo


@dataclass
class CreateDealerGroupCommand:
    name: str
    distributor_company_id: UUID
    actor_id: UUID
    description: str | None = None
    dealer_company_ids: list[UUID] = field(default_factory=list)


@dataclass
class UpdateDealerGroupCommand:
    group_id: UUID
    name: str
    distributor_company_id: UUID
    actor_id: UUID
    description: str | None = None
    dealer_company_ids: list[UUID] = field(default_factory=list)


@dataclass
class DeleteDealerGroupCommand:
    group_id: UUID
    actor_id: UUID


async def handle_create_dealer_group(
    cmd: CreateDealerGroupCommand, session: AsyncSession
) -> dict[str, Any]:
    _ensure_no_duplicate_dealers(cmd.dealer_company_ids)
    group = DealerGroup(
        group_id=None,
        name=cmd.name,
        description=cmd.description,
        distributor_company_id=cmd.distributor_company_id,
        dealer_company_ids=list(cmd.dealer_company_ids or []),
        created_by=cmd.actor_id,
    )
    group.ensure_valid()

    await _ensure_group_refs(session, group)
    if await repo.name_exists(
        session,
        group.name,
        distributor_company_id=cast("UUID", group.distributor_company_id),
    ):
        raise DealerGroupAlreadyExistsError(group.name)

    group_id = await repo.create_dealer_group(
        session,
        name=group.name,
        description=group.description,
        distributor_company_id=cast("UUID", group.distributor_company_id),
        created_by=cmd.actor_id,
    )
    await repo.replace_members(
        session,
        group_id,
        group.dealer_company_ids,
        created_by=cmd.actor_id,
    )

    saved = await repo.get_by_id(session, group_id)
    assert saved is not None
    return cast("dict[str, Any]", saved)


async def handle_update_dealer_group(
    cmd: UpdateDealerGroupCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.group_id)
    if existing is None:
        raise DealerGroupNotFoundError(cmd.group_id)

    _ensure_no_duplicate_dealers(cmd.dealer_company_ids)
    group = DealerGroup(
        group_id=cmd.group_id,
        name=cmd.name,
        description=cmd.description,
        distributor_company_id=cmd.distributor_company_id,
        dealer_company_ids=list(cmd.dealer_company_ids or []),
        created_by=existing.get("created_by"),
        updated_by=cmd.actor_id,
    )
    group.ensure_valid()

    await _ensure_group_refs(session, group)
    if await repo.name_exists(
        session,
        group.name,
        distributor_company_id=cast("UUID", group.distributor_company_id),
        exclude_id=cmd.group_id,
    ):
        raise DealerGroupAlreadyExistsError(group.name)

    updated = await repo.update_dealer_group(
        session,
        cmd.group_id,
        name=group.name,
        description=group.description,
        distributor_company_id=cast("UUID", group.distributor_company_id),
        updated_by=cmd.actor_id,
    )
    if not updated:
        raise DealerGroupNotFoundError(cmd.group_id)
    await repo.replace_members(
        session,
        cmd.group_id,
        group.dealer_company_ids,
        created_by=cmd.actor_id,
    )
    saved = await repo.get_by_id(session, cmd.group_id)
    assert saved is not None
    return cast("dict[str, Any]", saved)


async def handle_delete_dealer_group(
    cmd: DeleteDealerGroupCommand, session: AsyncSession
) -> dict[str, Any]:
    deleted = await repo.delete_dealer_group(
        session, cmd.group_id, updated_by=cmd.actor_id
    )
    if not deleted:
        raise DealerGroupNotFoundError(cmd.group_id)
    return {"id": cmd.group_id}


async def handle_distributor_can_manage_dealer_groups(
    distributor_company_id: UUID,
    session: AsyncSession,
) -> bool:
    return bool(await repo.distributor_can_manage_dealer_groups(
        session, distributor_company_id
    ))


async def _ensure_group_refs(
    session: AsyncSession, group: DealerGroup
) -> None:
    distributor_company_id = cast("UUID", group.distributor_company_id)
    if not await repo.distributor_company_exists(session, distributor_company_id):
        raise DistributorNotFoundError(distributor_company_id)

    existing_dealers = await repo.get_existing_dealer_company_ids(
        session,
        group.dealer_company_ids,
    )
    missing_dealers = [
        dealer for dealer in group.dealer_company_ids if dealer not in existing_dealers
    ]
    if missing_dealers:
        raise DealerNotFoundError(missing_dealers[0])

    if group.dealer_company_ids:
        linked_dealer_ids = set(
            await dist_repo.get_linked_dealer_ids(session, distributor_company_id)
        )
        if not set(group.dealer_company_ids).issubset(linked_dealer_ids):
            raise InvalidDealerGroupError("Дилер не входит в дилерскую сеть дистрибьютора")


def _ensure_no_duplicate_dealers(dealer_company_ids: list[UUID]) -> None:
    if len(set(dealer_company_ids)) != len(dealer_company_ids):
        raise InvalidDealerGroupError("Повторяющиеся дилеры в группе не допускаются")
