from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import tempfile
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _write_private_json(output: Path, payload: dict[str, Any]) -> None:
    """Atomically publish a token-bearing JSON file readable only by its owner."""

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(output)
        output.chmod(0o600)
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


def _post_json(
    opener: urllib.request.OpenerDirector,
    url: str,
    payload: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 - caller supplies local E2E URL
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = json.loads(error.read() or b"{}")
        return error.code, body


def _create_storage_state(base_url: str, phone: str, output: Path) -> None:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar)
    )
    status, login_payload = _post_json(
        opener,
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        {"phone": phone},
    )
    if status not in {200, 403}:
        raise RuntimeError(f"E2E login failed with HTTP {status}: {login_payload}")

    status, verify_payload = _post_json(
        opener,
        f"{base_url.rstrip('/')}/api/v1/auth/verify-phone",
        {"phone": phone, "code": "0000"},
    )
    if status != 200:
        raise RuntimeError(f"E2E OTP verification failed with HTTP {status}")
    if verify_payload.get("mfaRequired") or verify_payload.get("mfaSetupRequired"):
        raise RuntimeError(
            "Fixture must provide storage_state_path for an MFA-protected actor"
        )

    hostname = urlparse(base_url).hostname or "127.0.0.1"
    cookies = [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain or hostname,
            "path": cookie.path or "/",
            "expires": cookie.expires if cookie.expires is not None else -1,
            "httpOnly": cookie.has_nonstandard_attr("HttpOnly"),
            "secure": cookie.secure,
            "sameSite": "Strict",
        }
        for cookie in cookie_jar
    ]
    if not any(cookie["name"] == "accessToken" for cookie in cookies):
        raise RuntimeError("OTP verification did not produce an accessToken cookie")

    _write_private_json(output, {"cookies": cookies, "origins": []})


def _manifest_auth(manifest: Path, role: str) -> dict[str, Any]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    auth = payload.get("auth")
    if not isinstance(auth, dict) or not isinstance(auth.get(role), dict):
        raise TypeError(f"Fixture manifest is missing auth.{role}")
    return auth[role]


def prepare_storage_state(
    *,
    manifest: Path,
    role: str,
    base_url: str,
    output: Path,
    phone_override: str | None,
) -> None:
    actor = _manifest_auth(manifest, role)
    source_value = actor.get("storage_state_path")
    if isinstance(source_value, str) and source_value:
        source = Path(source_value)
        if not source.is_absolute():
            source = manifest.parent / source
        if not source.is_file():
            raise RuntimeError(f"Fixture storage state does not exist: {source}")
        if source.resolve() == output.resolve():
            output.chmod(0o600)
        else:
            source_payload = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(source_payload, dict):
                raise TypeError("Fixture storage state must be a JSON object")
            _write_private_json(output, source_payload)
        return

    phone_value = phone_override or actor.get("phone")
    if not isinstance(phone_value, str) or not phone_value:
        raise RuntimeError(f"Fixture manifest is missing auth.{role}.phone")
    _create_storage_state(base_url, phone_value, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--role",
        required=True,
        choices=("employee", "client", "client_non_owner"),
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--phone")
    arguments = parser.parse_args()

    prepare_storage_state(
        manifest=arguments.manifest,
        role=arguments.role,
        base_url=arguments.base_url,
        output=arguments.output,
        phone_override=arguments.phone,
    )


if __name__ == "__main__":
    main()
