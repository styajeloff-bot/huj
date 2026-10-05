"""SSRF-hardened temporary-image transfer for special-equipment imports."""

from __future__ import annotations

import asyncio
import hashlib
import io
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import UUID

import httpx
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    ProxyConnectionError,
    ReadTimeoutError,
)
from botocore.exceptions import (
    ConnectionError as BotoConnectionError,
)
from PIL import Image, ImageOps, UnidentifiedImageError

from domain.special_equipment_import import (
    ImportContractError,
    is_forbidden_ip,
    validate_https_source_url,
)
from infrastructure.services.catalog_image_fetchers.gdrive import (
    google_drive_download_url,
)
from infrastructure.services.special_equipment_import_storage import (
    ImportObjectStorage,
)
from infrastructure.settings import settings

_MAX_IMAGE_BYTES = 15 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_MAX_REDIRECTS = 3
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_FETCH_ATTEMPTS = 3
_STORAGE_ATTEMPTS = 3
_RETRY_DELAYS_SECONDS = (0.2, 0.5)
_TRANSIENT_STORAGE_CODES = {
    "InternalError",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
    "SlowDown",
    "Throttling",
    "ThrottlingException",
}


class ImageTransferError(RuntimeError):
    """Safe phase-specific failure that never contains a provider URL."""

    def __init__(self, code: str, *, phase: str) -> None:
        super().__init__(code)
        self.code = code
        self.phase = phase


@dataclass(frozen=True)
class TransferredImage:
    storage_key: str
    content_sha256: str
    size_bytes: int


def configured_image_hosts() -> frozenset[str]:
    return settings.special_equipment_image_source_hosts


async def transfer_temporary_image(
    *,
    source_url: str,
    owner_kind: str,
    owner_id: UUID,
    staging_job_id: UUID,
    storage: ImportObjectStorage,
    allowed_hosts: frozenset[str] | None = None,
    reserve_storage_key: (
        Callable[[TransferredImage], Awaitable[None]] | None
    ) = None,
) -> TransferredImage:
    hosts = allowed_hosts if allowed_hosts is not None else configured_image_hosts()
    normalized_source_url = google_drive_download_url(source_url) or source_url
    current = validate_https_source_url(normalized_source_url, hosts)
    timeout = httpx.Timeout(connect=5, read=20, write=10, pool=5)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    ) as client:
        for redirect_number in range(_MAX_REDIRECTS + 1):
            hostname, addresses = await _resolve_public_addresses(current)
            data, location = await _fetch_from_verified_addresses(
                client=client,
                raw_url=current,
                hostname=hostname,
                addresses=addresses,
            )
            if location is not None:
                if redirect_number == _MAX_REDIRECTS:
                    raise ImportContractError("IMAGE_REDIRECT_LIMIT")
                current = validate_https_source_url(urljoin(current, location), hosts)
                continue
            if data is None:  # pragma: no cover - helper contract guard
                raise ImportContractError("IMAGE_FETCH_FAILED")
            break
        else:  # pragma: no cover - loop always exits or raises
            raise ImportContractError("IMAGE_FETCH_FAILED")

    encoded = await asyncio.to_thread(_decode_and_reencode, bytes(data))
    digest = hashlib.sha256(encoded).hexdigest()
    if owner_kind == "category":
        key = (
            f"special-equipment/staged/{staging_job_id}/categories/"
            f"{owner_id}/{digest}.webp"
        )
    elif owner_kind == "product":
        key = (
            f"special-equipment/staged/{staging_job_id}/products/"
            f"{owner_id}/{digest}.webp"
        )
    else:
        raise ImportContractError("IMAGE_OWNER_INVALID")
    transferred = TransferredImage(
        storage_key=key,
        content_sha256=digest,
        size_bytes=len(encoded),
    )
    # Durable ownership is reserved before the object is created. If the
    # manifest commit fails ambiguously, there is no untracked S3 object; if
    # the later put fails, the manifest row gives cleanup a durable handle.
    if reserve_storage_key is not None:
        await reserve_storage_key(transferred)
    await _put_image_with_retry(storage, key, encoded)
    return transferred


