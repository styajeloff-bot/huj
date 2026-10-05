"""Google Drive image fetcher — direct-download URL, HTML guard, ext from MIME."""
from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

import httpx

from domain.services.catalog_image_fetcher import FetchedImage
from infrastructure.services.catalog_image_fetchers._client import get_client

logger = logging.getLogger("carcraft-backend")

_GDRIVE_FILE_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)/")

_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _ext_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".jpg"
    return _MIME_TO_EXT.get(content_type.split(";", 1)[0].strip().lower(), ".jpg")


def google_drive_download_url(url: str) -> str | None:
    """Convert a Google Drive shared-file URL to its HTTPS download URL."""
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https" or parsed.hostname != "drive.google.com":
        return None
    match = _GDRIVE_FILE_ID_RE.search(parsed.path)
    if not match:
        return None
    return f"https://drive.google.com/uc?export=download&id={match.group(1)}"


class GoogleDriveFetcher:
    """Fetcher for Google Drive shared-file URLs."""

    def supports(self, url: str) -> bool:
        return google_drive_download_url(url) is not None

    async def fetch(self, url: str) -> FetchedImage | None:
        download_url = google_drive_download_url(url)
        if download_url is None:
            logger.warning("gdrive_fetch_no_file_id url=%s", url)
            return None
        file_id = download_url.rpartition("=")[2]

        try:
            resp = await get_client().get(download_url)
        except httpx.HTTPError as exc:
            logger.warning("gdrive_download_failed file=%s err=%s", file_id, exc)
            return None

        if resp.status_code >= 400:
            logger.warning(
                "gdrive_download_status file=%s status=%s", file_id, resp.status_code
            )
            return None

        content_type = resp.headers.get("content-type", "image/jpeg")
        if "text/html" in content_type.lower():
            logger.warning(
                "gdrive_returned_html file=%s (auth wall?)", file_id
            )
            return None

        ext = _ext_from_content_type(content_type)
        return FetchedImage(
            content=resp.content,
            content_type=content_type.split(";", 1)[0].strip(),
            suggested_filename=f"{file_id}{ext}",
        )
