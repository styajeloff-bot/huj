"""Category management contracts completed for Bitrix task 21940."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.special_equipment_management import (
    ListRegistryQuery,
    handle_list,
)
from domain.special_equipment_management import (
    CategoryPathEdge,
    CategoryPathNode,
    SpecialEquipmentManagementIntegrityError,
    canonical_category_paths,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
)
from infrastructure.repositories import (
    special_equipment_management_repository as repository,
)
from infrastructure.repositories import (
    special_equipment_repository as public_repository,
)
from main import app


def _category(
    name: str,
    *,
    sort_order: int = 0,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    category_id: UUID | None = None,
) -> SpecialEquipmentCategory:
    suffix = uuid4().hex
    return SpecialEquipmentCategory(
        id=category_id or uuid4(),
        code=f"category-{suffix}",
        name=name,
        slug=f"category-{suffix}",
        usage_metric="engine_hours",
        sort_order=sort_order,
        created_at=created_at,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_primary_category_leaf_lookup_is_bounded_to_candidates(
    db_session: AsyncSession,
) -> None:
    root = _category("Корень")
    active_leaf = _category("Активный лист")
    inactive_leaf = _category("Неактивный лист")
    inactive_leaf.is_active = False
    unrelated = _category("Вне кандидатов")
    db_session.add_all((root, active_leaf, inactive_leaf, unrelated))
    await db_session.flush()
    db_session.add_all(
        (
            SpecialEquipmentCategoryRelation(
                parent_id=root.id,
                child_id=active_leaf.id,
                sort_order=0,
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=active_leaf.id,
                child_id=inactive_leaf.id,
                sort_order=0,
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=unrelated.id,
                child_id=root.id,
                sort_order=0,
            ),
        )
    )
    await db_session.flush()

    result = await public_repository.list_non_leaf_category_ids(
        db_session,
        (root.id, active_leaf.id),
    )

    assert result == {root.id}


def test_category_list_exposes_only_supported_sort_contract() -> None:
    operation = app.openapi()["paths"][
        "/api/v1/admin/special-equipment/categories"
    ]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    assert "updated_from" not in parameters
    assert "updated_to" not in parameters
    assert parameters["sort"]["schema"]["enum"] == [
        "hierarchy",
        "updated_desc",
    ]
    assert parameters["sort"]["schema"]["default"] == "hierarchy"


def test_updated_snapshot_query_matches_the_effective_update_index() -> None:
    statement = repository._category_snapshot_query(sort="updated_desc")
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "ORDER BY greatest(" in sql
    assert "special_equipment_categories.created_at" in sql
    assert "special_equipment_categories.updated_at" in sql
    assert "special_equipment_categories.id DESC" in sql


def test_canonical_paths_use_linear_dag_dynamic_programming() -> None:
    root_a, root_b, middle_a, middle_b, leaf = (uuid4() for _ in range(5))
    paths = canonical_category_paths(
        nodes=(
            CategoryPathNode(root_a, "А", 0),
            CategoryPathNode(root_b, "Б", 0),
            CategoryPathNode(middle_a, "Уровень", 0),
            CategoryPathNode(middle_b, "Уровень", 0),
            CategoryPathNode(leaf, "Лист", 0),
        ),
        edges=(
            CategoryPathEdge(root_a, middle_a, 0),
            CategoryPathEdge(root_b, middle_b, 0),
            CategoryPathEdge(middle_a, leaf, 5),
            CategoryPathEdge(middle_b, leaf, 0),
        ),
    )

    assert paths[leaf].display == "А / Уровень / Лист"
    assert paths[leaf].category_ids == (root_a, middle_a, leaf)


def test_canonical_paths_reject_rootless_cycle() -> None:
    first, second = uuid4(), uuid4()

    with pytest.raises(
        SpecialEquipmentManagementIntegrityError,
        match="цикл",
    ):
        canonical_category_paths(
            nodes=(
                CategoryPathNode(first, "Первая", 0),
                CategoryPathNode(second, "Вторая", 0),
            ),
            edges=(
                CategoryPathEdge(first, second, 0),
                CategoryPathEdge(second, first, 0),
            ),
        )


@pytest.mark.asyncio
async def test_category_sort_is_forwarded_through_the_application_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_list(
        _session: object, entity_type: str, **kwargs: Any
    ) -> tuple[list[dict[str, object]], int]:
        captured.update(entity_type=entity_type, **kwargs)
        return [], 0

    monkeypatch.setattr(repository, "list_entities", fake_list)

    await handle_list(
        ListRegistryQuery("category", sort="updated_desc"),
        object(),  # type: ignore[arg-type]
    )

    assert captured["sort"] == "updated_desc"
    assert "updated_from" not in captured
    assert "updated_to" not in captured


@pytest.mark.asyncio
async def test_hierarchy_uses_one_lexicographically_minimal_dag_path(
    db_session: AsyncSession,
) -> None:
    root_a = _category("Альфа")
    root_b = _category("Бета")
    branch_a = _category("Ветка")
    branch_b = _category("Ветка")
    shared = _category("Общая")
    db_session.add_all((root_a, root_b, branch_a, branch_b, shared))
    await db_session.flush()
    db_session.add_all(
        (
            SpecialEquipmentCategoryRelation(
                parent_id=root_a.id, child_id=branch_a.id, sort_order=0
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=root_b.id, child_id=branch_b.id, sort_order=0
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=branch_a.id, child_id=shared.id, sort_order=5
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=branch_b.id, child_id=shared.id, sort_order=0
            ),
        )
    )
    await db_session.flush()

    rows, total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=20,
        search="Альфа / Ветка / Общая",
        sort="hierarchy",
    )
    noncanonical_rows, noncanonical_total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=20,
        search="Бета / Ветка / Общая",
        sort="hierarchy",
    )

    assert total == 1
    assert [row["id"] for row in rows] == [shared.id]
    assert rows[0]["canonical_path"] == "Альфа / Ветка / Общая"
    assert noncanonical_total == 0
    assert noncanonical_rows == []

    same_name_rows, same_name_total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=20,
        search="Ветка",
        sort="hierarchy",
    )
    assert same_name_total == 3
    assert [
        row["canonical_path"]
        for row in same_name_rows
        if row["name"] == "Ветка"
    ] == [
        "Альфа / Ветка",
        "Бета / Ветка",
    ]

    alternate_rows, alternate_total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=20,
        category_level_ids=(root_b.id, branch_b.id),
        sort="hierarchy",
    )
    assert alternate_total == 2
    assert {row["id"] for row in alternate_rows} == {branch_b.id, shared.id}

    invalid_rows, invalid_total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=20,
        category_level_ids=(root_a.id, branch_b.id),
        sort="hierarchy",
    )
    assert invalid_total == 0
    assert invalid_rows == []


@pytest.mark.asyncio
async def test_category_resource_exposes_deduplicated_effective_attribute_groups(
    db_session: AsyncSession,
) -> None:
    root = _category("Корень")
    leaf = _category("Лист")
    default_group = SpecialEquipmentAttributeGroup(
        code=f"default-{uuid4().hex}",
        name="Основные",
        slug=f"default-{uuid4().hex}",
        sort_order=10,
    )
    override_group = SpecialEquipmentAttributeGroup(
        code=f"override-{uuid4().hex}",
        name="Приоритетные",
        slug=f"override-{uuid4().hex}",
        sort_order=1,
    )
    inherited = SpecialEquipmentAttribute(
        code=f"inherited-{uuid4().hex}",
        name="Мощность",
        attribute_group_id=default_group.id,
        data_type="number",
        filter_kind="range",
    )
    ungrouped = SpecialEquipmentAttribute(
        code=f"ungrouped-{uuid4().hex}",
        name="Комментарий",
        data_type="text",
        filter_kind="search",
    )
    db_session.add_all(
        [root, leaf, default_group, override_group, inherited, ungrouped]
    )
    await db_session.flush()
    db_session.add_all(
        [
            SpecialEquipmentCategoryRelation(
                parent_id=root.id,
                child_id=leaf.id,
                sort_order=0,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=root.id,
                attribute_id=inherited.id,
                is_filterable=True,
                is_visible=True,
                sort_order=5,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=leaf.id,
                attribute_id=inherited.id,
                group_id=override_group.id,
                is_required=True,
                is_filterable=True,
                is_visible=True,
                sort_order=2,
            ),
            SpecialEquipmentCategoryAttribute(
                category_id=leaf.id,
                attribute_id=ungrouped.id,
                is_visible=True,
                sort_order=3,
            ),
        ]
    )
    await db_session.flush()

    resource = await repository.get_entity(db_session, "category", leaf.id)

    assert resource is not None
    links = resource["effective_attribute_links"]
    assert [item["attribute_id"] for item in links] == [
        inherited.id,
        ungrouped.id,
    ]
    assert links[0] == {
        "attribute_id": inherited.id,
        "attribute_name": "Мощность",
        "data_type": "number",
        "filter_kind": "range",
        "group_id": override_group.id,
        "group_name": "Приоритетные",
        "group_sort_order": 1,
        "is_required": True,
        "is_filterable": True,
        "is_visible": True,
        "sort_order": 2,
    }
    assert links[1]["group_id"] is None
    assert links[1]["group_name"] == "Прочие"


@pytest.mark.asyncio
async def test_hierarchy_sort_and_pagination_are_stable(
    db_session: AsyncSession,
) -> None:
    root = _category("Корень", sort_order=0)
    second = _category("Второй")
    first_b = _category("Первый Б", category_id=UUID(int=2))
    first_a = _category("Первый А", category_id=UUID(int=1))
    db_session.add_all((root, second, first_b, first_a))
    await db_session.flush()
    db_session.add_all(
        (
            SpecialEquipmentCategoryRelation(
                parent_id=root.id, child_id=second.id, sort_order=2
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=root.id, child_id=first_b.id, sort_order=1
            ),
            SpecialEquipmentCategoryRelation(
                parent_id=root.id, child_id=first_a.id, sort_order=1
            ),
        )
    )
    await db_session.flush()

    first_page, total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=2,
        sort="hierarchy",
    )
    second_page, _ = await repository.list_entities(
        db_session,
        "category",
        offset=2,
        limit=2,
        sort="hierarchy",
    )

    assert total == 4
    assert [row["id"] for row in first_page + second_page] == [
        root.id,
        first_a.id,
        first_b.id,
        second.id,
    ]


@pytest.mark.asyncio
async def test_updated_desc_uses_effective_update_and_stable_id_tie_breaker(
    db_session: AsyncSession,
) -> None:
    older = _category(
        "Старая",
        created_at=datetime(2026, 8, 3, tzinfo=UTC),
        updated_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    tie_low = _category(
        "Новая А",
        category_id=UUID(int=1),
        created_at=datetime(2026, 8, 2, tzinfo=UTC),
        updated_at=datetime(2026, 8, 5, tzinfo=UTC),
    )
    tie_high = _category(
        "Новая Б",
        category_id=UUID(int=2),
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    created_wins = _category(
        "Создана позднее изменения",
        category_id=UUID(int=3),
        created_at=datetime(2026, 8, 6, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    db_session.add_all((older, tie_low, tie_high, created_wins))
    await db_session.flush()

    rows, total = await repository.list_entities(
        db_session,
        "category",
        offset=0,
        limit=20,
        sort="updated_desc",
    )

    assert total == 4
    assert [row["id"] for row in rows] == [
        created_wins.id,
        tie_high.id,
        tie_low.id,
        older.id,
    ]
    assert [row["canonical_path"] for row in rows] == [
        "Создана позднее изменения",
        "Новая Б",
        "Новая А",
        "Старая",
    ]


@pytest.mark.asyncio
async def test_category_page_query_count_is_constant(
    db_session: AsyncSession,
) -> None:
    categories = [_category(f"Категория {index:03d}") for index in range(30)]
    db_session.add_all(categories)
    await db_session.flush()
    statements: list[str] = []

    def record_query(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", record_query)
    try:
        rows, total = await repository.list_entities(
            db_session,
            "category",
            offset=0,
            limit=30,
            sort="hierarchy",
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_query)

    assert total == 30
    assert len(rows) == 30
    assert len(statements) == 4

    statements.clear()
    event.listen(bind, "before_cursor_execute", record_query)
    try:
        detail = await repository.get_entity(
            db_session,
            "category",
            rows[0]["id"],
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_query)

    assert detail == rows[0]
    assert len(statements) == 4
