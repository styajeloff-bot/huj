"""In-memory ObjectStorage fake for tests."""
from __future__ import annotations

from domain.services.object_storage import StoredObject


class FakeObjectStorage:
    def __init__(self, base_url: str = "http://fake-storage/bucket") -> None:
        self._base_url = base_url
        self.items: dict[str, StoredObject] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        self.items[key] = StoredObject(
            key=key,
            content_type=content_type,
            size=len(data),
            etag=f'"etag-{len(data)}"',
            data=data,
        )
        return self.public_url(key)

    async def get(self, key: str) -> StoredObject | None:
        return self.items.get(key)

    async def delete(self, key: str) -> bool:
        return self.items.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        return key in self.items

    def public_url(self, key: str) -> str:
        return f"{self._base_url}/{key}"
