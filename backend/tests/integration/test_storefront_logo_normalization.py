import struct
import zlib
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from PIL import Image, ImageCms
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import MAX_STOREFRONT_LOGO_BYTES
from infrastructure.models.storefronts import Storefront
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage


def _image_bytes(size: tuple[int, int], fmt: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (120, 100, 80)).save(output, format=fmt)
    return output.getvalue()


def _png_with_bad_pixel_crc() -> bytes:
    data = bytearray(_image_bytes((20, 10)))
    chunk = data.index(b"IDAT")
    size = int.from_bytes(data[chunk - 4 : chunk], "big")
    data[chunk + 4 + size] ^= 1
    return bytes(data)


def _animated_image(fmt: str) -> bytes:
    output = BytesIO()
    first = Image.new("RGBA", (20, 10), (255, 0, 0, 255))
    second = Image.new("RGBA", (20, 10), (0, 0, 255, 255))
    first.save(output, format=fmt, save_all=True, append_images=[second], duration=100)
    return output.getvalue()


def _unsafe_dimensions() -> bytes:
    data = _image_bytes((1, 1))
    header = struct.pack(">II", 5001, 5000) + data[24:29]
    checksum = struct.pack(">I", zlib.crc32(b"IHDR" + header))
    return data[:16] + header + checksum + data[33:]


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
async def test_legacy_logo_get_preserves_original_without_writing_or_version_change(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    fmt: str,
) -> None:
    storage = FakeObjectStorage()
    key = "legacy/aurus.webp"
    original = _image_bytes((505, 384), fmt)
    # Legacy metadata need not match its bytes: return the actual validated MIME.
    await storage.put(key, original, "image/webp")
    storefront = Storefront(
        slug="legacy-logo",
        is_default=False,
        is_active=True,
        version=7,
        logo_storage_key=key,
        logo_content_type="image/webp",
    )
    db_session.add(storefront)
    await db_session.flush()
    monkeypatch.setattr(
        storage, "put", AsyncMock(side_effect=AssertionError("GET wrote logo"))
    )
    monkeypatch.setattr(
        storage, "delete", AsyncMock(side_effect=AssertionError("GET deleted logo"))
    )
    set_object_storage(storage)
    try:
        logo = await client.get("/api/v1/storefronts/legacy-logo/logo")
        assert logo.status_code == 200, logo.text
        assert logo.headers["content-type"] == f"image/{fmt.lower()}"
        assert logo.headers["x-content-type-options"] == "nosniff"
        assert logo.content == original
        with Image.open(BytesIO(logo.content)) as decoded:
            assert decoded.size == (505, 384)
            assert decoded.format == fmt
        repeated = await client.get("/api/v1/storefronts/legacy-logo/logo")
        assert repeated.content == original
        stored_original = await storage.get(key)
        assert stored_original is not None and stored_original.data == original
        assert list(storage.items) == [key]
        public = await client.get("/api/v1/storefronts/legacy-logo")
        assert public.json()["version"] == 7
    finally:
        set_object_storage(None)


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
async def test_logo_upload_and_inherited_get_preserve_original_bytes_and_format(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    fmt: str,
) -> None:
    storage = FakeObjectStorage()
    set_object_storage(storage)
    try:
        root = (await client.get("/api/v1/storefront")).json()
        child = Storefront(slug="inherited-logo", is_default=False, is_active=True)
        db_session.add(child)
        await db_session.flush()
        image = Image.new(
            "RGB" if fmt == "JPEG" else "RGBA",
            (200, 100),
            (120, 100, 80) if fmt == "JPEG" else (120, 100, 80, 123),
        )
        exif = Image.Exif()
        exif[274] = 6
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        output = BytesIO()
        image.save(output, format=fmt, exif=exif, icc_profile=profile)
        original = output.getvalue()
        upload = await client.put(
            f"/api/v1/admin/storefronts/{root['id']}/logo",
            headers={"Authorization": f"Bearer {employee_token}"},
            files={"file": (f"logo.{fmt.lower()}", original, f"image/{fmt.lower()}")},
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["version"] == root["version"] + 1
        assert len(storage.items) == 1
        stored = next(iter(storage.items.values()))
        assert stored.data == original
        assert stored.content_type == f"image/{fmt.lower()}"
        extension = "jpg" if fmt == "JPEG" else fmt.lower()
        assert stored.key == f"storefronts/{root['id']}/logo.{extension}"
        with Image.open(BytesIO(stored.data)) as decoded:
            assert decoded.size == (200, 100)
            assert decoded.format == fmt
            assert decoded.getexif()[274] == 6
            assert decoded.info["icc_profile"] == profile
            if fmt != "JPEG":
                assert decoded.getchannel("A").getpixel((0, 0)) == 123
        inherited = await client.get("/api/v1/storefronts/inherited-logo/logo")
        assert inherited.status_code == 200, inherited.text
        assert inherited.content == original
        assert inherited.headers["content-type"] == f"image/{fmt.lower()}"
        assert (
            inherited.headers["cache-control"] == "public, max-age=0, must-revalidate"
        )
        assert (await client.get("/api/v1/storefront/logo")).content == original
        assert (await client.get("/api/v1/storefront")).json()[
            "version"
        ] == upload.json()["version"]
    finally:
        set_object_storage(None)


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (b"broken", "image/png"),
        (_image_bytes((2, 2), "BMP"), "image/png"),
        (_image_bytes((2, 2), "GIF"), "image/png"),
        (_image_bytes((20, 10), "JPEG"), "image/png"),
        (_png_with_bad_pixel_crc(), "image/png"),
        (_image_bytes((20, 10), "PNG")[:-12], "image/png"),
        (_image_bytes((20, 10), "JPEG")[:-8], "image/jpeg"),
        (_animated_image("PNG"), "image/png"),
        (_animated_image("WEBP"), "image/webp"),
        (_unsafe_dimensions(), "image/png"),
        (b"", "image/png"),
        (b"<svg/>", "image/svg+xml"),
        (b"x" * (MAX_STOREFRONT_LOGO_BYTES + 1), "image/png"),
    ],
    ids=[
        "broken",
        "bmp",
        "gif",
        "mime-mismatch",
        "bad-png-crc",
        "truncated-png",
        "truncated-jpeg",
        "animated-png",
        "animated-webp",
        "unsafe-pixels",
        "empty",
        "svg",
        "oversize",
    ],
)
async def test_invalid_logo_upload_preserves_previous_file_and_version(
    client: AsyncClient,
    employee_token: str,
    data: bytes,
    content_type: str,
) -> None:
    storage = FakeObjectStorage()
    set_object_storage(storage)
    try:
        root = (await client.get("/api/v1/storefront")).json()
        path = f"/api/v1/admin/storefronts/{root['id']}/logo"
        headers = {"Authorization": f"Bearer {employee_token}"}
        initial = await client.put(
            path,
            headers=headers,
            files={
                "file": ("valid.png", _image_bytes((20, 10)), "image/png"),
            },
        )
        assert initial.status_code == 200, initial.text
        stored_before = dict(storage.items)
        rejected = await client.put(
            path,
            headers=headers,
            files={
                "file": ("logo.png", data, content_type),
            },
        )
        assert rejected.status_code == 422, rejected.text
        assert "статич" in rejected.json()["detail"]
        assert storage.items == stored_before
        public = (await client.get("/api/v1/storefront")).json()
        assert public["version"] == initial.json()["version"]
        logo = await client.get("/api/v1/storefront/logo")
        assert logo.content == next(iter(stored_before.values())).data
    finally:
        set_object_storage(None)


