"""Well-known discovery endpoints (RFC 5785).

Exposes the JWKS (JSON Web Key Set) so external verifiers can validate
our ES256-signed JWTs without a shared secret.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from infrastructure.crypto.jwt_keys import all_public_keys
from infrastructure.services.mobile_id.keys import mobile_id_public_jwks

router = APIRouter()


class Jwk(BaseModel):
    """A single JSON Web Key (RFC 7517 §4)."""

    model_config = ConfigDict(extra="allow")

    kty: str
    crv: str | None = None
    x: str | None = None
    y: str | None = None
    n: str | None = None
    e: str | None = None
    use: str
    alg: str
    kid: str


class JwkSet(BaseModel):
    """A JWKS document — the response body of ``/.well-known/jwks.json``."""

    keys: list[Jwk]


@router.get(
    "/.well-known/jwks.json",
    response_model=JwkSet,
    summary="JSON Web Key Set",
    description=(
        "Публикует публичные ключи для проверки подписи JWT. "
        "Используется внешними сервисами (например, Express) для валидации "
        "ES256-токенов без общего секрета. Аутентификация не требуется."
    ),
    tags=["well-known"],
)
async def jwks() -> JSONResponse:
    """Return public halves of all currently-valid signing keys."""
    keys = [key.public_jwk for key in all_public_keys()]
    keys.extend(mobile_id_public_jwks())
    return JSONResponse({"keys": keys})
