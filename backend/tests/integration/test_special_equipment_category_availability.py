"""Category-context validation contracts."""

from uuid import uuid4

import pytest

from application.queries.special_equipment import handle_resolve_category_path


@pytest.mark.asyncio
async def test_resolver_accepts_each_real_path_to_shared_dag_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_a, root_b, shared = uuid4(), uuid4(), uuid4()

    async def snapshot(_session: object) -> dict[str, list[dict[str, object]]]:
        return {
            "categories": [
                {
                    "id": root_a,
                    "code": "a",
                    "name": "A",
                    "slug": "a",
                    "usage_metric": "engine_hours",
                    "sort_order": 0,
                    "image_key": None,
                    "product_count": 0,
                },
                {
                    "id": root_b,
                    "code": "b",
                    "name": "B",
                    "slug": "b",
                    "usage_metric": "engine_hours",
                    "sort_order": 0,
                    "image_key": None,
                    "product_count": 0,
                },
                {
                    "id": shared,
                    "code": "shared",
                    "name": "Общая",
                    "slug": "shared",
                    "usage_metric": "engine_hours",
                    "sort_order": 0,
                    "image_key": None,
                    "product_count": 0,
                },
            ],
            "relations": [
                {"parent_id": root_a, "child_id": shared, "sort_order": 0},
                {"parent_id": root_b, "child_id": shared, "sort_order": 0},
            ],
        }

    monkeypatch.setattr(
        "application.queries.special_equipment.repository.list_category_graph",
        snapshot,
    )
    first = await handle_resolve_category_path("a/shared", object())  # type: ignore[arg-type]
    second = await handle_resolve_category_path("b/shared", object())  # type: ignore[arg-type]
    assert first["category"]["id"] == shared
    assert second["category"]["id"] == shared
