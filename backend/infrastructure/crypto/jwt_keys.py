"""JWT signing key management (ES256 + JWKS + rotation).

FastAPI issues tokens signed with ES256 and a `kid` header. Public keys are
exposed via ``/.well-known/jwks.json`` so external verifiers (Express,
third-party services) can validate tokens without a shared secret.

Key rotation works by having multiple keys loaded simultaneously:
* exactly one "active" signing key (used for newly issued tokens);
* zero or more "verifying" keys (older public keys that are still published
  in JWKS so not-yet-expired tokens continue to validate).

Key sources (in priority order):
1. PEM files in ``settings.jwt_keys_dir``: ``<kid>.pem`` (private) paired with
   ``<kid>.pub.pem`` (public). If only the public half exists, that kid is
   verify-only.
"""
from __future__ import annotations

import base64
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from infrastructure.settings import settings

_logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True)
class JwtKey:
    """A single JWT signing/verifying key.

    ``private_key`` is None for verify-only keys (published in JWKS but no
    longer used for signing during a rotation window).
    """

    kid: str
    algorithm: str
    public_key: bytes
    public_jwk: dict[str, str]
    private_key: bytes | None = None


# ---------------------------------------------------------------------------
# Module-level registry (mutable, replaced atomically)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_keys_by_kid: dict[str, JwtKey] = {}


class _ActiveKidState:
    value: str | None = None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _ec_public_jwk(
    public_pem: bytes,
    kid: str,
    algorithm: str = "ES256",
) -> dict[str, str]:
    """Build an RFC 7517 JWK for a P-256 EC public key."""
    pub = serialization.load_pem_public_key(public_pem)
    if not isinstance(pub, ec.EllipticCurvePublicKey):
        msg = f"JWT key {kid!r} is not an EC public key"
        raise TypeError(msg)
    if not isinstance(pub.curve, ec.SECP256R1):
        msg = f"JWT key {kid!r} does not use the P-256 curve"
        raise TypeError(msg)
    nums = pub.public_numbers()
    # P-256 coordinates are 32 bytes big-endian.
    x_bytes = nums.x.to_bytes(32, "big")
    y_bytes = nums.y.to_bytes(32, "big")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(x_bytes),
        "y": _b64url(y_bytes),
        "use": "sig",
        "alg": algorithm,
        "kid": kid,
    }


def _load_from_disk(
    directory: Path,
    *,
    excluded_kids: frozenset[str] = frozenset(),
) -> dict[str, JwtKey]:
    """Scan ``directory`` for <kid>.pem / <kid>.pub.pem pairs."""
    keys: dict[str, JwtKey] = {}
    if not directory.is_dir():
        return keys
    # Collect all candidate kids from filenames.
    kids: set[str] = set()
    for entry in directory.iterdir():
        name = entry.name
        if name.endswith(".pub.pem"):
            kids.add(name[: -len(".pub.pem")])
        elif name.endswith(".pem"):
            kids.add(name[: -len(".pem")])
    for kid in kids:
        if kid in excluded_kids:
            continue
        priv_path = directory / f"{kid}.pem"
        pub_path = directory / f"{kid}.pub.pem"
        private_pem: bytes | None = None
        private_key: ec.EllipticCurvePrivateKey | None = None
        if priv_path.is_file():
            private_pem = priv_path.read_bytes()
            loaded_private = serialization.load_pem_private_key(
                private_pem,
                password=None,
            )
            if not isinstance(loaded_private, ec.EllipticCurvePrivateKey) or not isinstance(
                loaded_private.curve,
                ec.SECP256R1,
            ):
                msg = f"JWT private key {kid!r} must use EC P-256"
                raise TypeError(msg)
            private_key = loaded_private
        if pub_path.is_file():
            public_pem = pub_path.read_bytes()
        elif private_pem is not None:
            msg = f"JWT keypair {kid!r} is missing public file {kid}.pub.pem"
            raise RuntimeError(msg)
        else:
            continue
        loaded_public = serialization.load_pem_public_key(public_pem)
        if private_key is not None and (
            not isinstance(loaded_public, ec.EllipticCurvePublicKey)
            or private_key.public_key().public_numbers()
            != loaded_public.public_numbers()
        ):
            msg = f"JWT keypair {kid!r} private and public keys do not match"
            raise ValueError(msg)
        keys[kid] = JwtKey(
            kid=kid,
            algorithm="ES256",
            private_key=private_pem,
            public_key=public_pem,
            public_jwk=_ec_public_jwk(public_pem, kid),
        )
    return keys


