"""Application-level helpers for JWT-backed user authentication."""
from typing import Any, cast
from uuid import UUID

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import get_company_permissions
from domain.services.scopes import roles_to_scopes
from infrastructure.auth import decode_access_token
from infrastructure.cache.token_denylist import is_revoked
from infrastructure.repositories import auth_repository as repo
from infrastructure.repositories import company_registration_repository as company_repo
from infrastructure.repositories import employees_repository


def _decode_access_payload(token: str | None) -> dict[str, Any]:
    """Decode, verify signature/exp and extract a valid access-token payload."""
    if not token:
        raise ServiceError("Токен доступа не найден", 401)

    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise ServiceError("Токен доступа истек", 401) from exc
        raise ServiceError("Недействительный токен", 401) from exc

    user_id = payload.get("userId")
    if user_id is None:
        raise ServiceError("Недействительный токен", 401)

    return cast("dict[str, Any]", payload)


async def authenticate_access_token(
    token: str | None,
) -> dict[str, Any]:
    """Resolve user identity from an access token without a database roundtrip.

    Performs a Redis denylist check on the token's ``jti`` so revocations
    (logout / refresh rotation) take effect immediately rather than waiting
    for the access token's natural expiry.
    """
    payload = _decode_access_payload(token)

    if await is_revoked(payload.get("jti")):
        raise ServiceError("Токен отозван", 401)

    # Back-compat: tokens issued before the scope migration don't carry a
    # `scopes` claim. Derive them from `role` so older tokens still pass
    # scope-gated endpoints without being forced to re-login.
    role_scopes = roles_to_scopes(payload.get("role"))
    raw_scopes = payload.get("scopes")
    if isinstance(raw_scopes, list):
        # Role scopes are the server-side authorization source of truth. Merge
        # them into signed tokens issued before a new scope was introduced so
        # additive permission rollouts do not require every active user to
        # wait for access-token expiry or log in again.
        scopes = sorted({str(scope) for scope in raw_scopes} | set(role_scopes))
    else:
        scopes = role_scopes

    try:
        user_id = UUID(payload["userId"])
    except (AttributeError, ValueError, TypeError) as exc:
        raise ServiceError("Недействительный токен", 401) from exc

    company_id = payload.get("company_id")
    if company_id is not None:
        try:
            company_id = UUID(company_id)
        except (AttributeError, ValueError, TypeError) as exc:
            raise ServiceError("Недействительный токен", 401) from exc

    return {
        "id": user_id,
        "role": payload.get("role"),
        "scopes": scopes,
        "company_id": company_id,
        "jti": payload.get("jti"),
        "exp": payload.get("exp"),
    }


async def authenticate_access_token_with_db(
    token: str | None,
    session: AsyncSession,
) -> dict[str, Any]:
    """Resolve a fresh user snapshot from an access token."""
    auth_user = await authenticate_access_token(token)
    user = await repo.find_user_by_id(session, auth_user["id"])
    if not user:
        raise ServiceError("Пользователь не найден", 401)
    if not user["is_active"]:
        raise ServiceError("Пользователь деактивирован", 401)

    # Load active company and permissions. New multi-company users may have
    # no legacy users.company_id, so prefer selected history first, then the
    # first active linked company from list_user_companies.
    companies = await company_repo.list_user_companies(session, user["id"])
    allowed_company_ids = {c["id"] for c in companies}
    history = await company_repo.get_company_select_history(session, user["id"])

    active_company_id: UUID | None = None
    if history and history["company_id"] in allowed_company_ids:
        active_company_id = history["company_id"]
    elif companies:
        active_company_id = companies[0]["id"]
        await company_repo.upsert_company_select_history(
            session, user["id"], active_company_id
        )

    active_company = next(
        (c for c in companies if c["id"] == active_company_id), None
    )

    sub_role = None
    can_view = None
    can_create = None
    active_role = None
    position_id = None
    position_name = None
    active_company_name = None

    if active_company_id is not None:
        perms = await get_company_permissions(session, user["id"], active_company_id)
        sub_role = perms.get("sub_role")
        can_view = perms.get("can_view_applications")
        can_create = perms.get("can_create_applications")
        active_role = perms.get("role") or (active_company["role"] if active_company else None) or "client"
        position_id = perms.get("position_id") or (active_company.get("position_id") if active_company else None)
        if position_id is not None:
            position_id = str(position_id)
        position_name = active_company.get("position_name") if active_company else None
        active_company_name = active_company.get("name") if active_company else None

    available_companies = [
        {
            "id": str(c["id"]),
            "name": c["name"],
            "inn": c.get("inn"),
            "role": c.get("role") or "client",
            "position_id": str(c["position_id"]) if c.get("position_id") else None,
            "position_name": c.get("position_name"),
            "is_active": bool(c.get("is_active", True)),
        }
        for c in companies
    ]

    can_create_employees = False
    if user["role"] == "carcraft_employee":
        can_create_employees = True
    elif active_company_id is not None:
        can_create_employees = await employees_repository.check_can_create_employees(
            session,
            actor_user_id=user["id"],
            actor_role=active_role or "client",
            target_company_id=active_company_id,
        )

    return {
        "id": user["id"],
        "phone": user["phone"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "scopes": auth_user["scopes"],
        "company_id": str(active_company_id) if active_company_id else None,
        "is_active": user["is_active"],
        "sub_role": sub_role,
        "can_view_applications": can_view,
        "can_create_applications": can_create,
        "can_create_employees": can_create_employees,
        "active_role": active_role,
        "active_company_id": str(active_company_id) if active_company_id else None,
        "active_company_name": active_company_name,
        "position_id": position_id,
        "position_name": position_name,
        "available_companies": available_companies,
    }
