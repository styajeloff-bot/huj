"""Canonical strong ETags for hydrated management-registry resources."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(f"Unsupported ETag value: {type(value).__name__}")


def special_equipment_management_etag(resource: dict[str, Any]) -> str:
    """Fingerprint the full representation, including hydrated dependencies."""
    payload = json.dumps(
        resource,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f'"{resource["id"]}:{int(resource["lock_version"])}:{digest}"'


def special_equipment_trim_attributes_etag(
    *,
    trim_id: UUID,
    lock_version: int,
    items: list[dict[str, Any]],
) -> str:
    """Fingerprint the canonical full GET trim-attributes representation."""

    payload = json.dumps(
        {"items": items},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f'"{trim_id}:{int(lock_version)}:{digest}"'
