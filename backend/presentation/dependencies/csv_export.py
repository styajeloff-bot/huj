"""Shared CSV export helper for admin listing endpoints."""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi.responses import StreamingResponse


def _csv_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    formula_chars = ("=", "+", "-", "@", "\t", "\r")
    if text.startswith(formula_chars):
        text = "'" + text
    return text


def rows_to_csv(headers: list[str], rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_escape(row.get(h)) for h in headers])
    return buffer.getvalue().encode("utf-8-sig")


def csv_streaming_response(
    headers: list[str],
    rows: list[dict[str, Any]],
    filename: str,
) -> StreamingResponse:
    content = rows_to_csv(headers, rows)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
