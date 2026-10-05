from io import BytesIO

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import PublicUIConfig, default_public_ui_config
from infrastructure.models.storefronts import Storefront
from infrastructure.models.vehicles import Warehouse
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _public_ui_payload() -> PublicUIConfig:
    return default_public_ui_config()


async def test_admin_create_and_public_context_inherits_root_contacts(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    assert (await client.get("/api/v1/storefronts/cars")).status_code == 404
    warehouse = Warehouse(address="Москва", brand="FAW", status="active")
    db_session.add(warehouse)
    await db_session.flush()

    invalid_contact = await client.post(
        "/api/v1/admin/storefronts",
        headers=_auth(employee_token),
        json={
            "slug": "bad-contact",
            "warehouse_ids": [warehouse.id],
            "contact_phone": "+++++",
        },
    )
    assert invalid_contact.status_code == 422, invalid_contact.text

    response = await client.post(
        "/api/v1/admin/storefronts",
        headers=_auth(employee_token),
        json={"slug": "FAW", "warehouse_ids": [warehouse.id]},
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["slug"] == "faw"
    assert created["warehouse_ids"] == [str(warehouse.id)]
    assert created["public_ui"] == _public_ui_payload()

    public = await client.get("/api/v1/storefronts/faw")
    assert public.status_code == 200, public.text
    assert public.json()["contact_email"] == "info@multileasing.ru"
    assert public.json()["contact_phone"] == "+7 (930) 999-03-65"
    assert public.json()["contact_phone_href"] == "+79309990365"
    assert public.json()["is_active"] is True
    assert public.json()["logo_url"] == "/images/logo.png"
    assert public.json()["public_ui"] == _public_ui_payload()

    deactivated = await client.patch(
        f"/api/v1/admin/storefronts/{created['id']}",
        headers=_auth(employee_token),
        json={"is_active": False},
    )
    assert deactivated.status_code == 200, deactivated.text
    assert (await client.get("/api/v1/storefronts/faw")).status_code == 404
    assert (
        await client.delete(
            f"/api/v1/admin/storefronts/{created['id']}",
            headers=_auth(employee_token),
        )
    ).status_code == 405
    blocked_delete = await client.delete(
        f"/api/v1/admin/warehouses/{warehouse.id}",
        headers=_auth(employee_token),
    )
    assert blocked_delete.status_code == 409, blocked_delete.text
    assert blocked_delete.json()["blockingDependencies"]["storefronts"] == 1


async def test_root_branding_patch_and_safe_logo_round_trip(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    assert root["logo_url"] == "/images/logo.png"
    patch = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"contact_email": "root@example.com"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["contact_email"] == "root@example.com"

    image = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    payload = BytesIO()
    image.save(payload, format="PNG")
    storage = FakeObjectStorage()
    set_object_storage(storage)
    try:
        upload = await client.put(
            f"/api/v1/admin/storefronts/{root['id']}/logo",
            headers=_auth(employee_token),
            files={"file": ("logo.png", payload.getvalue(), "image/png")},
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["logo_url"] == "/api/v1/storefront/logo"

        logo = await client.get("/api/v1/storefront/logo")
        assert logo.status_code == 200
        assert logo.headers["content-type"] == "image/png"
        assert logo.headers["cache-control"] == "public, max-age=0, must-revalidate"
        assert logo.content == payload.getvalue()
        with Image.open(BytesIO(logo.content)) as decoded_logo:
            assert decoded_logo.format == "PNG"
            decoded_logo.verify()

        child = Storefront(
            slug="logo-child", is_default=False, is_active=True, version=1
        )
        db_session.add(child)
        await db_session.flush()
        own_logo = await client.put(
            f"/api/v1/admin/storefronts/{child.id}/logo",
            headers=_auth(employee_token),
            files={"file": ("logo.png", payload.getvalue(), "image/png")},
        )
        assert own_logo.status_code == 200
        cleared = await client.delete(
            f"/api/v1/admin/storefronts/{child.id}/logo",
            headers=_auth(employee_token),
        )
        assert cleared.status_code == 200, cleared.text
        assert (
            cleared.json()["effective_logo_url"]
            == "/api/v1/storefronts/logo-child/logo"
        )
        inherited = await client.get("/api/v1/storefronts/logo-child/logo")
        assert inherited.status_code == 200
        Image.open(BytesIO(inherited.content)).verify()
    finally:
        set_object_storage(None)


async def test_public_ui_patch_is_typed_persisted_and_enables_selected_home(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    public_ui = _public_ui_payload()
    public_ui["home_page_key"] = "about"
    pages = public_ui["pages"]
    pages["about"]["title"] = "  О компании  "
    response = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"public_ui": public_ui},
    )

    assert response.status_code == 200, response.text
    updated = response.json()["public_ui"]
    assert updated["home_page_key"] == "about"
    assert updated["pages"]["about"]["title"] == "О компании"
    assert (await client.get("/api/v1/storefront")).json()["public_ui"] == updated
    visibility = await client.get("/api/v1/section-visibility/public")
    sections = {item["key"]: item["is_visible"] for item in visibility.json()["sections"]}
    assert sections["about"] is True

    stored = await db_session.scalar(
        select(Storefront).where(Storefront.id == root["id"])
    )
    assert stored is not None
    assert stored.public_ui_updated_by is not None
    assert stored.public_ui_updated_at is not None


async def test_current_non_home_page_cannot_be_hidden_directly(
    client: AsyncClient,
    employee_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    public_ui = _public_ui_payload()
    public_ui["home_page_key"] = "about"
    selected = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"public_ui": public_ui},
    )
    assert selected.status_code == 200, selected.text

    rejected = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}/section-visibility/public",
        headers=_auth(employee_token),
        json={"sections": [{"key": "about", "is_visible": False}]},
    )

    assert rejected.status_code == 409, rejected.text
    assert "сначала выберите другую" in rejected.json()["detail"]
    visibility = await client.get("/api/v1/section-visibility/public")
    sections = {item["key"]: item["is_visible"] for item in visibility.json()["sections"]}
    assert sections["about"] is True


