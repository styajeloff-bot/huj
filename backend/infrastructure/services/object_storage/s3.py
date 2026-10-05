"""S3-compatible ObjectStorage implementation (aioboto3)."""
from __future__ import annotations

import logging
from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from domain.services.object_storage import StoredObject

logger = logging.getLogger("carcraft-backend")


def _client_error_code(exc: ClientError) -> str:
    code = exc.response.get("Error", {}).get("Code")
    return str(code) if code else "unknown"


class S3ObjectStorage:
    """aioboto3-backed adapter. Works with AWS S3 and S3-compatible services."""

    def __init__(
        self,
        *,
        endpoint: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        public_base_url: str = "",
    ) -> None:
        self._endpoint = endpoint or None
        self._region = region
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._public_base_url = public_base_url.rstrip("/")
        self._session = aioboto3.Session()

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            region_name=self._region,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return self.public_url(key)

    async def get(self, key: str) -> StoredObject | None:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                body = await response["Body"].read()
                return StoredObject(
                    key=key,
                    content_type=response.get("ContentType")
                    or "application/octet-stream",
                    size=int(response.get("ContentLength") or len(body)),
                    etag=response.get("ETag"),
                    data=body,
                )
        except ClientError as exc:
            code = _client_error_code(exc)
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            logger.warning("s3_get_failed error_code=%s", code)
            raise

    async def delete(self, key: str) -> bool:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self._bucket, Key=key)
                return True
        except ClientError as exc:
            code = _client_error_code(exc)
            if code in {"NoSuchKey", "404", "NotFound"}:
                return False
            logger.warning("s3_delete_failed error_code=%s", code)
            raise

    async def exists(self, key: str) -> bool:
        try:
            async with self._client() as s3:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
        except ClientError as exc:
            code = _client_error_code(exc)
            if code in {"NoSuchKey", "404", "NotFound"}:
                return False
            logger.warning("s3_exists_failed error_code=%s", code)
            raise

    def public_url(self, key: str) -> str:
        if self._public_base_url:
            return f"{self._public_base_url}/{key}"
        if self._endpoint:
            return f"{self._endpoint.rstrip('/')}/{self._bucket}/{key}"
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"
