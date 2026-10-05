"""Private S3 transport for resumable special-equipment imports.

Storage identifiers returned here are internal persistence details. HTTP
responses expose only FastAPI resource URLs built from import UUIDs.
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from collections.abc import AsyncIterable, AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import aioboto3
from botocore.exceptions import ClientError

from infrastructure.settings import settings


@dataclass(frozen=True)
class UploadedPart:
    size_bytes: int
    sha256: str
    storage_etag: str


@dataclass(frozen=True)
class ImportStoredObjectHead:
    size_bytes: int
    content_type: str
    etag: str | None


class ImportObjectStorage(Protocol):
    async def initiate_multipart(self, key: str, content_type: str) -> str: ...

    async def put_part_stream(
        self,
        *,
        key: str,
        upload_id: str,
        part_number: int,
        chunks: AsyncIterable[bytes],
        expected_size: int,
        expected_sha256: str,
        max_size: int,
    ) -> UploadedPart: ...

    async def complete_multipart(
        self,
        *,
        key: str,
        upload_id: str,
        parts: Iterable[tuple[int, str]],
    ) -> None: ...

    async def abort_multipart(self, *, key: str, upload_id: str) -> None: ...

    async def head(self, key: str) -> ImportStoredObjectHead | None: ...

    async def download_to_path(self, key: str, path: Path) -> str: ...

    def iter_bytes(
        self, key: str, *, start: int | None = None, end: int | None = None
    ) -> AsyncIterator[bytes]: ...

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    async def put_path(self, key: str, path: Path, content_type: str) -> None: ...

    async def get_bytes(self, key: str) -> bytes | None: ...

    async def delete(self, key: str) -> None: ...


class S3ImportObjectStorage:
    """aioboto3 adapter with bounded API-part spooling and streaming reads."""

    def __init__(
        self,
        *,
        endpoint: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        self._endpoint = endpoint or None
        self._region = region
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._session = aioboto3.Session()

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            region_name=self._region,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
        )

    async def initiate_multipart(self, key: str, content_type: str) -> str:
        async with self._client() as s3:
            result = await s3.create_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                ContentType=content_type,
            )
        return str(result["UploadId"])

    async def put_part_stream(
        self,
        *,
        key: str,
        upload_id: str,
        part_number: int,
        chunks: AsyncIterable[bytes],
        expected_size: int,
        expected_sha256: str,
        max_size: int,
    ) -> UploadedPart:
        digest = hashlib.sha256()
        received = 0
        # Keep only a small prefix in RAM; normal 16 MiB parts roll to disk.
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as body:
            async for chunk in chunks:
                if not chunk:
                    continue
                received += len(chunk)
                if received > max_size or received > expected_size:
                    raise ValueError("Upload part exceeds declared range")
                digest.update(chunk)
                body.write(chunk)
            if received != expected_size:
                raise ValueError("Upload part size does not match Content-Range")
            actual_digest = digest.hexdigest()
            if actual_digest != expected_sha256.lower():
                raise ValueError("Upload part checksum mismatch")
            body.seek(0)
            async with self._client() as s3:
                result = await s3.upload_part(
                    Bucket=self._bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=body,
                    ContentLength=received,
                )
        return UploadedPart(
            size_bytes=received,
            sha256=actual_digest,
            storage_etag=str(result["ETag"]),
        )

    async def complete_multipart(
        self,
        *,
        key: str,
        upload_id: str,
        parts: Iterable[tuple[int, str]],
    ) -> None:
        manifest = [
            {"PartNumber": number, "ETag": etag} for number, etag in sorted(parts)
        ]
        async with self._client() as s3:
            await s3.complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": manifest},
            )

    async def abort_multipart(self, *, key: str, upload_id: str) -> None:
        async with self._client() as s3:
            await s3.abort_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
            )

    async def head(self, key: str) -> ImportStoredObjectHead | None:
        try:
            async with self._client() as s3:
                result = await s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {
                "NoSuchKey",
                "404",
                "NotFound",
            }:
                return None
            raise
        return ImportStoredObjectHead(
            size_bytes=int(result["ContentLength"]),
            content_type=str(result.get("ContentType") or "application/octet-stream"),
            etag=result.get("ETag"),
        )

    async def download_to_path(self, key: str, path: Path) -> str:
        digest = hashlib.sha256()
        async with self._client() as s3:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"]
            try:
                with path.open("wb") as target:
                    while chunk := await body.read(1024 * 1024):
                        digest.update(chunk)
                        target.write(chunk)
            finally:
                body.close()
        return digest.hexdigest()

    async def iter_bytes(
        self, key: str, *, start: int | None = None, end: int | None = None
    ) -> AsyncIterator[bytes]:
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if start is not None:
            kwargs["Range"] = f"bytes={start}-{'' if end is None else end}"
        async with self._client() as s3:
            response = await s3.get_object(**kwargs)
            body = response["Body"]
            try:
                while chunk := await body.read(1024 * 1024):
                    yield chunk
            finally:
                body.close()

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

    async def put_path(self, key: str, path: Path, content_type: str) -> None:
        content_length = (await asyncio.to_thread(path.stat)).st_size
        with path.open("rb") as body:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=body,
                    ContentLength=content_length,
                    ContentType=content_type,
                )

    async def get_bytes(self, key: str) -> bytes | None:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                body = response["Body"]
                try:
                    return bytes(await body.read())
                finally:
                    body.close()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {
                "NoSuchKey",
                "404",
                "NotFound",
            }:
                return None
            raise

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)


class _ImportStorageState:
    storage: ImportObjectStorage | None = None


def get_special_equipment_import_storage() -> ImportObjectStorage:
    storage = _ImportStorageState.storage
    if storage is None:
        storage = S3ImportObjectStorage(
            endpoint=settings.s3_endpoint,
            region=settings.s3_region,
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
        _ImportStorageState.storage = storage
    return storage


def set_special_equipment_import_storage(
    storage: ImportObjectStorage | None,
) -> None:
    """Override the private adapter in tests."""
    _ImportStorageState.storage = storage
