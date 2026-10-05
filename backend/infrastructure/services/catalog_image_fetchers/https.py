"""Plain HTTPS image fetcher — accepts any https:// URL that serves an image."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from domain.services.catalog_image_fetcher import FetchedImage
from infrastructure.services.catalog_image_fetchers._client import get_client

logger = logging.getLogger("carcraft-backend")

_IMAGE_EXTS: frozenset[str] = frozenset(
    {".webp", ".png", ".jpeg", ".jpg", ".gif"}
)


def _url_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    dot = path.rfind(".")
    return path[dot:] if dot != -1 else ""


class HttpsImageFetcher:
    """Fallback fetcher for direct-https image URLs."""

    def supports(self, url: str) -> bool:
        if not url.startswith("https://"):
            return False
        # Extension match is a cheap pre-check; content-type is also
        # validated in `fetch()` to cover extensionless URLs.
        return _url_extension(url) in _IMAGE_EXTS or "." not in urlparse(url).path

    async def fetch(self, url: str) -> FetchedImage | None:
        try:
            resp = await get_client().get(url)
        except httpx.HTTPError as exc:
            logger.warning("https_image_download_failed url=%s err=%s", url, exc)
            return None

        if resp.status_code >= 400:
            logger.warning(
                "https_image_download_status url=%s status=%s",
                url,
                resp.status_code,
            )
            return None

        content_type = resp.headers.get("content-type", "")
        if not content_type.lower().startswith("image/"):
            logger.warning(
                "https_image_not_image url=%s content_type=%s", url, content_type
            )
            return None

        ext = _url_extension(url) or ".jpg"
        filename = urlparse(url).path.rsplit("/", 1)[-1] or f"image{ext}"
        return FetchedImage(
            content=resp.content,
            content_type=content_type.split(";", 1)[0].strip(),
            suggested_filename=filename,
        )
