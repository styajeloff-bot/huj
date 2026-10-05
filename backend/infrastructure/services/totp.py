"""TOTP service — secret generation, verification, QR rendering, backup codes."""
from __future__ import annotations

import base64
import hashlib
import io
import secrets

import pyotp
import qrcode

# 32 base32 chars == 160 bits of entropy, matches RFC 6238 recommendation and
# what Google Authenticator / Authy expect.
_SECRET_LENGTH = 32
# 10 URL-safe chars for a backup code — ~60 bits of entropy, displayed once
# to the user and hashed with SHA-256 before storing.
_BACKUP_CODE_LENGTH = 10
_DEFAULT_BACKUP_CODE_COUNT = 8
# Time-step tolerance on both sides of `now` (so ±1 == 30 s skew allowance).
_VERIFY_VALID_WINDOW = 1


def generate_secret() -> str:
    """Generate a fresh base32 TOTP secret of fixed length."""
    return pyotp.random_base32(length=_SECRET_LENGTH)


def verify_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against ``secret`` with ±1 window tolerance."""
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=_VERIFY_VALID_WINDOW)
    except (ValueError, TypeError):
        return False


def build_otpauth_url(secret: str, user_label: str, issuer: str) -> str:
    """Build an otpauth:// URL for QR code consumption."""
    return pyotp.TOTP(secret).provisioning_uri(name=user_label, issuer_name=issuer)


def render_qr_png_base64(otpauth_url: str) -> str:
    """Render ``otpauth_url`` as a base64-encoded PNG (no data: prefix)."""
    img = qrcode.make(otpauth_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def hash_backup_code(code: str) -> str:
    """SHA-256 hash of a backup code (lowercase hex)."""
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _generate_backup_code() -> str:
    """A URL-safe token trimmed to a fixed length, uppercased for readability."""
    # token_urlsafe produces ~1.33 chars per byte; generate a generous slice
    # then truncate and normalize case.
    raw = secrets.token_urlsafe(_BACKUP_CODE_LENGTH * 2)
    cleaned = "".join(ch for ch in raw if ch.isalnum())
    return cleaned[:_BACKUP_CODE_LENGTH].upper()


def generate_backup_codes(
    n: int = _DEFAULT_BACKUP_CODE_COUNT,
) -> list[tuple[str, str]]:
    """Generate ``n`` backup codes as ``(plain, hash)`` pairs.

    Plain codes are shown to the user exactly once; only the hashes are
    persisted.
    """
    codes: list[tuple[str, str]] = []
    seen: set[str] = set()
    while len(codes) < n:
        plain = _generate_backup_code()
        if plain in seen:
            continue
        seen.add(plain)
        codes.append((plain, hash_backup_code(plain)))
    return codes


__all__ = [
    "build_otpauth_url",
    "generate_backup_codes",
    "generate_secret",
    "hash_backup_code",
    "render_qr_png_base64",
    "verify_code",
]
