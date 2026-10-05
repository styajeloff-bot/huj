"""Abstract port for binary object storage (S3, GCS, Azure Blob, ...)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Metadata + body of a stored object, returned on read."""

    key: str
    content_type: str
    size: int
    etag: str | None
    data: bytes


class ObjectStorage(Protocol):
    """Provider-agnostic object storage port.

    The domain must not know whether the backend is S3, GCS, or another object storage.
    Concrete implementations live in `infrastructure/services/object_storage/`.
    """

    async def put(
        self, key: str, data: bytes, content_type: str
    ) -> str:
        """Store `data` under `key`. Returns the public URL for the object."""
        ...

    async def get(self, key: str) -> StoredObject | None:
        """Return the object, or None if it does not exist."""
        ...

    async def delete(self, key: str) -> bool:
        """Delete the object. Returns False if it didn't exist."""
        ...

    async def exists(self, key: str) -> bool:
        """Return True if the object exists in storage."""
        ...

    def public_url(self, key: str) -> str:
        """Return the canonical public URL for a stored object."""
        ...
