"""Resolve an explicitly selected notification company without switching cabinets."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.leasing_access import require_lc_context
from domain.errors import CompanyAccessDeniedError
from infrastructure.repositories import notification_recipients_repository as repo


async def require_notification_company_context(
    session: AsyncSession, *, user_id: UUID, role: str,
    company_id: UUID | None, notification_company_id: UUID | None = None,
    leasing_company_id: UUID | None = None,
) -> dict[str, Any]:
    """Validate current identity and return current permissions for the selection.

    The selector is never authority. Object ownership and operation-specific
    permissions remain enforced by the existing use cases. Without a selector,
    return fresh permission flags without imposing read as a universal prerequisite
    for creation; preserve the caller's company and never persist a global switch.
    """
    actor = await repo.get_user(session, user_id)
    if actor is None or not actor["is_active"] or actor["role"] != role:
        raise CompanyAccessDeniedError()
    selected = notification_company_id or company_id
    if role == "leasing_company" and leasing_company_id is not None and notification_company_id is None:
        lc_context = await require_lc_context(session, user_id=user_id,
            company_id=None, leasing_company_id=leasing_company_id)
        selected = lc_context["company_id"]
    context: dict[str, Any] = {
        "company_id": selected, "sub_role": None,
        "can_view_applications": False, "can_create_applications": False,
    }
    if role in {"carcraft_employee", "external_api"}:
        if notification_company_id is not None:
            raise CompanyAccessDeniedError()
        return context
    if selected is not None:
        candidates = await repo.candidate_contexts(
            session, company_ids={selected}, user_id=user_id,
            readable_only=notification_company_id is not None,
        )
        candidate = next((item for item in candidates if item["role"] == role), None)
        if candidate is None:
            raise CompanyAccessDeniedError()
        context.update({name: candidate[name] for name in (
            "sub_role", "can_view_applications", "can_create_applications",
        )})
    if notification_company_id is not None:
        context["notification_company_id"] = notification_company_id
        if leasing_company_id is not None:
            if role != "leasing_company":
                raise CompanyAccessDeniedError()
            await require_lc_context(session, user_id=user_id, company_id=selected,
                leasing_company_id=leasing_company_id)
    return context
