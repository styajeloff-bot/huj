"""Two-transaction stale-write coverage for trim assignments."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.commands import special_equipment_management as commands
from application.special_equipment_management_etag import (
    special_equipment_management_etag,
    special_equipment_trim_attributes_etag,
)
from domain.special_equipment_import import ImportAggregateSemanticConflictError
from domain.special_equipment_management import SpecialEquipmentTrimContractError
from infrastructure.repositories import (
    special_equipment_import_repository as import_repository,
)
from infrastructure.repositories import (
    special_equipment_management_repository as repository,
)

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class _ValueFixture:
    mark_id: UUID
    model_id: UUID
    category_id: UUID
    modification_id: UUID
    trim_id: UUID
    attribute_id: UUID
    suffix: str


@pytest_asyncio.fixture
async def value_fixture(_engine: AsyncEngine) -> AsyncIterator[_ValueFixture]:
    fixture = _ValueFixture(
        mark_id=uuid4(),
        model_id=uuid4(),
        category_id=uuid4(),
        modification_id=uuid4(),
        trim_id=uuid4(),
        attribute_id=uuid4(),
        suffix=uuid4().hex,
    )
    async with _engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_marks (id, code, name, slug) "
                "VALUES (:id, :code, :name, :slug)"
            ),
            {
                "id": fixture.mark_id,
                "code": f"m-{fixture.suffix}",
                "name": fixture.suffix,
                "slug": fixture.suffix,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_models "
                "(id, code, name, slug, mark_id) "
                "VALUES (:id, :code, :name, :slug, :mark_id)"
            ),
            {
                "id": fixture.model_id,
                "code": f"model-{fixture.suffix}",
                "name": fixture.suffix,
                "slug": fixture.suffix,
                "mark_id": fixture.mark_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_categories "
                "(id, code, name, slug, usage_metric) "
                "VALUES (:id, :code, :name, :slug, 'engine_hours')"
            ),
            {
                "id": fixture.category_id,
                "code": f"category-{fixture.suffix}",
                "name": fixture.suffix,
                "slug": fixture.suffix,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_modifications "
                "(id, code, name, slug, model_id) "
                "VALUES (:id, :code, :name, :slug, :model_id)"
            ),
            {
                "id": fixture.modification_id,
                "code": f"modification-{fixture.suffix}",
                "name": fixture.suffix,
                "slug": fixture.suffix,
                "model_id": fixture.model_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_attributes "
                "(id, code, name, data_type, filter_kind) "
                "VALUES (:id, :code, :name, 'text', 'search')"
            ),
            {
                "id": fixture.attribute_id,
                "code": f"attribute-{fixture.suffix}",
                "name": fixture.suffix,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_category_attributes "
                "(category_id, attribute_id) VALUES (:category_id, :attribute_id)"
            ),
            {
                "category_id": fixture.category_id,
                "attribute_id": fixture.attribute_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_modification_categories "
                "(modification_id, category_id, is_primary) "
                "VALUES (:modification_id, :category_id, TRUE)"
            ),
            {
                "modification_id": fixture.modification_id,
                "category_id": fixture.category_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_trims "
                "(id, code, name, slug, modification_id) "
                "VALUES (:id, :code, :name, :slug, :modification_id)"
            ),
            {
                "id": fixture.trim_id,
                "code": f"trim-{fixture.suffix}",
                "name": fixture.suffix,
                "slug": fixture.suffix,
                "modification_id": fixture.modification_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_trim_attributes "
                "(trim_id, attribute_id) VALUES (:trim_id, :attribute_id)"
            ),
            {
                "trim_id": fixture.trim_id,
                "attribute_id": fixture.attribute_id,
            },
        )
    try:
        yield fixture
    finally:
        async with _engine.begin() as connection:
            for statement, values in (
                (
                    "DELETE FROM special_equipment_trim_attribute_values "
                    "WHERE trim_id = :id",
                    {"id": fixture.trim_id},
                ),
                (
                    "DELETE FROM special_equipment_modification_attribute_values "
                    "WHERE modification_id = :id",
                    {"id": fixture.modification_id},
                ),
                (
                    "DELETE FROM special_equipment_category_attributes "
                    "WHERE category_id = :category_id "
                    "AND attribute_id = :attribute_id",
                    {
                        "category_id": fixture.category_id,
                        "attribute_id": fixture.attribute_id,
                    },
                ),
                (
                    "DELETE FROM special_equipment_trims WHERE id = :id",
                    {"id": fixture.trim_id},
                ),
                (
                    "DELETE FROM special_equipment_modifications WHERE id = :id",
                    {"id": fixture.modification_id},
                ),
                (
                    "DELETE FROM special_equipment_models WHERE id = :id",
                    {"id": fixture.model_id},
                ),
                (
                    "DELETE FROM special_equipment_marks WHERE id = :id",
                    {"id": fixture.mark_id},
                ),
                (
                    "DELETE FROM special_equipment_attributes WHERE id = :id",
                    {"id": fixture.attribute_id},
                ),
                (
                    "DELETE FROM special_equipment_categories WHERE id = :id",
                    {"id": fixture.category_id},
                ),
            ):
                await connection.execute(sa.text(statement), values)


async def _preconditions(
    engine: AsyncEngine,
    fixture: _ValueFixture,
) -> tuple[str, str]:
    async with AsyncSession(engine) as session:
        modification = await repository.get_entity(
            session, "modification", fixture.modification_id
        )
        trim = await repository.get_entity(session, "trim", fixture.trim_id)
        assert modification is not None
        assert trim is not None
        items = await repository.trim_attribute_state(session, fixture.trim_id)
    return (
        special_equipment_management_etag(modification),
        special_equipment_trim_attributes_etag(
            trim_id=fixture.trim_id,
            lock_version=trim["lock_version"],
            items=items,
        ),
    )


async def _held_trim_write(
    engine: AsyncEngine,
    fixture: _ValueFixture,
    *,
    etag: str,
    ready: asyncio.Event,
    release: asyncio.Event,
) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await commands.patch_trim_attribute_values(
            session,
            trim_id=fixture.trim_id,
            values=[
                {
                    "attribute_id": fixture.attribute_id,
                    "value_text": "trim-wins-lock",
                }
            ],
            expected_version=1,
            expected_etag=etag,
        )
        ready.set()
        await release.wait()
        await session.commit()


async def _assert_single_level_value(
    engine: AsyncEngine,
    fixture: _ValueFixture,
    *,
    expected_owner: str,
) -> None:
    async with engine.connect() as connection:
        modification_count = int(
            (
                await connection.execute(
                    sa.text(
                        "SELECT count(*) FROM "
                        "special_equipment_modification_attribute_values "
                        "WHERE modification_id = :modification_id "
                        "AND attribute_id = :attribute_id"
                    ),
                    {
                        "modification_id": fixture.modification_id,
                        "attribute_id": fixture.attribute_id,
                    },
                )
            ).scalar_one()
        )
        trim_count = int(
            (
                await connection.execute(
                    sa.text(
                        "SELECT count(*) FROM special_equipment_trim_attribute_values "
                        "WHERE trim_id = :trim_id AND attribute_id = :attribute_id"
                    ),
                    {
                        "trim_id": fixture.trim_id,
                        "attribute_id": fixture.attribute_id,
                    },
                )
            ).scalar_one()
        )
    assert modification_count + trim_count == 1
    assert ("modification" if modification_count else "trim") == expected_owner


def _modification_value_plan(
    fixture: _ValueFixture,
    *,
    full_snapshot: bool,
) -> dict[str, list[dict[str, Any]]]:
    aggregate = {
        "_aggregate_kind": "modification",
        "_aggregate_code": f"modification-{fixture.suffix}",
    }
    value_row = {
        "operation": "SET",
        "values": {
            "modification_id": fixture.modification_id,
            "attribute_id": fixture.attribute_id,
            "value_text": "import-value",
            "value_number": None,
            "value_boolean": None,
            "option_id": None,
        },
        "_sheet_code": "Характеристики модификаций",
        "_row_number": 9,
        **aggregate,
    }
    if not full_snapshot:
        return {"modification_attribute_values": [value_row]}
    return {
        "marks": [
            {
                "id": fixture.mark_id,
                "code": f"m-{fixture.suffix}",
                "operation": "SET",
                "values": {
                    "name": fixture.suffix,
                    "slug": fixture.suffix,
                    "is_active": True,
                },
                "_aggregate_kind": "mark",
                "_aggregate_code": f"m-{fixture.suffix}",
            }
        ],
        "models": [
            {
                "id": fixture.model_id,
                "code": f"model-{fixture.suffix}",
                "operation": "SET",
                "values": {
                    "name": fixture.suffix,
                    "slug": fixture.suffix,
                    "mark_id": fixture.mark_id,
                    "is_active": True,
                },
                "_aggregate_kind": "model",
                "_aggregate_code": f"model-{fixture.suffix}",
            }
        ],
        "categories": [
            {
                "id": fixture.category_id,
                "code": f"category-{fixture.suffix}",
                "operation": "SET",
                "values": {
                    "name": fixture.suffix,
                    "slug": fixture.suffix,
                    "usage_metric": "engine_hours",
                    "is_active": True,
                },
                "_aggregate_kind": "category",
                "_aggregate_code": f"category-{fixture.suffix}",
            }
        ],
        "attributes": [
            {
                "id": fixture.attribute_id,
                "code": f"attribute-{fixture.suffix}",
                "operation": "SET",
                "values": {
                    "name": fixture.suffix,
                    "data_type": "text",
                    "filter_kind": "search",
                    "is_active": True,
                },
                "_aggregate_kind": "attribute",
                "_aggregate_code": f"attribute-{fixture.suffix}",
            }
        ],
        "category_attributes": [
            {
                "operation": "SET",
                "values": {
                    "category_id": fixture.category_id,
                    "attribute_id": fixture.attribute_id,
                    "group_id": None,
                    "is_required": False,
                    "is_filterable": False,
                    "is_visible": True,
                    "sort_order": 0,
                },
                "_aggregate_kind": "category",
                "_aggregate_code": f"category-{fixture.suffix}",
            }
        ],
        "modifications": [
            {
                "id": fixture.modification_id,
                "code": f"modification-{fixture.suffix}",
                "operation": "SET",
                "values": {
                    "name": fixture.suffix,
                    "slug": fixture.suffix,
                    "model_id": fixture.model_id,
                    "is_active": True,
                },
                **aggregate,
            }
        ],
        "modification_categories": [
            {
                "operation": "SET",
                "values": {
                    "modification_id": fixture.modification_id,
                    "category_id": fixture.category_id,
                    "sort_order": 0,
                    "is_primary": True,
                },
                **aggregate,
            }
        ],
        "modification_attribute_values": [value_row],
        "trims": [
            {
                "id": fixture.trim_id,
                "code": f"trim-{fixture.suffix}",
                "operation": "SET",
                "values": {
                    "name": fixture.suffix,
                    "slug": fixture.suffix,
                    "modification_id": fixture.modification_id,
                    "sort_order": 0,
                    "is_active": True,
                },
                "_aggregate_kind": "trim",
                "_aggregate_code": f"trim-{fixture.suffix}",
            }
        ],
        "trim_attributes": [
            {
                "operation": "SET",
                "values": {
                    "trim_id": fixture.trim_id,
                    "attribute_id": fixture.attribute_id,
                    "group_id": None,
                    "is_required": False,
                    "is_filterable": False,
                    "sort_order": 0,
                },
                "_aggregate_kind": "trim",
                "_aggregate_code": f"trim-{fixture.suffix}",
            }
        ],
    }


async def _assert_waiter_is_blocked(task: asyncio.Task[Any]) -> None:
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=0.1)


async def test_two_independent_trim_writers_serialize_and_reject_stale_etag(
    _engine: AsyncEngine,
) -> None:
    mark_id = uuid4()
    model_id = uuid4()
    modification_id = uuid4()
    trim_id = uuid4()
    attribute_id = uuid4()
    suffix = uuid4().hex
    async with _engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_marks (id, code, name, slug) "
                "VALUES (:id, :code, :name, :slug)"
            ),
            {"id": mark_id, "code": f"m-{suffix}", "name": suffix, "slug": suffix},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_models "
                "(id, code, name, slug, mark_id) "
                "VALUES (:id, :code, :name, :slug, :mark_id)"
            ),
            {
                "id": model_id,
                "code": f"mo-{suffix}",
                "name": suffix,
                "slug": suffix,
                "mark_id": mark_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_modifications "
                "(id, code, name, slug, model_id) "
                "VALUES (:id, :code, :name, :slug, :model_id)"
            ),
            {
                "id": modification_id,
                "code": f"mod-{suffix}",
                "name": suffix,
                "slug": suffix,
                "model_id": model_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_trims "
                "(id, code, name, slug, modification_id) "
                "VALUES (:id, :code, :name, :slug, :modification_id)"
            ),
            {
                "id": trim_id,
                "code": f"trim-{suffix}",
                "name": suffix,
                "slug": suffix,
                "modification_id": modification_id,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_attributes "
                "(id, code, name, data_type, filter_kind) "
                "VALUES (:id, :code, :name, 'text', 'search')"
            ),
            {
                "id": attribute_id,
                "code": f"attr-{suffix}",
                "name": suffix,
            },
        )
        await connection.execute(
            sa.text(
                "INSERT INTO special_equipment_trim_attributes "
                "(trim_id, attribute_id) VALUES (:trim_id, :attribute_id)"
            ),
            {"trim_id": trim_id, "attribute_id": attribute_id},
        )

    initial_items = [
        {
            "attribute_id": attribute_id,
            "group_id": None,
            "is_required": False,
            "is_filterable": False,
            "sort_order": 0,
            "value_number": None,
            "value_text": None,
            "value_boolean": None,
            "option_id": None,
        }
    ]
    etag = special_equipment_trim_attributes_etag(
        trim_id=trim_id,
        lock_version=1,
        items=initial_items,
    )

    async def delete_assignment() -> str:
        async with AsyncSession(_engine, expire_on_commit=False) as session:
            try:
                await commands.delete_trim_attribute_assignment(
                    session,
                    trim_id=trim_id,
                    attribute_id=attribute_id,
                    expected_version=1,
                    expected_etag=etag,
                )
                await session.commit()
            except SpecialEquipmentTrimContractError as exc:
                await session.rollback()
                return exc.code
        return "deleted"

    outcomes = await asyncio.gather(delete_assignment(), delete_assignment())
    assert sorted(outcomes) == ["PRECONDITION_FAILED", "deleted"]

    async with AsyncSession(_engine) as session:
        trim = await repository.get_entity(session, "trim", trim_id)
        assert trim is not None
        assert trim["lock_version"] == 2
        assert await repository.trim_attribute_state(session, trim_id) == []

    async with _engine.begin() as connection:
        await connection.execute(
            sa.text("DELETE FROM special_equipment_trims WHERE id = :id"),
            {"id": trim_id},
        )
        await connection.execute(
            sa.text("DELETE FROM special_equipment_attributes WHERE id = :id"),
            {"id": attribute_id},
        )
        await connection.execute(
            sa.text("DELETE FROM special_equipment_modifications WHERE id = :id"),
            {"id": modification_id},
        )
        await connection.execute(
            sa.text("DELETE FROM special_equipment_models WHERE id = :id"),
            {"id": model_id},
        )
        await connection.execute(
            sa.text("DELETE FROM special_equipment_marks WHERE id = :id"),
            {"id": mark_id},
        )


async def test_trim_write_serializes_before_management_modification_patch(
    _engine: AsyncEngine,
    value_fixture: _ValueFixture,
) -> None:
    modification_etag, trim_etag = await _preconditions(_engine, value_fixture)
    trim_ready = asyncio.Event()
    release_trim = asyncio.Event()
    trim_task = asyncio.create_task(
        _held_trim_write(
            _engine,
            value_fixture,
            etag=trim_etag,
            ready=trim_ready,
            release=release_trim,
        )
    )
    await trim_ready.wait()

    async def patch_modification() -> str:
        async with AsyncSession(_engine, expire_on_commit=False) as session:
            try:
                await commands.patch_entity(
                    session,
                    entity_type="modification",
                    entity_id=value_fixture.modification_id,
                    values={
                        "attribute_values": [
                            {
                                "attribute_id": value_fixture.attribute_id,
                                "value_text": "management-value",
                            }
                        ]
                    },
                    expected_version=1,
                    expected_etag=modification_etag,
                )
                await session.commit()
            except SpecialEquipmentTrimContractError as exc:
                await session.rollback()
                return exc.code
        return "management_saved"

    management_task = asyncio.create_task(patch_modification())
    await _assert_waiter_is_blocked(management_task)
    release_trim.set()
    await asyncio.wait_for(trim_task, timeout=5)
    outcome = await asyncio.wait_for(management_task, timeout=5)

    assert outcome == "ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM"
    await _assert_single_level_value(
        _engine,
        value_fixture,
        expected_owner="trim",
    )


async def test_trim_write_forces_atomic_import_conflict_after_lock_wait(
    _engine: AsyncEngine,
    value_fixture: _ValueFixture,
) -> None:
    _modification_etag, trim_etag = await _preconditions(_engine, value_fixture)
    trim_ready = asyncio.Event()
    release_trim = asyncio.Event()
    trim_task = asyncio.create_task(
        _held_trim_write(
            _engine,
            value_fixture,
            etag=trim_etag,
            ready=trim_ready,
            release=release_trim,
        )
    )
    await trim_ready.wait()

    async def apply_atomic_import() -> str:
        async with AsyncSession(_engine, expire_on_commit=False) as session:
            try:
                await import_repository.apply_normalized_plan(
                    session,
                    job_id=uuid4(),
                    mode="FULL_SNAPSHOT",
                    template_version=3,
                    plan=_modification_value_plan(
                        value_fixture,
                        full_snapshot=True,
                    ),
                )
                await session.commit()
            except ImportAggregateSemanticConflictError as exc:
                await session.rollback()
                return exc.code
        return "atomic_applied"

    import_task = asyncio.create_task(apply_atomic_import())
    await _assert_waiter_is_blocked(import_task)
    release_trim.set()
    await asyncio.wait_for(trim_task, timeout=5)
    outcome = await asyncio.wait_for(import_task, timeout=5)

    assert outcome == "ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM"
    await _assert_single_level_value(
        _engine,
        value_fixture,
        expected_owner="trim",
    )


async def test_v4_snapshot_replaces_opposing_trim_value(
    _engine: AsyncEngine,
    value_fixture: _ValueFixture,
) -> None:
    _modification_etag, trim_etag = await _preconditions(_engine, value_fixture)
    async with AsyncSession(_engine, expire_on_commit=False) as session:
        await commands.patch_trim_attribute_values(
            session,
            trim_id=value_fixture.trim_id,
            values=[
                {
                    "attribute_id": value_fixture.attribute_id,
                    "value_text": "trim-value-to-replace",
                }
            ],
            expected_version=1,
            expected_etag=trim_etag,
        )
        await session.commit()

    async with AsyncSession(_engine, expire_on_commit=False) as session:
        result = await import_repository.apply_normalized_plan(
            session,
            job_id=uuid4(),
            mode="FULL_SNAPSHOT",
            template_version=4,
            plan=_modification_value_plan(
                value_fixture,
                full_snapshot=True,
            ),
        )
        assert result["rejected_aggregates"] == []
        await session.commit()

    await _assert_single_level_value(
        _engine,
        value_fixture,
        expected_owner="modification",
    )


async def test_trim_write_becomes_best_effort_import_row_rejection(
    _engine: AsyncEngine,
    value_fixture: _ValueFixture,
) -> None:
    _modification_etag, trim_etag = await _preconditions(_engine, value_fixture)
    trim_ready = asyncio.Event()
    release_trim = asyncio.Event()
    trim_task = asyncio.create_task(
        _held_trim_write(
            _engine,
            value_fixture,
            etag=trim_etag,
            ready=trim_ready,
            release=release_trim,
        )
    )
    await trim_ready.wait()

    async def apply_best_effort_import() -> dict[str, Any]:
        async with AsyncSession(_engine, expire_on_commit=False) as session:
            result = await import_repository.apply_normalized_plan(
                session,
                job_id=uuid4(),
                mode="PATCH",
                plan=_modification_value_plan(
                    value_fixture,
                    full_snapshot=False,
                ),
            )
            await session.commit()
            return result

    import_task = asyncio.create_task(apply_best_effort_import())
    await _assert_waiter_is_blocked(import_task)
    release_trim.set()
    await asyncio.wait_for(trim_task, timeout=5)
    result = await asyncio.wait_for(import_task, timeout=5)

    assert result["rejected_aggregates"] == [
        {
            "sheet_code": "Характеристики модификаций",
            "row_number": 9,
            "column_name": None,
            "severity": "error",
            "code": "ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM",
            "message": "Характеристика уже заполнена в комплектации модификации",
            "raw_value_preview": None,
            "entity_type": "modification",
            "external_key": f"modification-{value_fixture.suffix}",
        }
    ]
    await _assert_single_level_value(
        _engine,
        value_fixture,
        expected_owner="trim",
    )
