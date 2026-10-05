from __future__ import annotations

import base64
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from infrastructure.services.mobile_id.protocol import MOBILE_ID_ENC_KEY_ALGORITHM
from infrastructure.settings import settings

_SAFE_KID_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MIN_RSA_KEY_SIZE = 2048


@dataclass(frozen=True)
class MobileIdKey:
    kid: str
    private_pem: bytes
    public_jwk: dict[str, str]
    public_numbers: rsa.RSAPublicNumbers


@dataclass(frozen=True)
class MobileIdKeySet:
    configuration: tuple[str, str, str]
    signing: MobileIdKey
    encryption: MobileIdKey


_lock = threading.Lock()


class _MobileIdKeySetState:
    value: MobileIdKeySet | None = None


def _validated_kid(kid: str, setting_name: str) -> str:
    normalized = kid.strip()
    if (
        not normalized
        or _SAFE_KID_PATTERN.fullmatch(normalized) is None
        or ".." in normalized
        or normalized.endswith(".pub")
    ):
        msg = (
            f"{setting_name} must be a safe key basename containing only "
            "letters, digits, dot, underscore, or hyphen"
        )
        raise ValueError(msg)
    return normalized


def configured_mobile_id_kids() -> tuple[str, str]:
    """Return validated, non-colliding Mobile ID key identifiers."""
    sig_kid = _validated_kid(settings.mobile_id_sig_kid, "MOBILE_ID_SIG_KID")
    enc_kid = _validated_kid(settings.mobile_id_enc_kid, "MOBILE_ID_ENC_KID")
    if sig_kid == enc_kid:
        msg = "MOBILE_ID_SIG_KID and MOBILE_ID_ENC_KID must be different"
        raise ValueError(msg)
    active_kid = settings.jwt_active_kid.strip()
    if active_kid and active_kid in {sig_kid, enc_kid}:
        msg = "JWT_ACTIVE_KID must not collide with a Mobile ID kid"
        raise ValueError(msg)
    return sig_kid, enc_kid


def _configuration() -> tuple[str, str, str]:
    sig_kid, enc_kid = configured_mobile_id_kids()
    return settings.jwt_keys_dir.strip(), sig_kid, enc_kid


def _b64url_int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _load_key(directory: Path, kid: str, use: str, algorithm: str) -> MobileIdKey:
    private_path = directory / f"{kid}.pem"
    public_path = directory / f"{kid}.pub.pem"
    if not private_path.is_file():
        msg = f"Mobile ID keypair {kid!r} is missing private file {kid}.pem"
        raise RuntimeError(msg)
    if not public_path.is_file():
        msg = f"Mobile ID keypair {kid!r} is missing public file {kid}.pub.pem"
        raise RuntimeError(msg)
    try:
        private_key = serialization.load_pem_private_key(
            private_path.read_bytes(),
            password=None,
        )
        public_key = serialization.load_pem_public_key(public_path.read_bytes())
    except (OSError, TypeError, UnsupportedAlgorithm, ValueError) as exc:
        msg = f"Mobile ID keypair {kid!r} contains invalid PEM material"
        raise RuntimeError(msg) from exc
    if not isinstance(private_key, rsa.RSAPrivateKey) or not isinstance(
        public_key,
        rsa.RSAPublicKey,
    ):
        msg = f"Mobile ID keypair {kid!r} must use RSA"
        raise TypeError(msg)
    if private_key.key_size < _MIN_RSA_KEY_SIZE or public_key.key_size < _MIN_RSA_KEY_SIZE:
        msg = f"Mobile ID keypair {kid!r} must use RSA with at least 2048 bits"
        raise ValueError(msg)
    public_numbers = public_key.public_numbers()
    if private_key.public_key().public_numbers() != public_numbers:
        msg = f"Mobile ID keypair {kid!r} private and public keys do not match"
        raise RuntimeError(msg)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return MobileIdKey(
        kid=kid,
        private_pem=private_pem,
        public_jwk={
            "kty": "RSA",
            "use": use,
            "alg": algorithm,
            "kid": kid,
            "n": _b64url_int(public_numbers.n),
            "e": _b64url_int(public_numbers.e),
        },
        public_numbers=public_numbers,
    )


def prepare_mobile_id_keyset() -> MobileIdKeySet:
    """Read and validate the complete Mobile ID keyset without publishing it."""
    configuration = _configuration()
    directory_name, sig_kid, enc_kid = configuration
    if not directory_name:
        msg = "JWT_KEYS_DIR is required for Mobile ID keys"
        raise RuntimeError(msg)
    directory = Path(directory_name)
    if not directory.is_dir():
        msg = "JWT_KEYS_DIR does not contain a readable key directory"
        raise RuntimeError(msg)
    signing = _load_key(directory, sig_kid, "sig", "RS256")
    encryption = _load_key(directory, enc_kid, "enc", MOBILE_ID_ENC_KEY_ALGORITHM)
    if signing.public_numbers == encryption.public_numbers:
        msg = "Mobile ID signing and encryption keys must use different RSA material"
        raise ValueError(msg)
    return MobileIdKeySet(
        configuration=configuration,
        signing=signing,
        encryption=encryption,
    )


def install_mobile_id_keyset(keyset: MobileIdKeySet | None) -> None:
    """Atomically publish a validated immutable key snapshot."""
    with _lock:
        _MobileIdKeySetState.value = keyset


def _current_keyset() -> MobileIdKeySet:
    configuration = _configuration()
    with _lock:
        current = _MobileIdKeySetState.value
    if current is not None and current.configuration == configuration:
        return current
    prepared = prepare_mobile_id_keyset()
    install_mobile_id_keyset(prepared)
    return prepared


def mobile_id_private_key_pem(kid: str) -> bytes:
    normalized_kid = _validated_kid(kid, "Mobile ID kid")
    keyset = _current_keyset()
    for key in (keyset.signing, keyset.encryption):
        if key.kid == normalized_kid:
            return key.private_pem
    msg = f"Mobile ID private key {normalized_kid!r} is not configured"
    raise FileNotFoundError(msg)


def mobile_id_public_jwks() -> list[dict[str, str]]:
    if not settings.mobile_id_enabled:
        return []
    keyset = _current_keyset()
    return [dict(keyset.signing.public_jwk), dict(keyset.encryption.public_jwk)]
