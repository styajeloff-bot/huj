"""Shared `?format=` export dependency per REST_CONVENTIONS §3.

Listing endpoints accept a uniform ``?format=json|csv|xlsx`` query
parameter instead of dedicated ``/export`` sub-paths. The dependency
encodes the enum via ``Literal`` so FastAPI produces clean OpenAPI docs
and 422 responses for unsupported values automatically.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Query

ExportFormat = Literal["json", "csv", "xlsx"]
"""Canonical export format enum. Handlers can narrow further (e.g. only
``json`` / ``xlsx``) by validating after the dependency runs."""


def export_format_dep(
    _format: Annotated[ExportFormat, Query(alias="format")] = "json",
) -> ExportFormat:
    """Return the requested export format (default ``json``).

    The query-string name exposed to clients is ``format``
    (``?format=json|csv|xlsx``).

    Usage::

        from presentation.dependencies.export_format import (
            ExportFormat,
            export_format_dep,
        )

        @router.get("/things")
        async def list_things(
            fmt: Annotated[ExportFormat, Depends(export_format_dep)],
        ) -> ...:
            ...
    """
    return _format


__all__ = ["ExportFormat", "export_format_dep"]
