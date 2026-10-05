"""Render a filled СОПД PDF from the .md template.

Two concerns live here:

* ``compute_template_hash()`` — sha256 of the ``sopd.md`` that the
  Docker image ships. Cached after first read; the hash is the first
  half of the render-cache key. Bumping the template in the image
  produces a new hash and the cache table automatically falls through
  to re-render.

* ``compute_context_hash()`` — canonical-JSON sha256 of the fill dict.
  Two renders with identical context share a cache row.

* ``render_pdf(context)`` — runs Jinja2 → Markdown → WeasyPrint. Returns
  the PDF bytes. Callers must invoke this from a taskiq worker or
  background thread; WeasyPrint is CPU-heavy.

The key under which we store renders in S3 is:

    {settings.document_storage_prefix}/sopd/{template_hash}/{context_hash}.pdf
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

# Template search order: image build installs it at ``/app``; local dev
# has it in the fastapi package root. Kept as a tuple so tests can
# monkey-patch for a fixture template.
_TEMPLATE_CANDIDATES: tuple[Path, ...] = (
    Path("/app/sopd.md"),
    Path(__file__).resolve().parents[2] / "sopd.md",
)


class _TemplateState:
    path_cache: Path | None = None
    hash_cache: str | None = None


# TODO(tender-demo): remove this fallback after the tender video is recorded.
# For the demo we guarantee a СОПД PDF always comes back — if the renderer
# fails or the template is missing, routers serve this pre-rendered static
# file instead of surfacing an error. Real prod must expose the underlying
# failure so it can be fixed.
_FALLBACK_PDF_CANDIDATES: tuple[Path, ...] = (
    Path("/app/sopd.pdf"),
    Path(__file__).resolve().parents[2] / "sopd.pdf",
)


def load_fallback_sopd_pdf() -> bytes | None:
    """Return the static pre-rendered СОПД PDF if present, else ``None``."""
    for path in _FALLBACK_PDF_CANDIDATES:
        if path.is_file():
            return path.read_bytes()
    return None


class SopdTemplateUnavailableError(RuntimeError):
    """Raised when ``sopd.md`` is not present."""


def _resolve_template() -> Path:
    if _TemplateState.path_cache is not None:
        return _TemplateState.path_cache
    for path in _TEMPLATE_CANDIDATES:
        if path.is_file():
            _TemplateState.path_cache = path
            return path
    raise SopdTemplateUnavailableError(
        "sopd.md not found — template not present in the image"
    )


def compute_template_hash() -> str:
    """Sha256 of the template file, cached after first read."""
    if _TemplateState.hash_cache is not None:
        return _TemplateState.hash_cache
    path = _resolve_template()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    _TemplateState.hash_cache = h.hexdigest()
    return _TemplateState.hash_cache


def compute_context_hash(context: dict[str, Any]) -> str:
    """Sha256 of the canonicalised context JSON (sorted keys, no spaces)."""
    canonical = json.dumps(
        context, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_s3_key(*, template_hash: str, context_hash: str) -> str:
    prefix = settings.document_storage_prefix.rstrip("/")
    return f"{prefix}/sopd/{template_hash}/{context_hash}.pdf"


def _normalise_context(context: dict[str, Any]) -> dict[str, str]:
    """Fill every known placeholder with a string.

    The template's tokens are the canonical set — missing fields render
    as an empty string so blank СОПД (no passport data yet) looks like
    the printable placeholder form.
    """
    keys = (
        "full_name",
        "gender",
        "birth_date",
        "birth_place",
        "passport_series_number",
        "passport_issued_by",
        "passport_issued_at",
        "passport_code",
        "address",
        "inn",
        "phone",
        "email",
        "leasing_companies",
        "contractors",
    )
    normalised: dict[str, str] = {}
    for key in keys:
        value = context.get(key)
        normalised[key] = "" if value is None else str(value)
    return normalised


def _render_sync(context: dict[str, Any]) -> bytes:
    """Synchronous Jinja2 + Markdown + WeasyPrint pipeline. Runs in a thread."""
    import markdown
    from jinja2 import Template
    from weasyprint import CSS, HTML

    template_path = _resolve_template()
    md_source = template_path.read_text(encoding="utf-8")
    rendered_md = Template(md_source).render(_normalise_context(context))
    html = markdown.markdown(
        rendered_md,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    css = """
    @page { size: A4; margin: 2cm; }
    body {
        font-family: "DejaVu Sans", sans-serif;
        font-size: 11pt;
        line-height: 1.4;
        color: #000;
    }
    h1 { font-size: 14pt; text-align: center; margin-bottom: 1em; }
    h2 { font-size: 12pt; margin-top: 1.2em; margin-bottom: 0.6em; }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 0.5em 0;
    }
    th, td {
        border: 1px solid #000;
        padding: 4px 6px;
        text-align: left;
        vertical-align: top;
    }
    th { background: #eee; }
    ul { margin: 0.5em 0; padding-left: 1.5em; }
    p { margin: 0.4em 0; }
    """
    return HTML(string=html).write_pdf(stylesheets=[CSS(string=css)])  # type: ignore[no-any-return]


async def render_pdf(context: dict[str, Any]) -> bytes:
    """Async wrapper: runs the heavy pipeline in a worker thread."""
    return await asyncio.to_thread(_render_sync, context)
