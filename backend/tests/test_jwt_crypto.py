"""Tests for ES256 JWTs + JWKS."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from httpx import AsyncClient
from jose import jwt
from jose.exceptions import JWTError

from infrastructure.auth import decode_access_token, generate_tokens
from infrastructure.crypto.jwt_keys import (
    active_signing_key,
    all_public_keys,
    load_signing_keys,
    set_dev_keys,
)
from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
from infrastructure.settings import settings


def test_es256_token_round_trips() -> None:
    """Tokens minted with ES256 carry a `kid` and decode successfully."""
    access, refresh = generate_tokens(UUID("00000000-0000-0000-0000-00000000002a"), "client", None)

    header = jwt.get_unverified_header(access)  # NOSONAR — test inspects header before verified decode below
    assert header["alg"] == "ES256"
    assert header["kid"] == active_signing_key().kid

    payload = decode_access_token(access)
    assert payload["userId"] == "00000000-0000-0000-0000-00000000002a"
    assert payload["role"] == "client"
    # Refresh header also carries the kid
    refresh_header = jwt.get_unverified_header(refresh)  # NOSONAR — test inspects header before verified decode below
    assert refresh_header["alg"] == "ES256"
    assert refresh_header["kid"] == active_signing_key().kid


def test_hs256_token_without_kid_is_rejected() -> None:
    """HS256 access JWTs are no longer accepted."""
    token = jwt.encode(
        {"userId": 99, "role": "client"},
        settings.jwt_access_secret,
        algorithm="HS256",
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_unknown_kid_rejected() -> None:
    """A token referencing an unknown kid must not validate."""
    # Use the active key's private material but advertise a bogus kid.
    key = active_signing_key()
    token = jwt.encode(
        {"userId": 1},
        key.private_key,
        algorithm="ES256",
        headers={"kid": "nope-not-real"},
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


@pytest.mark.asyncio
async def test_jwks_endpoint_shape(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JWKS endpoint returns a well-formed JWK set."""
    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    resp = await client.get("/.well-known/jwks.json")
    assert resp.status_code == 200
    body = resp.json()
    assert "keys" in body
    assert isinstance(body["keys"], list)
    assert len(body["keys"]) >= 1

    # The active signing key must be present.
    kids = {jwk["kid"] for jwk in body["keys"]}
    assert active_signing_key().kid in kids

    for jwk_entry in body["keys"]:
        if jwk_entry["kty"] == "EC":
            assert jwk_entry["crv"] == "P-256"
            assert jwk_entry["use"] == "sig"
            assert jwk_entry["alg"] == "ES256"
            assert isinstance(jwk_entry["x"], str) and jwk_entry["x"]
            assert isinstance(jwk_entry["y"], str) and jwk_entry["y"]
        elif jwk_entry["kty"] == "RSA":
            assert jwk_entry["use"] in {"sig", "enc"}
            assert isinstance(jwk_entry["n"], str) and jwk_entry["n"]
            assert isinstance(jwk_entry["e"], str) and jwk_entry["e"]
        else:
            pytest.fail(f"unexpected JWK type: {jwk_entry['kty']}")
        assert isinstance(jwk_entry["kid"], str) and jwk_entry["kid"]
        # No private material must leak
        assert "d" not in jwk_entry
        assert "p" not in jwk_entry
        assert "q" not in jwk_entry


@pytest.mark.asyncio
async def test_jwks_endpoint_can_publish_mobile_id_rsa_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from presentation.routers.well_known import jwks as render_jwks

    jwt_private, jwt_public = _write_private_key_pair(
        tmp_path,
        kid="jwt-active-shared-dir",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    for kid in ("mobile-id-sig", "mobile-id-enc"):
        _write_private_key_pair(
            tmp_path,
            kid=kid,
            private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
        )
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_active_kid", "jwt-active-shared-dir")
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "mobile-id-sig")
    monkeypatch.setattr(settings, "mobile_id_enc_kid", "mobile-id-enc")

    try:
        load_and_validate_key_configuration()
        access_token, _ = generate_tokens(uuid4(), "client", None)
        response = await render_jwks()
        assert response.status_code == 200
        body = json.loads(bytes(response.body))
        keys = {jwk["kid"]: jwk for jwk in body["keys"]}

        assert jwt.get_unverified_header(access_token) == {
            "alg": "ES256",
            "kid": "jwt-active-shared-dir",
            "typ": "JWT",
        }
        assert keys["jwt-active-shared-dir"]["kty"] == "EC"
        assert keys["mobile-id-sig"]["kty"] == "RSA"
        assert keys["mobile-id-sig"]["use"] == "sig"
        assert keys["mobile-id-enc"]["kty"] == "RSA"
        assert keys["mobile-id-enc"]["use"] == "enc"
        assert keys["mobile-id-sig"]["alg"] == "RS256"
        assert keys["mobile-id-enc"]["alg"] == "RSA-OAEP-256"
        for kid in ("mobile-id-sig", "mobile-id-enc"):
            assert keys[kid]["n"]
            assert keys[kid]["e"]
            assert "d" not in keys[kid]
    finally:
        set_dev_keys(jwt_private, jwt_public, kid="jwt-active-shared-dir")


