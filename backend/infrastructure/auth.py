"""JWT token utilities.

ES256 token handling:
* Newly-issued tokens carry a ``kid`` header so external verifiers can pick the
  right public key from our JWKS endpoint.
* HS256 access/refresh JWTs are not accepted.

Standard claim validation (G6):
* Newly-issued tokens carry ``iss``, ``aud`` and ``nbf`` (RFC 7519).
* Decode validates ``iss``/``aud`` strictly; tokens with the *wrong* values
  are rejected unconditionally. Tokens that *lack* these claims (issued
  before this change) are tolerated while
  ``settings.jwt_legacy_no_iss_aud_accept`` is True.
"""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from jose import jwt
from jose.exceptions import JWTClaimsError, JWTError

from domain.services.scopes import roles_to_scopes
from infrastructure.crypto.jwt_keys import active_signing_key, get_key_by_kid
from infrastructure.settings import settings


def _sign(payload: dict[str, Any]) -> str:
    """Encode ``payload`` as ES256 with the active JWT key."""
    key = active_signing_key()
    return cast(
        "str",
        jwt.encode(
            payload,
            key.private_key,
            algorithm=key.algorithm,
            headers={"kid": key.kid},
        )
    )


def _decode_with_policy(
    token: str,
    key: Any,
    algorithms: list[str],
) -> dict[str, Any]:
    """Decode ``token`` with strict iss/aud validation, falling back to lax
    verification only when the legacy back-compat flag is on AND the offending
    claims are *absent* (not merely wrong).
    """
    options = {
        "leeway": settings.jwt_clock_skew_tolerance_seconds,
        "verify_signature": True,
    }
    try:
        return cast(
            "dict[str, Any]",
            jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options=options,
            ),
        )
    except JWTClaimsError:
        if not settings.jwt_legacy_no_iss_aud_accept:
            raise
        # Decode with signature verified but without iss/aud checks to inspect
        # claims: if iss/aud are present-but-wrong, re-raise.
        decoded = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            options={
                **options,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
        has_iss = "iss" in decoded
        has_aud = "aud" in decoded
        if has_iss and decoded.get("iss") != settings.jwt_issuer:
            raise
        if has_aud:
            aud_claim = decoded.get("aud")
            aud_values: list[str]
            if isinstance(aud_claim, list):
                aud_values = [str(v) for v in aud_claim]
            else:
                aud_values = [str(aud_claim)]
            if settings.jwt_audience not in aud_values:
                raise
        # Claims are missing (legacy token) — return the decoded payload with
        # signature and exp/nbf validation intact.
        return cast("dict[str, Any]", decoded)


def _decode(token: str) -> dict[str, Any]:
    """Verify and decode a token using the kid-indexed public key."""
    header = jwt.get_unverified_header(token)  # NOSONAR — header used only to select the verification key
    kid = header.get("kid")
    if kid:
        key = get_key_by_kid(kid)
        if key is not None:
            return _decode_with_policy(token, key.public_key, [key.algorithm])
        msg = f"Unknown kid: {kid}"
        raise JWTError(msg)

    msg = "JWT token is missing kid; HS256 access/refresh tokens are not accepted"
    raise JWTError(msg)


def generate_tokens(
    user_id: UUID,
    role: str | None,
    company_id: UUID | None,
    *,
    refresh_session_id: UUID | None = None,
) -> tuple[str, str]:
    """Generate (access_token, refresh_token) pair for the given user.

    Both tokens carry a unique ``jti`` so individual tokens can be revoked
    server-side (via the Redis denylist) without invalidating the whole
    refresh session.
    """
    now = datetime.now(UTC)
    access_jti = secrets.token_urlsafe(16)
    refresh_jti = secrets.token_urlsafe(16)
    scopes = roles_to_scopes(role)
    access_payload: dict[str, Any] = {
        "userId": str(user_id) if isinstance(user_id, UUID) else user_id,
        "role": role,
        "scopes": scopes,
        "company_id": str(company_id) if isinstance(company_id, UUID) else company_id,
        "jti": access_jti,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_expiry_minutes),
    }
    refresh_payload: dict[str, Any] = {
        "userId": str(user_id) if isinstance(user_id, UUID) else user_id,
        "role": role,
        "company_id": str(company_id) if isinstance(company_id, UUID) else company_id,
        "sid": str(refresh_session_id) if isinstance(refresh_session_id, UUID) else refresh_session_id,
        "jti": refresh_jti,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(days=settings.refresh_token_expiry_days),
    }
    access_token = _sign(access_payload)
    refresh_token = _sign(refresh_payload)
    return access_token, refresh_token


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access JWT token."""
    return _decode(token)


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh JWT token."""
    return _decode(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
