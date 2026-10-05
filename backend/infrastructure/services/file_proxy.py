"""Exchange / catalog file proxying.

The object-storage bucket is private — a direct ``storage.yandexcloud.net``
URL returns Access Denied in the browser. To keep the frontend agnostic of
storage internals, every ``*_file_url`` column that used to hold the raw
S3 URL is now served through a backend proxy endpoint. The stored value
itself can be either the legacy ``https://…`` URL (written before this
patch) or the new bare S3 key — :func:`resolve_s3_key` normalises both.

There is no authenticated token in the proxy URLs; the proxy endpoints
themselves enforce ownership (LC owns the cart / request, dealer owns the
bid, etc.). The path carries the business id, which the endpoint resolves
to the actual stored key server-side.
"""
from __future__ import annotations

from uuid import UUID

from infrastructure.settings import settings


def _endpoint() -> str:
    return (settings.s3_endpoint or "").rstrip("/")


def _bucket() -> str:
    return settings.s3_bucket


def _prefixes() -> list[str]:
    """Possible URL prefixes that precede the raw S3 key in legacy values."""
    endpoint = _endpoint()
    bucket = _bucket()
    prefixes: list[str] = []
    if endpoint and bucket:
        prefixes.append(f"{endpoint}/{bucket}/")
    if bucket:
        prefixes.append(
            f"https://{bucket}.s3.{settings.s3_region}.amazonaws.com/"
        )
    return prefixes


def resolve_s3_key(stored: str | None) -> str | None:
    """Return the bare S3 key for a stored ``*_file_url`` value.

    Handles both legacy absolute URLs (``https://storage…/bucket/KEY``) and
    new values that already hold the bare key. Returns ``None`` when the
    input is empty so callers can branch on "no file attached".
    """
    if not stored:
        return None
    value = str(stored).strip()
    if not value:
        return None
    for prefix in _prefixes():
        if value.startswith(prefix):
            return value[len(prefix):]
    if value.startswith(("http://", "https://")):
        # Unrecognised absolute URL — fall back to the path component.
        return value.split("/", 3)[-1]
    return value


def exchange_cart_item_file_url(item_id: UUID) -> str:
    return f"/api/v1/exchange/cart/{item_id}/file"


def exchange_bid_file_url(bid_id: UUID) -> str:
    return f"/api/v1/exchange/bids/{bid_id}/file"


def exchange_bid_kp_url(bid_id: UUID) -> str:
    return f"/api/v1/exchange/bids/{bid_id}/kp"


def exchange_request_file_url(request_id: UUID) -> str:
    return f"/api/v1/exchange/requests/{request_id}/file"
