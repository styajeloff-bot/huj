from __future__ import annotations

import subprocess
from pathlib import Path


def test_mobile_id_key_generation_script_creates_stable_key_files(
    tmp_path: Path,
) -> None:
    script = Path("scripts/generate-mobile-id-keys.sh")

    first = subprocess.run(  # noqa: S603 - fixed repo script path with pytest tmp dir
        [str(script), str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    sig_before = (tmp_path / "sig.pem").read_bytes()
    enc_before = (tmp_path / "enc.pem").read_bytes()

    second = subprocess.run(  # noqa: S603 - fixed repo script path with pytest tmp dir
        [str(script), str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Generated Mobile ID keypair: sig" in first.stdout
    assert "Generated Mobile ID keypair: enc" in first.stdout
    assert "Mobile ID keypair already exists: sig" in second.stdout
    assert "Mobile ID keypair already exists: enc" in second.stdout
    assert (tmp_path / "sig.pem").read_bytes() == sig_before
    assert (tmp_path / "enc.pem").read_bytes() == enc_before
    for kid in ("sig", "enc"):
        assert (tmp_path / f"{kid}.pem").is_file()
        assert (tmp_path / f"{kid}.pub.pem").is_file()
        assert oct((tmp_path / f"{kid}.pem").stat().st_mode & 0o777) == "0o600"


def test_dockerfile_does_not_generate_or_configure_mobile_id_keys() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "generate-mobile-id-keys.sh" not in dockerfile
    assert "MOBILE_ID_BUILD_DIR" not in dockerfile
    assert "MOBILE_ID_KEY_DIR" not in dockerfile


def test_mobile_id_operator_script_points_to_shared_jwt_keys_dir() -> None:
    script = Path("scripts/generate-mobile-id-keys.sh").read_text(encoding="utf-8")

    assert "Set JWT_KEYS_DIR=$OUT_DIR" in script
    assert "MOBILE_ID_KEY_DIR" not in script


def test_dockerignore_excludes_private_keys_and_local_key_directories() -> None:
    patterns = {
        line.strip()
        for line in Path(".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "*.pem" in patterns
    assert {"keys", "mobile-id-keys", ".local-secrets", ".local_secrets"} <= patterns