def test_all_public_keys_returns_registered_keys() -> None:
    """``all_public_keys`` mirrors the registry."""
    keys = all_public_keys()
    assert len(keys) >= 1
    assert any(k.kid == active_signing_key().kid for k in keys)


def test_load_signing_keys_fails_with_explicit_path_when_keys_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime config must provide JWT keys; no dev fallback is allowed."""
    missing_dir = tmp_path / "missing-jwt-keys"
    monkeypatch.setattr(settings, "jwt_keys_dir", str(missing_dir))

    with pytest.raises(RuntimeError) as exc_info:
        load_signing_keys()

    message = str(exc_info.value)
    assert "JWT signing keys are missing" in message
    assert "JWT_KEYS_DIR/settings.jwt_keys_dir" in message
    assert str(missing_dir) in message


def _write_private_key_pair(
    directory: Path,
    *,
    kid: str,
    private_key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
) -> tuple[bytes, bytes]:
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (directory / f"{kid}.pem").write_bytes(private_pem)
    (directory / f"{kid}.pub.pem").write_bytes(public_pem)
    return private_pem, public_pem


def test_jwt_loader_ignores_only_configured_mobile_id_kids_in_shared_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jwt_private, jwt_public = _write_private_key_pair(
        tmp_path,
        kid="jwt-active",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    for kid in ("operator-sig", "operator-enc"):
        _write_private_key_pair(
            tmp_path,
            kid=kid,
            private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
        )
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_active_kid", "jwt-active")
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "operator-sig")
    monkeypatch.setattr(settings, "mobile_id_enc_kid", "operator-enc")

    try:
        load_signing_keys(
            excluded_kids=frozenset({"operator-sig", "operator-enc"})
        )
        active = active_signing_key()
        assert active.kid == "jwt-active"
        assert active.algorithm == "ES256"
        assert active.public_jwk["kty"] == "EC"
        assert {key.kid for key in all_public_keys()} == {"jwt-active"}
    finally:
        set_dev_keys(jwt_private, jwt_public, kid="jwt-active")


def test_jwt_loader_strictly_rejects_unconfigured_rsa_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jwt_private, jwt_public = _write_private_key_pair(
        tmp_path,
        kid="jwt-active",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    _write_private_key_pair(
        tmp_path,
        kid="operator-sig",
        private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )
    _write_private_key_pair(
        tmp_path,
        kid="operator-enc",
        private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )
    _write_private_key_pair(
        tmp_path,
        kid="unexpected-rsa",
        private_key=rsa.generate_private_key(public_exponent=65537, key_size=2048),
    )
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_active_kid", "jwt-active")
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "operator-sig")
    monkeypatch.setattr(settings, "mobile_id_enc_kid", "operator-enc")

    try:
        with pytest.raises(TypeError, match=r"unexpected-rsa.*must use EC P-256"):
            load_signing_keys(
                excluded_kids=frozenset({"operator-sig", "operator-enc"})
            )
    finally:
        set_dev_keys(jwt_private, jwt_public, kid="jwt-active")


def test_jwt_loader_keeps_lexicographic_rotation_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_private, old_public = _write_private_key_pair(
        tmp_path,
        kid="20260811-old",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    _write_private_key_pair(
        tmp_path,
        kid="20260812-new",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_active_kid", "")

    try:
        load_signing_keys()
        assert active_signing_key().kid == "20260812-new"
    finally:
        set_dev_keys(old_private, old_public, kid="20260811-old")


def test_jwt_loader_keeps_public_only_retired_rotation_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retired_private, retired_public = _write_private_key_pair(
        tmp_path,
        kid="20260811-retired",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    (tmp_path / "20260811-retired.pem").unlink()
    _write_private_key_pair(
        tmp_path,
        kid="20260812-active",
        private_key=ec.generate_private_key(ec.SECP256R1()),
    )
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_active_kid", "20260812-active")

    try:
        load_signing_keys()
        keys = {key.kid: key for key in all_public_keys()}
        assert active_signing_key().kid == "20260812-active"
        assert set(keys) == {"20260811-retired", "20260812-active"}
        assert keys["20260811-retired"].private_key is None
    finally:
        set_dev_keys(retired_private, retired_public, kid="20260811-retired")


# ---------------------------------------------------------------------------
# G6: iss / aud / nbf claim tests
# ---------------------------------------------------------------------------


def test_generated_tokens_carry_iss_aud_nbf() -> None:
    """Encoded tokens include the RFC 7519 iss/aud/nbf claims."""
    access, refresh = generate_tokens(UUID("00000000-0000-0000-0000-00000000007b"), "client", None)

    access_claims = jwt.get_unverified_claims(access)  # NOSONAR — test inspects claims before verified decode below
    assert access_claims["iss"] == settings.jwt_issuer
    assert access_claims["aud"] == settings.jwt_audience
    assert "nbf" in access_claims
    # nbf should match iat for fresh tokens
    assert access_claims["nbf"] == access_claims["iat"]

    refresh_claims = jwt.get_unverified_claims(refresh)  # NOSONAR — test inspects claims before verified decode below
    assert refresh_claims["iss"] == settings.jwt_issuer
    assert refresh_claims["aud"] == settings.jwt_audience
    assert "nbf" in refresh_claims


def test_decode_succeeds_with_matching_iss_aud() -> None:
    """A token with the configured iss/aud round-trips cleanly."""
    access, _ = generate_tokens(UUID("00000000-0000-0000-0000-000000000007"), "client", None)
    payload = decode_access_token(access)
    assert payload["userId"] == "00000000-0000-0000-0000-000000000007"
    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.jwt_audience


def _mint_token_by_hand(claims: dict[str, object]) -> str:
    """Mint an ES256 token using the active signing key with arbitrary claims."""
    key = active_signing_key()
    return cast(
        "str",
        jwt.encode(
            claims,
            key.private_key,
            algorithm=key.algorithm,
            headers={"kid": key.kid},
        ),
    )


def test_decode_rejects_wrong_audience() -> None:
    """Wrong `aud` is a hard rejection — not tolerated by the legacy flag."""
    now = datetime.now(UTC)
    token = _mint_token_by_hand(
        {
            "userId": 1,
            "iss": settings.jwt_issuer,
            "aud": "wrong-service",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
        },
    )
    # Back-compat flag is on by default, but mismatched (not missing) aud must
    # still fail.
    assert settings.jwt_legacy_no_iss_aud_accept is True
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_decode_rejects_wrong_issuer() -> None:
    """Wrong `iss` is a hard rejection."""
    now = datetime.now(UTC)
    token = _mint_token_by_hand(
        {
            "userId": 1,
            "iss": "evil-issuer",
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
        },
    )
    assert settings.jwt_legacy_no_iss_aud_accept is True
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_decode_allows_legacy_token_without_iss_aud() -> None:
    """Legacy tokens (no iss/aud) are accepted while the compat flag is on."""
    now = datetime.now(UTC)
    token = _mint_token_by_hand(
        {
            "userId": 42,
            "role": "client",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
    )
    assert settings.jwt_legacy_no_iss_aud_accept is True
    payload = decode_access_token(token)
    assert payload["userId"] == 42


def test_decode_rejects_legacy_token_when_flag_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the legacy flag off, iss/aud become mandatory."""
    now = datetime.now(UTC)
    token = _mint_token_by_hand(
        {
            "userId": 42,
            "role": "client",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
    )
    monkeypatch.setattr(settings, "jwt_legacy_no_iss_aud_accept", False)
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_decode_allows_nbf_within_tolerance() -> None:
    """nbf slightly in the future decodes thanks to the clock-skew leeway."""
    now = datetime.now(UTC)
    token = _mint_token_by_hand(
        {
            "userId": 1,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now + timedelta(seconds=10),
            "exp": now + timedelta(minutes=5),
        },
    )
    # Default tolerance is 30s, so nbf = now+10 must pass.
    payload = decode_access_token(token)
    assert payload["userId"] == 1


def test_decode_rejects_nbf_beyond_tolerance() -> None:
    """nbf beyond the configured clock-skew tolerance fails."""
    now = datetime.now(UTC)
    token = _mint_token_by_hand(
        {
            "userId": 1,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now + timedelta(seconds=60),
            "exp": now + timedelta(minutes=5),
        },
    )
    # Default tolerance is 30s, so nbf = now+60 must be rejected.
    with pytest.raises(JWTError):
        decode_access_token(token)
