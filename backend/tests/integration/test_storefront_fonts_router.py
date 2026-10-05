from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.vehicles import Warehouse
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage
from tests.infrastructure.test_font_normalizer import _test_ttf


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_font_catalog_requires_storefront_admin_scope(
    client: AsyncClient,
    client_token: str,
) -> None:
    unauthenticated = await client.get("/api/v1/admin/storefront-fonts")
    assert unauthenticated.status_code == 401

    forbidden = await client.get(
        "/api/v1/admin/storefront-fonts", headers=_auth(client_token)
    )
    assert forbidden.status_code == 403


async def test_font_upload_trims_metadata_before_enforcing_length(
    client: AsyncClient,
    employee_token: str,
) -> None:
    storage = FakeObjectStorage()
    set_object_storage(storage)
    try:
        name = "N" * 120
        description = "D" * 500
        response = await client.post(
            "/api/v1/admin/storefront-fonts",
            headers=_auth(employee_token),
            data={"name": f"  {name}  ", "description": f"  {description}  "},
            files={
                "file": (
                    "boundary.ttf",
                    _test_ttf("Boundary Font"),
                    "font/ttf",
                )
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["name"] == name
        assert response.json()["description"] == description
    finally:
        set_object_storage(None)


async def test_font_catalog_appearance_content_and_delete_fallback(  # noqa: PLR0915
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    storage = FakeObjectStorage()
    set_object_storage(storage)
    try:
        empty = await client.get(
            "/api/v1/admin/storefront-fonts", headers=_auth(employee_token)
        )
        assert empty.status_code == 200
        assert empty.json() == {"items": []}

        invalid = await client.post(
            "/api/v1/admin/storefront-fonts",
            headers=_auth(employee_token),
            data={"name": "Broken"},
            files={"file": ("broken.ttf", b"not a font", "font/ttf")},
        )
        assert invalid.status_code == 422, invalid.text
        assert storage.items == {}

        upload = await client.post(
            "/api/v1/admin/storefront-fonts",
            headers=_auth(employee_token),
            data={"name": "  Brand Sans  ", "description": "  Main brand  "},
            files={"file": ("brand.ttf", _test_ttf(), "font/ttf")},
        )
        assert upload.status_code == 201, upload.text
        font = upload.json()
        font_id = font["id"]
        assert upload.headers["location"] == (
            f"/api/v1/admin/storefront-fonts/{font_id}"
        )
        assert font["name"] == "Brand Sans"
        assert font["description"] == "Main brand"
        assert font["content_type"] == "font/woff2"
        assert font["storefront_usage_count"] == 0
        assert len(font["checksum_sha256"]) == 64
        assert list(storage.items) == [
            f"storefront-fonts/{font_id}/font.woff2"
        ]
        assert next(iter(storage.items.values())).data.startswith(b"wOF2")

        duplicate_name = await client.post(
            "/api/v1/admin/storefront-fonts",
            headers=_auth(employee_token),
            data={"name": "brand sans"},
            files={"file": ("other.otf", _test_ttf(), "font/otf")},
        )
        assert duplicate_name.status_code == 409

        duplicate_content = await client.post(
            "/api/v1/admin/storefront-fonts",
            headers=_auth(employee_token),
            data={"name": "Another"},
            files={"file": ("same.woff", _test_ttf(), "font/woff")},
        )
        assert duplicate_content.status_code == 409
        assert "Brand Sans" in duplicate_content.json()["detail"]

        edited = await client.patch(
            f"/api/v1/admin/storefront-fonts/{font_id}",
            headers=_auth(employee_token),
            json={"name": "Brand Display", "description": ""},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["name"] == "Brand Display"
        assert edited.json()["description"] is None

        root = (await client.get("/api/v1/storefront")).json()
        default_appearance = root["appearance"]
        assert default_appearance == {
            "colors": {
                "primary": "#3367BD",
                "background": "#F9FAFB",
                "surface": "#FFFFFF",
                "text": "#111827",
            },
            "border_radius": "medium",
            "font": {"id": None, "family": "Mulish", "url": None},
            "color_overrides": {},
        }

        low_contrast = await client.patch(
            f"/api/v1/admin/storefronts/{root['id']}",
            headers=_auth(employee_token),
            json={
                "appearance": {
                    "colors": {
                        "primary": "#eeeeee",
                        "background": "#ffffff",
                        "surface": "#ffffff",
                        "text": "#111827",
                    },
                    "border_radius": "large",
                    "font_id": font_id,
                }
            },
        )
        assert low_contrast.status_code == 200, low_contrast.text
        assert low_contrast.json()["appearance"]["colors"]["primary"] == "#EEEEEE"
        assert low_contrast.json()["version"] == root["version"] + 1

        invalid_hex = await client.patch(
            f"/api/v1/admin/storefronts/{root['id']}",
            headers=_auth(employee_token),
            json={
                "appearance": {
                    "colors": {
                        "primary": "#EEEEEE80",
                        "background": "#FFFFFF",
                        "surface": "#FFFFFF",
                        "text": "#111827",
                    },
                    "border_radius": "large",
                    "font_id": font_id,
                }
            },
        )
        assert invalid_hex.status_code == 422
        assert (await client.get("/api/v1/storefront")).json()["version"] == root[
            "version"
        ] + 1

        appearance = {
            "colors": {
                "primary": "#0050a4",
                "background": "#f9fafb",
                "surface": "#ffffff",
                "text": "#111827",
            },
            "border_radius": "large",
            "font_id": font_id,
        }
        updated = await client.patch(
            f"/api/v1/admin/storefronts/{root['id']}",
            headers=_auth(employee_token),
            json={"appearance": appearance},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["appearance"]["colors"]["primary"] == "#0050A4"
        assert updated.json()["appearance"]["font_id"] == font_id
        assert updated.json()["version"] == low_contrast.json()["version"] + 1

        public = (await client.get("/api/v1/storefront")).json()
        assert public["appearance"]["font"] == {
            "id": font_id,
            "family": f"storefront-font-{font_id.replace('-', '')}",
            "url": f"/api/v1/storefront-fonts/{font_id}/content",
        }
        assert "description" not in public["appearance"]["font"]

        content = await client.get(f"/api/v1/storefront-fonts/{font_id}/content")
        assert content.status_code == 200
        assert content.headers["content-type"] == "font/woff2"
        assert content.headers["x-content-type-options"] == "nosniff"
        assert content.headers["cache-control"] == (
            "public, max-age=31536000, immutable"
        )
        assert content.headers["etag"] == f'"{font["checksum_sha256"]}"'
        cached = await client.get(
            f"/api/v1/storefront-fonts/{font_id}/content",
            headers={"If-None-Match": content.headers["etag"]},
        )
        assert cached.status_code == 304
        assert cached.content == b""

        warehouse = Warehouse(address="Минск", brand="FAW", status="active")
        db_session.add(warehouse)
        await db_session.flush()
        child = await client.post(
            "/api/v1/admin/storefronts",
            headers=_auth(employee_token),
            json={"slug": "font-snapshot", "warehouse_ids": [warehouse.id]},
        )
        assert child.status_code == 201, child.text
        assert child.json()["appearance"] == updated.json()["appearance"]

        listed = await client.get(
            "/api/v1/admin/storefront-fonts", headers=_auth(employee_token)
        )
        assert listed.json()["items"][0]["storefront_usage_count"] == 2
        root_version = updated.json()["version"]
        child_version = child.json()["version"]

        deleted = await client.delete(
            f"/api/v1/admin/storefront-fonts/{font_id}",
            headers=_auth(employee_token),
        )
        assert deleted.status_code == 204, deleted.text
        assert storage.items == {}
        root_after = (await client.get("/api/v1/storefront")).json()
        child_after = (await client.get("/api/v1/storefronts/font-snapshot")).json()
        assert root_after["version"] == root_version + 1
        assert child_after["version"] == child_version + 1
        assert root_after["appearance"]["font"]["family"] == "Mulish"
        assert child_after["appearance"]["font"]["id"] is None
        assert (
            await client.get(f"/api/v1/storefront-fonts/{font_id}/content")
        ).status_code == 404
    finally:
        set_object_storage(None)
