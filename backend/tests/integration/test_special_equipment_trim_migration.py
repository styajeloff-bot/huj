"""Real PostgreSQL upgrade/downgrade coverage for trim migration 097."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("filled", [False, True])
async def test_trim_097_round_trip_preserves_existing_state(  # noqa: PLR0915
    db_session: AsyncSession,
    filled: bool,
) -> None:
    schema = f"trim_096_{uuid4().hex}"
    connection = await db_session.connection()

    def exercise(sync_connection: sa.Connection) -> None:  # noqa: PLR0915
        migration_path = (
            Path(__file__).parents[2]
            / "alembic"
            / "versions"
            / "097_special_equipment_trim_contract.py"
        )
        spec = importlib.util.spec_from_file_location(
            "trim_migration_097_under_test", migration_path
        )
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration_any = cast("Any", migration)
        original_op = migration_any.op
        quoted_schema = sync_connection.dialect.identifier_preparer.quote_schema(schema)
        try:
            sync_connection.exec_driver_sql(f"CREATE SCHEMA {quoted_schema}")
            sync_connection.exec_driver_sql(f"SET search_path TO {quoted_schema}")
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_attribute_groups "
                "(id uuid PRIMARY KEY)"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_attributes "
                "(id uuid PRIMARY KEY)"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_attribute_options ("
                "id uuid NOT NULL, attribute_id uuid NOT NULL, "
                "PRIMARY KEY (id), UNIQUE (attribute_id, id))"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_modifications "
                "(id uuid PRIMARY KEY)"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_catalog_mutation_receipts ("
                "id uuid PRIMARY KEY, resource_type varchar(32) NOT NULL, "
                "CONSTRAINT ck_se_catalog_mutation_receipts_resource_type CHECK ("
                "resource_type IN ('category', 'mark', 'model', 'modification', "
                "'attribute_group', 'attribute', 'attribute_option', 'product', "
                "'color')))"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_trims ("
                "id uuid PRIMARY KEY, modification_id uuid NOT NULL, "
                "lock_version bigint NOT NULL DEFAULT 1, "
                "sort_order integer NOT NULL DEFAULT 0, "
                "CONSTRAINT ck_se_trims_lock_version CHECK (lock_version >= 1), "
                "CONSTRAINT ck_se_trims_sort_order CHECK (sort_order >= 0), "
                "CONSTRAINT fk_se_trims_modification FOREIGN KEY (modification_id) "
                "REFERENCES special_equipment_modifications(id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT, "
                "CONSTRAINT uq_se_trims_id_modification "
                "UNIQUE (id, modification_id))"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_trim_attributes ("
                "trim_id uuid NOT NULL, attribute_id uuid NOT NULL, group_id uuid, "
                "sort_order integer NOT NULL DEFAULT 0, "
                "PRIMARY KEY (trim_id, attribute_id), "
                "CONSTRAINT ck_se_trim_attributes_sort_order "
                "CHECK (sort_order >= 0), "
                "CONSTRAINT fk_se_trim_attributes_trim FOREIGN KEY (trim_id) "
                "REFERENCES special_equipment_trims(id) "
                "ON UPDATE CASCADE ON DELETE CASCADE, "
                "CONSTRAINT fk_se_trim_attributes_attribute FOREIGN KEY (attribute_id) "
                "REFERENCES special_equipment_attributes(id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT, "
                "CONSTRAINT fk_se_trim_attributes_group FOREIGN KEY (group_id) "
                "REFERENCES special_equipment_attribute_groups(id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT)"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_trim_attribute_values ("
                "trim_id uuid NOT NULL, attribute_id uuid NOT NULL, option_id uuid, "
                "value_number numeric(20, 4), value_text text, value_boolean boolean, "
                "PRIMARY KEY (trim_id, attribute_id), "
                "CONSTRAINT ck_se_trim_attribute_values_one_value CHECK ("
                "num_nonnulls(value_number, value_text, value_boolean, option_id) = 1), "
                "CONSTRAINT ck_se_trim_attribute_values_text_size CHECK ("
                "value_text IS NULL OR octet_length(value_text) <= 2000), "
                "CONSTRAINT fk_se_trim_attribute_values_assignment "
                "FOREIGN KEY (trim_id, attribute_id) REFERENCES "
                "special_equipment_trim_attributes(trim_id, attribute_id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT, "
                "CONSTRAINT fk_se_trim_attribute_values_option_attribute "
                "FOREIGN KEY (attribute_id, option_id) REFERENCES "
                "special_equipment_attribute_options(attribute_id, id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT)"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_modification_attribute_values ("
                "modification_id uuid NOT NULL, attribute_id uuid NOT NULL, "
                "value_number numeric(20, 4), value_text text, "
                "value_boolean boolean, option_id uuid, "
                "PRIMARY KEY (modification_id, attribute_id))"
            )
            sync_connection.exec_driver_sql(
                "CREATE TABLE special_equipment_products ("
                "id uuid PRIMARY KEY, modification_id uuid NOT NULL, trim_id uuid, "
                "CONSTRAINT fk_se_products_trim FOREIGN KEY (trim_id) "
                "REFERENCES special_equipment_trims(id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT, "
                "CONSTRAINT fk_se_products_trim_modification "
                "FOREIGN KEY (trim_id, modification_id) "
                "REFERENCES special_equipment_trims(id, modification_id) "
                "ON UPDATE CASCADE ON DELETE RESTRICT)"
            )
            if filled:
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_attribute_groups VALUES "
                    "('10000000-0000-0000-0000-000000000001')"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_attributes VALUES "
                    "('10000000-0000-0000-0000-000000000004'), "
                    "('10000000-0000-0000-0000-000000000006')"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_modifications VALUES "
                    "('10000000-0000-0000-0000-000000000003')"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_trims "
                    "(id, modification_id) VALUES ("
                    "'10000000-0000-0000-0000-000000000002', "
                    "'10000000-0000-0000-0000-000000000003')"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_trim_attributes "
                    "(trim_id, attribute_id, group_id) VALUES ("
                    "'10000000-0000-0000-0000-000000000002', "
                    "'10000000-0000-0000-0000-000000000004', "
                    "'10000000-0000-0000-0000-000000000001')"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_trim_attribute_values "
                    "(trim_id, attribute_id, value_number) VALUES ("
                    "'10000000-0000-0000-0000-000000000002', "
                    "'10000000-0000-0000-0000-000000000004', 275)"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_products VALUES ("
                    "'10000000-0000-0000-0000-000000000005', "
                    "'10000000-0000-0000-0000-000000000003', "
                    "'10000000-0000-0000-0000-000000000002')"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_modification_attribute_values "
                    "(modification_id, attribute_id, value_number) VALUES ("
                    "'10000000-0000-0000-0000-000000000003', "
                    "'10000000-0000-0000-0000-000000000006', 420)"
                )
                sync_connection.exec_driver_sql(
                    "INSERT INTO special_equipment_products VALUES ("
                    "'10000000-0000-0000-0000-000000000007', "
                    "'10000000-0000-0000-0000-000000000003', NULL)"
                )

            migration_any.op = Operations(
                MigrationContext.configure(sync_connection)
            )
            migration.upgrade()
            constraints = {
                row[0]: bytes(row[1]).decode()
                for row in sync_connection.exec_driver_sql(
                    "SELECT c.conname, c.confdeltype FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE n.nspname = current_schema() AND c.contype = 'f' "
                    "AND c.conname LIKE 'fk_se_%'"
                )
            }
            assert constraints == {
                "fk_se_trims_modification": "r",
                "fk_se_trim_attributes_trim": "c",
                "fk_se_trim_attributes_attribute": "r",
                "fk_se_trim_attributes_group": "n",
                "fk_se_trim_attribute_values_assignment": "r",
                "fk_se_trim_attribute_values_option_attribute": "r",
                "fk_se_products_trim_modification": "r",
            }
            checks = {
                row[0]
                for row in sync_connection.exec_driver_sql(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE n.nspname = current_schema() AND c.contype = 'c' "
                    "AND c.conname LIKE 'ck_se_trim%'"
                )
            }
            assert checks == {
                "ck_se_trims_lock_version",
                "ck_se_trims_sort_order",
                "ck_se_trim_attributes_sort_order",
                "ck_se_trim_attribute_values_one_value",
                "ck_se_trim_attribute_values_text_size",
            }
            receipt_check = sync_connection.exec_driver_sql(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = current_schema() "
                "AND c.conname = 'ck_se_catalog_mutation_receipts_resource_type'"
            ).scalar_one()
            assert "'trim'::character varying" in receipt_check
            sync_connection.exec_driver_sql(
                "INSERT INTO special_equipment_catalog_mutation_receipts "
                "(id, resource_type) VALUES "
                "('10000000-0000-0000-0000-000000000008', 'trim'), "
                "('10000000-0000-0000-0000-000000000009', 'mark')"
            )
            if filled:
                sync_connection.exec_driver_sql(
                    "DELETE FROM special_equipment_attribute_groups"
                )
                assert sync_connection.exec_driver_sql(
                    "SELECT group_id IS NULL FROM special_equipment_trim_attributes"
                ).scalar_one()
                assert sync_connection.exec_driver_sql(
                    "SELECT count(*) FROM special_equipment_products"
                ).scalar_one() == 2
                assert sync_connection.exec_driver_sql(
                    "SELECT count(*) FROM special_equipment_products "
                    "WHERE trim_id IS NULL"
                ).scalar_one() == 1
                assert sync_connection.exec_driver_sql(
                    "SELECT value_number FROM "
                    "special_equipment_modification_attribute_values"
                ).scalar_one() == 420

            migration.downgrade()
            constraints = {
                row[0]: bytes(row[1]).decode()
                for row in sync_connection.exec_driver_sql(
                    "SELECT c.conname, c.confdeltype FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE n.nspname = current_schema() AND c.contype = 'f' "
                    "AND c.conname LIKE 'fk_se_%'"
                )
            }
            assert constraints == {
                "fk_se_trims_modification": "r",
                "fk_se_trim_attributes_trim": "c",
                "fk_se_trim_attributes_attribute": "r",
                "fk_se_trim_attributes_group": "r",
                "fk_se_trim_attribute_values_assignment": "r",
                "fk_se_trim_attribute_values_option_attribute": "r",
                "fk_se_products_trim": "r",
                "fk_se_products_trim_modification": "r",
            }
            receipt_check = sync_connection.exec_driver_sql(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = current_schema() "
                "AND c.conname = 'ck_se_catalog_mutation_receipts_resource_type'"
            ).scalar_one()
            assert "'trim'::character varying" not in receipt_check
            assert sync_connection.exec_driver_sql(
                "SELECT resource_type FROM "
                "special_equipment_catalog_mutation_receipts ORDER BY resource_type"
            ).scalars().all() == ["mark"]
            if filled:
                assert sync_connection.exec_driver_sql(
                    "SELECT count(*) FROM special_equipment_trim_attributes"
                ).scalar_one() == 1
                assert sync_connection.exec_driver_sql(
                    "SELECT count(*) FROM special_equipment_products"
                ).scalar_one() == 2
                assert sync_connection.exec_driver_sql(
                    "SELECT count(*) FROM special_equipment_products "
                    "WHERE trim_id IS NULL"
                ).scalar_one() == 1
                assert sync_connection.exec_driver_sql(
                    "SELECT value_number FROM "
                    "special_equipment_modification_attribute_values"
                ).scalar_one() == 420
        finally:
            migration_any.op = original_op
            sync_connection.exec_driver_sql("SET search_path TO public")
            sync_connection.exec_driver_sql(f"DROP SCHEMA {quoted_schema} CASCADE")

    await connection.run_sync(exercise)
