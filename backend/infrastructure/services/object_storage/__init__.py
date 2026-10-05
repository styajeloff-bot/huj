"""Concrete object storage providers and DI factory."""
from __future__ import annotations

from domain.services.object_storage import ObjectStorage
from infrastructure.services.object_storage.s3 import S3ObjectStorage
from infrastructure.settings import settings


class _StorageState:
    storage: ObjectStorage | None = None


def get_object_storage() -> ObjectStorage:
    """FastAPI dependency — singleton ObjectStorage provider."""
    if _StorageState.storage is None:
        _StorageState.storage = S3ObjectStorage(
            endpoint=settings.s3_endpoint,
            region=settings.s3_region,
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            public_base_url=settings.s3_public_base_url,
        )
    return _StorageState.storage


def set_object_storage(storage: ObjectStorage | None) -> None:
    """Override provider (used by tests)."""
    _StorageState.storage = storage
