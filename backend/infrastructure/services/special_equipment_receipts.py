"""Secure ingestion of provider-hosted special-equipment fiscal receipts.

The provider URL is deliberately ephemeral: callers pass it in memory, this
module validates and downloads it, and only the deterministic object-storage
key is returned for persistence.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit
from uuid import UUID

import httpx

from domain.services.object_storage import ObjectStorage
from infrastructure.settings import settings

_PDF_CONTENT_TYPE = "application/pdf"
_PDF_MAGIC = b"%PDF-"
_MAX_URL_LENGTH = 2048


class ReceiptIngestionError(RuntimeError):
    """A logging-safe receipt ingestion failure with no provider URL/body."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def receipt_storage_key(payment_id: UUID) -> str:
    """Stable private key makes callback/fiscalization replays idempotent."""

    return f"special-equipment/receipts/{payment_id}/receipt.pdf"


def configured_receipt_hosts() -> frozenset[str]:
    """Return exact allowlisted hosts, including the configured provider host."""

    values = {
        _canonical_hostname(value)
        for value in settings.modulkassa_receipt_source_hosts.split(",")
        if value.strip()
    }
    provider_host = urlsplit(settings.modulkassa_api_url).hostname
    if provider_host:
        values.add(_canonical_hostname(provider_host))
    return frozenset(values)


