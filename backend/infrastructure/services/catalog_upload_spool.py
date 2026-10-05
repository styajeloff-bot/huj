"""Shared local spool for large catalog uploads.

Used as a fallback when the configured object storage refuses a raw XLSX
upload. In dev compose this path is shared by fastapi and taskiq-worker via
the existing `/app/application` bind mount.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from domain.services.object_storage import StoredObject

_SCHEME = "local-catalog://"
_SAFE_NAME_RE = re.compile(r"^[a-f0-9]{32}\.xlsx$")
_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _spool_dir() -> Path:
    app_root = Path(__file__).resolve().parents[2]
    return app_root / "application" / ".catalog_uploads"


def is_catalog_spool_key(key: str) -> bool:
    return key.startswith(_SCHEME)


async def write_catalog_upload(data: bytes) -> str:
    name = f"{uuid.uuid4().hex}.xlsx"
    path = _spool_dir() / name
    await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    return f"{_SCHEME}{name}"


async def read_catalog_upload(key: str) -> StoredObject | None:
    if not is_catalog_spool_key(key):
        return None
    name = key.removeprefix(_SCHEME)
    if not _SAFE_NAME_RE.fullmatch(name):
        return None
    path = _spool_dir() / name
    if not await asyncio.to_thread(path.exists):
        return None
    data = await asyncio.to_thread(path.read_bytes)
    return StoredObject(
        key=key,
        content_type=_XLSX_CONTENT_TYPE,
        size=len(data),
        etag=None,
        data=data,
    )
