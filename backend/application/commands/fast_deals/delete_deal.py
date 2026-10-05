"""Delete a draft that was never sent; a sent deal can only be cancelled."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.access import load_for_mutation
from application.fast_deals.actor import Actor
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import FastDealStateError
from domain.fast_deals.values import DealStatus
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import fast_deal_repository as repo

logger = logging.getLogger("carcraft-backend")

_NOT_DELETABLE = "Удалить можно только черновик, который ещё не отправляли"


@dataclass
class DeleteFastDealCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None


async def handle_delete_fast_deal(
    cmd: DeleteFastDealCommand, session: AsyncSession, storage: ObjectStorage
) -> None:
    """Remove the draft with its children, then its files from the private storage.

    Only the initiator, only a draft with ``sent_at IS NULL``. The storage is not part
    of the database transaction: a failed removal of an object is logged and does not
    undo the deletion (the object stays unreachable, no row points at it).
    """
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require_initiator()
    ctx.require(Action.DELETE, _NOT_DELETABLE)
    if ctx.deal["status"] != DealStatus.DRAFT or ctx.deal["sent_at"] is not None:
        raise FastDealStateError(_NOT_DELETABLE)
    keys: list[str] = await repo.delete_draft_cascade(session, ctx.deal_id)
    for key in keys:
        try:
            await storage.delete(key)
        except Exception:
            logger.warning(
                "fast_deal_storage_cleanup_failed deal_id=%s key=%s", ctx.deal_id, key,
                exc_info=True,
            )
