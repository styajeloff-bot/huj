"""Pillow-based image processing (sync Pillow run in a thread).

Vehicle images use :func:`optimize_image`. Format-preserving,
resizes to at most ``settings.image_max_width`` x ``settings.image_max_height``
while keeping aspect ratio and never upscaling.

Storefront logos are validated separately and never resized or re-encoded.
"""

from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from domain.storefronts import MAX_STOREFRONT_LOGO_BYTES
from infrastructure.settings import settings

_JPEG_QUALITY = 85
_MAX_DECODED_IMAGE_PIXELS = 25_000_000

_EXT_BY_CONTENT_TYPE: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def extension_for_content_type(content_type: str) -> str:
    """Return a filename extension (with leading dot) for an output content type."""
    return _EXT_BY_CONTENT_TYPE.get(content_type, "")


def _normalize_input_content_type(content_type: str) -> str:
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct == "image/jpg":
        return "image/jpeg"
    return ct


def _optimize_sync(data: bytes, content_type: str) -> tuple[bytes, str]:
    ct = _normalize_input_content_type(content_type)
    max_size = (settings.image_max_width, settings.image_max_height)
    with Image.open(BytesIO(data)) as img:
        if (
            img.width <= 0
            or img.height <= 0
            or img.width * img.height > _MAX_DECODED_IMAGE_PIXELS
        ):
            raise ValueError("Image dimensions exceed the safe decode limit")
        # Note: Image.thumbnail uses LANCZOS resampling which is technically
        # lossy (pixel resampling). The encoder settings below are lossless
        # for PNG/WebP — the only loss is the spatial downsample itself,
        # which the caller accepts as an explicit tradeoff for the target
        # tile size. ``thumbnail`` never upscales.
        if ct == "image/png":
            png_img = (
                img
                if img.mode in ("RGB", "RGBA", "L", "LA", "P")
                else img.convert("RGBA")
            )
            png_img.thumbnail(max_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            png_img.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"

        if ct == "image/webp":
            webp_img = (
                img.copy()
                if img.mode in ("RGB", "RGBA")
                else img.convert("RGBA" if "A" in img.mode else "RGB")
            )
            webp_img.thumbnail(max_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            webp_img.save(out, format="WEBP", lossless=True, quality=100)
            return out.getvalue(), "image/webp"

        if ct == "image/gif":
            # Animated GIFs collapse to their first frame, re-encoded as PNG
            # (lossless). Animation is out of scope.
            img.seek(0)
            frame = img.convert("RGBA")
            frame.thumbnail(max_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            frame.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"

        # JPEG and anything unknown -> progressive JPEG q=85.
        rgb = img.convert("RGB")
        rgb.thumbnail(max_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        rgb.save(out, format="JPEG", quality=_JPEG_QUALITY, progressive=True)
        return out.getvalue(), "image/jpeg"


async def optimize_image(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Resize (``settings.image_max_width`` x ``settings.image_max_height``)
    preserving the source format.

    - PNG  -> PNG  (``optimize=True``, lossless zlib).
    - WebP -> WebP (``lossless=True, quality=100``).
    - GIF  -> PNG  (first frame only, lossless).
    - JPEG / unknown -> progressive JPEG q=85.

    Returns ``(optimized_bytes, output_content_type)``.
    """
    return await asyncio.to_thread(_optimize_sync, data, content_type)


def _validate_storefront_logo_image_sync(data: bytes) -> str:
    """Fully validate a static raster and return its actual MIME type."""
    if not data or len(data) > MAX_STOREFRONT_LOGO_BYTES:
        raise ValueError("Storefront logo exceeds the upload size limit")
    with Image.open(BytesIO(data)) as img:
        content_type = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }.get(img.format or "")
        if content_type is None:
            raise ValueError("Unsupported storefront logo format")
        if (
            img.width <= 0
            or img.height <= 0
            or img.width * img.height > _MAX_DECODED_IMAGE_PIXELS
        ):
            raise ValueError("Image dimensions exceed the safe decode limit")
        if getattr(img, "n_frames", 1) != 1:
            raise ValueError("Animated storefront logos are not supported")
        img.verify()
    # verify checks container integrity (including PNG CRCs), but does not
    # necessarily decode pixels. Reopen and force a complete raster decode too.
    with Image.open(BytesIO(data)) as img:
        img.load()
    return content_type


async def validate_storefront_logo_image(data: bytes) -> str:
    """Validate a static JPEG/PNG/WebP without changing any original bytes.

    Return the decoded MIME type. The caller stores/serves the original data;
    dimensions, alpha, ICC profile and EXIF orientation remain untouched.
    """
    return await asyncio.to_thread(_validate_storefront_logo_image_sync, data)