async def _fetch_from_verified_addresses(
    *,
    client: httpx.AsyncClient,
    raw_url: str,
    hostname: str,
    addresses: tuple[str, ...],
) -> tuple[bytes, None] | tuple[None, str]:
    """Fetch through already validated IPs without reopening DNS resolution."""
    last_code = "IMAGE_FETCH_UNAVAILABLE"
    last_error: Exception | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        for address in addresses:
            pinned_url = _pinned_https_url(raw_url, address)
            try:
                async with client.stream(
                    "GET",
                    pinned_url,
                    headers={
                        "Accept": "image/webp,image/png,image/jpeg",
                        "Host": hostname,
                    },
                    extensions={"sni_hostname": hostname},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ImportContractError("IMAGE_REDIRECT_INVALID")
                        return None, location
                    if response.status_code != 200:
                        raise ImportContractError(
                            f"IMAGE_HTTP_STATUS_{response.status_code}"
                        )
                    return await _read_image_body(response), None
            except (httpx.TimeoutException, TimeoutError) as exc:
                last_code = "IMAGE_FETCH_TIMEOUT"
                last_error = exc
            except httpx.TransportError as exc:
                last_code = "IMAGE_FETCH_UNAVAILABLE"
                last_error = exc
        if attempt < _FETCH_ATTEMPTS - 1:
            await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])
    raise ImageTransferError(last_code, phase="fetch") from last_error


async def _read_image_body(response: httpx.Response) -> bytes:
    content_type = (
        response.headers.get("content-type", "").split(";", 1)[0].casefold()
    )
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ImportContractError("IMAGE_CONTENT_TYPE_INVALID")
    declared = response.headers.get("content-length")
    if declared:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise ImportContractError("IMAGE_CONTENT_LENGTH_INVALID") from exc
        if declared_size > _MAX_IMAGE_BYTES:
            raise ImportContractError("IMAGE_SIZE_EXCEEDED")
    data = bytearray()
    async for chunk in response.aiter_bytes(64 * 1024):
        data.extend(chunk)
        if len(data) > _MAX_IMAGE_BYTES:
            raise ImportContractError("IMAGE_SIZE_EXCEEDED")
    return bytes(data)


async def _put_image_with_retry(
    storage: ImportObjectStorage,
    key: str,
    data: bytes,
) -> None:
    last_error: Exception | None = None
    for attempt in range(_STORAGE_ATTEMPTS):
        try:
            await storage.put_bytes(key, data, "image/webp")
            return
        except ImportContractError:
            raise
        except Exception as exc:
            last_error = exc
            if (
                is_transient_import_storage_error(exc)
                and attempt < _STORAGE_ATTEMPTS - 1
            ):
                await asyncio.sleep(_RETRY_DELAYS_SECONDS[attempt])
                continue
            break
    raise ImageTransferError(
        "IMAGE_STORAGE_UNAVAILABLE",
        phase="storage",
    ) from last_error


def is_transient_import_storage_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            BotoConnectionError,
            ConnectionClosedError,
            ConnectTimeoutError,
            EndpointConnectionError,
            HTTPClientError,
            ProxyConnectionError,
            ReadTimeoutError,
        ),
    ):
        return True
    if not isinstance(exc, ClientError):
        return False
    response = exc.response
    code = str(response.get("Error", {}).get("Code") or "")
    try:
        status = int(
            response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
        )
    except (TypeError, ValueError):
        status = 0
    return code in _TRANSIENT_STORAGE_CODES or status in {408, 429} or status >= 500


async def _resolve_public_addresses(raw_url: str) -> tuple[str, tuple[str, ...]]:
    hostname = urlsplit(raw_url).hostname
    if not hostname:
        raise ImportContractError("IMAGE_HOST_INVALID")
    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ImportContractError("IMAGE_DNS_FAILED") from exc
    addresses = {str(result[4][0]) for result in results}
    if not addresses or any(is_forbidden_ip(address) for address in addresses):
        raise ImportContractError("IMAGE_SSRF_ADDRESS_BLOCKED")
    return hostname, tuple(sorted(addresses))


def _pinned_https_url(raw_url: str, address: str) -> str:
    parsed = urlsplit(raw_url)
    netloc = f"[{address}]" if ":" in address else address
    return urlunsplit(("https", netloc, parsed.path, parsed.query, ""))


def _decode_and_reencode(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ImportContractError("IMAGE_FORMAT_INVALID")
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
                raise ImportContractError("IMAGE_PIXEL_LIMIT_EXCEEDED")
            transposed = ImageOps.exif_transpose(source)
            target_mode = "RGBA" if _has_transparency(transposed) else "RGB"
            image = (
                transposed
                if transposed.mode == target_mode
                else transposed.convert(target_mode)
            )
            image.thumbnail(
                (settings.image_max_width, settings.image_max_height),
                resample=Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
            return output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise ImportContractError("IMAGE_DECODE_FAILED") from exc


def _has_transparency(image: Image.Image) -> bool:
    """Detect alpha capability without allocating another full-size RGBA image."""
    return "A" in image.getbands() or "transparency" in image.info