async def ingest_receipt_pdf(
    *,
    payment_id: UUID,
    source_url: str,
    storage: ObjectStorage,
    allowed_hosts: frozenset[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_bytes: int | None = None,
    max_redirects: int | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Fetch a verified PDF and store it under a private deterministic key.

    The return value from ``ObjectStorage.put`` can be a public S3 URL and is
    intentionally discarded.  Public access is exclusively through FastAPI's
    authenticated receipt-content endpoint.
    """

    key = receipt_storage_key(payment_id)
    if await storage.exists(key):
        return key

    body = await fetch_receipt_pdf(
        source_url,
        allowed_hosts=allowed_hosts,
        transport=transport,
        max_bytes=max_bytes,
        max_redirects=max_redirects,
        timeout_seconds=timeout_seconds,
    )
    await storage.put(key, body, _PDF_CONTENT_TYPE)
    return key


async def fetch_receipt_pdf(
    source_url: str,
    *,
    allowed_hosts: frozenset[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_bytes: int | None = None,
    max_redirects: int | None = None,
    timeout_seconds: float | None = None,
) -> bytes:
    """Download a PDF with HTTPS, SSRF, redirect, timeout and size guards."""

    hosts = (
        frozenset(_canonical_hostname(host) for host in allowed_hosts)
        if allowed_hosts is not None
        else configured_receipt_hosts()
    )
    byte_limit = (
        settings.modulkassa_receipt_max_bytes if max_bytes is None else max_bytes
    )
    redirect_limit = (
        settings.modulkassa_receipt_max_redirects
        if max_redirects is None
        else max_redirects
    )
    wall_timeout = timeout_seconds or settings.modulkassa_receipt_download_timeout
    if byte_limit <= 0 or redirect_limit < 0 or wall_timeout <= 0:
        raise ReceiptIngestionError("RECEIPT_DOWNLOAD_CONFIG_INVALID")

    current = _validate_source_url(source_url, hosts)
    try:
        async with asyncio.timeout(wall_timeout):
            return await _download_receipt_pdf(
                current,
                allowed_hosts=hosts,
                byte_limit=byte_limit,
                redirect_limit=redirect_limit,
                wall_timeout=wall_timeout,
                transport=transport,
            )
    except ReceiptIngestionError:
        raise
    except TimeoutError as exc:
        raise ReceiptIngestionError("RECEIPT_DOWNLOAD_TIMEOUT") from exc
    except httpx.TimeoutException as exc:
        raise ReceiptIngestionError("RECEIPT_DOWNLOAD_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise ReceiptIngestionError("RECEIPT_DOWNLOAD_FAILED") from exc

    raise ReceiptIngestionError("RECEIPT_DOWNLOAD_FAILED")  # pragma: no cover


async def _download_receipt_pdf(
    current: str,
    *,
    allowed_hosts: frozenset[str],
    byte_limit: int,
    redirect_limit: int,
    wall_timeout: float,
    transport: httpx.AsyncBaseTransport | None,
) -> bytes:
    client_timeout = httpx.Timeout(
        connect=min(5.0, wall_timeout),
        read=min(10.0, wall_timeout),
        write=min(5.0, wall_timeout),
        pool=min(5.0, wall_timeout),
    )
    async with httpx.AsyncClient(
        timeout=client_timeout,
        follow_redirects=False,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
        transport=transport,
    ) as client:
        for redirect_number in range(redirect_limit + 1):
            hostname, addresses = await _resolve_public_addresses(current)
            # Connect to exactly the address validated above.  Using the
            # hostname here would make the HTTP transport resolve it again and
            # reopen a DNS-rebinding window between validation and connection.
            pinned_url = _pinned_https_url(current, addresses[0])
            async with client.stream(
                "GET",
                pinned_url,
                headers={
                    "Accept": _PDF_CONTENT_TYPE,
                    "Host": hostname,
                },
                extensions={"sni_hostname": hostname},
            ) as response:
                if response.is_redirect:
                    if redirect_number == redirect_limit:
                        raise ReceiptIngestionError("RECEIPT_REDIRECT_LIMIT")
                    location = response.headers.get("location")
                    if not location:
                        raise ReceiptIngestionError("RECEIPT_REDIRECT_INVALID")
                    current = _validate_source_url(
                        urljoin(current, location), allowed_hosts
                    )
                    continue
                return await _validated_pdf_body(response, byte_limit)
    raise ReceiptIngestionError("RECEIPT_DOWNLOAD_FAILED")  # pragma: no cover


async def _validated_pdf_body(response: httpx.Response, byte_limit: int) -> bytes:
    if response.status_code != 200:
        raise ReceiptIngestionError(f"RECEIPT_HTTP_STATUS_{response.status_code}")
    content_type = (
        response.headers.get("content-type", "")
        .split(";", 1)[0]
        .strip()
        .casefold()
    )
    if content_type != _PDF_CONTENT_TYPE:
        raise ReceiptIngestionError("RECEIPT_CONTENT_TYPE_INVALID")
    declared_length = response.headers.get("content-length")
    if declared_length:
        try:
            declared_size = int(declared_length)
        except ValueError as exc:
            raise ReceiptIngestionError("RECEIPT_CONTENT_LENGTH_INVALID") from exc
        if declared_size < 0 or declared_size > byte_limit:
            raise ReceiptIngestionError("RECEIPT_SIZE_EXCEEDED")
    data = bytearray()
    async for chunk in response.aiter_bytes(64 * 1024):
        data.extend(chunk)
        if len(data) > byte_limit:
            raise ReceiptIngestionError("RECEIPT_SIZE_EXCEEDED")
    body = bytes(data)
    if not body.startswith(_PDF_MAGIC):
        raise ReceiptIngestionError("RECEIPT_PDF_MAGIC_INVALID")
    return body


def _validate_source_url(raw_url: str, allowed_hosts: frozenset[str]) -> str:
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > _MAX_URL_LENGTH:
        raise ReceiptIngestionError("RECEIPT_URL_INVALID")
    if raw_url != raw_url.strip():
        raise ReceiptIngestionError("RECEIPT_URL_INVALID")
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise ReceiptIngestionError("RECEIPT_URL_INVALID") from exc
    if parsed.scheme.casefold() != "https":
        raise ReceiptIngestionError("RECEIPT_HTTPS_REQUIRED")
    if parsed.username or parsed.password:
        raise ReceiptIngestionError("RECEIPT_URL_CREDENTIALS_FORBIDDEN")
    if parsed.fragment:
        raise ReceiptIngestionError("RECEIPT_URL_FRAGMENT_FORBIDDEN")
    if not parsed.hostname:
        raise ReceiptIngestionError("RECEIPT_HOST_INVALID")
    try:
        hostname = _canonical_hostname(parsed.hostname)
    except UnicodeError as exc:
        raise ReceiptIngestionError("RECEIPT_HOST_INVALID") from exc
    if hostname not in allowed_hosts:
        raise ReceiptIngestionError("RECEIPT_HOST_NOT_ALLOWLISTED")
    if port not in {None, 443}:
        raise ReceiptIngestionError("RECEIPT_PORT_INVALID")
    return raw_url


def _canonical_hostname(value: str) -> str:
    return value.strip().rstrip(".").encode("idna").decode("ascii").casefold()


async def _resolve_public_addresses(raw_url: str) -> tuple[str, tuple[str, ...]]:
    hostname = urlsplit(raw_url).hostname
    if not hostname:
        raise ReceiptIngestionError("RECEIPT_HOST_INVALID")
    try:
        hostname = _canonical_hostname(hostname)
    except UnicodeError as exc:
        raise ReceiptIngestionError("RECEIPT_HOST_INVALID") from exc
    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ReceiptIngestionError("RECEIPT_DNS_FAILED") from exc
    addresses = {str(result[4][0]).split("%", 1)[0] for result in results}
    try:
        forbidden = not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        )
    except ValueError as exc:
        raise ReceiptIngestionError("RECEIPT_DNS_FAILED") from exc
    if forbidden:
        raise ReceiptIngestionError("RECEIPT_SSRF_ADDRESS_BLOCKED")
    return hostname, tuple(sorted(addresses))


def _pinned_https_url(raw_url: str, address: str) -> str:
    parsed = urlsplit(raw_url)
    netloc = f"[{address}]" if ":" in address else address
    return urlunsplit(("https", netloc, parsed.path, parsed.query, ""))
