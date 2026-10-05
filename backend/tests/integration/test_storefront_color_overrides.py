import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefront_color_keys import STOREFRONT_COLOR_OVERRIDE_KEYS
from infrastructure.models.vehicles import Warehouse


async def test_color_overrides_round_trip_preserve_on_omission_and_reset_explicitly(
    client: AsyncClient, employee_token: str,
) -> None:
    headers = {"Authorization": f"Bearer {employee_token}"}
    root = (await client.get("/api/v1/storefront")).json()
    path = f"/api/v1/admin/storefronts/{root['id']}"
    appearance = {
        "colors": root["appearance"]["colors"],
        "border_radius": "none",
        "font_id": None,
    }
    saved = await client.patch(path, headers=headers, json={"appearance": {
        **appearance,
        "color_overrides": {"models.card.image_background": "#aabbcc"},
    }})
    assert saved.status_code == 200, saved.text
    assert saved.json()["appearance"]["color_overrides"] == {
        "models.card.image_background": "#AABBCC",
    }
    assert saved.json()["version"] == root["version"] + 1
    public = (await client.get("/api/v1/storefront")).json()
    assert public["appearance"]["color_overrides"] == {
        "models.card.image_background": "#AABBCC",
    }
    legacy = await client.patch(path, headers=headers, json={"appearance": appearance})
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["appearance"] == saved.json()["appearance"]
    unchanged = await client.patch(path, headers=headers, json={"contact_email": "a@b.ru"})
    assert unchanged.json()["appearance"] == saved.json()["appearance"]
    replaced = await client.patch(path, headers=headers, json={"appearance": {
        **appearance, "color_overrides": {"footer.background": "#ffffff"},
    }})
    assert replaced.json()["appearance"]["color_overrides"] == {
        "footer.background": "#FFFFFF",
    }
    reset = await client.patch(path, headers=headers, json={"appearance": {
        **appearance, "color_overrides": {},
    }})
    assert reset.status_code == 200, reset.text
    assert reset.json()["appearance"]["color_overrides"] == {}


@pytest.mark.parametrize("overrides", [
    None, [], {"unknown.background": "#FFFFFF"},
    {"footer.background": "#FFFFFF; color:red"}, {"footer.background": "#FFFFFF00"},
    {"footer.background": 123456}, {"footer.background": None},
])
async def test_invalid_override_rejects_entire_storefront_patch(
    client: AsyncClient, employee_token: str, overrides: object,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    headers = {"Authorization": f"Bearer {employee_token}"}
    path = f"/api/v1/admin/storefronts/{root['id']}"
    before = (await client.get(path, headers=headers)).json()
    rejected = await client.patch(path, headers=headers, json={
        "contact_email": "changed@example.com",
        "appearance": {
            "colors": dict.fromkeys(["primary", "background", "surface", "text"], "#ABCDEF"),
            "border_radius": "large", "font_id": None, "color_overrides": overrides,
        },
    })
    assert rejected.status_code == 422, rejected.text
    assert (await client.get(path, headers=headers)).json() == before


async def test_all_override_keys_are_public_and_copied_as_independent_snapshot(
    client: AsyncClient, db_session: AsyncSession, employee_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    headers = {"Authorization": f"Bearer {employee_token}"}
    path = f"/api/v1/admin/storefronts/{root['id']}"
    appearance = {
        "colors": root["appearance"]["colors"], "border_radius": "none", "font_id": None,
        "color_overrides": dict.fromkeys(STOREFRONT_COLOR_OVERRIDE_KEYS, "#abcdef"),
    }
    saved = await client.patch(path, headers=headers, json={"appearance": appearance})
    assert saved.status_code == 200, saved.text
    normalized = dict.fromkeys(STOREFRONT_COLOR_OVERRIDE_KEYS, "#ABCDEF")
    assert saved.json()["appearance"]["color_overrides"] == normalized
    public = (await client.get("/api/v1/storefront")).json()
    assert public["appearance"]["color_overrides"] == normalized
    warehouse = Warehouse(address="Минск", brand="AURUS", status="active")
    db_session.add(warehouse)
    await db_session.flush()
    child = await client.post("/api/v1/admin/storefronts", headers=headers, json={
        "slug": "override-snapshot", "warehouse_ids": [str(warehouse.id)],
    })
    assert child.status_code == 201, child.text
    assert child.json()["appearance"]["color_overrides"] == normalized
    reset = await client.patch(path, headers=headers, json={"appearance": {
        **appearance, "color_overrides": {},
    }})
    assert reset.status_code == 200, reset.text
    child_public = (await client.get("/api/v1/storefronts/override-snapshot")).json()
    assert child_public["appearance"]["color_overrides"] == normalized


async def test_override_patch_keeps_administrator_access_boundary(
    client: AsyncClient, client_token: str,
) -> None:
    root = (await client.get("/api/v1/storefront")).json()
    path = f"/api/v1/admin/storefronts/{root['id']}"
    assert (await client.patch(path, json={})).status_code == 401
    forbidden = await client.patch(path, json={}, headers={
        "Authorization": f"Bearer {client_token}",
    })
    assert forbidden.status_code == 403
