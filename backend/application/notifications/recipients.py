"""One current access projection for recipient resolution and email rechecks."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications.get_application import (
    ApplicationAccessQuery,
    get_authorized_application,
)
from application.services.exchange_access import can_read_exchange_request
from domain.errors import DomainError
from domain.events.notifications import NotificationEvent
from domain.notification_policy import POLICIES, targets_context
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import exchange_request_repository as exchange_repo
from infrastructure.repositories import (
    notification_document_group_repository as document_groups,
)
from infrastructure.repositories import notification_recipients_repository as repo


async def load_context(
    session: AsyncSession, event: NotificationEvent
) -> dict[str, Any] | None:
    if event.event_type.startswith("leasing."):
        return await repo.leasing_context(session, event.aggregate_id)
    context = await exchange_repo.get_notification_context(session, event.aggregate_id)
    if context is not None:
        context["distributor_company_ids"] = await repo.distributor_company_ids(session)
    return context


def _companies(context: dict[str, Any]) -> set[UUID]:
    companies = set(context.get("dealer_company_ids", ())) | set(
        context.get("distributor_company_ids", ())
    )
    companies.update(context.get("lc_company_ids", {}).values())
    companies.add(context.get("lc_company_id"))
    companies.add(context.get("application", {}).get("company_id"))
    companies.discard(None)
    return companies


async def authorized_context(
    session: AsyncSession,
    event: NotificationEvent,
    recipient: dict[str, Any],
) -> bool:
    """Use the same object projection as HTTP, including hidden child rows."""
    if event.event_type.startswith("exchange."):
        dealer_id = event.payload.get("dealer_company_id")
        if (
            recipient["role"] == "distributor"
            and event.event_type
            in {
                "exchange.bid_created",
                "exchange.bid_updated",
                "exchange.bid_withdrawn",
            }
            and dealer_id is None
        ):
            context = await exchange_repo.get_notification_context(
                session, event.aggregate_id
            )
            if not context or context.get("distributor_id") != recipient.get(
                "company_id"
            ):
                return False
        return await can_read_exchange_request(
            session,
            request_id=event.aggregate_id,
            user_id=recipient["user_id"],
            role=recipient["role"],
            company_id=recipient.get("company_id"),
            dealer_company_id=UUID(str(dealer_id)) if dealer_id else None,
        )
    try:
        _, dealer_filter = await get_authorized_application(
            ApplicationAccessQuery(
                application_id=event.aggregate_id,
                actor_id=recipient["user_id"],
                actor_role=recipient["role"],
                actor_company_id=recipient.get("company_id"),
                actor_leasing_company_id=recipient.get("leasing_company_id"),
            ),
            session,
        )
        vehicle_id = event.payload.get("application_vehicle_id")
        if vehicle_id is not None and dealer_filter is not None:
            vehicles = await app_repo.list_application_vehicles_with_catalog(
                session, event.aggregate_id, dealer_filter=dealer_filter,
                distributor_company_id=recipient.get("company_id") if recipient["role"] == "distributor" else None,
            )
            if str(vehicle_id) not in {str(vehicle["id"]) for vehicle in vehicles}:
                return False
        return True
    except DomainError:
        return False


async def resolve_recipients(
    session: AsyncSession,
    event: NotificationEvent,
    *,
    user_id: UUID | None = None,
    company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    if event.event_type == "document_registry.expiring":
        from application.notifications.document_registry_recipients import (
            resolve_document_registry_recipients,
        )

        return await resolve_document_registry_recipients(
            session, event, user_id=user_id, company_id=company_id,
        )
    if event.event_type.startswith("monetization."):
        from application.notifications.monetization_recipients import (
            resolve_monetization_recipients,
        )

        return await resolve_monetization_recipients(session, event, user_id=user_id, company_id=company_id)
    if event.event_type.startswith("fast_deal."):
        from application.notifications.fast_deal_recipients import (
            resolve_fast_deal_recipients,
        )

        return await resolve_fast_deal_recipients(
            session, event, user_id=user_id, company_id=company_id,
        )
    context = await load_context(session, event)
    if context is None:
        return []
    candidates = await repo.candidate_contexts(
        session,
        company_ids=_companies(context),
        include_employees="carcraft_employee" in POLICIES[event.event_type].roles,
        user_id=user_id,
    )
    recipients: dict[UUID, dict[str, Any]] = {}
    for candidate in sorted(
        candidates, key=lambda c: (str(c["user_id"]), str(c.get("company_id")))
    ):
        if company_id is not None and candidate.get("company_id") != company_id:
            continue
        if candidate["role"] == "leasing_company" and event.event_type.startswith(
            "leasing."
        ):
            lc_ids = [
                lc_id
                for lc_id, company_id in context.get("lc_company_ids", {}).items()
                if company_id == candidate["company_id"]
            ]
        else:
            lc_ids = [None]
        for lc_id in lc_ids:
            recipient = candidate | {
                "leasing_company_id": lc_id,
                "storefront_slug": context.get("storefront_slug"),
            }
            if targets_context(event, recipient, context) and await authorized_context(
                session, event, recipient
            ):
                recipients.setdefault(candidate["user_id"], recipient)
    return list(recipients.values())


async def event_is_current(
    session: AsyncSession, event: NotificationEvent, now: datetime
) -> bool:
    if event.event_type == "document_registry.expiring":
        from application.notifications.document_registry_expiry import (
            document_expiry_is_current,
        )

        return await document_expiry_is_current(session, event, now)
    if event.event_type == "leasing.documents_uploads_summary":
        return await document_groups.summary_matches_closed_group(session, event)
    if event.event_type not in {"exchange.deadline_24h", "exchange.deadline_1h"}:
        return True
    request = await exchange_repo.get_by_id(session, event.aggregate_id)
    if (
        request is None
        or request["status"] != "open"
        or request.get("expiration_at") is None
    ):
        return False
    original = event.payload.get("expiration_at")
    return (
        original is not None
        and datetime.fromisoformat(original) == request["expiration_at"]
        and request["expiration_at"] > now
    )
