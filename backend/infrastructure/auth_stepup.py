"""Short-lived signed tokens for MFA step-up between phone verification
and the second-factor submission.

The MFA step-up token is one-shot, not a session — HS256 with the access
secret is sufficient and avoids touching the ES256 migration surface in
``infrastructure/auth.py``.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from jose import JWTError, jwt

from infrastructure.settings import settings


class MfaStepUpTokenError(Exception):
    """Base class for step-up token validation failures.

    Carries a short machine-readable ``code`` so the application layer
    can translate it to an HTTP error without importing JWT internals.
    """

    code: str = "MFA_TOKEN_INVALID"


class MfaStepUpTokenExpiredError(MfaStepUpTokenError):
    code = "MFA_TOKEN_EXPIRED"


class MfaStepUpTokenInvalidError(MfaStepUpTokenError):
    code = "MFA_TOKEN_INVALID"


class MfaSetupTokenError(Exception):
    """Base class for mandatory-setup token validation failures.

    Mirrors :class:`MfaStepUpTokenError` but for the ``purpose: mfa_setup``
    half-session issued to privileged roles that haven't enrolled yet.
    """

    code: str = "MFA_SETUP_TOKEN_INVALID"


class MfaSetupTokenExpiredError(MfaSetupTokenError):
    code = "MFA_SETUP_TOKEN_EXPIRED"


class MfaSetupTokenInvalidError(MfaSetupTokenError):
    code = "MFA_SETUP_TOKEN_INVALID"


# Purpose claim — lets the verifier reject tokens issued for other flows
# even if the secret is ever reused (defence in depth).
_PURPOSE = "mfa_step_up"
# 5 minutes is enough for a user to fish out their authenticator app; any
# longer meaningfully widens the replay window for a stolen interstitial.
_TTL_SECONDS = 5 * 60
# The mandatory-setup token covers the enrolment flow (scan QR, confirm
# first code), which takes longer — 15 minutes is a reasonable balance
# between UX and replay exposure.
_SETUP_PURPOSE = "mfa_setup"
_SETUP_TTL_SECONDS = 15 * 60
# Algorithm is fixed to HS256 regardless of what the access-token migration
# does — this token never leaves the server-to-client loopback.
_ALGORITHM = "HS256"


def issue_mfa_token(user_id: UUID) -> str:
    """Issue a signed one-shot MFA step-up token for ``user_id``."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "userId": str(user_id),
        "purpose": _PURPOSE,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(seconds=_TTL_SECONDS),
    }
    return cast("str", jwt.encode(payload, settings.jwt_access_secret, algorithm=_ALGORITHM))


def decode_mfa_token(token: str) -> dict[str, Any]:
    """Validate and decode a step-up token.

    Raises :class:`MfaStepUpTokenExpiredError` / :class:`MfaStepUpTokenInvalidError`
    so the application layer can translate those into HTTP errors without
    coupling infrastructure to any particular error-mapping module.
    """
    try:
        payload = cast(
            "dict[str, Any]",
            jwt.decode(
                token,
                settings.jwt_access_secret,
                algorithms=[_ALGORITHM],
            ),
        )
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise MfaStepUpTokenExpiredError("MFA_TOKEN_EXPIRED") from exc
        raise MfaStepUpTokenInvalidError("MFA_TOKEN_INVALID") from exc

    if payload.get("purpose") != _PURPOSE:
        raise MfaStepUpTokenInvalidError("MFA_TOKEN_INVALID")
    user_id = payload.get("userId")
    if not isinstance(user_id, str):
        raise MfaStepUpTokenInvalidError("MFA_TOKEN_INVALID")
    return {"user_id": UUID(user_id), "jti": payload.get("jti")}


def build_mfa_setup_token(user_id: UUID) -> str:
    """Issue a short-lived token authorising mandatory MFA enrolment.

    Distinct ``purpose: mfa_setup`` prevents confusion with the step-up
    token used post-enrolment; both live in the same HS256 keyspace.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "userId": str(user_id),
        "purpose": _SETUP_PURPOSE,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(seconds=_SETUP_TTL_SECONDS),
    }
    return cast("str", jwt.encode(payload, settings.jwt_access_secret, algorithm=_ALGORITHM))


def decode_mfa_setup_token(token: str) -> dict[str, Any]:
    """Validate and decode a mandatory-MFA setup token.

    Raises :class:`MfaSetupTokenExpiredError` / :class:`MfaSetupTokenInvalidError`
    for the application layer to translate into HTTP errors.
    """
    try:
        payload = cast(
            "dict[str, Any]",
            jwt.decode(
                token,
                settings.jwt_access_secret,
                algorithms=[_ALGORITHM],
            ),
        )
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise MfaSetupTokenExpiredError("MFA_SETUP_TOKEN_EXPIRED") from exc
        raise MfaSetupTokenInvalidError("MFA_SETUP_TOKEN_INVALID") from exc

    if payload.get("purpose") != _SETUP_PURPOSE:
        raise MfaSetupTokenInvalidError("MFA_SETUP_TOKEN_INVALID")
    user_id = payload.get("userId")
    if not isinstance(user_id, str):
        raise MfaSetupTokenInvalidError("MFA_SETUP_TOKEN_INVALID")
    return {"user_id": UUID(user_id), "jti": payload.get("jti")}


__all__ = [
    "MfaSetupTokenError",
    "MfaSetupTokenExpiredError",
    "MfaSetupTokenInvalidError",
    "MfaStepUpTokenError",
    "MfaStepUpTokenExpiredError",
    "MfaStepUpTokenInvalidError",
    "build_mfa_setup_token",
    "decode_mfa_setup_token",
    "decode_mfa_token",
    "issue_mfa_token",
]