async def test_new_storefront_copies_public_ui_as_independent_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    first_root_ui = _public_ui_payload()
    pages = first_root_ui["pages"]
    pages["special_equipment_catalog"]["title"] = "Спецтехника"
    root_patch = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"public_ui": first_root_ui},
    )
    assert root_patch.status_code == 200, root_patch.text

    warehouse = Warehouse(address="Казань", brand="FAW", status="active")
    db_session.add(warehouse)
    await db_session.flush()
    created = await client.post(
        "/api/v1/admin/storefronts",
        headers=_auth(employee_token),
        json={"slug": "snapshot", "warehouse_ids": [warehouse.id]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["public_ui"] == root_patch.json()["public_ui"]

    second_root_ui = _public_ui_payload()
    second_pages = second_root_ui["pages"]
    second_pages["special_equipment_catalog"]["title"] = "Новый каталог"
    changed_root = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"public_ui": second_root_ui},
    )
    assert changed_root.status_code == 200, changed_root.text

    child = await client.get("/api/v1/storefronts/snapshot")
    assert child.status_code == 200, child.text
    assert child.json()["public_ui"]["pages"]["special_equipment_catalog"]["title"] == "Спецтехника"


async def test_public_ui_patch_rejects_invalid_shape(
    client: AsyncClient,
    employee_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    missing_page = _public_ui_payload()
    pages = missing_page["pages"]
    pages.pop("about")
    invalid_shape = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"public_ui": missing_page},
    )
    assert invalid_shape.status_code == 422, invalid_shape.text

    blank_title = _public_ui_payload()
    blank_pages = blank_title["pages"]
    blank_pages["home"]["title"] = "   "
    invalid_title = await client.patch(
        f"/api/v1/admin/storefronts/{root['id']}",
        headers=_auth(employee_token),
        json={"public_ui": blank_title},
    )
    assert invalid_title.status_code == 422, invalid_title.text
