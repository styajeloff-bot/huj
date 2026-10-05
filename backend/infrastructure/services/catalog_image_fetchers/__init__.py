"""Pluggable catalog image fetchers.

Concrete adapters implement `domain.services.catalog_image_fetcher.CatalogImageFetcher`.
The registry dispatches a URL to the first fetcher whose `supports()` returns True,
so registration order matters: GDrive URLs are also HTTPS, therefore the GDrive
fetcher must come first.
"""
from __future__ import annotations

import logging

from domain.services.catalog_image_fetcher import (
    CatalogImageFetcher,
    FetchedImage,
)
from infrastructure.services.catalog_image_fetchers.gdrive import GoogleDriveFetcher
from infrastructure.services.catalog_image_fetchers.https import HttpsImageFetcher

logger = logging.getLogger("carcraft-backend")


class CatalogImageFetcherRegistry:
    """Holds an ordered list of fetchers and dispatches URLs to the first match."""

    def __init__(self, fetchers: list[CatalogImageFetcher]) -> None:
        self._fetchers = fetchers

    async def fetch(self, url: str) -> FetchedImage | None:
        for fetcher in self._fetchers:
            if fetcher.supports(url):
                try:
                    return await fetcher.fetch(url)
                except Exception as exc:
                    logger.warning(
                        "catalog_image_fetch_failed url=%s fetcher=%s err=%s",
                        url,
                        type(fetcher).__name__,
                        exc,
                    )
                    return None
        logger.debug("catalog_image_no_fetcher url=%s", url)
        return None


_registry_holder: list[CatalogImageFetcherRegistry] = []


def get_fetcher_registry() -> CatalogImageFetcherRegistry:
    """Singleton factory wiring the default fetcher chain."""
    if not _registry_holder:
        _registry_holder.append(
            CatalogImageFetcherRegistry(
                [GoogleDriveFetcher(), HttpsImageFetcher()],
            )
        )
    return _registry_holder[0]


__all__ = [
    "CatalogImageFetcherRegistry",
    "GoogleDriveFetcher",
    "HttpsImageFetcher",
    "get_fetcher_registry",
]
