"""Upsert dealer group from CSV import using the company-based contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.support.create_dealer_group import (
    CreateDealerGroupCommand,
    UpdateDealerGroupCommand,
    handle_create_dealer_group,
    handle_update_dealer_group,
)
from infrastructure.repositories import dealer_group_repository as repo


@dataclass
class UpsertDealerGroupCommand:
    name: str
    distributor_company_id: UUID
    actor_id: UUID
    description: str | None = None
    dealer_company_ids: list[UUID] = field(default_factory=list)
    group_id: UUID | None = None


@dataclass
class UpsertDealerGroupResult:
    action: str  # "created" | "updated"
    group_id: UUID


async def handle_upsert_dealer_group(
    cmd: UpsertDealerGroupCommand, session: AsyncSession
) -> UpsertDealerGroupResult:
    existing_id: UUID | None = None

    if cmd.group_id is not None:
        existing = await repo.get_by_id(session, cmd.group_id)
        if existing is not None:
            existing_id = cmd.group_id
    if existing_id is None:
        existing_id = await repo.get_id_by_name(
            session,
            cmd.name,
            distributor_company_id=cmd.distributor_company_id,
        )

    if existing_id is not None:
        group = await handle_update_dealer_group(
            UpdateDealerGroupCommand(
                group_id=existing_id,
                name=cmd.name,
                description=cmd.description,
                distributor_company_id=cmd.distributor_company_id,
                dealer_company_ids=list(cmd.dealer_company_ids),
                actor_id=cmd.actor_id,
            ),
            session,
        )
        return UpsertDealerGroupResult(action="updated", group_id=group["id"])

    group = await handle_create_dealer_group(
        CreateDealerGroupCommand(
            name=cmd.name,
            description=cmd.description,
            distributor_company_id=cmd.distributor_company_id,
            dealer_company_ids=list(cmd.dealer_company_ids),
            actor_id=cmd.actor_id,
        ),
        session,
    )
    return UpsertDealerGroupResult(action="created", group_id=group["id"])
