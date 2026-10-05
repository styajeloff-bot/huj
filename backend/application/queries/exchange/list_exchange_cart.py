"""List the current user's exchange cart contents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.exchange_supports import (
    resolve_exchange_support_selection,
    selected_support_price_summary,
)
from infrastructure.repositories import exchange_cart_repository as repo


@dataclass
class ListExchangeCartQuery:
    user_id: UUID


async def handle_list_exchange_cart(
    query: ListExchangeCartQuery, session: AsyncSession
) -> dict[str, Any]:
    items = await repo.list_for_user(session, query.user_id)
    enriched: list[dict[str, Any]] = []
    for item in items:
        warehouses = await repo.list_warehouses(session, item["id"])
        options = await repo.list_options(session, item["id"])
        comments = await repo.list_dealer_comments(session, item["id"])
        try:
            support_selection = await resolve_exchange_support_selection(
                session,
                user_id=query.user_id,
                vehicle_id=item["vehicle_id"],
                requested_ids=list(item.get("selected_support_ids") or []),
                select_default=False,
            )
            eligible_support_programs = support_selection.program_details
        except ServiceError:
            # Stale saved selections must not make the whole cart unreadable.
            fallback = await resolve_exchange_support_selection(
                session,
                user_id=query.user_id,
                vehicle_id=item["vehicle_id"],
                requested_ids=[],
                select_default=False,
            )
            eligible_support_programs = fallback.program_details
        price_summary = selected_support_price_summary(
            eligible_support_programs,
            list(item.get("selected_support_ids") or []),
            fallback_base_price=float(item.get("base_price") or 0),
        )
        enriched.append(
            {
                **item,
                **price_summary,
                # Client-side state exposed as flat id arrays — the UI
                # indexes into these to drive checkbox/toggle state.
                "selected_warehouse_ids": [
                    str(w["warehouse_id"]) for w in warehouses
                ],
                "selected_option_ids": [
                    str(o["dealer_option_id"]) for o in options
                ],
                "dealer_comments": comments,
                "eligible_support_programs": eligible_support_programs,
            }
        )
    return {
        "cart_items": enriched,
        "summary": {"total_items": len(enriched)},
    }
