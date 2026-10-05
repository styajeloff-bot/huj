"""Validate private resources, then load the unchanged production Taskiq broker."""

# ruff: noqa: E402
# Transport isolation must precede any production module binding topic constants.
import json
import re
from pathlib import Path

import runtime
from runtime import require
from infrastructure.settings import settings

CONFIG = json.loads(Path("/taskiq-config.json").read_text())
require(
    re.fullmatch(r"[a-f0-9]{12}", CONFIG["run_id"]), "Invalid private run identifier"
)
NAME = "22296-taskiq-e2e-" + CONFIG["run_id"]
require(CONFIG["name"] == NAME, "Invalid private resource name")
require(
    CONFIG["db"] == "documentregistry22296_audit_taskiq_" + CONFIG["run_id"],
    "Refusing non-private database",
)
require(
    CONFIG["bucket"] == NAME and CONFIG["redis"] == NAME + "-redis",
    "Refusing non-private storage",
)
require(
    CONFIG["topic"] == NAME + ".notification.events.v1"
    and CONFIG["dlq"] == NAME + ".notification.events.dlq.v1",
    "Refusing non-private topics",
)
require(CONFIG["group"] == NAME + "-notifications", "Refusing shared consumer group")
require(
    settings.db_host == "postgres" and settings.db_name == CONFIG["db"],
    "Refusing non-private DB configuration",
)
require(
    settings.s3_bucket == CONFIG["bucket"]
    and settings.s3_endpoint == "http://minio:9000",
    "Refusing non-private S3 configuration",
)
require(
    settings.redis_url == "redis://" + CONFIG["redis"] + ":6379/0",
    "Refusing shared Redis",
)
require(
    settings.kafka_brokers == "redpanda:9092"
    and settings.kafka_notification_consumer_group == CONFIG["group"],
    "Refusing external/shared Kafka context",
)
require(
    not settings.dadata_api_key and not settings.smsc_login and not settings.smtp_host,
    "Refusing external credentials",
)
require(
    Path.cwd() == Path("/runtime") and settings.jwt_keys_dir == "/runtime/jwt",
    "Refusing shared runtime",
)
runtime.FIXTURE_TARGETS = {
    CONFIG["db"]: {"bucket": CONFIG["bucket"], "host_root": CONFIG["runtime"]}
}
from infrastructure.messaging import topics

topics.NOTIFICATION_EVENTS = CONFIG["topic"]
topics.NOTIFICATION_EVENTS_DLQ = CONFIG["dlq"]
topics.TOPIC_PARTITIONS = {CONFIG["topic"]: 1, CONFIG["dlq"]: 1}
from infrastructure.taskiq_broker import broker  # noqa: F401 - Taskiq CLI entrypoint
