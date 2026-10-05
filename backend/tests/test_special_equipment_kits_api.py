"""Tests for special equipment kit products API."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_base_setup(
    client: AsyncClient,
    token: str,
) -> dict[str, str]:
    suffix = uuid4().hex[:6]
    # 1. Chassis category (root)
    cat_res = await client.post(
        "/api/v1/admin/special-equipment/categories",
        headers={**_auth(token), "Idempotency-Key": f"c-cat-{suffix}"},
        json={
            "code": f"CH_CAT_{suffix.upper()}",
            "name": f"Категория шасси {suffix}",
            "usage_metric": "engine_hours",
        },
    )
    assert cat_res.status_code == 201
    category_id = cat_res.json()["id"]

    # 2. Mark & Model
    mark_res = await client.post(
        "/api/v1/admin/special-equipment/marks",
        headers={**_auth(token), "Idempotency-Key": f"c-m-{suffix}"},
        json={"code": f"CH_MARK_{suffix.upper()}", "name": f"Марка шасси {suffix}"},
    )
    assert mark_res.status_code == 201
    mark_id = mark_res.json()["id"]

    model_res = await client.post(
        "/api/v1/admin/special-equipment/models",
        headers={**_auth(token), "Idempotency-Key": f"c-mod-{suffix}"},
        json={"mark_id": mark_id, "category_id": category_id, "code": f"CH_MODEL_{suffix.upper()}", "name": f"Модель шасси {suffix}"},
    )
    assert model_res.status_code == 201
    model_id = model_res.json()["id"]

    # 3. Modification
    modif_res = await client.post(
        "/api/v1/admin/special-equipment/modifications",
        headers={**_auth(token), "Idempotency-Key": f"c-modif-{suffix}"},
        json={
            "model_id": model_id,
            "code": f"CH_MODIF_{suffix.upper()}",
            "name": f"Модификация шасси {suffix}",
            "category_ids": [category_id],
        },
    )
    assert modif_res.status_code == 201
    modification_id = modif_res.json()["id"]

    # 4. Superstructure Attribute Group & Attribute
    grp_res = await client.post(
        "/api/v1/admin/special-equipment/attribute-groups",
        headers={**_auth(token), "Idempotency-Key": f"ss-grp-{suffix}"},
        json={"code": f"SS_GRP_{suffix.upper()}", "name": f"Группа надстроек {suffix}"},
    )
    assert grp_res.status_code == 201
    group_id = grp_res.json()["id"]

    attr_res = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(token), "Idempotency-Key": f"ss-attr-{suffix}"},
        json={
            "attribute_group_id": group_id,
            "code": f"SS_ATTR_{suffix.upper()}",
            "name": f"Грузоподъемность {suffix}",
            "data_type": "number",
            "filter_kind": "range",
        },
    )
    assert attr_res.status_code == 201
    attr_id = attr_res.json()["id"]

    # 5. Superstructure Mark, Model & Type
    ss_mark_res = await client.post(
        "/api/v1/admin/special-equipment/marks",
        headers={**_auth(token), "Idempotency-Key": f"ss-m-{suffix}"},
        json={"code": f"SS_MARK_{suffix.upper()}", "name": f"Марка надстройки {suffix}"},
    )
    assert ss_mark_res.status_code == 201
    ss_mark_id = ss_mark_res.json()["id"]

    ss_model_res = await client.post(
        "/api/v1/admin/special-equipment/models",
        headers={**_auth(token), "Idempotency-Key": f"ss-model-{suffix}"},
        json={"mark_id": ss_mark_id, "category_id": category_id, "code": f"SS_MODEL_{suffix.upper()}", "name": f"Модель надстройки {suffix}"},
    )
    assert ss_model_res.status_code == 201
    ss_model_id = ss_model_res.json()["id"]

    ss_modif_res = await client.post(
        "/api/v1/admin/special-equipment/modifications",
        headers={**_auth(token), "Idempotency-Key": f"ss-modif-{suffix}"},
        json={
            "model_id": ss_model_id,
            "code": f"SS_MODIF_{suffix.upper()}",
            "name": f"Модификация надстройки {suffix}",
            "category_ids": [category_id],
        },
    )
    assert ss_modif_res.status_code == 201
    ss_modification_id = ss_modif_res.json()["id"]

    ss_res = await client.post(
        "/api/v1/admin/special-equipment/superstructures",
        headers={**_auth(token), "Idempotency-Key": f"ss-type-{suffix}"},
        json={
            "code": f"SS_TYPE_{suffix.upper()}",
            "name": f"КМУ {suffix}",
            "category_ids": [category_id],
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
        },
    )
    assert ss_res.status_code == 201
    superstructure_id = ss_res.json()["id"]

    return {
        "category_id": category_id,
        "mark_id": mark_id,
        "model_id": model_id,
        "modification_id": modification_id,
        "superstructure_id": superstructure_id,
        "ss_model_id": ss_model_id,
        "ss_modification_id": ss_modification_id,
        "attr_id": attr_id,
        "group_id": group_id,
        "suffix": suffix,
    }


async def test_kit_product_create_and_get(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    payload = {
        "code": f"KIT-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["modification_id"],
        "category_ids": [setup["category_id"]],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-{suffix}"},
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["is_kit"] is True
    assert data["superstructure_id"] == setup["superstructure_id"]
    assert data["superstructure_name"] == f"КМУ-100 {suffix}"
    assert data["superstructure_manufacturer"] == f"Завод {suffix}"

    kit_id = data["id"]
    get_res = await client.get(
        f"/api/v1/admin/special-equipment/products/{kit_id}",
        headers=_auth(employee_token),
    )
    assert get_res.status_code == 200
    kit_details = get_res.json()
    assert kit_details["id"] == kit_id
    assert kit_details["is_kit"] is True
    assert kit_details["superstructure_name"] == f"КМУ-100 {suffix}"
    assert kit_details["title"] == f"КМУ-100 {suffix} на базе Марка шасси {setup['suffix']} Модель шасси {setup['suffix']}"
    assert len(kit_details["superstructure_values"]) == 1


async def test_kit_product_compatible_attachments_forbidden(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    payload = {
        "code": f"KIT2-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["modification_id"],
        "category_ids": [setup["category_id"]],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit2-{suffix}"},
        json=payload,
    )
    assert res.status_code == 201
    kit_id = res.json()["id"]

    compat_res = await client.get(
        f"/api/v1/admin/special-equipment/products/{kit_id}/compatible-attachments",
        headers=_auth(employee_token),
    )
    assert compat_res.status_code == 422
    assert compat_res.json()["code"] == "KIT_COMPATIBILITY_FORBIDDEN"


async def test_kit_without_modification_with_chassis_values(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    # Create chassis attribute & group
    grp_res = await client.post(
        "/api/v1/admin/special-equipment/attribute-groups",
        headers={**_auth(employee_token), "Idempotency-Key": f"c-grp-{suffix}"},
        json={"code": f"CH_GRP_{suffix.upper()}", "name": f"Группа шасси {suffix}"},
    )
    assert grp_res.status_code == 201
    ch_grp_id = grp_res.json()["id"]

    attr_res = await client.post(
        "/api/v1/admin/special-equipment/attributes",
        headers={**_auth(employee_token), "Idempotency-Key": f"c-attr-{suffix}"},
        json={
            "attribute_group_id": ch_grp_id,
            "code": f"CH_ATTR_{suffix.upper()}",
            "name": f"Мощность двигателя {suffix}",
            "data_type": "number",
            "filter_kind": "range",
        },
    )
    assert attr_res.status_code == 201
    ch_attr_id = attr_res.json()["id"]

    # Link attribute to category
    cat_etag = (
        await client.get(
            f"/api/v1/admin/special-equipment/categories/{setup['category_id']}",
            headers=_auth(employee_token),
        )
    ).headers["ETag"]
    attr_link_res = await client.put(
        f"/api/v1/admin/special-equipment/categories/{setup['category_id']}/attributes",
        headers={**_auth(employee_token), "If-Match": cat_etag},
        json={
            "items": [
                {
                    "attribute_id": ch_attr_id,
                    "group_id": ch_grp_id,
                    "is_required": False,
                    "is_visible": True,
                    "is_filterable": False,
                    "sort_order": 0,
                }
            ]
        },
    )
    assert attr_link_res.status_code == 200

    # Create kit without modification
    payload = {
        "code": f"KIT-NOMOD-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": None,
        "category_ids": [setup["category_id"]],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "chassis_values": [
            {
                "attribute_id": ch_attr_id,
                "value_number": "300.0",
            }
        ],
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-nomod-{suffix}"},
        json=payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["is_kit"] is True
    assert data["modification_id"] is None
    assert data["superstructure_name"] == f"КМУ-100 {suffix}"

    kit_id = data["id"]
    get_res = await client.get(
        f"/api/v1/admin/special-equipment/products/{kit_id}",
        headers=_auth(employee_token),
    )
    assert get_res.status_code == 200
    kit_details = get_res.json()
    assert kit_details["id"] == kit_id
    assert kit_details["is_kit"] is True
    assert len(kit_details["chassis_values"]) == 1
    assert kit_details["chassis_values"][0]["attribute_id"] == ch_attr_id
    assert len(kit_details["superstructure_values"]) == 1


async def test_kit_with_modification_rejects_chassis_values(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    payload = {
        "code": f"KIT-REJ-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["modification_id"],
        "category_ids": [setup["category_id"]],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "chassis_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "300.0",
            }
        ],
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-rej-{suffix}"},
        json=payload,
    )
    assert res.status_code == 422
    assert res.json()["code"] == "KIT_CHASSIS_VALUES_WITH_MODIFICATION"


async def test_kit_rejects_attachment_category(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    # Create category in attachment branch
    att_cat_res = await client.post(
        "/api/v1/admin/special-equipment/categories",
        headers={**_auth(employee_token), "Idempotency-Key": f"att-cat-{suffix}"},
        json={
            "code": f"ATT_CAT_{suffix.upper()}",
            "name": f"Категория надстроек {suffix}",
            "usage_metric": "engine_hours",
            "is_attachment_category": True,
        },
    )
    assert att_cat_res.status_code == 201
    att_category_id = att_cat_res.json()["id"]

    payload = {
        "code": f"KIT-ATTCAT-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["modification_id"],
        "category_ids": [att_category_id],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-attcat-{suffix}"},
        json=payload,
    )
    assert res.status_code == 422
    assert res.json()["code"] == "KIT_ATTACHMENT_CATEGORY"


async def test_kit_rejects_chassis_modification_model_mismatch(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    # Pass ss_modification_id as chassis modification_id (different model)
    payload = {
        "code": f"KIT-MODMIS-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["ss_modification_id"],
        "category_ids": [setup["category_id"]],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-modmis-{suffix}"},
        json=payload,
    )
    assert res.status_code == 422
    assert res.json()["code"] == "KIT_CHASSIS_MODIFICATION_MODEL_MISMATCH"


async def test_kit_kind_immutable_on_patch(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    payload = {
        "code": f"KIT-IMM-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["modification_id"],
        "category_ids": [setup["category_id"]],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-imm-{suffix}"},
        json=payload,
    )
    assert res.status_code == 201
    kit_id = res.json()["id"]

    get_res = await client.get(
        f"/api/v1/admin/special-equipment/products/{kit_id}",
        headers=_auth(employee_token),
    )
    etag = get_res.headers["ETag"]

    patch_res = await client.patch(
        f"/api/v1/admin/special-equipment/products/{kit_id}",
        headers={**_auth(employee_token), "If-Match": etag},
        json={"superstructure_id": None},
    )
    assert patch_res.status_code == 422
    assert patch_res.json()["code"] == "PRODUCT_KIND_IMMUTABLE"


async def test_attachment_sources_endpoint(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    # Create attachment category
    att_cat_res = await client.post(
        "/api/v1/admin/special-equipment/categories",
        headers={**_auth(employee_token), "Idempotency-Key": f"src-cat-{suffix}"},
        json={
            "code": f"SRC_CAT_{suffix.upper()}",
            "name": f"Навесное оборудование {suffix}",
            "usage_metric": "engine_hours",
            "is_attachment_category": True,
        },
    )
    assert att_cat_res.status_code == 201
    att_cat_id = att_cat_res.json()["id"]

    # Create modification for attachment category
    ss_mod_res = await client.post(
        "/api/v1/admin/special-equipment/modifications",
        headers={**_auth(employee_token), "Idempotency-Key": f"src-mod-{suffix}"},
        json={
            "model_id": setup["ss_model_id"],
            "code": f"SRC_MOD_{suffix.upper()}",
            "name": f"Модификация надстройки источник {suffix}",
            "category_ids": [att_cat_id],
        },
    )
    assert ss_mod_res.status_code == 201
    src_mod_id = ss_mod_res.json()["id"]

    # Create attachment product
    att_prod_res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"src-prod-{suffix}"},
        json={
            "code": f"ATT-PROD-{suffix.upper()}",
            "modification_id": src_mod_id,
            "category_ids": [att_cat_id],
            "price": "500000.00",
            "currency_code": "RUB",
            "manufacture_year": 2024,
            "no_vin": True,
            "condition": "new",
            "sale_status": "available",
            "publication_status": "draft",
        },
    )
    assert att_prod_res.status_code == 201

    # Call attachment sources
    sources_res = await client.get(
        f"/api/v1/admin/special-equipment/products/attachment-sources?model_id={setup['ss_model_id']}&search={suffix}",
        headers=_auth(employee_token),
    )
    assert sources_res.status_code == 200
    sources = sources_res.json()["items"]
    assert len(sources) >= 1
    found = next((item for item in sources if item["code"] == f"ATT-PROD-{suffix.upper()}"), None)
    assert found is not None
    assert found["superstructure_name"] != ""
    assert found["superstructure_manufacturer"] != ""


async def test_kit_rejects_category_not_in_superstructure(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    # Create category not attached to the superstructure type
    other_cat_res = await client.post(
        "/api/v1/admin/special-equipment/categories",
        headers={**_auth(employee_token), "Idempotency-Key": f"oth-cat-{suffix}"},
        json={
            "code": f"OTH_CAT_{suffix.upper()}",
            "name": f"Другая категория {suffix}",
            "usage_metric": "engine_hours",
        },
    )
    assert other_cat_res.status_code == 201
    other_cat_id = other_cat_res.json()["id"]

    payload = {
        "code": f"KIT-NOTALL-{suffix.upper()}",
        "model_id": setup["model_id"],
        "modification_id": setup["modification_id"],
        "category_ids": [other_cat_id],
        "superstructure_id": setup["superstructure_id"],
        "superstructure_modification_id": setup["ss_modification_id"],
        "superstructure_name": f"КМУ-100 {suffix}",
        "superstructure_manufacturer": f"Завод {suffix}",
        "price": "10000000.00",
        "currency_code": "RUB",
        "manufacture_year": 2024,
        "no_vin": True,
        "condition": "new",
        "sale_status": "available",
        "publication_status": "draft",
        "superstructure_values": [
            {
                "attribute_id": setup["attr_id"],
                "value_number": "5000.0",
            }
        ],
    }

    res = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": f"kit-notall-{suffix}"},
        json=payload,
    )
    assert res.status_code == 422
    assert res.json()["code"] == "KIT_CATEGORY_NOT_ALLOWED"


async def test_superstructure_patch_allows_existing_inactive_category(
    client: AsyncClient,
    employee_token: str,
) -> None:
    setup = await _create_base_setup(client, employee_token)
    suffix = uuid4().hex[:6]

    # Deactivate the category already attached to superstructure
    cat_get_res = await client.get(
        f"/api/v1/admin/special-equipment/categories/{setup['category_id']}",
        headers=_auth(employee_token),
    )
    cat_etag = cat_get_res.headers["ETag"]
    cat_patch_res = await client.patch(
        f"/api/v1/admin/special-equipment/categories/{setup['category_id']}",
        headers={**_auth(employee_token), "If-Match": cat_etag},
        json={"is_active": False},
    )
    assert cat_patch_res.status_code == 200

    # Patch superstructure keeping the now-inactive category — should succeed
    ss_get_res = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/{setup['superstructure_id']}",
        headers=_auth(employee_token),
    )
    ss_etag = ss_get_res.headers["ETag"]
    ss_patch_res = await client.patch(
        f"/api/v1/admin/special-equipment/superstructures/{setup['superstructure_id']}",
        headers={**_auth(employee_token), "If-Match": ss_etag},
        json={"name": f"Обновленная КМУ {suffix}", "category_ids": [setup["category_id"]]},
    )
    assert ss_patch_res.status_code == 200
    assert ss_patch_res.json()["name"] == f"Обновленная КМУ {suffix}"

    # Creating a new inactive category and trying to add it to superstructure should fail
    new_inact_cat_res = await client.post(
        "/api/v1/admin/special-equipment/categories",
        headers={**_auth(employee_token), "Idempotency-Key": f"inact-cat-{suffix}"},
        json={
            "code": f"INACT_CAT_{suffix.upper()}",
            "name": f"Неактивная категория {suffix}",
            "usage_metric": "engine_hours",
            "is_active": False,
        },
    )
    assert new_inact_cat_res.status_code == 201
    new_inact_cat_id = new_inact_cat_res.json()["id"]

    ss_get_res2 = await client.get(
        f"/api/v1/admin/special-equipment/superstructures/{setup['superstructure_id']}",
        headers=_auth(employee_token),
    )
    ss_etag2 = ss_get_res2.headers["ETag"]
    fail_patch_res = await client.patch(
        f"/api/v1/admin/special-equipment/superstructures/{setup['superstructure_id']}",
        headers={**_auth(employee_token), "If-Match": ss_etag2},
        json={"category_ids": [setup["category_id"], new_inact_cat_id]},
    )
    assert fail_patch_res.status_code == 422


