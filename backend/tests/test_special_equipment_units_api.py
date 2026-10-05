"""Tests for special equipment units directory API."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_unit_create_and_get(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    payload = {
        "code": f"UNIT_{suffix.upper()}",
        "name": f"ед_{suffix}",
    }
    response = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"unit-create-{suffix}"},
        json=payload,
    )
    assert response.status_code == 201
    created = response.json()
    assert created["code"] == payload["code"]
    assert created["name"] == payload["name"]
    assert created["is_active"] is True
    assert created["attribute_count"] == 0
    assert "slug" in created
    assert "lock_version" in created

    unit_id = created["id"]
    get_res = await client.get(
        f"/api/v1/admin/special-equipment/units/{unit_id}",
        headers=_auth(employee_token),
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == unit_id
    assert "ETag" in get_res.headers


async def test_unit_create_rejects_duplicate_code_or_name(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    payload = {
        "code": f"DUP_{suffix.upper()}",
        "name": f"дубль_{suffix}",
    }
    first = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup-1-{suffix}"},
        json=payload,
    )
    assert first.status_code == 201

    # Duplicate code (different case)
    dup_code = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup-2-{suffix}"},
        json={"code": payload["code"].lower(), "name": f"другое_{suffix}"},
    )
    assert dup_code.status_code == 409

    # Duplicate name (different case and spaces)
    dup_name = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup-3-{suffix}"},
        json={"code": f"DIFF_{suffix.upper()}", "name": f"  {payload['name'].upper()}  "},
    )
    assert dup_name.status_code == 409


async def test_unit_list_and_filter(
    client: AsyncClient,
    employee_token: str,
) -> None:
    prefix = uuid4().hex[:6]
    res1 = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"list-1-{prefix}"},
        json={"code": f"L1_{prefix.upper()}", "name": f"Лист1_{prefix}"},
    )
    assert res1.status_code == 201
    unit1 = res1.json()

    res2 = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"list-2-{prefix}"},
        json={"code": f"L2_{prefix.upper()}", "name": f"Лист2_{prefix}"},
    )
    assert res2.status_code == 201
    unit2 = res2.json()

    # Deactivate unit2
    patch2 = await client.patch(
        f"/api/v1/admin/special-equipment/units/{unit2['id']}",
        headers={**_auth(employee_token), "If-Match": res2.headers["ETag"]},
        json={"is_active": False},
    )
    assert patch2.status_code == 200

    # Search by prefix
    list_all = await client.get(
        f"/api/v1/admin/special-equipment/units?q={prefix}",
        headers=_auth(employee_token),
    )
    assert list_all.status_code == 200
    ids_all = {item["id"] for item in list_all.json()["items"]}
    assert unit1["id"] in ids_all
    assert unit2["id"] in ids_all

    # Filter is_active=true
    list_active = await client.get(
        f"/api/v1/admin/special-equipment/units?q={prefix}&is_active=true",
        headers=_auth(employee_token),
    )
    assert list_active.status_code == 200
    ids_active = {item["id"] for item in list_active.json()["items"]}
    assert unit1["id"] in ids_active
    assert unit2["id"] not in ids_active

    # Filter is_active=false
    list_inactive = await client.get(
        f"/api/v1/admin/special-equipment/units?q={prefix}&is_active=false",
        headers=_auth(employee_token),
    )
    assert list_inactive.status_code == 200
    ids_inactive = {item["id"] for item in list_inactive.json()["items"]}
    assert unit1["id"] not in ids_inactive
    assert unit2["id"] in ids_inactive


async def test_unit_patch_preconditions(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"pre-{suffix}"},
        json={"code": f"PR_{suffix.upper()}", "name": f"Пре_{suffix}"},
    )
    assert res.status_code == 201
    unit = res.json()

    # Missing If-Match -> 428
    no_etag = await client.patch(
        f"/api/v1/admin/special-equipment/units/{unit['id']}",
        headers=_auth(employee_token),
        json={"name": f"Новое_{suffix}"},
    )
    assert no_etag.status_code == 428

    # Wrong If-Match -> 412
    wrong_etag = await client.patch(
        f"/api/v1/admin/special-equipment/units/{unit['id']}",
        headers={**_auth(employee_token), "If-Match": f'"{unit["id"]}:999:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"'},
        json={"name": f"Новое_{suffix}"},
    )
    assert wrong_etag.status_code == 412


async def test_unit_patch_success(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"pts-{suffix}"},
        json={"code": f"PTS_{suffix.upper()}", "name": f"ПатчУсп_{suffix}"},
    )
    assert res.status_code == 201
    unit = res.json()
    etag = res.headers["ETag"]

    # Valid If-Match -> 200
    patched = await client.patch(
        f"/api/v1/admin/special-equipment/units/{unit['id']}",
        headers={**_auth(employee_token), "If-Match": etag},
        json={"name": f"Изм_{suffix}"},
    )
    assert patched.status_code == 200
    updated = patched.json()
    assert updated["name"] == f"Изм_{suffix}"
    assert updated["lock_version"] == unit["lock_version"] + 1
    assert patched.headers["ETag"] != etag


async def test_unit_delete_unused(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"del-u-{suffix}"},
        json={"code": f"DELU_{suffix.upper()}", "name": f"УдалН_{suffix}"},
    )
    assert res.status_code == 201
    unit = res.json()
    etag = res.headers["ETag"]

    # Delete unused unit -> 204
    deleted = await client.delete(
        f"/api/v1/admin/special-equipment/units/{unit['id']}",
        headers={**_auth(employee_token), "If-Match": etag},
    )
    assert deleted.status_code == 204

    # Now 404
    get_res = await client.get(
        f"/api/v1/admin/special-equipment/units/{unit['id']}",
        headers=_auth(employee_token),
    )
    assert get_res.status_code == 404


async def test_unit_delete_in_use_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res_used = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"del-used-{suffix}"},
        json={"code": f"USED_{suffix.upper()}", "name": f"Занят_{suffix}"},
    )
    assert res_used.status_code == 201
    unit_used = res_used.json()

    # Create attribute with this unit
    attr_res = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"attr-{suffix}"},
        json={
            "code": f"ATTR_{suffix.upper()}",
            "name": f"Хар_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": unit_used["id"],
        },
    )
    assert attr_res.status_code == 201

    # Get fresh unit representation and ETag
    fresh_unit = await client.get(
        f"/api/v1/admin/special-equipment/units/{unit_used['id']}",
        headers=_auth(employee_token),
    )
    assert fresh_unit.status_code == 200
    assert fresh_unit.json()["attribute_count"] == 1

    # Delete should fail with 409 UNIT_IN_USE
    del_used = await client.delete(
        f"/api/v1/admin/special-equipment/units/{unit_used['id']}",
        headers={**_auth(employee_token), "If-Match": fresh_unit.headers["ETag"]},
    )
    assert del_used.status_code == 409
    body = del_used.json()
    assert body["code"] == "UNIT_IN_USE"
    assert body["attribute_count"] == 1


async def test_unit_merge_self_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res_a = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"mself-{suffix}"},
        json={"code": f"MS_{suffix.upper()}", "name": f"Сам_{suffix}"},
    )
    assert res_a.status_code == 201
    unit_a = res_a.json()

    merge_self = await client.post(
        f"/api/v1/admin/special-equipment/units/{unit_a['id']}/merge",
        headers={**_auth(employee_token), "If-Match": res_a.headers["ETag"]},
        json={"target_unit_id": unit_a["id"]},
    )
    assert merge_self.status_code == 422


async def test_unit_merge_success(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res_a = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"merge-a-{suffix}"},
        json={"code": f"MA_{suffix.upper()}", "name": f"СлитА_{suffix}"},
    )
    assert res_a.status_code == 201
    unit_a = res_a.json()

    res_b = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"merge-b-{suffix}"},
        json={"code": f"MB_{suffix.upper()}", "name": f"СлитБ_{suffix}"},
    )
    assert res_b.status_code == 201
    unit_b = res_b.json()

    # Attach two attributes to unit_a
    attr1 = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"attr1-{suffix}"},
        json={
            "code": f"A1_{suffix.upper()}",
            "name": f"Хар1_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": unit_a["id"],
        },
    )
    assert attr1.status_code == 201
    attr2 = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"attr2-{suffix}"},
        json={
            "code": f"A2_{suffix.upper()}",
            "name": f"Хар2_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": unit_a["id"],
        },
    )
    assert attr2.status_code == 201

    # Get fresh unit_a representation and ETag after attributes linked
    fresh_a = await client.get(
        f"/api/v1/admin/special-equipment/units/{unit_a['id']}",
        headers=_auth(employee_token),
    )
    assert fresh_a.status_code == 200

    # Successful merge A -> B
    merge_ok = await client.post(
        f"/api/v1/admin/special-equipment/units/{unit_a['id']}/merge",
        headers={**_auth(employee_token), "If-Match": fresh_a.headers["ETag"]},
        json={"target_unit_id": unit_b["id"]},
    )
    assert merge_ok.status_code == 200
    target_unit = merge_ok.json()
    assert target_unit["id"] == unit_b["id"]

    # Verify unit_a no longer exists
    get_a = await client.get(
        f"/api/v1/admin/special-equipment/units/{unit_a['id']}",
        headers=_auth(employee_token),
    )
    assert get_a.status_code == 404

    # Verify attributes now point to unit_b
    get_attr1 = await client.get(
        f"/api/v1/admin/special-equipment/attributes/{attr1.json()['id']}",
        headers=_auth(employee_token),
    )
    assert get_attr1.status_code == 200
    assert get_attr1.json()["unit_id"] == unit_b["id"]
    assert get_attr1.json()["unit"] == unit_b["name"]


async def test_attribute_unit_id_inactive_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res_inact = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"u-inact-{suffix}"},
        json={"code": f"UINACT_{suffix.upper()}", "name": f"Неакт_{suffix}"},
    )
    assert res_inact.status_code == 201
    unit_inact = res_inact.json()
    await client.patch(
        f"/api/v1/admin/special-equipment/units/{unit_inact['id']}",
        headers={**_auth(employee_token), "If-Match": res_inact.headers["ETag"]},
        json={"is_active": False},
    )

    attr_inact = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"att-inact-{suffix}"},
        json={
            "code": f"AI_{suffix.upper()}",
            "name": f"НеактХ_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": unit_inact["id"],
        },
    )
    assert attr_inact.status_code == 422
    assert attr_inact.json()["code"] == "UNIT_INACTIVE"


async def test_attribute_unit_id_missing_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    attr_missing = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"att-miss-{suffix}"},
        json={
            "code": f"AM_{suffix.upper()}",
            "name": f"НетХ_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": str(uuid4()),
        },
    )
    assert attr_missing.status_code == 422
    assert attr_missing.json()["code"] == "UNIT_NOT_FOUND"


async def test_attribute_unit_id_active_and_clear(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    res_act = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"u-act-{suffix}"},
        json={"code": f"UACT_{suffix.upper()}", "name": f"Акт_{suffix}"},
    )
    assert res_act.status_code == 201
    unit_act = res_act.json()

    # Create attribute with active unit -> 201
    attr_ok = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"att-ok-{suffix}"},
        json={
            "code": f"AOK_{suffix.upper()}",
            "name": f"ОкХ_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": unit_act["id"],
        },
    )
    assert attr_ok.status_code == 201, attr_ok.text
    created_attr = attr_ok.json()
    assert created_attr["unit_id"] == unit_act["id"]
    assert created_attr["unit"] == unit_act["name"]

    # Clear unit (unit_id: None) -> 200
    patch_clear = await client.patch(
        f"/api/v1/admin/special-equipment/attributes/{created_attr['id']}",
        headers={**_auth(employee_token), "If-Match": attr_ok.headers["ETag"]},
        json={"unit_id": None},
    )
    assert patch_clear.status_code == 200
    cleared = patch_clear.json()
    assert cleared["unit_id"] is None
    assert cleared["unit"] is None


async def test_attribute_patch_to_inactive_unit_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    # Create active unit and inactive unit
    res_act = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"u-act-{suffix}"},
        json={"code": f"UACT_{suffix.upper()}", "name": f"Акт_{suffix}"},
    )
    assert res_act.status_code == 201
    unit_act = res_act.json()

    res_inact = await client.post(
        "/api/v1/admin/special-equipment/units",
        headers={**_auth(employee_token), "Idempotency-Key": f"u-inact-{suffix}"},
        json={"code": f"UINACT_{suffix.upper()}", "name": f"Неакт_{suffix}"},
    )
    assert res_inact.status_code == 201
    unit_inact = res_inact.json()
    await client.patch(
        f"/api/v1/admin/special-equipment/units/{unit_inact['id']}",
        headers={**_auth(employee_token), "If-Match": res_inact.headers["ETag"]},
        json={"is_active": False},
    )

    # Create attribute with active unit
    attr_ok = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"att-ok-{suffix}"},
        json={
            "code": f"AOK_{suffix.upper()}",
            "name": f"ОкХ_{suffix}",
            "data_type": "number",
            "filter_kind": "range",
            "unit_id": unit_act["id"],
        },
    )
    assert attr_ok.status_code == 201
    created_attr = attr_ok.json()

    # Patch attribute to inactive unit -> 422 UNIT_INACTIVE
    patch_inact = await client.patch(
        f"/api/v1/admin/special-equipment/attributes/{created_attr['id']}",
        headers={**_auth(employee_token), "If-Match": attr_ok.headers["ETag"]},
        json={"unit_id": unit_inact["id"]},
    )
    assert patch_inact.status_code == 422
    assert patch_inact.json()["code"] == "UNIT_INACTIVE"
