"""Host-side isolated Taskiq E2E orchestration (Linux, Docker, Python stdlib).

Run from the repository: python3 scripts/e2e/22296/taskiq_run.py.
The existing fixture stack supplies PostgreSQL/MinIO/Kafka and the built image;
its application processes, databases, buckets and queues are never modified.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

LABEL = "carcraft.22296.taskiq.run-id"
BASE_CONTAINER = "carcraft-22296-e2e-backend-1"
POSTGRES = "carcraft-22296-e2e-postgres-1"
NETWORK = "carcraft-22296-e2e_default"
PYTHON = "/app/.venv/bin/python"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def progress(stage, **values):
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False), flush=True)


class Runner:
    def __init__(self):
        self.run_id = uuid4().hex[:12]
        self.name = "22296-taskiq-e2e-" + self.run_id
        self.directory = Path(tempfile.mkdtemp(prefix=self.name + "-"))
        self.directory.chmod(0o700)
        runtime = self.directory / "runtime"
        runtime.mkdir(mode=0o700)
        self.config = {
            "run_id": self.run_id,
            "name": self.name,
            "db": "documentregistry22296_audit_taskiq_" + self.run_id,
            "bucket": self.name,
            "redis": self.name + "-redis",
            "group": self.name + "-notifications",
            "topic": self.name + ".notification.events.v1",
            "dlq": self.name + ".notification.events.dlq.v1",
            "runtime": str(runtime),
        }
        self.containers = []
        self.database_owned = False
        self.environment_ready = False
        self.counter = 0
        self.user = "documentregistry22296"
        self.environment = {}
        self.image = ""
        self.task_ids = []
        self.e2e = Path(__file__).resolve().parent
        self.source = self.e2e.parents[2] / "backend"

    def command(self, stage, args, *, timeout=60, check=True):
        self.counter += 1
        output = self.directory / f"{self.counter:03}-{stage}.private.log"
        output.touch(mode=0o600)
        with output.open("w") as log:
            result = subprocess.run(
                args, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False
            )
        content = output.read_text()
        if check and result.returncode:
            safe_errors = [
                line[:500]
                for line in content.splitlines()
                if line.startswith(
                    (
                        "AssertionError:",
                        "RuntimeError:",
                        "ModuleNotFoundError:",
                        "ImportError:",
                    )
                )
            ]
            progress(
                "taskiq_command_failed",
                command_stage=stage,
                exit_code=result.returncode,
                errors=safe_errors[-3:],
            )
            raise RuntimeError(
                f"{stage} failed (exit {result.returncode}); private diagnostics withheld"
            )
        return result.returncode, content

    def inspect(self, name):
        code, content = self.command(
            "inspect", ["docker", "inspect", name], check=False
        )
        return json.loads(content)[0] if code == 0 else None

    def emit_progress(self, content):
        for line in content.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and str(event.get("stage", "")).startswith(
                ("taskiq_", "local_keys_", "migration_", "fixture_manifest_")
            ):
                print(json.dumps(event, ensure_ascii=False), flush=True)
                if event.get("stage") == "taskiq_task_completed":
                    self.task_ids.append(event["task_id"])

    def configure(self):
        require(
            self.e2e.name == "22296" and self.source.is_dir(),
            "Run only from the feature E2E directory",
        )
        base = self.inspect(BASE_CONTAINER)
        require(base and base["State"]["Running"], "Start the fixture backend first")
        mounts = {
            item["Destination"]: Path(item["Source"]).resolve()
            for item in base["Mounts"]
        }
        require(
            mounts.get("/source") == self.source and mounts.get("/e2e") == self.e2e,
            "Fixture image source does not match this checkout",
        )
        require(
            NETWORK in base["NetworkSettings"]["Networks"],
            "Refusing an unrelated network",
        )
        self.image = base["Config"]["Image"]
        require(
            self.image == "carcraft-documentregistry22296-backend:local",
            "Refusing an unrelated image",
        )
        env = dict(item.split("=", 1) for item in base["Config"]["Env"])
        require(
            env.get("DB_HOST") == "postgres" and env.get("DB_USER") == self.user,
            "Refusing non-fixture database credentials",
        )
        require(
            env.get("DB_NAME")
            in {"documentregistry22296", "documentregistry22296_followup"},
            "Refusing non-fixture origin",
        )
        require(
            env.get("S3_ENDPOINT") == "http://minio:9000"
            and env.get("KAFKA_BROKERS") == "redpanda:9092",
            "Refusing external services",
        )
        require(
            not any(
                env.get(key) for key in ("DADATA_API_KEY", "SMSC_LOGIN", "SMTP_HOST")
            ),
            "Refusing external credentials",
        )
        self.environment = {
            **env,
            "DB_NAME": self.config["db"],
            "S3_BUCKET": self.config["bucket"],
            "REDIS_URL": "redis://" + self.config["redis"] + ":6379/0",
            "KAFKA_NOTIFICATION_CONSUMER_GROUP": self.config["group"],
            "PYTHONPATH": "/e2e:/source",
            "JWT_KEYS_DIR": "/runtime/jwt",
        }
        require(
            all(
                "\n" not in value and "\r" not in value
                for value in self.environment.values()
            ),
            "Unsupported multiline fixture environment",
        )
        env_file = self.directory / "environment.private"
        env_file.write_text(
            "".join(f"{key}={value}\n" for key, value in self.environment.items())
        )
        env_file.chmod(0o600)
        config_file = self.directory / "config.json"
        config_file.write_text(json.dumps(self.config))
        config_file.chmod(0o600)
        marker = Path(self.config["runtime"]) / "fixture-target.json"
        marker.write_text(
            json.dumps(
                {
                    "database": self.config["db"],
                    "bucket": self.config["bucket"],
                    "host_root": self.config["runtime"],
                }
            )
        )
        marker.chmod(0o600)
        self.environment_ready = True

    def psql(self, stage, sql):
        return self.command(
            stage,
            [
                "docker",
                "exec",
                POSTGRES,
                "psql",
                "-U",
                self.user,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-Atqc",
                sql,
            ],
        )

    def run_container(self, suffix, command, *, detached=False, timeout=120):
        name = self.name + "-" + suffix
        self.containers.append(name)
        args = [
            "docker",
            "run",
            "--pull",
            "never",
            "--name",
            name,
            "--label",
            LABEL + "=" + self.run_id,
            "--network",
            NETWORK,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--workdir",
            "/runtime",
            "--entrypoint",
            "",
            "--env-file",
            str(self.directory / "environment.private"),
            "--mount",
            f"type=bind,source={self.source},target=/source,readonly",
            "--mount",
            f"type=bind,source={self.e2e},target=/e2e,readonly",
            "--mount",
            f"type=bind,source={self.config['runtime']},target=/runtime",
            "--mount",
            f"type=bind,source={self.directory / 'config.json'},target=/taskiq-config.json,readonly",
        ]
        args += ["--detach"] if detached else []
        code, output = self.command(
            "run-" + suffix, args + [self.image, *command], timeout=timeout
        )
        self.emit_progress(output)
        return name

    def start(self):
        self.configure()
        require(
            re.fullmatch(
                r"documentregistry22296_audit_taskiq_[a-f0-9]{12}", self.config["db"]
            ),
            "Unsafe database name",
        )
        _, existing = self.psql(
            "check-db",
            "SELECT 1 FROM pg_database WHERE datname = '" + self.config["db"] + "'",
        )
        require(not existing.strip(), "Refusing to reuse an existing private database")
        self.database_owned = True
        self.psql(
            "create-db",
            'CREATE DATABASE "' + self.config["db"] + '" OWNER "' + self.user + '"',
        )
        redis = self.config["redis"]
        self.containers.append(redis)
        self.command(
            "redis-start",
            [
                "docker",
                "run",
                "--pull",
                "never",
                "--detach",
                "--name",
                redis,
                "--label",
                LABEL + "=" + self.run_id,
                "--network",
                NETWORK,
                "--tmpfs",
                "/data",
                "redis:7-alpine",
            ],
        )
        for _ in range(100):
            code, output = self.command(
                "redis-ready",
                ["docker", "exec", redis, "redis-cli", "ping"],
                check=False,
            )
            if code == 0 and output.strip() == "PONG":
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Private Redis never became ready")
        progress(
            "taskiq_isolated_resources_created",
            database=self.config["db"],
            bucket=self.config["bucket"],
            private_redis=redis,
        )
        self.run_container(
            "setup", [PYTHON, "/e2e/taskiq_setup.py", "init"], timeout=180
        )
        self.run_container(
            "backend",
            [
                PYTHON,
                "-m",
                "uvicorn",
                "taskiq_server:app",
                "--host",
                "0.0.0.0",
                "--port",
                "3002",
                "--lifespan",
                "off",
            ],
            detached=True,
        )
        self.run_container(
            "consumer", [PYTHON, "/e2e/taskiq_consumer.py"], detached=True
        )
        self.run_container(
            "worker",
            [
                "/app/.venv/bin/taskiq",
                "worker",
                "taskiq_bootstrap:broker",
                "application.tasks",
                "--workers",
                "1",
                "--max-async-tasks",
                "2",
                "--max-prefetch",
                "2",
            ],
            detached=True,
        )
        for _ in range(200):
            code, _ = self.command(
                "http-ready",
                [
                    "docker",
                    "exec",
                    self.name + "-backend",
                    "curl",
                    "-fsS",
                    "http://localhost:3002/api/v1/health",
                ],
                check=False,
            )
            if (
                code == 0
                and (Path(self.config["runtime"]) / "taskiq-consumer-ready").exists()
            ):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Private HTTP/consumer processes never became ready")
        progress(
            "taskiq_production_processes_started",
            worker="original Taskiq CLI and callbacks",
            consumer="original notification event handler",
        )
        _, output = self.command(
            "verify",
            ["docker", "exec", self.name + "-backend", PYTHON, "/e2e/taskiq_verify.py"],
            timeout=150,
        )
        self.emit_progress(output)
        self.verify_logs()

    def verify_logs(self):
        _, output = self.command(
            "worker-logs", ["docker", "logs", self.name + "-worker"]
        )
        events = []
        for line in output.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        completed = {
            event.get("task_id")
            for event in events
            if event.get("event") == "task.completed"
        }
        require(
            len(self.task_ids) == 3 and set(self.task_ids) <= completed,
            "Production worker logs do not confirm all three scan tasks",
        )
        startup = {event.get("event") for event in events}
        require(
            {"taskiq.worker.image_client.started", "taskiq.worker.kafka.started"}
            <= startup,
            "Original worker startup callbacks did not complete",
        )
        failures = [event for event in events if event.get("event") == "task.failed"]
        require(not failures, "Private Taskiq worker reported a failed task")
        warnings = []
        for event in events:
            if event.get("level") not in {"warning", "error"}:
                continue
            message = str(event.get("message", ""))
            for key, value in self.environment.items():
                if value and any(
                    secret in key
                    for secret in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")
                ):
                    message = message.replace(value, "[redacted]")
            message = re.sub(r"(://)[^/@\s]+:[^/@\s]+@", r"\1[redacted]@", message)
            warnings.append(
                {
                    "event": event.get("event"),
                    "level": event.get("level"),
                    "message": message[:400],
                }
            )
        progress(
            "taskiq_original_worker_verified",
            completed_scan_tasks=3,
            startup_callbacks=True,
            warnings=warnings,
        )

    def remove_container(self, name):
        container = self.inspect(name)
        if container is None:
            return
        require(
            container["Config"].get("Labels", {}).get(LABEL) == self.run_id,
            "Refusing to stop an unowned container",
        )
        if container["State"]["Running"]:
            self.command("stop-container", ["docker", "stop", "--timeout", "10", name])
        self.command("remove-container", ["docker", "rm", "--force", "--volumes", name])

    def cleanup(self):
        errors = []
        for name in list(self.containers):
            if name != self.config["redis"]:
                try:
                    self.remove_container(name)
                except Exception as exc:
                    errors.append(type(exc).__name__ + ": container cleanup")
        if self.environment_ready:
            try:
                self.run_container(
                    "cleanup", [PYTHON, "/e2e/taskiq_setup.py", "cleanup"], timeout=90
                )
            except Exception as exc:
                errors.append(type(exc).__name__ + ": S3/Kafka cleanup")
        if self.environment_ready:
            try:
                require(
                    self.config["group"] == self.name + "-notifications",
                    "Refusing shared consumer group cleanup",
                )
                rpk = [
                    "docker",
                    "exec",
                    "carcraft-22296-e2e-redpanda-1",
                    "rpk",
                    "group",
                ]
                for _ in range(40):
                    _, content = self.command(
                        "list-groups",
                        rpk
                        + ["list", "--format", "json", "-X", "brokers=localhost:9092"],
                    )
                    groups = json.loads(content)
                    if not any(
                        group["group"] == self.config["group"] for group in groups
                    ):
                        break
                    # rpk may exit zero with a per-group GROUP_NOT_EMPTY status.
                    # Verify broker state after graceful consumer shutdown.
                    self.command(
                        "delete-group",
                        rpk
                        + [
                            "delete",
                            self.config["group"],
                            "-X",
                            "brokers=localhost:9092",
                        ],
                    )
                    time.sleep(0.25)
                else:
                    raise RuntimeError(
                        "Private Kafka consumer group remains after cleanup"
                    )
            except Exception as exc:
                errors.append(type(exc).__name__ + ": Kafka group cleanup")
        for name in list(self.containers):
            try:
                self.remove_container(name)
            except Exception as exc:
                errors.append(type(exc).__name__ + ": container removal")
        if self.database_owned:
            try:
                require(
                    self.config["db"]
                    == "documentregistry22296_audit_taskiq_" + self.run_id,
                    "Refusing to drop non-owned DB",
                )
                self.psql(
                    "drop-db",
                    'DROP DATABASE IF EXISTS "' + self.config["db"] + '" WITH (FORCE)',
                )
                _, remains = self.psql(
                    "verify-db-removed",
                    "SELECT 1 FROM pg_database WHERE datname = '"
                    + self.config["db"]
                    + "'",
                )
                require(not remains.strip(), "Private database remains after cleanup")
            except Exception as exc:
                errors.append(type(exc).__name__ + ": database cleanup")
        require(
            self.directory.resolve().parent == Path(tempfile.gettempdir()).resolve()
            and self.directory.name.startswith(self.name + "-"),
            "Refusing unsafe temporary directory cleanup",
        )
        # Containers use the host UID so all private runtime files remain
        # removable by the process that created this temporary directory.
        shutil.rmtree(self.directory)
        progress(
            "taskiq_private_resources_removed",
            database=self.config["db"],
            containers=len(set(self.containers)),
            errors=errors,
        )
        require(not errors, "Some private resources require cleanup; see stage summary")


def main():
    require(os.name == "posix", "Run this host launcher in Linux/WSL")
    runner = Runner()
    try:
        runner.start()
    finally:
        runner.cleanup()


if __name__ == "__main__":
    main()
