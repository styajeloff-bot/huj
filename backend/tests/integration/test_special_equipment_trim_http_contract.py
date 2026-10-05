"""End-to-end HTTP contract for trim attribute candidates and replacement."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import special_equipment_management as commands
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
    SpecialEquipmentTrim,
    SpecialEquipmentTrimAttribute,
    SpecialEquipmentTrimAttributeValue,
)
from infrastructure.repositories import (
    special_equipment_management_repository as repository,
)

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_http_modification(
    db_session: AsyncSession,
    *,
    prefix: str,
    is_active: bool,
) -> dict:
    mark = await commands.create_entity(
        db_session,
        entity_type="mark",
        values={"code": f"{prefix}-mark", "name": "Марка", "is_active": True},
    )
    model = await commands.create_entity(
        db_session,
        entity_type="model",
        values={
            "code": f"{prefix}-model",
            "name": "Модель",
            "mark_id": mark["id"],
            "is_active": True,
        },
    )
    category = await commands.create_entity(
        db_session,
        entity_type="category",
        values={
            "code": f"{prefix}-category",
            "name": "Категория",
            "usage_metric": "engine_hours",
            "sort_order": 0,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": [],
        },
    )
    return await commands.create_entity(
        db_session,
        entity_type="modification",
        values={
            "code": f"{prefix}-modification",
            "name": "Модификация",
            "model_id": model["id"],
            "year_from": None,
            "year_to": None,
            "is_active": is_active,
            "category_ids": [category["id"]],
            "attribute_values": [],
        },
    )


async def test_missing_trim_uses_problem_contract(
    client: AsyncClient,
    employee_token: str,
) -> None:
    missing_modification = await client.get(
        (
            "/api/v1/admin/special-equipment/modifications/"
            f"{uuid4()}/trim-attribute-candidates"
        ),
        headers=_auth(employee_token),
    )
    assert missing_modification.status_code == 404
    assert missing_modification.headers["content-type"].startswith(
        "application/problem+json"
    )
    assert missing_modification.json()["code"] == "MODIFICATION_NOT_FOUND"

    response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{uuid4()}",
        headers=_auth(employee_token),
    )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "TRIM_NOT_FOUND"

    legacy_values = await client.get(
        f"/api/v1/admin/special-equipment/trims/{uuid4()}/attribute-values",
        headers=_auth(employee_token),
    )
    assert legacy_values.status_code == 404
    assert legacy_values.headers["content-type"].startswith(
        "application/problem+json"
    )
    assert legacy_values.json()["code"] == "TRIM_NOT_FOUND"


async def test_admin_product_and_modification_validation_use_problem_contract(
    client: AsyncClient,
    employee_token: str,
) -> None:
    product = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={**_auth(employee_token), "Idempotency-Key": "invalid-product"},
        json={},
    )
    modification = await client.patch(
        f"/api/v1/admin/special-equipment/modifications/{uuid4()}",
        headers=_auth(employee_token),
        json={"year_from": "не год"},
    )

    for response in (product, modification):
        assert response.status_code == 422
        assert response.headers["content-type"].startswith(
            "application/problem+json"
        )
        payload = response.json()
        assert {"type", "title", "status", "detail", "code"} <= set(payload)


async def test_trim_create_lifecycle_errors_use_exact_problem_codes(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    active = await _create_http_modification(
        db_session,
        prefix="trim-create-active",
        is_active=True,
    )
    await db_session.commit()
    payload = {"modification_id": str(active["id"]), "name": "Базовая"}
    created = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={**_auth(employee_token), "Idempotency-Key": "create-valid"},
        json=payload,
    )
    assert created.status_code == 201
    duplicate = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={**_auth(employee_token), "Idempotency-Key": "create-duplicate"},
        json=payload,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "TRIM_NAME_ALREADY_EXISTS"


async def test_trim_create_rejects_inactive_or_missing_modification(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    inactive = await _create_http_modification(
        db_session,
        prefix="trim-create-inactive",
        is_active=False,
    )
    await db_session.commit()
    inactive_preview = await client.get(
        (
            "/api/v1/admin/special-equipment/modifications/"
            f"{inactive['id']}/trim-attribute-candidates"
        ),
        headers=_auth(employee_token),
    )
    assert inactive_preview.status_code == 404
    assert inactive_preview.json()["code"] == "MODIFICATION_NOT_FOUND"

    inactive_response = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={**_auth(employee_token), "Idempotency-Key": "create-inactive"},
        json={"modification_id": str(inactive["id"]), "name": "Неактивная"},
    )
    assert inactive_response.status_code == 404
    assert inactive_response.json()["code"] == "MODIFICATION_NOT_FOUND"


async def test_trim_create_validates_missing_modification_and_exact_body(
    client: AsyncClient,
    employee_token: str,
) -> None:
    missing = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={**_auth(employee_token), "Idempotency-Key": "create-missing"},
        json={"modification_id": str(uuid4()), "name": "Нет"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "MODIFICATION_NOT_FOUND"

    for key, body in (
        ("create-whitespace", {"modification_id": str(uuid4()), "name": "   "}),
        (
            "create-bulk",
            {
                "modification_id": str(uuid4()),
                "name": "Лишнее поле",
                "attribute_links": [],
            },
        ),
    ):
        response = await client.post(
            "/api/v1/admin/special-equipment/trims",
            headers={**_auth(employee_token), "Idempotency-Key": key},
            json=body,
        )
        assert response.status_code == 422
        assert response.headers["content-type"].startswith(
            "application/problem+json"
        )


async def test_trim_candidate_can_be_selected_and_persisted_through_http(  # noqa: PLR0915
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    mark = await commands.create_entity(
        db_session,
        entity_type="mark",
        values={"code": "trim-contract-mark", "name": "Марка", "is_active": True},
    )
    model = await commands.create_entity(
        db_session,
        entity_type="model",
        values={
            "code": "trim-contract-model",
            "name": "Модель",
            "mark_id": mark["id"],
            "is_active": True,
        },
    )
    group = await commands.create_entity(
        db_session,
        entity_type="attribute_group",
        values={
            "code": "trim-contract-group",
            "name": "Основные параметры",
            "sort_order": 0,
            "is_active": True,
        },
    )
    attribute = await commands.create_entity(
        db_session,
        entity_type="attribute",
        values={
            "code": "trim-contract-power",
            "name": "Мощность",
            "data_type": "number",
            "unit": "л.с.",
            "filter_kind": "range",
            "is_active": True,
            "options": [],
        },
    )
    category = await commands.create_entity(
        db_session,
        entity_type="category",
        values={
            "code": "trim-contract-category",
            "name": "Тестовая техника",
            "usage_metric": "engine_hours",
            "sort_order": 0,
            "is_active": True,
            "parent_ids": [],
            "attribute_links": [
                {
                    "attribute_id": attribute["id"],
                    "group_id": group["id"],
                    "is_required": True,
                    "is_filterable": True,
                    "is_visible": True,
                    "sort_order": 0,
                }
            ],
        },
    )
    modification = await commands.create_entity(
        db_session,
        entity_type="modification",
        values={
            "code": "trim-contract-modification",
            "name": "Модификация",
            "model_id": model["id"],
            "year_from": 2024,
            "year_to": 2026,
            "is_active": True,
            "category_ids": [category["id"]],
            "attribute_values": [],
        },
    )
    await db_session.commit()
    preview_response = await client.get(
        (
            "/api/v1/admin/special-equipment/modifications/"
            f"{modification['id']}/trim-attribute-candidates"
        ),
        headers=_auth(employee_token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_candidate = preview_response.json()["candidates"][0]
    assert preview_candidate["attribute_id"] == str(attribute["id"])
    assert preview_candidate["is_required"] is True
    assert preview_candidate["is_available"] is True
    assert preview_candidate["modification_value"] is None
    empty_trim_list = await client.get(
        "/api/v1/admin/special-equipment/trims",
        headers=_auth(employee_token),
        params={"modification_id": str(modification["id"])},
    )
    assert empty_trim_list.status_code == 200
    assert empty_trim_list.json() == {"items": []}

    trim_payload = {
        "name": "Базовая",
        "modification_id": str(modification["id"]),
    }
    trim_create_response = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={
            **_auth(employee_token),
            "Idempotency-Key": "trim-contract-create",
        },
        json=trim_payload,
    )
    assert trim_create_response.status_code == 201, trim_create_response.text
    trim = trim_create_response.json()
    assert set(trim) == {"id", "modification_id", "name", "is_active"}
    assert trim["name"] == "Базовая"
    assert trim["is_active"] is True
    assert trim_create_response.headers["location"].endswith(f"/trims/{trim['id']}")
    trim_list_response = await client.get(
        "/api/v1/admin/special-equipment/trims",
        headers=_auth(employee_token),
        params={"modification_id": str(modification["id"])},
    )
    assert trim_list_response.status_code == 200
    assert trim_list_response.json() == {"items": [trim]}
    missing_selector_response = await client.get(
        "/api/v1/admin/special-equipment/trims",
        headers=_auth(employee_token),
    )
    assert missing_selector_response.status_code == 422
    assert missing_selector_response.headers["content-type"].startswith(
        "application/problem+json"
    )
    trimmed_name_response = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={
            **_auth(employee_token),
            "Idempotency-Key": "trim-contract-trimmed-name",
        },
        json={**trim_payload, "name": "  Комфорт  "},
    )
    assert trimmed_name_response.status_code == 201
    assert trimmed_name_response.json()["name"] == "Комфорт"
    trim_replay_response = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={
            **_auth(employee_token),
            "Idempotency-Key": "trim-contract-create",
        },
        json=trim_payload,
    )
    assert trim_replay_response.status_code == 201, trim_replay_response.text
    assert trim_replay_response.json()["id"] == trim["id"]

    candidates_response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-candidates",
        headers=_auth(employee_token),
    )

    assert candidates_response.status_code == 200, candidates_response.text
    candidate = candidates_response.json()["candidates"][0]
    assert candidate["attribute_id"] == str(attribute["id"])
    assert candidate["is_required"] is True
    assert candidate["is_available"] is True
    assert candidate["modification_value"] is None
    assert candidates_response.json() == preview_response.json()

    current_response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attributes",
        headers=_auth(employee_token),
    )
    assert current_response.status_code == 200, current_response.text
    assert current_response.json() == {"items": []}

    trim_response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}",
        headers=_auth(employee_token),
    )
    assert trim_response.status_code == 200, trim_response.text
    assert trim_response.headers["etag"] == current_response.headers["etag"]

    no_op_trim_patch = await client.patch(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}",
        headers={
            **_auth(employee_token),
            "If-Match": current_response.headers["etag"],
        },
        json={"is_active": True},
    )
    assert no_op_trim_patch.status_code == 200, no_op_trim_patch.text
    assert no_op_trim_patch.headers["etag"] == current_response.headers["etag"]
    selected_candidate = {
        "attribute_id": candidate["attribute_id"],
        "group_id": candidate["group_id"],
        "is_required": candidate["is_required"],
        "is_filterable": candidate["is_filterable"],
        "sort_order": candidate["sort_order"],
    }
    create_response = await client.post(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attributes",
        headers={
            **_auth(employee_token),
            "If-Match": current_response.headers["etag"],
        },
        json=selected_candidate,
    )

    assert create_response.status_code == 201, create_response.text
    assigned = {
        **selected_candidate,
        "value_number": None,
        "value_text": None,
        "value_boolean": None,
        "option_id": None,
    }
    assert create_response.json() == {"item": assigned}

    persisted_response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attributes",
        headers=_auth(employee_token),
    )
    assert persisted_response.status_code == 200, persisted_response.text
    assert persisted_response.json() == {"items": [assigned]}

    value_request_payload = {
        "attribute_id": candidate["attribute_id"],
        "value_number": "275",
        "value_text": None,
        "value_boolean": None,
        "option_id": None,
    }
    expected_value_response = {
        **value_request_payload,
        "value_number": 275.0,
    }
    values_patch_response = await client.put(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-values",
        headers={
            **_auth(employee_token),
            "If-Match": persisted_response.headers["etag"],
        },
        json={"values": [value_request_payload]},
    )
    assert values_patch_response.status_code == 200, values_patch_response.text
    assert values_patch_response.json() == {"saved": [expected_value_response]}

    values_persisted_response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attributes",
        headers=_auth(employee_token),
    )
    assert values_persisted_response.status_code == 200, values_persisted_response.text
    assert values_persisted_response.json()["items"] == [
        {**selected_candidate, **expected_value_response}
    ]
    legacy_values_response = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-values",
        headers=_auth(employee_token),
    )
    assert legacy_values_response.status_code == 200, legacy_values_response.text
    assert legacy_values_response.json()["items"] == [expected_value_response]
    assert legacy_values_response.json()["lock_version"] >= 1
    assert (
        legacy_values_response.headers["etag"]
        == values_persisted_response.headers["etag"]
    )

    no_op_response = await client.put(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-values",
        headers={
            **_auth(employee_token),
            "If-Match": values_persisted_response.headers["etag"],
        },
        json={"values": [value_request_payload]},
    )
    assert no_op_response.status_code == 200, no_op_response.text
    assert no_op_response.json() == {"saved": []}
    assert no_op_response.headers["etag"] == values_persisted_response.headers["etag"]

    missing_precondition = await client.put(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-values",
        headers=_auth(employee_token),
        json={"values": []},
    )
    assert missing_precondition.status_code == 428
    assert missing_precondition.headers["content-type"].startswith(
        "application/problem+json"
    )
    assert missing_precondition.json()["code"] == "PRECONDITION_REQUIRED"

    delete_url = (
        f"/api/v1/admin/special-equipment/trims/{trim['id']}"
        f"/attributes/{attribute['id']}"
    )
    deleted = await client.delete(
        delete_url,
        headers={
            **_auth(employee_token),
            "If-Match": no_op_response.headers["etag"],
        },
    )
    assert deleted.status_code == 204, deleted.text
    assert deleted.headers["etag"] != no_op_response.headers["etag"]

    deleted_again = await client.delete(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attributes/{attribute['id']}",
        headers={**_auth(employee_token), "If-Match": deleted.headers["etag"]},
    )
    assert deleted_again.status_code == 204, deleted_again.text
    assert deleted_again.headers["etag"] == deleted.headers["etag"]

    await repository.patch_entity(
        db_session,
        "attribute",
        attribute["id"],
        {"is_active": False},
    )
    await db_session.commit()
    inactive_candidates = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-candidates",
        headers=_auth(employee_token),
    )
    assert inactive_candidates.status_code == 200, inactive_candidates.text
    assert inactive_candidates.json() == {"candidates": []}
    archived = await client.patch(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}",
        headers={
            **_auth(employee_token),
            "If-Match": deleted_again.headers["etag"],
        },
        json={"is_active": False},
    )
    assert archived.status_code == 200, archived.text
    assert archived.headers["etag"] != deleted_again.headers["etag"]
    after_archive = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attributes",
        headers=_auth(employee_token),
    )
    assert after_archive.headers["etag"] == archived.headers["etag"]

    stale = await client.put(
        f"/api/v1/admin/special-equipment/trims/{trim['id']}/attribute-values",
        headers={
            **_auth(employee_token),
            "If-Match": no_op_response.headers["etag"],
        },
        json={"values": []},
    )
    assert stale.status_code == 412
    assert stale.headers["content-type"].startswith("application/problem+json")
    assert stale.json()["code"] == "PRECONDITION_FAILED"


async def test_delete_trim_http_contract_success(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    prefix = f"trim-del-{uuid4().hex[:8]}"
    modification = await _create_http_modification(
        db_session,
        prefix=prefix,
        is_active=True,
    )
    category_id = modification["category_ids"][0]
    attribute = await commands.create_entity(
        db_session,
        entity_type="attribute",
        values={
            "code": f"{prefix}-attr",
            "name": "Мощность",
            "data_type": "number",
            "unit": "л.с.",
            "filter_kind": "range",
            "is_active": True,
            "options": [],
        },
    )
    await commands.patch_entity(
        db_session,
        entity_type="category",
        entity_id=category_id,
        values={
            "attribute_links": [
                {
                    "attribute_id": attribute["id"],
                    "group_id": None,
                    "is_required": False,
                    "is_filterable": False,
                    "is_visible": True,
                    "sort_order": 0,
                }
            ]
        },
        expected_version=1,
    )
    await db_session.commit()

    trim_payload = {
        "name": f"Комплектация {prefix}",
        "modification_id": str(modification["id"]),
    }
    trim_res = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={
            **_auth(employee_token),
            "Idempotency-Key": f"create-trim-{prefix}",
        },
        json=trim_payload,
    )
    assert trim_res.status_code == 201, trim_res.text
    trim = trim_res.json()
    trim_id = trim["id"]

    trim_detail = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers=_auth(employee_token),
    )
    assign_res = await client.post(
        f"/api/v1/admin/special-equipment/trims/{trim_id}/attributes",
        headers={
            **_auth(employee_token),
            "If-Match": trim_detail.headers["etag"],
        },
        json={
            "attribute_id": str(attribute["id"]),
            "group_id": None,
            "is_required": False,
            "is_filterable": False,
            "sort_order": 0,
        },
    )
    assert assign_res.status_code == 201, assign_res.text

    val_res = await client.put(
        f"/api/v1/admin/special-equipment/trims/{trim_id}/attribute-values",
        headers={
            **_auth(employee_token),
            "If-Match": assign_res.headers["etag"],
        },
        json={
            "values": [
                {
                    "attribute_id": str(attribute["id"]),
                    "value_number": "150.5",
                    "value_text": None,
                    "value_boolean": None,
                    "option_id": None,
                }
            ]
        },
    )
    assert val_res.status_code == 200, val_res.text
    current_etag = val_res.headers["etag"]

    no_etag_res = await client.delete(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers=_auth(employee_token),
    )
    assert no_etag_res.status_code == 428

    stale_res = await client.delete(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers={
            **_auth(employee_token),
            "If-Match": 'W/"1"',
        },
    )
    assert stale_res.status_code == 412
    assert stale_res.json()["code"] == "PRECONDITION_FAILED"

    delete_res = await client.delete(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers={
            **_auth(employee_token),
            "If-Match": current_etag,
        },
    )
    assert delete_res.status_code == 204, delete_res.text

    get_res = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers=_auth(employee_token),
    )
    assert get_res.status_code == 404

    trim_rows = await db_session.execute(
        sa.select(SpecialEquipmentTrim).where(SpecialEquipmentTrim.id == trim_id)
    )
    assert trim_rows.scalar_one_or_none() is None

    attr_rows = await db_session.execute(
        sa.select(SpecialEquipmentTrimAttribute).where(
            SpecialEquipmentTrimAttribute.trim_id == trim_id
        )
    )
    assert attr_rows.scalars().all() == []

    val_rows = await db_session.execute(
        sa.select(SpecialEquipmentTrimAttributeValue).where(
            SpecialEquipmentTrimAttributeValue.trim_id == trim_id
        )
    )
    assert val_rows.scalars().all() == []


async def test_delete_trim_http_contract_conflict_with_product(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    prefix = f"trim-conflict-{uuid4().hex[:8]}"
    modification = await _create_http_modification(
        db_session,
        prefix=prefix,
        is_active=True,
    )
    trim_res = await client.post(
        "/api/v1/admin/special-equipment/trims",
        headers={
            **_auth(employee_token),
            "Idempotency-Key": f"create-trim-{prefix}",
        },
        json={
            "name": f"Комплектация {prefix}",
            "modification_id": str(modification["id"]),
        },
    )
    assert trim_res.status_code == 201, trim_res.text
    trim = trim_res.json()
    trim_id = trim["id"]

    trim_detail = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers=_auth(employee_token),
    )
    current_etag = trim_detail.headers["etag"]

    seller = Company(
        name=f"Seller {prefix}",
        inn=prefix[:12].replace("-", "0").ljust(10, "1"),
        company_type="dealer",
        is_active=True,
    )
    db_session.add(seller)
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"{prefix}-prod",
        slug=f"{prefix}-prod",
        modification_id=modification["id"],
        trim_id=trim_id,
        seller_company_id=seller.id,
        price=Decimal("5000000.00"),
        condition="new",
        no_vin=True,
        vin=None,
        publication_status="published",
        sale_status="available",
        published_at=datetime.now(UTC),
    )
    db_session.add(product)
    await db_session.commit()

    deps_res = await client.get(
        f"/api/v1/admin/special-equipment/trims/{trim_id}/dependencies",
        headers=_auth(employee_token),
    )
    assert deps_res.status_code == 200
    assert deps_res.json()["blockers"] == {"products": 1}
    assert deps_res.json()["can_delete"] is False

    conflict_res = await client.delete(
        f"/api/v1/admin/special-equipment/trims/{trim_id}",
        headers={
            **_auth(employee_token),
            "If-Match": current_etag,
        },
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["code"] == "SPECIAL_EQUIPMENT_DEPENDENCY_CONFLICT"


async def test_delete_trim_http_contract_not_found(
    client: AsyncClient,
    employee_token: str,
) -> None:
    non_existent_id = uuid4()
    missing_del = await client.delete(
        f"/api/v1/admin/special-equipment/trims/{non_existent_id}",
        headers={
            **_auth(employee_token),
            "If-Match": f'"{non_existent_id}:1:{"a"*64}"',
        },
    )
    assert missing_del.status_code == 404


