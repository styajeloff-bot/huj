"""FastAPI auth dependencies.

Two transports for the access token:

* ``accessToken`` cookie — what the SPA uses. Always honoured.
* ``Authorization: Bearer …`` header — gated. The frontend never sends
  this; it is reserved for external integrations (server-to-server,
  partner APIs) and only accepted when the decoded token carries role
  ``external_api``.

Concrete reason for the gate: a copy-pasted user cookie value cannot be
replayed via ``Authorization``, even though the token itself is valid —
production traffic must come through the cookie path.
"""
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from application.authentication import (
    authenticate_access_token,
    authenticate_access_token_with_db,
)
from application.errors import ServiceError
from domain.services.scopes import has_all_scopes
from infrastructure.database import get_db

EXTERNAL_API_ROLE = "external_api"


def _extract_token(
    access_token: str | None = Cookie(default=None, alias="accessToken"),
    authorization: str | None = Header(default=None),
) -> tuple[str | None, str | None]:
    """Return ``(token, source)`` where source is ``"cookie"`` or ``"bearer"``."""
    if access_token:
        return access_token, "cookie"
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:], "bearer"
    return None, None


def _to_http(exc: ServiceError) -> HTTPException:
    code: str | None = None
    if str(exc) == "Токен доступа не найден":
        code = "TOKEN_MISSING"
    elif str(exc) == "Токен доступа истек":
        code = "TOKEN_EXPIRED"
    elif str(exc) == "Недействительный токен":
        code = "TOKEN_INVALID"
    elif str(exc) == "Токен отозван":
        code = "TOKEN_REVOKED"
    elif str(exc) == "Пользователь не найден":
        code = "USER_NOT_FOUND"
    elif str(exc) == "Пользователь деактивирован":
        code = "USER_DEACTIVATED"
    elif str(exc) == "Bearer auth доступен только для внешних интеграций":
        code = "BEARER_NOT_ALLOWED"
    # Let the global handler turn this into the canonical flat shape.
    return HTTPException(status_code=exc.status_code, detail={"error": str(exc), "code": code})


def _ensure_bearer_allowed(user: dict[str, Any], source: str | None) -> None:
    """Reject Bearer-sourced tokens for non-external roles.

    Cookie path is always allowed. Bearer is allowed when
    the token's role is ``external_api``.
    """
    if source != "bearer":
        return
    if user.get("role") == EXTERNAL_API_ROLE:
        return
    raise ServiceError(
        "Bearer auth доступен только для внешних интеграций", 401
    )


async def get_current_user(
    extracted: Annotated[tuple[str | None, str | None], Depends(_extract_token)],
) -> dict[str, Any]:
    token, source = extracted
    try:
        user = await authenticate_access_token(token)
        _ensure_bearer_allowed(user, source)
    except ServiceError as exc:
        raise _to_http(exc) from exc
    return user


async def get_current_user_optional(
    extracted: Annotated[tuple[str | None, str | None], Depends(_extract_token)],
) -> dict[str, Any] | None:
    """Best-effort token decode. Returns ``None`` for missing/invalid tokens.

    Used for endpoints that personalize behavior when a user is signed in
    (e.g. calculator history save) but otherwise serve anonymous traffic.
    """
    token, source = extracted
    if not token:
        return None
    try:
        user = await authenticate_access_token(token)
        _ensure_bearer_allowed(user, source)
    except ServiceError:
        return None
    return user


async def get_current_user_optional_strict(
    extracted: Annotated[tuple[str | None, str | None], Depends(_extract_token)],
) -> dict[str, Any] | None:
    """Allow anonymous access, but reject a malformed or revoked presented token.

    Public event collectors use this variant so an invalid cookie cannot be
    silently downgraded to an anonymous identity and poison attribution.
    """
    token, source = extracted
    if not token:
        return None
    try:
        user = await authenticate_access_token(token)
        _ensure_bearer_allowed(user, source)
    except ServiceError as exc:
        raise _to_http(exc) from exc
    return user


async def get_current_user_with_db(
    extracted: Annotated[tuple[str | None, str | None], Depends(_extract_token)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    token, source = extracted
    try:
        user = await authenticate_access_token_with_db(token, session)
        _ensure_bearer_allowed(user, source)
    except ServiceError as exc:
        raise _to_http(exc) from exc
    return user


def require_roles(*roles: str) -> Callable[..., Any]:
    """Returns a dependency that checks user role.

    Kept for back-compat during the scope migration — new code should prefer
    :func:`require_scopes`.
    """

    async def _checker(
        user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Недостаточно прав доступа",
                    "code": "INSUFFICIENT_PERMISSIONS",
                },
            )
        return user

    setattr(_checker, "_required_roles", frozenset(roles))  # noqa: B010
    return _checker


def require_scopes(*scopes: str) -> Callable[..., Any]:
    """Returns a dependency that checks the user holds ALL of ``scopes``.

    Scopes are derived from the user's role via the domain mapper
    (see :mod:`domain.services.scopes`). The token carries them in the
    ``scopes`` claim; older tokens without the claim fall back to a
    role-derived list on decode.
    """

    required = scopes

    async def _checker(
        user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        if not has_all_scopes(user.get("scopes"), required):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Недостаточно прав доступа",
                    "code": "INSUFFICIENT_PERMISSIONS",
                },
            )
        return user

    setattr(_checker, "_required_scopes", frozenset(required))  # noqa: B010
    return _checker


def require_any_scopes(*scopes: str) -> Callable[..., Any]:
    """Return a dependency that accepts at least one of ``scopes``.

    This is intentionally separate from :func:`require_scopes`, whose
    all-scopes contract is relied on throughout the API.  It is useful for a
    read projection shared by otherwise independent bounded contexts without
    granting either context's broader write/read permissions.
    """

    required = tuple(dict.fromkeys(scopes))
    if not required:
        raise ValueError("require_any_scopes needs at least one scope")

    async def _checker(
        user: Annotated[dict[str, Any], Depends(get_current_user)],
    ) -> dict[str, Any]:
        granted = set(user.get("scopes") or ())
        if granted.isdisjoint(required):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Недостаточно прав доступа",
                    "code": "INSUFFICIENT_PERMISSIONS",
                },
            )
        return user

    setattr(  # noqa: B010
        _checker,
        "_required_any_scopes",
        frozenset(required),
    )
    return _checker
