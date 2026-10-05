"""Read the documented parser-api EGRUL PDF response."""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import PurePosixPath

import httpx

from infrastructure.settings import settings

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_RESPONSE_BYTES = MAX_PDF_BYTES * 4 // 3 + 65536


@dataclass(frozen=True)
class EgrulExtract:
    status: str
    filename: str = ""
    content: bytes = b""


async def fetch_egrul_extract(*, inn: str | None, ogrn: str | None) -> EgrulExtract:
    if not settings.parser_api_key or not (inn or ogrn):
        return EgrulExtract("unavailable")
    params = {"key": settings.parser_api_key}
    params["inn" if inn else "ogrn"] = str(inn or ogrn)
    url = settings.parser_api_url.rstrip("/") + "/parser/nalog_egrul_api/pdf_download"
    try:
        async with httpx.AsyncClient(timeout=settings.parser_api_timeout_ms / 1000, follow_redirects=False) as client, client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    return EgrulExtract("unavailable")
        return _decode_extract(bytes(body))
    except (httpx.HTTPError, ValueError, binascii.Error):
        return EgrulExtract("unavailable")


def _decode_extract(body: bytes) -> EgrulExtract:
    data = json.loads(body)
    if not isinstance(data, dict) or data.get("success") != 1:
        return EgrulExtract("unavailable")
    if not data.get("pdf_content"):
        return EgrulExtract("not_found")
    if not isinstance(data["pdf_content"], str):
        return EgrulExtract("unavailable")
    content = base64.b64decode(data["pdf_content"], validate=True)
    if not content.startswith(b"%PDF-") or len(content) > MAX_PDF_BYTES:
        return EgrulExtract("unavailable")
    name = PurePosixPath(str(data.get("file_name") or "egrul.pdf").replace("\\", "/")).name
    if not name.lower().endswith(".pdf") or len(name) > 240:
        name = "egrul.pdf"
    return EgrulExtract("updated", name, content)
