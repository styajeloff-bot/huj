"""Structured, process-wide logging for CarCraft Python services.

The public seam deliberately keeps serialization, context isolation, redaction,
exception rendering, and dependency suppression out of application callers.
"""

from __future__ import annotations

import json
import logging
import math
import re
import traceback
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from types import TracebackType
from typing import Literal
from uuid import UUID

type ServiceName = Literal[
    "carcraft-api",
    "carcraft-event-worker",
    "carcraft-taskiq-worker",
    "carcraft-taskiq-scheduler",
]
type LogLevel = Literal["debug", "info", "warning", "error", "critical"]
type ScalarLogValue = str | int | float | bool | None
type LogValue = (
    ScalarLogValue
    | UUID
    | datetime
    | date
    | Decimal
    | Enum
    | Mapping[str, "LogValue"]
    | Sequence["LogValue"]
)

LOGGER_NAME = "carcraft-backend"
SCHEMA_VERSION = 1

_DEFAULT_COMPONENT = "application"
_MAX_STRING_LENGTH = 16_384
_MAX_COLLECTION_LENGTH = 50
_MAX_NESTING_DEPTH = 6
_REDACTED = "[REDACTED]"
_TRUNCATED = "[TRUNCATED]"

_SYSTEM_FIELDS = frozenset(
    {
        "timestamp",
        "schema_version",
        "level",
        "service_name",
        "environment",
        "service_version",
        "event",
        "message",
    }
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])(?:"
    r"authorization|cookie|set[_-]?cookie|password|passwd|pass|"
    r"access[_-]?token|refresh[_-]?token|token|api[_-]?key|secret|"
    r"signature|credential|otp|sms[_-]?code|email|phone|passport|"
    r"headers|request[_-]?body|response[_-]?body"
    r")(?:$|[_-])",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_RE = re.compile(
    r"([?&](?:(?:x-amz-|x-goog-)?(?:signature|credential|security-token)|"
    r"token|access_token|refresh_token|search|q|api_key|key|password|code)="
    r")[^&\s\"]+",
    re.IGNORECASE,
)
_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|password|passwd|api[_-]?key|"
    r"secret|access[_-]?token|refresh[_-]?token|signature|credential|"
    r"token|code|otp|sms[_-]?code|search|q|email|phone|passport)\b\s*[:=]\s*"
    r"(\[REDACTED\]|[^,;\s}\]]+|"
    r"\"[^\"]*\"|'[^']*')"
)
_SENSITIVE_HEADER_RE = re.compile(
    r"(?im)\b(authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n]+"
)
_URL_USERINFO_RE = re.compile(r"(?P<scheme>https?://)[^/@\s]+@", re.IGNORECASE)
_BEARER_PATH_RE = re.compile(
    r"(?P<prefix>/s/)[^/?#\s\"']+",
    re.IGNORECASE,
)
_ACCOUNTING_INN_PATH_RE = re.compile(
    r"(?P<prefix>/api/v1/accounting/)\d{10}(?:\d{2})?(?=$|[/ ?#\"'])",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE_FIELD_RE = re.compile(
    r"(?i)\b(phone|телефон)\b\s*[:=]\s*(?:\+?\d[\s().-]*){10,15}"
)
_PHONE_RE = re.compile(r"(?<!\w)\+\d(?:[\s().-]*\d){9,14}(?!\d)")

_log_context: ContextVar[dict[str, LogValue] | None] = ContextVar(
    "carcraft_log_context", default=None
)


@dataclass(slots=True)
class _RuntimeContext:
    service_name: str = "unknown"
    environment: str = "local"
    service_version: str = "unknown"


_runtime_context = _RuntimeContext()


def _utc_timestamp() -> str:
    now = datetime.now(UTC)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _redact_text(value: str) -> str:
    redacted = _SENSITIVE_HEADER_RE.sub(r"\1=[REDACTED]", value)
    redacted = _SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _URL_USERINFO_RE.sub(r"\g<scheme>[REDACTED]@", redacted)
    redacted = _BEARER_PATH_RE.sub(r"\g<prefix>[REDACTED]", redacted)
    redacted = _ACCOUNTING_INN_PATH_RE.sub(r"\g<prefix>[REDACTED]", redacted)
    redacted = _EMAIL_RE.sub(_REDACTED, redacted)
    redacted = _PHONE_FIELD_RE.sub(r"\1=[REDACTED]", redacted)
    redacted = _PHONE_RE.sub(_REDACTED, redacted)
    redacted = _SENSITIVE_TEXT_RE.sub(r"\1=[REDACTED]", redacted)
    if len(redacted) > _MAX_STRING_LENGTH:
        return f"{redacted[:_MAX_STRING_LENGTH]}{_TRUNCATED}"
    return redacted


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
    return _SENSITIVE_KEY_RE.search(normalized) is not None


def _normalize_value(  # noqa: PLR0911, PLR0912
    value: object, *, key: str = "", depth: int = 0
) -> object:
    if key and _is_sensitive_key(key):
        return _REDACTED
    if depth > _MAX_NESTING_DEPTH:
        return _TRUNCATED
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite float is not a valid log value")
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _normalize_value(value.value, key=key, depth=depth + 1)
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for raw_key, item in list(value.items())[:_MAX_COLLECTION_LENGTH]:
            normalized_key = str(raw_key)
            result[normalized_key] = _normalize_value(
                item,
                key=normalized_key,
                depth=depth + 1,
            )
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [
            _normalize_value(item, depth=depth + 1)
            for item in value[:_MAX_COLLECTION_LENGTH]
        ]
    raise TypeError(f"unsupported log value type: {type(value).__name__}")


def _redact_legacy_argument(
    value: object,
    *,
    key: str = "",
    depth: int = 0,
) -> object:
    """Redact positional logging arguments before %-interpolation occurs."""

    if key and _is_sensitive_key(key):
        return _REDACTED
    if depth > _MAX_NESTING_DEPTH:
        return _TRUNCATED
    if isinstance(value, str):
        redacted: object = _redact_text(value)
    elif isinstance(value, Mapping):
        redacted = {
            raw_key: _redact_legacy_argument(
                item,
                key=str(raw_key),
                depth=depth + 1,
            )
            for raw_key, item in list(value.items())[:_MAX_COLLECTION_LENGTH]
        }
    elif isinstance(value, tuple):
        redacted = tuple(
            _redact_legacy_argument(item, depth=depth + 1)
            for item in value[:_MAX_COLLECTION_LENGTH]
        )
    elif isinstance(value, list):
        redacted = [
            _redact_legacy_argument(item, depth=depth + 1)
            for item in value[:_MAX_COLLECTION_LENGTH]
        ]
    else:
        redacted = value
    return redacted


def _safe_message(record: logging.LogRecord) -> str:
    template = str(record.msg)
    if not record.args:
        return _redact_text(template)

    if isinstance(record.args, Mapping):
        safe_args: object = _redact_legacy_argument(record.args)
    else:
        safe_args = tuple(_redact_legacy_argument(value) for value in record.args)
    try:
        rendered = template % safe_args
    except (TypeError, ValueError):
        rendered = f"{template} args={safe_args!r}"
    return _redact_text(rendered)


def _record_fields(record: logging.LogRecord) -> Mapping[str, object]:
    raw_fields = getattr(record, "log_fields", {})
    if isinstance(raw_fields, Mapping):
        return raw_fields
    raise TypeError("log_fields must be a mapping")


def _current_context() -> dict[str, LogValue]:
    return dict(_log_context.get() or {})


def _exception_fields(record: logging.LogRecord) -> dict[str, object]:
    if not record.exc_info:
        return {}
    error = record.exc_info[1]
    stacktrace = "".join(traceback.format_exception(*record.exc_info))
    return {
        "error_type": type(error).__name__ if error else "Exception",
        "error_message": _redact_text(str(error)) if error else "",
        "stacktrace": _redact_text(stacktrace),
    }


def _normalized_level(level: int) -> LogLevel:
    if level >= logging.CRITICAL:
        return "critical"
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    if level >= logging.INFO:
        return "info"
    return "debug"


class StructuredJsonFormatter(logging.Formatter):
    """Serialize every Python record to one safe JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            event = str(getattr(record, "log_event", "python.log"))
            combined: dict[str, object] = {}
            combined.update(_current_context())
            combined.update(_record_fields(record))
            for reserved in _SYSTEM_FIELDS:
                combined.pop(reserved, None)
            component = combined.pop("component", _DEFAULT_COMPONENT)

            payload: dict[str, object] = {
                "timestamp": _utc_timestamp(),
                "schema_version": SCHEMA_VERSION,
                "level": _normalized_level(record.levelno),
                "service_name": _runtime_context.service_name,
                "component": _redact_text(str(component)),
                "event": _redact_text(event),
                "message": _safe_message(record),
                "environment": _runtime_context.environment,
                "service_version": _runtime_context.service_version,
            }
            for key, value in combined.items():
                payload[str(key)] = _normalize_value(value, key=str(key))
            payload.update(_exception_fields(record))
            return json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except Exception as exc:
            fallback = {
                "timestamp": _utc_timestamp(),
                "schema_version": SCHEMA_VERSION,
                "level": "error",
                "service_name": _runtime_context.service_name,
                "component": "logging",
                "event": "logging.serialization_failed",
                "message": "Log record could not be serialized safely",
                "environment": _runtime_context.environment,
                "service_version": _runtime_context.service_version,
                "error_type": type(exc).__name__,
            }
            return json.dumps(fallback, ensure_ascii=False, separators=(",", ":"))


class RedactSensitiveQueryFilter(logging.Filter):
    """Redact secrets before other formatters can render a legacy record."""

    @classmethod
    def _redact(cls, value: object) -> object:
        return _redact_legacy_argument(value)

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.args:
            record.msg = self._redact(record.msg)
        elif isinstance(record.args, tuple):
            record.args = tuple(self._redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_legacy_argument(value, key=str(key))
                for key, value in record.args.items()
            }
        return True


def _new_stream_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    return handler


def _configure_root_logger(*, level: int, handler: logging.Handler) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def _suppress_noisy_dependencies() -> None:
    for logger_name in (
        "aioboto3",
        "aiobotocore",
        "aiokafka",
        "boto3",
        "botocore",
        "faststream",
        "httpcore",
        "httpx",
        "kafka",
        "taskiq",
    ):
        dependency_logger = logging.getLogger(logger_name)
        if dependency_logger.level == logging.NOTSET or (
            dependency_logger.level < logging.WARNING
        ):
            dependency_logger.setLevel(logging.WARNING)
        dependency_logger.handlers.clear()
        dependency_logger.propagate = True


def _normalize_runtime_loggers() -> None:
    for logger_name in ("uvicorn", "uvicorn.error"):
        runtime_logger = logging.getLogger(logger_name)
        runtime_logger.handlers.clear()
        runtime_logger.propagate = True


def _disable_uvicorn_access_log() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.filters.clear()
    access_logger.propagate = False
    access_logger.disabled = True


def configure_logging(*, service_name: ServiceName) -> None:
    """Configure one JSON record per event for the current process."""

    from infrastructure.settings import settings

    _runtime_context.service_name = service_name
    _runtime_context.environment = settings.environment or "unknown"
    _runtime_context.service_version = settings.service_version or "unknown"

    configured_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    level = configured_level if isinstance(configured_level, int) else logging.INFO
    handler = _new_stream_handler()
    _configure_root_logger(level=level, handler=handler)
    backend_logger = logging.getLogger(LOGGER_NAME)
    backend_logger.setLevel(level)
    backend_logger.handlers.clear()
    backend_logger.addHandler(handler)
    backend_logger.propagate = False
    backend_logger.disabled = False
    backend_logger.filters.clear()
    _disable_uvicorn_access_log()
    _normalize_runtime_loggers()
    _suppress_noisy_dependencies()


@contextmanager
def bind_log_context(**fields: LogValue) -> Iterator[None]:
    """Bind fields for the current async context and restore them on exit."""

    current = _current_context()
    current.update(
        {key: value for key, value in fields.items() if key not in _SYSTEM_FIELDS}
    )
    token = _log_context.set(current)
    try:
        yield
    finally:
        _log_context.reset(token)


def get_log_context_field(name: str) -> LogValue | None:
    """Return one correlation field without exposing mutable context state."""

    return (_log_context.get() or {}).get(name)


def normalize_correlation_id(value: object) -> str | None:
    """Return a canonical UUID correlation identifier or ``None``."""

    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        return None


def log_event(
    level: LogLevel,
    event: str,
    message: str,
    /,
    *,
    error: BaseException | None = None,
    **fields: LogValue,
) -> None:
    """Emit a structured event without allowing logging failures to escape."""

    logger = logging.getLogger(LOGGER_NAME)
    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    safe_fields = {
        key: value for key, value in fields.items() if key not in _SYSTEM_FIELDS
    }
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None
    if error is not None:
        exc_info = (type(error), error, error.__traceback__)
    try:
        logger.log(
            numeric_level,
            message,
            extra={"log_event": event, "log_fields": safe_fields},
            exc_info=exc_info,
        )
    except Exception:
        # Logging must never change the outcome of the operation being observed.
        return
