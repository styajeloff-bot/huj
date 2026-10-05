"""Shared httpx.AsyncClient for catalog image fetchers.

A single client is started in the FastAPI lifespan and closed on shutdown.
``get_client()`` raises ``RuntimeError`` if used before ``start()`` — no
lazy init, so forgetting to wire lifespan is caught loudly rather than
silently leaking connections via per-call clients.
"""
from __future__ import annotations

import httpx

from infrastructure.settings import settings


class _CatalogImageHttpClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.catalog_image_fetch_timeout,
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=settings.catalog_image_http_max_connections,
                    max_keepalive_connections=(
                        settings.catalog_image_http_max_keepalive
                    ),
                ),
            )

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "catalog image fetcher client used before start() —"
                " check lifespan wiring"
            )
        return self._client


_holder = _CatalogImageHttpClient()


async def start() -> None:
    await _holder.start()


async def stop() -> None:
    await _holder.stop()


def get_client() -> httpx.AsyncClient:
    return _holder.get()


__all__ = ["get_client", "start", "stop"]
