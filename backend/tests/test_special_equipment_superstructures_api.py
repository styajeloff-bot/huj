"""Tests for special equipment superstructures directory API."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_hierarchy(
    client: AsyncClient,
    token: str,
) -> tuple[str, str, str, str, str]:
    suffix = uuid4().hex[:6]
    # 0. Category
    cat_res = await client.post(
        "/api/v1/admin/special-equipment/categories",
        headers={**_auth(token), "Idempotency-Key": f"cat-{suffix}"},
        json={
            "code": f"CAT_{suffix.upper()}",
            "name": f"Категория {suffix}",
            "usage_metric": "engine_hours",
        },
    )
    assert cat_res.status_code == 201
    category_id = cat_res.json()["id"]

    # 1. Mark
    mark_res = await client.post(
        "/api/v1/admin/special-equipment/marks",
        headers={**_auth(token), "Idempotency-Key": f"m-{suffix}"},
        json={"code": f"MARK_{suffix.upper()}", "name": f"Марка {suffix}"},
    )
    assert mark_res.status_code == 201
    mark_id = mark_res.json()["id"]

    # 2. Model
    model_res = await client.post(
        "/api/v1/admin/special-equipment/models",
        headers={**_auth(token), "Idempotency-Key": f"mod-{suffix}"},
        json={"mark_id": mark_id, "code": f"MODEL_{suffix.upper()}", "name": f"Модель {suffix}"},
    )
    assert model_res.status_code == 201
    model_id = model_res.json()["id"]

    # 3. Modification
    modification_res = await client.post(
        "/api/v1/admin/special-equipment/modifications",
        headers={**_auth(token), "Idempotency-Key": f"modif-{suffix}"},
        json={
            "model_id": model_id,
            "code": f"MODIF_{suffix.upper()}",
            "name": f"Модификация {suffix}",
            "category_ids": [category_id],
        },
    )
    assert modification_res.status_code == 201
    modification_id = modification_res.json()["id"]

    # 4. Attribute group
    group_res = await client.post(
        "/api/v1/admin/special-equipment/attribute-groups",
        headers={**_auth(token), "Idempotency-Key": f"grp-{suffix}"},
        json={"code": f"GRP_{suffix.upper()}", "name": f"Группа {suffix}"},
    )
    assert group_res.status_code == 201
    group_id = group_res.json()["id"]

    # 5. Attribute
    attr_res = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(token), "Idempotency-Key": f"attr-{suffix}"},
        json={
            "attribute_group_id": group_id,
            "code": f"ATTR_{suffix.upper()}",
            "name": f"Атрибут {suffix}",
            "data_type": "number",
            "filter_kind": "range",
        },
    )
    assert attr_res.status_code == 201
    attr_id = attr_res.json()["id"]

    return mark_id, model_id, modification_id, group_id, attr_id


async def test_superstructure_create_and_get(
    client: AsyncClient,
    employee_token: str,
) -> None:
    _mark_id, _model_id, _modification_id, group_id, attr_id = await _create_hierarchy(
        client, employee_token
    )
    suffix = uuid4().hex[:6]
    payload = {
        "code": f"SS_{suffix.upper()}",
        "name": f"КМУ {suffix}",
        "is_active": True,
        "attributes": [
            {
                "attribute_id": attr_id,
                "group_id": group_id,
                "is_required": True,
                "is_visible": True,
                "is_filterable": False,
                "sort_order": 0,
            }
        ],
    }

    response = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"ss-{suffix}"},
        json=payload,
    )
    assert response.status_code == 201
    created = response.json()
    assert created["code"] == payload["code"]
    assert created["name"] == payload["name"]
    assert created["is_active"] is True
    assert created["attribute_count"] == 1
    assert created["product_count"] == 0
    assert len(created["attributes"]) == 1
    assert created["attributes"][0]["attribute_id"] == attr_id
    assert created["attributes"][0]["group_id"] == group_id
    assert created["attributes"][0]["is_required"] is True
    assert created["attributes"][0]["is_visible"] is True

    ss_id = created["id"]
    get_res = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/{ss_id}",
        headers=_auth(employee_token),
    )
    assert get_res.status_code == 200
    details = get_res.json()
    assert details["id"] == ss_id
    assert details["name"] == payload["name"]
    assert "ETag" in get_res.headers


async def test_superstructure_duplicate_code_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    base_payload = {
        "code": f"SS_{suffix.upper()}",
        "name": f"КМУ {suffix}",
        "is_active": True,
    }
    res1 = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup1-{suffix}"},
        json=base_payload,
    )
    assert res1.status_code == 201

    dup_code_payload = {**base_payload, "name": f"Other {suffix}"}
    res2 = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup2-{suffix}"},
        json=dup_code_payload,
    )
    assert res2.status_code == 409
    assert res2.json()["code"] == "SUPERSTRUCTURE_CODE_CONFLICT"


async def test_superstructure_duplicate_name_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    suffix = uuid4().hex[:6]
    base_payload = {
        "code": f"SS_{suffix.upper()}",
        "name": f"КМУ {suffix}",
        "is_active": True,
    }
    res1 = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup1-{suffix}"},
        json=base_payload,
    )
    assert res1.status_code == 201

    dup_name_payload = {**base_payload, "code": f"OTHER_{suffix.upper()}"}
    res2 = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"dup3-{suffix}"},
        json=dup_name_payload,
    )
    assert res2.status_code == 409
    assert res2.json()["code"] == "SUPERSTRUCTURE_NAME_CONFLICT"


async def test_superstructure_attribute_group_mismatch_rejected(
    client: AsyncClient,
    employee_token: str,
) -> None:
    _, _model_id, _, _group1_id, attr1_id = await _create_hierarchy(
        client, employee_token
    )
    suffix = uuid4().hex[:6]
    # Create group2
    g2_res = await client.post(
        "/api/v1/admin/special-equipment/attribute-groups",
        headers={**_auth(employee_token), "Idempotency-Key": f"g2-{suffix}"},
        json={"code": f"G2_{suffix.upper()}", "name": f"Группа 2 {suffix}"},
    )
    assert g2_res.status_code == 201
    group2_id = g2_res.json()["id"]

    # Link attr1 with group2 instead of group1
    res = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"gm-{suffix}"},
        json={
            "code": f"GM_{suffix.upper()}",
            "name": f"Группа {suffix}",
            "attributes": [
                {
                    "attribute_id": attr1_id,
                    "group_id": group2_id,
                    "is_required": False,
                    "is_visible": False,
                    "is_filterable": False,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert res.status_code == 422
    assert res.json()["code"] == "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH"


async def test_superstructure_card_limit_exceeded(
    client: AsyncClient,
    employee_token: str,
) -> None:
    _, _, _, group_id, _ = await _create_hierarchy(
        client, employee_token
    )
    # Create 7 attributes in group
    attr_ids = []
    for i in range(7):
        suffix = uuid4().hex[:6]
        a_res = await client.post(
            "/api/v1/admin/special-equipment/attributes",
            headers={**_auth(employee_token), "Idempotency-Key": f"a{i}-{suffix}"},
            json={
                "attribute_group_id": group_id,
                "code": f"A{i}_{suffix.upper()}",
                "name": f"Атрибут {i} {suffix}",
                "data_type": "number",
                "filter_kind": "range",
            },
        )
        assert a_res.status_code == 201
        attr_ids.append(a_res.json()["id"])

    suffix = uuid4().hex[:6]
    res = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"lim-{suffix}"},
        json={
            "code": f"LIM_{suffix.upper()}",
            "name": f"Лимит {suffix}",
            "attributes": [
                {
                    "attribute_id": aid,
                    "group_id": group_id,
                    "is_required": False,
                    "is_visible": True,  # in card!
                    "is_filterable": False,
                    "sort_order": idx,
                }
                for idx, aid in enumerate(attr_ids)
            ],
        },
    )
    assert res.status_code == 422
    assert res.json()["code"] == "SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED"


async def test_superstructure_attribute_candidates(
    client: AsyncClient,
    employee_token: str,
) -> None:
    _, _, _, group_id, attr_id = await _create_hierarchy(
        client, employee_token
    )
    res = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/attribute-candidates?group_id={group_id}",
        headers=_auth(employee_token),
    )
    assert res.status_code == 200
    candidates = res.json()["items"]
    target = next((c for c in candidates if c["attribute_id"] == attr_id), None)
    assert target is not None
    assert target["group_id"] == group_id
    assert target["group_name"].startswith("Группа ")
    assert target["attribute_name"].startswith("Атрибут ")
    assert target["attribute_code"].startswith("ATTR_")
    assert target["is_active"] is True


async def test_superstructure_patch_and_cascade_delete(
    client: AsyncClient,
    employee_token: str,
) -> None:
    _mark_id, _model_id, _modification_id, group_id, attr_id = await _create_hierarchy(
        client, employee_token
    )
    suffix = uuid4().hex[:6]
    create_res = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(employee_token), "Idempotency-Key": f"patch-{suffix}"},
        json={
            "code": f"P_{suffix.upper()}",
            "name": f"Патч {suffix}",
            "is_active": True,
        },
    )
    assert create_res.status_code == 201
    ss_id = create_res.json()["id"]

    # GET ETag
    get_res = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/{ss_id}",
        headers=_auth(employee_token),
    )
    etag = get_res.headers["ETag"]

    # PATCH
    patch_res = await client.patch(
        f"/api/v1/admin/special-equipment/superstructures/{ss_id}",
        headers={**_auth(employee_token), "If-Match": etag},
        json={
            "name": f"Обновленная надстройка {suffix}",
            "attributes": [
                {
                    "attribute_id": attr_id,
                    "group_id": group_id,
                    "is_required": False,
                    "is_visible": True,
                    "is_filterable": True,
                    "sort_order": 1,
                }
            ],
        },
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["name"] == f"Обновленная надстройка {suffix}"
    assert len(patched["attributes"]) == 1

    # Cascade preview
    prev_res = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/{ss_id}/delete-preview",
        headers=_auth(employee_token),
    )
    assert prev_res.status_code == 200
    prev_data = prev_res.json()
    preview_token = prev_data["preview_token"]

    # Cascade delete
    del_res = await client.post(
        f"/api/v1/admin/special-equipment/superstructures/{ss_id}/cascade-delete",
        headers={**_auth(employee_token), "If-Match": patch_res.headers["ETag"]},
        json={
            "confirmation": "УДАЛИТЬ",
            "preview_token": preview_token,
        },
    )
    assert del_res.status_code == 200
    assert del_res.json()["deleted"]["superstructures"] == 1

    # Verify not found after delete
    get_after = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/{ss_id}",
        headers=_auth(employee_token),
    )
    assert get_after.status_code == 404
