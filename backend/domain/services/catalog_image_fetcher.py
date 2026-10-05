"""Port for fetching catalog images from arbitrary URL sources.

Concrete implementations (Google Drive, plain HTTPS, ...) live under
`infrastructure/services/catalog_image_fetchers/`. The domain only knows
the abstract contract — no I/O imports here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FetchedImage:
    """Bytes + metadata for an image successfully fetched from a remote URL."""

    content: bytes
    content_type: str
    suggested_filename: str


class CatalogImageFetcher(Protocol):
    """A pluggable strategy for downloading a catalog image from one source.

    Implementations are tried in registration order; the first whose
    `supports(url)` returns True wins.
    """

    def supports(self, url: str) -> bool:
        """Return True if this fetcher can handle the given URL."""
        ...

    async def fetch(self, url: str) -> FetchedImage | None:
        """Download the image. Return None on any non-fatal failure."""
        ...
