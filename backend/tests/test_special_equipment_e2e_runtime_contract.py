from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
E2E_SCRIPTS = REPOSITORY_ROOT / "scripts" / "e2e"


def _run_script(name: str, *arguments: str) -> list[str]:
    result = subprocess.run(  # noqa: S603 - fixed repository script path
        ["/bin/bash", str(E2E_SCRIPTS / name), *arguments],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "E2E_RUN_ID": "contract-test"},
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def test_local_provisioner_contract_uses_isolated_containers_without_compose() -> None:
    plan = _run_script("provision.sh", "--print-plan")

    assert plan == [
        "provision network carcraft-e2e-contract-test-net",
        "provision postgres carcraft-e2e-contract-test-postgres",
        "provision redis carcraft-e2e-contract-test-redis",
        "provision redpanda carcraft-e2e-contract-test-redpanda",
        "health postgres",
        "health redis",
        "health redpanda",
        "render nginx config",
        "validate nginx config",
        "provision nginx carcraft-e2e-contract-test-nginx",
        "write runtime state",
    ]
    provisioner = (E2E_SCRIPTS / "provision.sh").read_text(encoding="utf-8")
    assert "docker compose" not in provisioner
    assert "docker-compose" not in provisioner


def test_local_provisioner_reserves_distinct_host_ports_in_one_operation() -> None:
    result = subprocess.run(  # noqa: S603 - fixed repository helper path
        [
            "/bin/bash",
            "-c",
            f'source "{E2E_SCRIPTS / "common.sh"}"; '
            "e2e_select_ports 0 0 0 0 0 0 0 0",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    ports = result.stdout.split()

    assert len(ports) == 8
    assert len(set(ports)) == 8


def test_runtime_state_is_created_with_private_permissions() -> None:
    run_id = f"contract-{uuid4().hex[:12]}"
    state_dir = REPOSITORY_ROOT / ".e2e-runtime" / run_id
    try:
        subprocess.run(  # noqa: S603 - fixed repository helper path
            [
                "/bin/bash",
                "-c",
                f'source "{E2E_SCRIPTS / "common.sh"}"; '
                "e2e_require_run_id; "
                "e2e_prepare_private_state",
            ],
            cwd=REPOSITORY_ROOT,
            env={
                **os.environ,
                "E2E_RUN_ID": run_id,
                "E2E_STATE_DIR": str(state_dir),
            },
            check=True,
        )

        assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE((state_dir / "runtime.env").stat().st_mode) == 0o600
    finally:
        subprocess.run(  # noqa: S603 - fixed repository cleanup path
            [
                "/bin/bash",
                str(E2E_SCRIPTS / "cleanup.sh"),
                "--state-dir",
                str(state_dir),
            ],
            cwd=REPOSITORY_ROOT,
            env={
                **os.environ,
                "E2E_RUN_ID": run_id,
                "E2E_PRESERVE_FRONTEND_ARTIFACTS": "true",
            },
            check=False,
        )


def test_runtime_state_refuses_external_path_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / "external-runtime"
    state_dir.mkdir(mode=0o755)
    state_file = state_dir / "runtime.env"
    state_file.write_text("sentinel\n", encoding="utf-8")
    state_file.chmod(0o644)

    result = subprocess.run(  # noqa: S603 - fixed repository helper path
        [
            "/bin/bash",
            "-c",
            f'source "{E2E_SCRIPTS / "common.sh"}"; '
            "e2e_require_run_id; "
            "e2e_prepare_private_state",
        ],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "E2E_RUN_ID": "contract-test",
            "E2E_STATE_DIR": str(state_dir),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Refusing E2E state directory" in result.stderr
    assert state_file.read_text(encoding="utf-8") == "sentinel\n"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o755
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o644


def test_provisioner_rejects_external_state_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / "external-provision-runtime"
    state_dir.mkdir(mode=0o755)
    state_file = state_dir / "runtime.env"
    state_file.write_text("provision-sentinel\n", encoding="utf-8")
    state_file.chmod(0o644)

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        ["/bin/bash", str(E2E_SCRIPTS / "provision.sh")],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "E2E_RUN_ID": "contract-test",
            "E2E_STATE_DIR": str(state_dir),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Refusing E2E state directory" in result.stderr
    assert state_file.read_text(encoding="utf-8") == "provision-sentinel\n"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o755
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o644


def test_ci_runner_rejects_external_state_before_mutation(tmp_path: Path) -> None:
    state_dir = tmp_path / "external-ci-runtime"
    state_dir.mkdir(mode=0o755)
    state_file = state_dir / "runtime.env"
    state_file.write_text("ci-sentinel\n", encoding="utf-8")
    state_file.chmod(0o644)
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    for executable in ("bun", "curl", "uv"):
        stub = stub_bin / executable
        stub.write_text("#!/bin/sh\nexit 86\n", encoding="utf-8")
        stub.chmod(0o755)

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        ["/bin/bash", str(E2E_SCRIPTS / "run.sh"), "--ci"],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "PATH": f"{stub_bin}:{os.environ['PATH']}",
            "E2E_RUN_ID": "contract-test",
            "E2E_STATE_DIR": str(state_dir),
            "E2E_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Refusing E2E state directory" in result.stderr
    assert sorted(path.name for path in state_dir.iterdir()) == ["runtime.env"]
    assert state_file.read_text(encoding="utf-8") == "ci-sentinel\n"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o755
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o644


def test_runtime_state_refuses_directory_owned_by_another_run() -> None:
    requested_run_id = f"contract-{uuid4().hex[:12]}"
    owner_run_id = f"contract-{uuid4().hex[:12]}"
    state_dir = REPOSITORY_ROOT / ".e2e-runtime" / owner_run_id
    state_dir.mkdir(parents=True)
    state_file = state_dir / "runtime.env"
    state_file.write_text("owner-sentinel\n", encoding="utf-8")
    try:
        result = subprocess.run(  # noqa: S603 - fixed repository helper path
            [
                "/bin/bash",
                "-c",
                f'source "{E2E_SCRIPTS / "common.sh"}"; '
                "e2e_require_run_id; "
                "e2e_prepare_private_state",
            ],
            cwd=REPOSITORY_ROOT,
            env={
                **os.environ,
                "E2E_RUN_ID": requested_run_id,
                "E2E_STATE_DIR": str(state_dir),
            },
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert state_file.read_text(encoding="utf-8") == "owner-sentinel\n"
    finally:
        subprocess.run(  # noqa: S603 - fixed repository cleanup path
            [
                "/bin/bash",
                str(E2E_SCRIPTS / "cleanup.sh"),
                "--state-dir",
                str(state_dir),
            ],
            cwd=REPOSITORY_ROOT,
            env={
                **os.environ,
                "E2E_RUN_ID": owner_run_id,
                "E2E_PRESERVE_FRONTEND_ARTIFACTS": "true",
            },
            check=False,
        )


def test_runtime_state_refuses_symlink_escape_before_mutation(tmp_path: Path) -> None:
    run_id = f"contract-{uuid4().hex[:12]}"
    runtime_root = REPOSITORY_ROOT / ".e2e-runtime"
    runtime_root.mkdir(exist_ok=True)
    external_dir = tmp_path / "external-target"
    external_dir.mkdir()
    state_file = external_dir / "runtime.env"
    state_file.write_text("symlink-sentinel\n", encoding="utf-8")
    state_link = runtime_root / run_id
    state_link.symlink_to(external_dir, target_is_directory=True)
    try:
        result = subprocess.run(  # noqa: S603 - fixed repository helper path
            [
                "/bin/bash",
                "-c",
                f'source "{E2E_SCRIPTS / "common.sh"}"; '
                "e2e_require_run_id; "
                "e2e_prepare_private_state",
            ],
            cwd=REPOSITORY_ROOT,
            env={
                **os.environ,
                "E2E_RUN_ID": run_id,
                "E2E_STATE_DIR": str(state_link),
            },
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert state_file.read_text(encoding="utf-8") == "symlink-sentinel\n"
        assert state_link.is_symlink()
    finally:
        state_link.unlink(missing_ok=True)


def test_runner_contract_orders_backfill_services_and_all_acceptance_suites() -> None:
    plan = _run_script("run.sh", "--ci", "--print-plan")

    assert plan == [
        "prepare artifacts",
        "health PostgreSQL",
        "health Redis",
        "health Redpanda",
        "health S3 and bucket",
        "generate ES256 keys",
        "verify migration 085 -> head",
        "migrate database to head",
        "start FastAPI",
        "start Taskiq worker",
        "build Nuxt",
        "start Nuxt",
        "start Nginx",
        "health FastAPI",
        "health Taskiq worker",
        "health Nuxt",
        "health Nginx public API",
        "test migrated legacy catalog full-stack",
        "remove migrated legacy rows",
        "apply E2E fixture contract-test",
        "test traceability guard desktop-chromium",
        "test 21940 desktop-chromium",
        "reset fixture contract-test before 21954 desktop-chromium",
        "test 21954 desktop-chromium",
        "reset fixture contract-test before 21984 desktop-chromium",
        "test 21984 desktop-chromium",
        "reset fixture contract-test before 22098 desktop-chromium",
        "test 22098 desktop-chromium",
        "reset fixture contract-test before 22130 desktop-chromium",
        "test 22130 desktop-chromium",
        "reset fixture contract-test before 22282 desktop-chromium",
        "test 22282 desktop-chromium",
        "collect logs and artifacts",
    ]


def test_runner_exports_the_shared_fixture_reset_command() -> None:
    contract = _run_script("run.sh", "--print-environment-contract")

    assert contract == [
        f"E2E_FIXTURE_RESET_COMMAND=/bin/bash {E2E_SCRIPTS / 'reset-fixture.sh'}",
        "E2E_FIXTURE_MANIFEST mirrors E2E_MANIFEST",
        "E2E_NAMESPACE=E2E_RUN_ID for every fixture reset",
    ]


def test_runner_executes_traceability_guard_for_desktop_contract() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    assert "traceability.guard.spec.ts" in runner
    assert "junit-traceability-$project.xml" in runner
    assert "for project in desktop-chromium; do" in runner


def test_runner_keeps_auth_state_in_ephemeral_runtime_and_removes_it_on_exit() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")
    reset = (E2E_SCRIPTS / "reset-fixture.sh").read_text(encoding="utf-8")

    assert 'E2E_AUTH_STATE_DIR="$E2E_STATE_DIR/auth"' in runner
    assert 'E2E_EMPLOYEE_STORAGE_STATE="$E2E_AUTH_STATE_DIR/employee-storage-state.json"' in runner
    assert 'E2E_CLIENT_STORAGE_STATE="$E2E_AUTH_STATE_DIR/client-storage-state.json"' in runner
    assert 'remove_auth_states' in runner
    assert '--auth-state-dir "$E2E_AUTH_STATE_DIR"' in reset


def test_runner_reuses_one_namespace_for_every_suite_and_project() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    assert 'E2E_NAMESPACE="$E2E_RUN_ID"' in runner
    assert "E2E_ACCEPTANCE_SUITES:-21940 21954 21984 22098 22130" in runner
    assert 'apply_fixture "$E2E_RUN_ID-' not in runner
    assert 'local namespace="$1"' not in runner


def test_runner_is_compatible_with_the_macos_bash_3_runtime() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    assert "declare -A" not in runner


def test_runner_starts_taskiq_with_an_explicit_broker_and_task_module() -> None:
    contract = _run_script("run.sh", "--print-process-contract")

    assert contract == [
        "Taskiq=uv run taskiq worker --log-level INFO "
        "--log-format %(message)s "
        "infrastructure.taskiq_broker:broker application.tasks"
    ]


def test_runner_uses_the_installed_bun_binary_for_playwright() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    assert "bunx playwright" not in runner
    assert runner.count("bun x playwright test") == 3


def test_runner_routes_nuxt_ssr_api_requests_through_the_e2e_nginx_entrypoint() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    assert 'NUXT_API_INTERNAL_BASE="$PUBLIC_URL"' in runner


def test_local_browser_loads_nuxt_directly_while_ci_keeps_the_nginx_entrypoint() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    assert 'APP_URL="$PUBLIC_URL"' in runner
    assert 'APP_URL="$FRONTEND_URL"' in runner
    assert 'E2E_APP_BASE_URL="$APP_URL"' in runner


def test_cleanup_contract_targets_only_the_selected_run() -> None:
    plan = _run_script("cleanup.sh", "--print-plan")

    assert plan == [
        "stop host processes for contract-test",
        "remove generated frontend test-results",
        "remove generated frontend playwright-report",
        "remove container carcraft-e2e-contract-test-nginx",
        "remove container carcraft-e2e-contract-test-redpanda",
        "remove container carcraft-e2e-contract-test-redis",
        "remove container carcraft-e2e-contract-test-postgres",
        "remove network carcraft-e2e-contract-test-net",
        "remove runtime state for contract-test",
    ]


def test_backfill_contract_retains_legacy_rows_for_full_stack_smoke() -> None:
    plan = _run_script("verify-backfill.sh", "--print-plan")

    assert plan == [
        "migrate database to 085",
        "seed legacy 085 rows",
        "migrate database to head",
        "verify category=false and cart quantity=1 at head",
        "retain legacy rows for full-stack smoke",
    ]


def test_backfill_verifies_the_current_single_alembic_head() -> None:
    backfill = (E2E_SCRIPTS / "backfill_21954.py").read_text(encoding="utf-8")

    assert "ScriptDirectory.from_config(config).get_heads()" in backfill
    assert "Expected one Alembic head" in backfill
    assert "if revision != expected_revision:" in backfill
    assert 'Expected Alembic revision 087' not in backfill


def test_runner_smokes_migrated_legacy_catalog_before_cleanup_and_fixture() -> None:
    runner = (E2E_SCRIPTS / "run.sh").read_text(encoding="utf-8")

    migration = runner.index('bash "$SCRIPT_DIR/verify-backfill.sh"')
    backend_start = runner.index("start_process backend")
    browser_smoke = runner.index("21954-backfill.smoke.spec.ts")
    legacy_cleanup = runner.index('backfill_21954.py" cleanup')
    fixture = runner.index("apply_fixture", legacy_cleanup)

    assert migration < backend_start < browser_smoke < legacy_cleanup < fixture


def test_auth_state_prefers_fixture_generated_mfa_session(tmp_path: Path) -> None:
    source = tmp_path / "fixture-employee-state.json"
    output = tmp_path / "employee-storage-state.json"
    expected = {
        "cookies": [
            {
                "name": "accessToken",
                "value": "fixture-token",
                "domain": "127.0.0.1",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }
    source.write_text(json.dumps(expected), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "auth": {
                    "employee": {
                        "phone": "+76660000001",
                        "storage_state_path": source.name,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(  # noqa: S603 - fixed repository helper path
        [
            sys.executable,
            str(E2E_SCRIPTS / "auth_state.py"),
            "--manifest",
            str(manifest),
            "--role",
            "employee",
            "--base-url",
            "http://127.0.0.1:1",
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )

    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_cleanup_refuses_to_signal_a_pid_without_matching_start_time() -> None:
    run_id = f"contract-{uuid4().hex[:12]}"
    state_dir = REPOSITORY_ROOT / ".e2e-runtime" / run_id
    state_dir.mkdir(parents=True)
    sleeper = subprocess.Popen(["/bin/sleep", "30"])
    try:
        (state_dir / "backend.pid").write_text(f"{sleeper.pid}\n", encoding="utf-8")
        subprocess.run(  # noqa: S603 - fixed repository cleanup script
            ["/bin/bash", str(E2E_SCRIPTS / "cleanup.sh"), "--state-dir", str(state_dir)],
            cwd=REPOSITORY_ROOT,
            env={
                **os.environ,
                "E2E_RUN_ID": run_id,
                "E2E_PRESERVE_FRONTEND_ARTIFACTS": "true",
            },
            check=True,
        )

        assert sleeper.poll() is None
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=5)


def test_nginx_template_preserves_public_api_and_frontend_routing() -> None:
    template = (E2E_SCRIPTS / "nginx.conf.template").read_text(encoding="utf-8")

    assert "listen __NGINX_PORT__;" in template
    assert "server __BACKEND_HOST__:__BACKEND_PORT__;" in template
    assert "server __FRONTEND_HOST__:__FRONTEND_PORT__;" in template
    assert "location /api {" in template
    assert "proxy_pass http://backend/api;" in template
    assert "location / {" in template
    assert "proxy_pass http://frontend;" in template
    assert '"$request_method $uri $server_protocol"' in template


def test_nginx_renderer_uses_the_requested_listener_port(tmp_path: Path) -> None:
    rendered = tmp_path / "nginx.conf"
    subprocess.run(  # noqa: S603 - fixed repository helper path
        [
            "/bin/bash",
            "-c",
            f'source "{E2E_SCRIPTS / "common.sh"}"; '
            f'e2e_render_nginx_config "{E2E_SCRIPTS / "nginx.conf.template"}" '
            f'"{rendered}" 8080 127.0.0.1 3002 127.0.0.1 3000',
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )

    config = rendered.read_text(encoding="utf-8")
    assert "listen 8080;" in config
    assert "__NGINX_PORT__" not in config


def test_nginx_categories_fault_is_cookie_scoped_and_exact_path_only() -> None:
    template = (E2E_SCRIPTS / "nginx.conf.template").read_text(encoding="utf-8")

    assert "map $http_cookie $e2e_fault_categories" in template
    assert "e2e_fault_categories=1" in template
    assert "location = /api/v1/special-equipment/categories {" in template
    assert "if ($e2e_fault_categories)" in template
    assert "return 503" in template
    assert template.count("if ($e2e_fault_categories)") == 1


def test_gitlab_e2e_job_is_manual_non_blocking_and_keeps_diagnostics() -> None:
    config = (REPOSITORY_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    job = config.split("e2e:special-equipment:", maxsplit=1)[1].split(
        "\nbuild:", maxsplit=1
    )[0]
    rules = job.split("  rules:\n", maxsplit=1)[1]

    assert "  stage: e2e\n" in job
    assert "allow_failure: true" in job
    assert "scripts/e2e/run.sh --ci" in job
    assert rules.count("when: manual") == 2
    assert "when: always" not in rules
    assert "frontend/test-results/*.xml" in job
    assert "artifacts/e2e/**/*" in job
    assert all(
        service in config
        for service in (
            "postgres:16-alpine",
            "redis:7-alpine",
            "redpandadata/redpanda:",
        )
    )
    assert config.index("e2e:special-equipment:") < config.index(
        "scripts/e2e/run.sh --ci"
    )
    assert "mcr.microsoft.com/playwright:v1.62.1-noble" in config


def test_gitlab_e2e_job_tracks_every_shared_homepage_dependency() -> None:
    config = (REPOSITORY_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")

    for dependency in (
        "backend/main.py",
        "backend/scripts/seed_model_showcase_e2e.py",
        "frontend/pages/index.vue",
        "frontend/components/FAQ.vue",
        "frontend/components/TheFooter.vue",
        "frontend/components/TheHeader.vue",
        "frontend/components/ui/Modal.vue",
        "frontend/components/ui/modalIsolation.ts",
        "frontend/components/ui/ToastNotifications.vue",
        "frontend/features/auth/**/*",
        "frontend/features/cart/**/*",
        "frontend/features/calculator/**/*",
        "frontend/features/commerce/**/*",
        "frontend/pages/cart/**/*",
    ):
        assert config.count(f"        - {dependency}") == 2


def test_gitlab_e2e_job_bootstraps_verified_tools_and_ssh_host_identity() -> None:
    config = (REPOSITORY_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")

    assert "https://bun.sh/install" not in config
    assert "https://astral.sh/uv/install.sh" not in config
    assert "ssh-keyscan" not in config
    assert "SDK_SSH_KNOWN_HOSTS" not in config
    for contract in (
        'BUN_VERSION: "1.3.14"',
        "951ee2aee855f08595aeec6225226a298d3fea83a3dcd6465c09cbccdf7e848f",
        "a27ffb63a8310375836e0d6f668ae17fa8d8d18b88c37c821c65331973a19a3b",
        'UV_VERSION: "0.9.7"',
        "b26fcc8dfa1c39b5a5613445af3be3eefda45d9a39359bee271eafe34913583e",
        "8b3d31a154673c6d357727d2083a33525b515589d153fa5b5455e1db9e9e6363",
        "set -euo pipefail",
        "sha256sum --check",
        'GITLAB_CARCRAFT_KNOWN_HOST: "gitlab.carcraft.ru ssh-ed25519 '
        'AAAAC3NzaC1lZDI1NTE5AAAAIM8o7Dymzrou1iw4BwkhuOTxxfVqBmKij+Yu1aePYvIy"',
        "printf '%s\\n' \"$GITLAB_CARCRAFT_KNOWN_HOST\" >\"$HOME/.ssh/known_hosts\"",
        "StrictHostKeyChecking=yes",
    ):
        assert contract in config


def test_local_runtime_and_browser_artifacts_are_ignored() -> None:
    ignores = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "!scripts/e2e/" in ignores
    assert "!scripts/e2e/**" in ignores
    assert "/.e2e-runtime/" in ignores
    assert "/artifacts/e2e/" in ignores
    assert "/backend/artifacts/e2e/" in ignores
    assert "/frontend/test-results/" in ignores
    assert "/frontend/playwright-report/" in ignores