@pytest.mark.parametrize(
    "data",
    [
        b"broken",
        _png_with_bad_pixel_crc(),
        _image_bytes((20, 10), "PNG")[:-12],
        _image_bytes((20, 10), "JPEG")[:-8],
        _image_bytes((2, 2), "GIF"),
        _animated_image("PNG"),
        _animated_image("WEBP"),
        _unsafe_dimensions(),
        b"x" * (MAX_STOREFRONT_LOGO_BYTES + 1),
    ],
    ids=[
        "broken",
        "bad-crc",
        "truncated-png",
        "truncated-jpeg",
        "gif",
        "animated-png",
        "animated-webp",
        "unsafe-pixels",
        "oversize",
    ],
)
async def test_invalid_legacy_logo_returns_404_without_modification(
    client: AsyncClient,
    db_session: AsyncSession,
    data: bytes,
) -> None:
    storage = FakeObjectStorage()
    key = "legacy/invalid-logo.png"
    await storage.put(key, data, "image/png")
    db_session.add(
        Storefront(
            slug="invalid-logo",
            is_default=False,
            is_active=True,
            version=7,
            logo_storage_key=key,
            logo_content_type="image/png",
        )
    )
    await db_session.flush()
    before = dict(storage.items)
    set_object_storage(storage)
    try:
        response = await client.get("/api/v1/storefronts/invalid-logo/logo")
        assert response.status_code == 404, response.text
        assert storage.items == before
        assert (await client.get("/api/v1/storefronts/invalid-logo")).json()[
            "version"
        ] == 7
    finally:
        set_object_storage(None)


async def test_replacing_logo_format_updates_extension_and_removes_only_previous_logo(
    client: AsyncClient,
    employee_token: str,
) -> None:
    storage = FakeObjectStorage()
    await storage.put("other/logo.png", _image_bytes((20, 10)), "image/png")
    unrelated = storage.items["other/logo.png"]
    set_object_storage(storage)
    try:
        root = (await client.get("/api/v1/storefront")).json()
        path = f"/api/v1/admin/storefronts/{root['id']}/logo"
        for version_delta, (fmt, extension) in enumerate(
            [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp"), ("JPEG", "jpg")],
            start=1,
        ):
            original = _image_bytes((250, 170), fmt)
            content_type = f"image/{fmt.lower()}"
            response = await client.put(
                path,
                headers={"Authorization": f"Bearer {employee_token}"},
                files={
                    "file": (
                        "untrusted-filename.webp",
                        original,
                        content_type + "; charset=binary",
                    )
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["version"] == root["version"] + version_delta
            key = f"storefronts/{root['id']}/logo.{extension}"
            assert set(storage.items) == {key, "other/logo.png"}
            assert storage.items["other/logo.png"] == unrelated
            assert storage.items[key].data == original
            assert storage.items[key].content_type == content_type
            downloaded = await client.get("/api/v1/storefront/logo")
            assert downloaded.content == original
            assert downloaded.headers["content-type"] == content_type
    finally:
        set_object_storage(None)