def _raise_missing_keys_error(directory: str) -> None:
    configured = directory or "<empty>"
    checked_path = str(Path(directory)) if directory else "<not configured>"
    msg = (
        "JWT signing keys are missing. "
        f"JWT_KEYS_DIR/settings.jwt_keys_dir={configured!r}; "
        f"checked path: {checked_path}. "
        "Expected at least one <kid>.pem private key, optionally paired with "
        "<kid>.pub.pem."
    )
    _logger.error(msg)
    raise RuntimeError(msg)


def _pick_active_kid(keys: dict[str, JwtKey], configured: str) -> str | None:
    """Choose which kid signs new tokens."""
    signing_candidates = [k for k, v in keys.items() if v.private_key is not None]
    if configured:
        configured_key = keys.get(configured)
        if configured_key is None or configured_key.private_key is None:
            msg = (
                f"Configured JWT_ACTIVE_KID {configured!r} is not an available "
                "ES256 private key"
            )
            raise RuntimeError(msg)
        return configured
    if not signing_candidates:
        return None
    return max(signing_candidates)


def prepare_signing_keys(
    *,
    excluded_kids: frozenset[str] = frozenset(),
) -> tuple[dict[str, JwtKey], str]:
    """Validate a key registry without mutating the process-wide snapshot."""
    directory = settings.jwt_keys_dir.strip()
    keys = _load_from_disk(Path(directory), excluded_kids=excluded_kids) if directory else {}
    if not keys:
        _raise_missing_keys_error(directory)
    active = _pick_active_kid(keys, settings.jwt_active_kid.strip())
    if active is None:
        msg = "No active JWT signing key available"
        raise RuntimeError(msg)
    return keys, active


def install_signing_keys(keys: dict[str, JwtKey], active_kid: str) -> None:
    """Atomically publish a previously validated JWT registry."""
    with _lock:
        _keys_by_kid.clear()
        _keys_by_kid.update(keys)
        _ActiveKidState.value = active_kid


def load_signing_keys(*, excluded_kids: frozenset[str] = frozenset()) -> None:
    """(Re)load keys from configured sources.

    Idempotent — calling this on startup wipes and rebuilds the registry.
    """
    keys, active = prepare_signing_keys(excluded_kids=excluded_kids)
    install_signing_keys(keys, active)


def _ensure_loaded() -> None:
    if not _keys_by_kid:
        load_signing_keys()


def active_signing_key() -> JwtKey:
    """Return the key used for newly issued tokens."""
    _ensure_loaded()
    if _ActiveKidState.value is None or _ActiveKidState.value not in _keys_by_kid:
        msg = "No active JWT signing key available"
        raise RuntimeError(msg)
    key = _keys_by_kid[_ActiveKidState.value]
    if key.private_key is None:
        msg = f"Active JWT key {key.kid!r} has no private material"
        raise RuntimeError(msg)
    return key


def all_public_keys() -> list[JwtKey]:
    """All keys exposed via JWKS (public halves only)."""
    _ensure_loaded()
    return list(_keys_by_kid.values())


def get_key_by_kid(kid: str) -> JwtKey | None:
    """Look up a key for verification. Returns None if unknown."""
    _ensure_loaded()
    return _keys_by_kid.get(kid)


def set_dev_keys(
    private_pem: bytes,
    public_pem: bytes,
    *,
    kid: str = "dev-test",
    algorithm: str = "ES256",
) -> JwtKey:
    """Install a single keypair as THE active key. Intended for tests."""
    key = JwtKey(
        kid=kid,
        algorithm=algorithm,
        private_key=private_pem,
        public_key=public_pem,
        public_jwk=_ec_public_jwk(public_pem, kid, algorithm=algorithm),
    )
    with _lock:
        _keys_by_kid.clear()
        _keys_by_kid[kid] = key
        _ActiveKidState.value = kid
    return key
