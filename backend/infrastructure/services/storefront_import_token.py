"""Short-lived preview capabilities, isolated from access-token audience."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from jose import jwt
from jose.exceptions import JWTError

from domain.storefront_transfer import StaleStorefrontPreviewError
from infrastructure.crypto.jwt_keys import active_signing_key, get_key_by_kid
from infrastructure.settings import settings

_AUDIENCE = "storefront-settings-import"


def _claims(actor_id: UUID, data: bytes, state: list[dict[str, Any]]) -> dict[str, str]:
    serialized = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "sub": str(actor_id),
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "state_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
    }


def issue_preview_token(actor_id: UUID, data: bytes, state: list[dict[str, Any]]) -> str:
    key = active_signing_key()
    now = datetime.now(UTC)
    return cast("str", jwt.encode({
        **_claims(actor_id, data, state), "iss": settings.jwt_issuer,
        "aud": _AUDIENCE, "iat": now, "exp": now + timedelta(minutes=15),
    }, key.private_key, algorithm="ES256", headers={"kid": key.kid}))


def verify_preview_token(
    token: str, actor_id: UUID, data: bytes, state: list[dict[str, Any]],
) -> None:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "ES256" or not isinstance(kid, str):
            raise StaleStorefrontPreviewError
        key = get_key_by_kid(kid)
        if key is None:
            raise StaleStorefrontPreviewError
        payload = jwt.decode(
            token, key.public_key, algorithms=["ES256"], audience=_AUDIENCE,
            issuer=settings.jwt_issuer,
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
        if any(payload.get(field) != value for field, value in _claims(actor_id, data, state).items()):
            raise StaleStorefrontPreviewError
    except (JWTError, ValueError, TypeError) as exc:
        raise StaleStorefrontPreviewError from exc
