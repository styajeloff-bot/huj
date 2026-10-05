from __future__ import annotations

import ast
import importlib.util
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch

FASTAPI_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = FASTAPI_ROOT / "alembic" / "versions"


def _literal_revision_id(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "revision":
                    value = ast.literal_eval(node.value)
                    assert isinstance(value, str), (
                        f"{path.name}: revision must be a string"
                    )
                    return value

        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "revision":
                assert node.value is not None, f"{path.name}: revision is missing"
                value = ast.literal_eval(node.value)
                assert isinstance(value, str), (
                    f"{path.name}: revision must be a string"
                )
                return value

    raise AssertionError(f"{path.name}: revision is missing")


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_revision_ids_are_unique() -> None:
    revision_to_files: dict[str, list[str]] = {}

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue

        revision = _literal_revision_id(path)
        revision_to_files.setdefault(revision, []).append(path.name)

    duplicates = {
        revision: filenames
        for revision, filenames in revision_to_files.items()
        if len(filenames) > 1
    }

    assert duplicates == {}


def test_alembic_has_single_head() -> None:
    config = Config(str(FASTAPI_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(FASTAPI_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["136"]


def test_recent_alembic_revisions_form_linear_chain() -> None:
    config = Config(str(FASTAPI_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(FASTAPI_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    revision_ids = [
        *(f"{number:03d}" for number in range(79, 88)),
        "088_special_equipment_colors",
        *(f"{number:03d}" for number in range(89, 137)),
    ]
    revisions = [script.get_revision(revision_id) for revision_id in revision_ids]

    assert all(revision is not None for revision in revisions)
    for parent, child in pairwise(revisions):
        assert parent is not None
        assert child is not None
        assert child.down_revision == parent.revision


@pytest.mark.parametrize(
    ("tables", "has_price_schema", "expected_price_repairs", "expected_visibility_repairs"),
    [
        (
            {"workspace_role_section_visibility"},
            False,
            1,
            1,
        ),
        (
            {"workspace_role_section_visibility"},
            True,
            0,
            1,
        ),
        ({"section_visibility"}, False, 1, 0),
        ({"section_visibility"}, True, 0, 0),
    ],
)
def test_100_reconciles_every_ambiguous_099_schema_state(
    monkeypatch: MonkeyPatch,
    tables: set[str],
    has_price_schema: bool,
    expected_price_repairs: int,
    expected_visibility_repairs: int,
) -> None:
    migration = _load_migration(
        VERSIONS_DIR / "100_generalize_section_visibility.py"
    )
    state = {"has_price_schema": has_price_schema}
    price_repairs = 0
    visibility_repairs = 0

    def column_names(table_name: str) -> set[str]:
        if table_name == "special_equipment_products":
            return {"price_on_request"} if state["has_price_schema"] else set()
        if table_name == "section_visibility":
            return {"scope"}
        raise AssertionError(f"unexpected table inspection: {table_name}")

    def repair_price_schema() -> None:
        nonlocal price_repairs
        price_repairs += 1
        state["has_price_schema"] = True

    def repair_visibility_schema() -> None:
        nonlocal visibility_repairs
        visibility_repairs += 1

    monkeypatch.setattr(migration, "_table_names", lambda: tables)
    monkeypatch.setattr(migration, "_column_names", column_names)
    monkeypatch.setattr(
        migration.runpy,
        "run_path",
        lambda _path: {"upgrade": repair_price_schema},
    )
    monkeypatch.setattr(
        migration,
        "_upgrade_visibility_schema",
        repair_visibility_schema,
    )

    migration.upgrade()

    assert price_repairs == expected_price_repairs
    assert visibility_repairs == expected_visibility_repairs


def test_095_adds_independent_catalog_visibility_defaults() -> None:
    migration = (
        VERSIONS_DIR
        / "095_application_vehicle_catalog_price_visibility.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "095"' in migration
    assert 'down_revision: str | None = "094"' in migration
    assert '"discount_show_catalog_price"' in migration
    assert '"markup_show_catalog_price"' in migration
    assert migration.count("nullable=False") == 2
    assert migration.count("server_default=sa.true()") == 2
    assert migration.count(
        'op.drop_column(\n        "application_vehicles",'
    ) == 2


def test_clickhouse_alembic_has_single_head() -> None:
    config = Config(str(FASTAPI_ROOT / "alembic_clickhouse.ini"))
    config.set_main_option(
        "script_location",
        str(FASTAPI_ROOT / "alembic_clickhouse"),
    )
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["007"]


def test_098_confirms_only_active_vehicles_with_complete_saved_discount(
    monkeypatch: MonkeyPatch,
) -> None:
    migration = _load_migration(
        VERSIONS_DIR / "098_confirm_discounted_application_vehicles.py"
    )
    metadata = sa.MetaData()
    application_vehicles = sa.Table(
        "application_vehicles",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("car_status", sa.String(length=50), nullable=False),
        sa.Column("discount_type", sa.String(length=50), nullable=True),
        sa.Column("discount_value", sa.Numeric(15, 2), nullable=True),
    )
    engine = sa.create_engine("sqlite://")
    vehicle_ids = [uuid4() for _ in range(5)]

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            application_vehicles.insert(),
            [
                {
                    "id": vehicle_ids[0],
                    "car_status": "active",
                    "discount_type": "rubles_off",
                    "discount_value": 100,
                },
                {
                    "id": vehicle_ids[1],
                    "car_status": "active",
                    "discount_type": "rubles_off",
                    "discount_value": None,
                },
                {
                    "id": vehicle_ids[2],
                    "car_status": "active",
                    "discount_type": None,
                    "discount_value": 100,
                },
                {
                    "id": vehicle_ids[3],
                    "car_status": "not_confirmed",
                    "discount_type": "rubles_off",
                    "discount_value": 100,
                },
                {
                    "id": vehicle_ids[4],
                    "car_status": "replacement",
                    "discount_type": "rubles_off",
                    "discount_value": 100,
                },
            ],
        )
        monkeypatch.setattr(migration.op, "execute", connection.execute)

        migration.upgrade()

        rows: dict[UUID, str] = {
            row[0]: row[1]
            for row in connection.execute(
                sa.select(application_vehicles.c.id, application_vehicles.c.car_status)
            )
        }

    assert rows == {
        vehicle_ids[0]: "confirmed",
        vehicle_ids[1]: "active",
        vehicle_ids[2]: "active",
        vehicle_ids[3]: "not_confirmed",
        vehicle_ids[4]: "replacement",
    }
