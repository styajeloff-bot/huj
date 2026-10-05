"""Document recognition HTTP client (provider-agnostic; currently DBRAIN).

This is a thin transport wrapper. Field mapping (passport → questionnaire)
and confidence thresholds are business logic and live in the application
layer or domain services, not here.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from infrastructure.logging import log_event
from infrastructure.settings import settings


@dataclass(frozen=True)
class _DocTypeConfig:
    doc_type: str
    use_internal_api: bool = False
    normalization_fias: bool = False


# Map our document_type values onto the provider's `doc_type` parameter.
# Extend as new recognised document classes are added.
_PROVIDER_DOC_TYPES: dict[str, _DocTypeConfig] = {
    "ceo_passport_page23": _DocTypeConfig(
        doc_type="passport_main",
        use_internal_api=True,
    ),
    "ceo_passport_registration": _DocTypeConfig(
        doc_type="passport_registration",
        normalization_fias=True,
    ),
}


@dataclass(frozen=True)
class RecognitionResult:
    success: bool
    data: dict[str, Any] | None = None
    task_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PassportPage:
    """Single page input for :func:`recognize_passport_batch`."""

    passport_type: str
    file_bytes: bytes
    filename: str
    content_type: str


@dataclass(frozen=True)
class BatchRecognitionResult:
    """Per-page result map — same keys as the input ``passport_type`` values.

    ``raw_response`` carries the full provider payload for audit/debug.
    """

    per_page: dict[str, RecognitionResult]
    raw_response: dict[str, Any] | None = None
    task_id: str | None = None


class DocumentRecognitionError(RuntimeError):
    """Raised when the recognition provider is misconfigured or unsupported."""


def calculate_file_hash(buffer: bytes) -> str:
    """SHA-256 hex digest — used as cache key to avoid re-recognising the same file."""
    return hashlib.sha256(buffer).hexdigest()


def is_supported(document_type: str) -> bool:
    return document_type in _PROVIDER_DOC_TYPES


async def recognize_document(
    file_bytes: bytes,
    document_type: str,
    filename: str = "document.jpg",
    content_type: str = "image/jpeg",
) -> RecognitionResult:
    """POST the document to the recognition provider and return the parsed response.

    Returns ``RecognitionResult(success=False, error=...)`` on transport / HTTP
    failures so the caller can fall back to manual review without crashing
    a background task. Misconfiguration (no token, unknown doc_type) raises
    :class:`DocumentRecognitionError` because those are programmer errors.
    """
    if not settings.document_recognition_token:
        raise DocumentRecognitionError(
            "document_recognition_token is not configured"
        )

    cfg = _PROVIDER_DOC_TYPES.get(document_type)
    if cfg is None:
        raise DocumentRecognitionError(
            f"unsupported document type: {document_type}"
        )

    params: dict[str, str] = {
        "token": settings.document_recognition_token,
        "doc_type": cfg.doc_type,
        "mode": "recognize_only",
        "return_crops": "false",
    }
    if cfg.use_internal_api:
        params["use_internal_api"] = "true"
    if cfg.normalization_fias:
        params["normalization_fias"] = "true"

    url = f"{settings.document_recognition_host.rstrip('/')}/recognize"

    try:
        async with httpx.AsyncClient(
            timeout=settings.document_recognition_timeout_seconds
        ) as client:
            response = await client.post(
                url,
                params=params,
                files={"image": (filename, file_bytes, content_type)},
            )
    except httpx.HTTPError as exc:
        log_event(
            "warning",
            "document.recognition.transport_failed",
            "Document recognition provider request failed",
            error=exc,
            component="document_recognition",
            dependency="document-recognition-provider",
            operation="recognize",
        )
        return RecognitionResult(success=False, error=str(exc))

    if response.status_code >= 400:
        log_event(
            "warning",
            "document.recognition.provider_error",
            "Document recognition provider returned an error",
            component="document_recognition",
            dependency="document-recognition-provider",
            operation="recognize",
            http_status_code=response.status_code,
            response_size_bytes=len(response.content),
        )
        return RecognitionResult(
            success=False,
            error=f"provider error {response.status_code}",
        )

    payload = response.json()
    items = payload.get("items")
    log_event(
        "info",
        "document.recognition.completed",
        "Document recognition completed",
        component="document_recognition",
        dependency="document-recognition-provider",
        operation="recognize",
        task_id=payload.get("task_id"),
        item_count=len(items) if isinstance(items, list) else 0,
    )
    return RecognitionResult(
        success=True,
        data=payload,
        task_id=payload.get("task_id"),
    )


async def recognize_passport_batch(
    pages: list[PassportPage],
) -> BatchRecognitionResult:
    """Recognize multiple passport pages.

    DBRAIN does not reliably support multiple files in a single ``/recognize``
    request (it often returns only the first page regardless of how many
    ``image`` parts are sent). We therefore fan-out to parallel single-page
    calls and merge the results back into a ``BatchRecognitionResult``.
    """
    if not pages:
        raise DocumentRecognitionError("no pages to recognize")

    results = await asyncio.gather(
        *(
            recognize_document(
                file_bytes=p.file_bytes,
                document_type=p.passport_type,
                filename=p.filename,
                content_type=p.content_type,
            )
            for p in pages
        ),
        return_exceptions=True,
    )

    per_page: dict[str, RecognitionResult] = {}
    raw_items: list[dict[str, Any]] = []
    task_ids: list[str] = []

    for page, result in zip(pages, results, strict=True):
        if not isinstance(result, RecognitionResult):
            per_page[page.passport_type] = RecognitionResult(
                success=False,
                error=f"single-page recognition failed: {result}",
            )
        else:
            per_page[page.passport_type] = result
            if result.data and isinstance(result.data, dict):
                raw_items.extend(result.data.get("items", []))
                if result.task_id:
                    task_ids.append(result.task_id)

    # Build a synthetic payload that looks like a batch response so
    # downstream consumers (cache, SOPD context) see the same shape.
    synthetic_payload: dict[str, Any] = {"items": raw_items}
    if task_ids:
        synthetic_payload["task_id"] = task_ids[0]

    return BatchRecognitionResult(
        per_page=per_page,
        raw_response=synthetic_payload,
        task_id=task_ids[0] if task_ids else None,
    )
