"""Integration and API contracts for special equipment catalog cascade delete."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import special_equipment_management as commands
from application.special_equipment_management_etag import (
    special_equipment_management_etag,
)
from domain.special_equipment_cascade_delete import (
    CASCADE_CONFIRMATION_INVALID,
    CASCADE_DELETE_BLOCKED,
    CASCADE_PREVIEW_STALE,
    CASCADE_TOO_LARGE,
    CascadeBlockers,
    CascadeConfirmationInvalidError,
    CascadeDeleteBlockedError,
    CascadePlan,
    CascadePreviewStaleError,
    CascadeTooLargeError,
    ClearRef,
    DistributorBlocker,
    EntityRef,
    ProductBlocker,
    ProductBlockerDocument,
    SupportProgramBlocker,
    SupportProgramBlockerReference,
    UnlinkRef,
    UserImpact,
)


def _make_dummy_plan(
    *,
    root_type: str = "marks",
    root_id: UUID | None = None,
    preview_token: str = "test_token_123",  # noqa: S107
    blockers: CascadeBlockers | None = None,
    cart_items: int = 0,
    favorites: int = 0,
) -> CascadePlan:
    rid = root_id or uuid4()
    root_ref = EntityRef(type="mark", id=rid, code="test-mark", name="Тестовая марка")
    delete_items = {
        "marks": [root_ref],
        "models": [EntityRef(type="model", id=uuid4(), code="mod-1", name="Модель 1")],
    }
    return CascadePlan(
        root=root_ref,
        delete=delete_items,
        unlink=[UnlinkRef(type="category_relation", count=2, description="2 связи отвязаны")],
        clear=[ClearRef(type="product", field="trim_id", count=1, description="Очищена комплектация у 1 товара")],
        attribute_values_to_delete_count=0,
        user_impact=UserImpact(cart_items=cart_items, favorites=favorites),
        blockers=blockers or CascadeBlockers(),
        counts={"marks": 1, "models": 1},
        total_affected=2,
        preview_token=preview_token,
        catalog_revision=42,
    )


@pytest.mark.asyncio
async def test_cascade_delete_preview_endpoint_success(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    plan = _make_dummy_plan(root_id=mark_id, preview_token="valid_token_abc")
    monkeypatch.setattr(commands, "preview_cascade_delete", AsyncMock(return_value=plan))

    response = await client.get(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/delete-preview",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["root"]["id"] == str(mark_id)
    assert data["root"]["type"] == "mark"
    assert data["preview_token"] == "valid_token_abc"
    assert data["catalog_revision"] == 42
    assert len(data["delete"]) == 2
    assert data["total"] == 2
    assert data["unlink"][0]["count"] == 2
    assert data["clear"][0]["count"] == 1


@pytest.mark.asyncio
async def test_cascade_delete_preview_with_blockers(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    prod_id = uuid4()
    blockers = CascadeBlockers(
        products=[
            ProductBlocker(
                product=EntityRef(type="product", id=prod_id, code="PRD-01", name="Экскаватор"),
                documents=[
                    ProductBlockerDocument(type="application", id=uuid4(), number="APP-100", status="active")
                ],
            )
        ],
        distributors=[
            DistributorBlocker(company={"id": str(uuid4()), "name": "Дистрибьютор Восток", "inn": "7701234567"})
        ],
        support_programs=[
            SupportProgramBlocker(
                program={"id": str(uuid4()), "name": "Субсидия 2026", "is_active": True},
                references=[SupportProgramBlockerReference(type="mark", id=mark_id, name="Тестовая марка")],
            )
        ],
    )
    plan = _make_dummy_plan(root_id=mark_id, blockers=blockers)
    monkeypatch.setattr(commands, "preview_cascade_delete", AsyncMock(return_value=plan))

    response = await client.get(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/delete-preview",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["blockers"]["products"]) == 1
    assert data["blockers"]["products"][0]["product"]["id"] == str(prod_id)
    assert len(data["blockers"]["distributors"]) == 1
    assert len(data["blockers"]["support_programs"]) == 1


@pytest.mark.asyncio
async def test_cascade_delete_endpoint_confirmation_invalid(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    etag = special_equipment_management_etag({"id": mark_id, "lock_version": 1})
    monkeypatch.setattr(
        commands,
        "cascade_delete_entity",
        AsyncMock(side_effect=CascadeConfirmationInvalidError("Ожидается слово 'УДАЛИТЬ'")),
    )

    response = await client.post(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/cascade-delete",
        headers={"Authorization": f"Bearer {employee_token}", "If-Match": etag},
        json={"confirmation": "не_удалять", "preview_token": "token"},
    )

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == CASCADE_CONFIRMATION_INVALID
    assert body["status"] == 400


@pytest.mark.asyncio
async def test_cascade_delete_endpoint_blocked_returns_409_problem_details(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    etag = special_equipment_management_etag({"id": mark_id, "lock_version": 1})
    blockers = CascadeBlockers(
        distributors=[
            DistributorBlocker(company={"id": str(uuid4()), "name": "Дилер Восток", "inn": "7701111111"})
        ]
    )
    monkeypatch.setattr(
        commands,
        "cascade_delete_entity",
        AsyncMock(side_effect=CascadeDeleteBlockedError(blockers=blockers)),
    )

    response = await client.post(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/cascade-delete",
        headers={"Authorization": f"Bearer {employee_token}", "If-Match": etag},
        json={"confirmation": "УДАЛИТЬ", "preview_token": "token"},
    )

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == CASCADE_DELETE_BLOCKED
    assert len(body["blockers"]["distributors"]) == 1


@pytest.mark.asyncio
async def test_cascade_delete_endpoint_stale_preview_returns_409_with_new_preview(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    etag = special_equipment_management_etag({"id": mark_id, "lock_version": 1})
    new_plan = _make_dummy_plan(root_id=mark_id, preview_token="new_fresh_token_xyz")
    monkeypatch.setattr(
        commands,
        "cascade_delete_entity",
        AsyncMock(side_effect=CascadePreviewStaleError(plan=new_plan)),
    )

    response = await client.post(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/cascade-delete",
        headers={"Authorization": f"Bearer {employee_token}", "If-Match": etag},
        json={"confirmation": "УДАЛИТЬ", "preview_token": "old_stale_token"},
    )

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == CASCADE_PREVIEW_STALE
    assert body["preview"]["preview_token"] == "new_fresh_token_xyz"


@pytest.mark.asyncio
async def test_cascade_delete_endpoint_too_large_returns_422(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    monkeypatch.setattr(
        commands,
        "preview_cascade_delete",
        AsyncMock(side_effect=CascadeTooLargeError(total=6000, max_rows=5000)),
    )

    response = await client.get(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/delete-preview",
        headers={"Authorization": f"Bearer {employee_token}"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == CASCADE_TOO_LARGE
    assert body["total"] == 6000
    assert body["max_rows"] == 5000


@pytest.mark.asyncio
async def test_cascade_delete_endpoint_success(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_id = uuid4()
    etag = special_equipment_management_etag({"id": mark_id, "lock_version": 1})
    expected_result = {
        "deleted": {"marks": 1, "models": 2, "modifications": 3, "products": 5},
        "catalog_revision": 43,
    }
    monkeypatch.setattr(
        commands,
        "cascade_delete_entity",
        AsyncMock(return_value=expected_result),
    )

    response = await client.post(
        f"/api/v1/admin/special-equipment/marks/{mark_id}/cascade-delete",
        headers={"Authorization": f"Bearer {employee_token}", "If-Match": etag},
        json={"confirmation": "УДАЛИТЬ", "preview_token": "valid_token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["catalog_revision"] == 43
    assert body["deleted"]["marks"] == 1
    assert body["deleted"]["products"] == 5


@pytest.mark.asyncio
async def test_colors_endpoint_supports_cascade_delete(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    color_id = uuid4()
    etag = special_equipment_management_etag({"id": color_id, "lock_version": 1})
    expected_result = {
        "deleted": {"colors": 1},
        "catalog_revision": 44,
    }
    monkeypatch.setattr(
        commands,
        "cascade_delete_entity",
        AsyncMock(return_value=expected_result),
    )

    response = await client.post(
        f"/api/v1/admin/special-equipment/colors/{color_id}/cascade-delete",
        headers={"Authorization": f"Bearer {employee_token}", "If-Match": etag},
        json={"confirmation": "УДАЛИТЬ", "preview_token": "color_token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"]["colors"] == 1
    assert body["catalog_revision"] == 44


@pytest.mark.asyncio
async def test_db_apply_cascade_delete_mark(db_session: AsyncSession) -> None:
    import sqlalchemy as sa

    from infrastructure.models.special_equipment import (
        SpecialEquipmentCatalogDeletionLog,
        SpecialEquipmentMark,
        SpecialEquipmentModel,
        SpecialEquipmentModification,
        SpecialEquipmentProduct,
        SpecialEquipmentTrim,
    )
    from infrastructure.models.special_equipment_import import (
        SpecialEquipmentCatalogState,
    )
    from infrastructure.repositories import (
        special_equipment_cascade_delete_repository as repo,
    )

    suffix = uuid4().hex[:8]
    mark = SpecialEquipmentMark(id=uuid4(), code=f"mark-{suffix}", name="Mark", slug=f"mark-{suffix}")
    model = SpecialEquipmentModel(id=uuid4(), mark_id=mark.id, code=f"model-{suffix}", name="Model", slug=f"model-{suffix}")
    modification = SpecialEquipmentModification(
        id=uuid4(), model_id=model.id, code=f"mod-{suffix}", name="Mod", slug=f"mod-{suffix}"
    )
    trim = SpecialEquipmentTrim(
        id=uuid4(), modification_id=modification.id, code=f"trim-{suffix}", name="Trim", slug=f"trim-{suffix}"
    )
    product = SpecialEquipmentProduct(
        id=uuid4(),
        code=f"prod-{suffix}",
        modification_id=modification.id,
        trim_id=trim.id,
        condition="new",
        no_vin=True,
        sale_status="available",
        publication_status="draft",
        slug=f"prod-{suffix}",
    )
    db_session.add_all([mark, model, modification, trim])
    await db_session.flush()
    db_session.add(product)
    await db_session.flush()

    root_ref, graph = await repo.load_cascade_graph(db_session, "marks", mark.id)
    assert root_ref.id == mark.id
    from domain.special_equipment_cascade_delete import build_cascade_plan
    plan = build_cascade_plan(root_ref, graph)

    revision_before = (
        await db_session.scalar(
            sa.select(SpecialEquipmentCatalogState.revision).where(
                SpecialEquipmentCatalogState.singleton.is_(True)
            )
        )
        or 0
    )

    deleted_counts = await repo.apply_cascade_plan(db_session, plan, user_id=None, catalog_revision=revision_before)

    assert deleted_counts["marks"] == 1
    assert deleted_counts["models"] == 1
    assert deleted_counts["modifications"] == 1
    assert deleted_counts["trims"] == 1
    assert deleted_counts["products"] == 1

    # Verify rows no longer exist
    mark_exists = await db_session.scalar(sa.select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.id == mark.id))
    assert mark_exists is None

    prod_exists = await db_session.scalar(sa.select(SpecialEquipmentProduct.id).where(SpecialEquipmentProduct.id == product.id))
    assert prod_exists is None

    # Verify catalog revision incremented
    revision_after = (
        await db_session.scalar(
            sa.select(SpecialEquipmentCatalogState.revision).where(
                SpecialEquipmentCatalogState.singleton.is_(True)
            )
        )
    )
    assert revision_after == revision_before + 1

    # Verify deletion log entry
    log_row = (
        await db_session.execute(
            sa.select(SpecialEquipmentCatalogDeletionLog).where(
                SpecialEquipmentCatalogDeletionLog.root_id == mark.id
            )
        )
    ).scalar_one_or_none()
    assert log_row is not None
    assert log_row.root_type == "mark"
    assert log_row.catalog_revision == revision_after


@pytest.mark.asyncio
async def test_db_trim_delete_clears_product_trim_id(db_session: AsyncSession) -> None:
    import sqlalchemy as sa

    from infrastructure.models.special_equipment import (
        SpecialEquipmentMark,
        SpecialEquipmentModel,
        SpecialEquipmentModification,
        SpecialEquipmentProduct,
        SpecialEquipmentTrim,
    )
    from infrastructure.repositories import (
        special_equipment_cascade_delete_repository as repo,
    )

    suffix = uuid4().hex[:8]
    mark = SpecialEquipmentMark(id=uuid4(), code=f"mark-{suffix}", name="Mark", slug=f"mark-{suffix}")
    model = SpecialEquipmentModel(id=uuid4(), mark_id=mark.id, code=f"model-{suffix}", name="Model", slug=f"model-{suffix}")
    modification = SpecialEquipmentModification(
        id=uuid4(), model_id=model.id, code=f"mod-{suffix}", name="Mod", slug=f"mod-{suffix}"
    )
    trim = SpecialEquipmentTrim(
        id=uuid4(), modification_id=modification.id, code=f"trim-{suffix}", name="Trim", slug=f"trim-{suffix}"
    )
    product = SpecialEquipmentProduct(
        id=uuid4(),
        code=f"prod-{suffix}",
        modification_id=modification.id,
        trim_id=trim.id,
        condition="new",
        no_vin=True,
        sale_status="available",
        publication_status="draft",
        slug=f"prod-{suffix}",
    )
    db_session.add_all([mark, model, modification, trim])
    await db_session.flush()
    db_session.add(product)
    await db_session.flush()

    root_ref, graph = await repo.load_cascade_graph(db_session, "trims", trim.id)
    from domain.special_equipment_cascade_delete import build_cascade_plan
    plan = build_cascade_plan(root_ref, graph)

    await repo.apply_cascade_plan(db_session, plan, user_id=None, catalog_revision=0)

    # Trim deleted
    trim_exists = await db_session.scalar(sa.select(SpecialEquipmentTrim.id).where(SpecialEquipmentTrim.id == trim.id))
    assert trim_exists is None

    # Product remains, trim_id cleared
    refreshed_prod = await db_session.scalar(
        sa.select(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id == product.id)
    )
    assert refreshed_prod is not None
    assert refreshed_prod.trim_id is None
    assert refreshed_prod.publication_status == "draft"


@pytest.mark.asyncio
async def test_db_color_delete_clears_product_color_id(db_session: AsyncSession) -> None:
    import sqlalchemy as sa

    from infrastructure.models.special_equipment import (
        SpecialEquipmentColor,
        SpecialEquipmentMark,
        SpecialEquipmentModel,
        SpecialEquipmentModification,
        SpecialEquipmentProduct,
    )
    from infrastructure.repositories import (
        special_equipment_cascade_delete_repository as repo,
    )

    suffix = uuid4().hex[:8]
    color = SpecialEquipmentColor(id=uuid4(), code=f"color-{suffix}", name="Red", applicability="both")
    mark = SpecialEquipmentMark(id=uuid4(), code=f"mark-{suffix}", name="Mark", slug=f"mark-{suffix}")
    model = SpecialEquipmentModel(id=uuid4(), mark_id=mark.id, code=f"model-{suffix}", name="Model", slug=f"model-{suffix}")
    modification = SpecialEquipmentModification(
        id=uuid4(), model_id=model.id, code=f"mod-{suffix}", name="Mod", slug=f"mod-{suffix}"
    )
    product = SpecialEquipmentProduct(
        id=uuid4(),
        code=f"prod-{suffix}",
        modification_id=modification.id,
        body_color_id=color.id,
        interior_color_id=color.id,
        condition="new",
        no_vin=True,
        sale_status="available",
        publication_status="draft",
        slug=f"prod-{suffix}",
    )
    db_session.add_all([color, mark, model, modification])
    await db_session.flush()
    db_session.add(product)
    await db_session.flush()

    root_ref, graph = await repo.load_cascade_graph(db_session, "colors", color.id)
    from domain.special_equipment_cascade_delete import build_cascade_plan
    plan = build_cascade_plan(root_ref, graph)

    await repo.apply_cascade_plan(db_session, plan, user_id=None, catalog_revision=0)

    # Color deleted
    color_exists = await db_session.scalar(sa.select(SpecialEquipmentColor.id).where(SpecialEquipmentColor.id == color.id))
    assert color_exists is None

    # Product remains, colors cleared
    refreshed_prod = await db_session.scalar(
        sa.select(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id == product.id)
    )
    assert refreshed_prod is not None
    assert refreshed_prod.body_color_id is None
    assert refreshed_prod.interior_color_id is None

