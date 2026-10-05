"""Fire-and-forget publisher for auth-audit events on Kafka.

Writes to the ``auth.events.v1`` topic with a stable envelope so a
downstream consumer (SIEM, audit DB, Metabase) can build a unified log
of who did what when.

Failure policy: never raise. Audit is observational — a broken pipe to
Kafka must not block login, logout, or refresh. Failures are logged at
``WARNING`` and dropped.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from infrastructure.messaging.broker import get_broker
from infrastructure.messaging.topics import AUTH_EVENTS

logger = logging.getLogger("carcraft-backend")

# Event type constants — string values mirror what lands in Kafka and
# what downstream consumers grep for. Keep stable across refactors.
LOGIN_REQUESTED = "login.requested"
LOGIN_SUCCEEDED = "login.succeeded"
LOGIN_FAILED = "login.failed"
PHONE_LOCKED = "phone.locked"
REFRESH_ROTATED = "refresh.rotated"
REFRESH_REUSE_DETECTED = "refresh.reuse_detected"
LOGOUT = "logout"
AUTH_REVOKED = "token.revoked"
SESSIONS_REVOKED_ALL = "sessions.revoked_all"
MFA_SETUP_STARTED = "mfa.setup_started"
MFA_ENABLED = "mfa.enabled"
MFA_DISABLED = "mfa.disabled"
MFA_LOGIN_SUCCEEDED = "mfa.login_succeeded"
MFA_LOGIN_FAILED = "mfa.login_failed"
MFA_BACKUP_CODE_USED = "mfa.backup_code_used"
MFA_BACKUP_CODES_REGENERATED = "mfa.backup_codes_regenerated"
MFA_SETUP_REQUIRED = "mfa.setup_required"
WEBHOOK_REPLAY_REJECTED = "webhook.replay_rejected"
SESSION_REVOKED = "session.revoked"
ADMIN_FORCE_LOGOUT = "admin.force_logout"
ADMIN_USER_DISABLED = "admin.user_disabled"
ADMIN_USER_ENABLED = "admin.user_enabled"
ADMIN_MFA_RESET = "admin.mfa_reset"
SESSION_INACTIVE_EXPIRED = "session.inactive_expired"
ACCOUNT_ERASED = "account.erased"
INVITE_SENT = "invite.sent"

_tasks: set[asyncio.Task[None]] = set()


def emit(event: str, /, **fields: Any) -> None:
    """Schedule a non-blocking publish of an auth event to Kafka."""
    pending_before = len(_tasks)
    task = asyncio.create_task(_publish(event, fields))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    logger.debug(
        "auth_emit_scheduled event=%s pending_before=%d pending_after=%d",
        event,
        pending_before,
        len(_tasks),
    )


def _serialize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


async def _publish(event: str, fields: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **{k: _serialize_value(v) for k, v in fields.items()},
    }
    try:
        await get_broker().publish(payload, topic=AUTH_EVENTS)
    except Exception as exc:
        logger.warning("auth_event_publish_failed event=%s err=%s", event, exc)
    finally:
        logger.debug(
            "auth_emit_done event=%s pending=%d", event, len(_tasks)
        )
