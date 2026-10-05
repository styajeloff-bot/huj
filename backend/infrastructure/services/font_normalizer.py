"""Decode storefront fonts and emit a deterministic WOFF2 object."""

from __future__ import annotations

import asyncio
from io import BytesIO

from fontTools.ttLib import TTFont


class FontNormalizationError(ValueError):
    """The uploaded bytes are not a usable OpenType font."""


def _require_valid_font(font: TTFont, *, woff2: bool = False) -> None:
    required_tables = {"head", "maxp", "cmap", "name"}
    if not required_tables.issubset(font.keys()) or not font.getGlyphOrder():
        raise FontNormalizationError
    if woff2 and font.flavor != "woff2":
        raise FontNormalizationError


def _require_normalized_bytes(data: bytes) -> None:
    if not data:
        raise FontNormalizationError


def _normalize_font_to_woff2_sync(data: bytes) -> bytes:
    source = BytesIO(data)
    output = BytesIO()
    try:
        with TTFont(
            source,
            lazy=False,
            recalcBBoxes=False,
            recalcTimestamp=False,
        ) as font:
            _require_valid_font(font)
            font.flavor = "woff2"
            font.save(output, reorderTables=False)

        normalized = output.getvalue()
        _require_normalized_bytes(normalized)
        with TTFont(
            BytesIO(normalized),
            lazy=False,
            recalcBBoxes=False,
            recalcTimestamp=False,
        ) as verification:
            _require_valid_font(verification, woff2=True)
    except FontNormalizationError:
        raise
    except Exception as exc:
        raise FontNormalizationError from exc
    return normalized


async def normalize_font_to_woff2(data: bytes) -> bytes:
    return await asyncio.to_thread(_normalize_font_to_woff2_sync, data)
