"""Database trigger and migration tests for se_product_warehouse_prepare and warehouses.is_active."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.special_equipment_management_repository import (
    product_warehouse_integrity_error_code,
)

pytestmark = pytest.mark.asyncio

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "131_update_se_product_warehouse_trigger.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_131_under_test", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def test_migration_131_upgrade_and_downgrade(db_session: AsyncSession) -> None:
    migration = _load_migration()
    migration_any = cast("Any", migration)
    original_op = migration_any.op

    connection = await db_session.connection()

    def run_migrations(sync_conn: sa.Connection) -> None:
        context = MigrationContext.configure(sync_conn)
        op = Operations(context)
        migration_any.op = op
        try:
            # Upgrade installs updated trigger function
            migration.upgrade()
            # Downgrade reinstates legacy trigger function
            migration.downgrade()
            # Upgrade again to leave DB in updated state
            migration.upgrade()
        finally:
            migration_any.op = original_op

    await connection.run_sync(run_migrations)


async def test_se_product_warehouse_trigger_lifecycle(db_session: AsyncSession) -> None:
    migration = _load_migration()
    migration_any = cast("Any", migration)
    original_op = migration_any.op

    connection = await db_session.connection()

    def setup_trigger(sync_conn: sa.Connection) -> None:
        context = MigrationContext.configure(sync_conn)
        op = Operations(context)
        migration_any.op = op
        try:
            migration.upgrade()
        finally:
            migration_any.op = original_op

        sync_conn.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_se_product_warehouse_prepare "
                "ON special_equipment_products;"
            )
        )
        sync_conn.execute(
            sa.text(
                """
                CREATE TRIGGER trg_se_product_warehouse_prepare
                BEFORE INSERT OR UPDATE OF no_vin, warehouse_id
                ON special_equipment_products
                FOR EACH ROW EXECUTE FUNCTION se_product_warehouse_prepare();
                """
            )
        )

    await connection.run_sync(setup_trigger)

    # Setup company, mark, model, modification
    company_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO companies (id, name, inn, kpp, ogrn, legal_address, is_active, company_type)
            VALUES (:cid, 'Test Company', '7700000000', '770001001', '1027700000000', 'Moscow', true, 'dealer')
            """
        ),
        {"cid": company_id},
    )

    prefix = uuid4().hex[:8]
    mark_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_marks (id, code, name, slug, is_active)
            VALUES (:mid, :code, 'Test Mark', :code, true)
            """
        ),
        {"mid": mark_id, "code": f"mark-{prefix}"},
    )

    model_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_models (id, mark_id, code, name, slug, is_active)
            VALUES (:mod_id, :mid, :code, 'Test Model', :code, true)
            """
        ),
        {"mod_id": model_id, "mid": mark_id, "code": f"model-{prefix}"},
    )

    modification_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_modifications (id, model_id, code, name, slug, is_active)
            VALUES (:moid, :mod_id, :code, 'Test Mod', :code, true)
            """
        ),
        {"moid": modification_id, "mod_id": model_id, "code": f"mod-{prefix}"},
    )

    active_warehouse_id = uuid4()
    inactive_warehouse_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO warehouses (id, name, owner_company_id, owner_company_type, address, is_active)
            VALUES (:aid, 'Active WH', :cid, 'dealer', 'Address 1', true),
                   (:iid, 'Inactive WH', :cid, 'dealer', 'Address 2', false)
            """
        ),
        {
            "aid": active_warehouse_id,
            "iid": inactive_warehouse_id,
            "cid": company_id,
        },
    )

    # 1. Product with active warehouse succeeds
    prod_active_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_products (
                id, modification_id, code, slug, condition, manufacture_year,
                currency_code, publication_status, sale_status, no_vin, vin, warehouse_id
            ) VALUES (
                :pid, :moid, :code, :code, 'new', 2025,
                'RUB', 'draft', 'available', false, 'TESTVIN0000000001', :wh
            )
            """
        ),
        {
            "pid": prod_active_id,
            "moid": modification_id,
            "code": f"prod-act-{prefix}",
            "wh": active_warehouse_id,
        },
    )

    # 2. Product with inactive warehouse raises trg_se_product_warehouse_active
    prod_inactive_id = uuid4()
    with pytest.raises(IntegrityError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                sa.text(
                    """
                    INSERT INTO special_equipment_products (
                        id, modification_id, code, slug, condition, manufacture_year,
                        currency_code, publication_status, sale_status, no_vin, vin, warehouse_id
                    ) VALUES (
                        :pid, :moid, :code, :code, 'new', 2025,
                        'RUB', 'draft', 'available', false, 'TESTVIN0000000002', :wh
                    )
                    """
                ),
                {
                    "pid": prod_inactive_id,
                    "moid": modification_id,
                    "code": f"prod-inact-{prefix}",
                    "wh": inactive_warehouse_id,
                },
            )
    assert product_warehouse_integrity_error_code(exc_info.value) == "WAREHOUSE_INACTIVE"

    # 3. Product with no_vin=True and warehouse raises trg_se_product_warehouse_no_vin
    prod_no_vin_id = uuid4()
    with pytest.raises(IntegrityError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                sa.text(
                    """
                    INSERT INTO special_equipment_products (
                        id, modification_id, code, slug, condition, manufacture_year,
                        currency_code, publication_status, sale_status, no_vin, vin, warehouse_id
                    ) VALUES (
                        :pid, :moid, :code, :code, 'new', 2025,
                        'RUB', 'draft', 'available', true, null, :wh
                    )
                    """
                ),
                {
                    "pid": prod_no_vin_id,
                    "moid": modification_id,
                    "code": f"prod-novin-{prefix}",
                    "wh": active_warehouse_id,
                },
            )
    assert product_warehouse_integrity_error_code(exc_info.value) == "WAREHOUSE_NOT_ALLOWED"

    # 4. Product with non-existent warehouse raises fk_se_products_warehouse
    prod_nonexistent_id = uuid4()
    with pytest.raises(IntegrityError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                sa.text(
                    """
                    INSERT INTO special_equipment_products (
                        id, modification_id, code, slug, condition, manufacture_year,
                        currency_code, publication_status, sale_status, no_vin, vin, warehouse_id
                    ) VALUES (
                        :pid, :moid, :code, :code, 'new', 2025,
                        'RUB', 'draft', 'available', false, 'TESTVIN0000000004', :wh
                    )
                    """
                ),
                {
                    "pid": prod_nonexistent_id,
                    "moid": modification_id,
                    "code": f"prod-nonex-{prefix}",
                    "wh": uuid4(),
                },
            )
    assert product_warehouse_integrity_error_code(exc_info.value) == "WAREHOUSE_NOT_FOUND"


async def _setup_scenario_entities(db_session: AsyncSession) -> dict[str, Any]:
    migration = _load_migration()
    migration_any = cast("Any", migration)
    original_op = migration_any.op

    connection = await db_session.connection()

    def setup_trigger(sync_conn: sa.Connection) -> None:
        context = MigrationContext.configure(sync_conn)
        op = Operations(context)
        migration_any.op = op
        try:
            migration.upgrade()
        finally:
            migration_any.op = original_op

        sync_conn.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_se_product_warehouse_prepare "
                "ON special_equipment_products;"
            )
        )
        sync_conn.execute(
            sa.text(
                """
                CREATE TRIGGER trg_se_product_warehouse_prepare
                BEFORE INSERT OR UPDATE OF no_vin, warehouse_id
                ON special_equipment_products
                FOR EACH ROW EXECUTE FUNCTION se_product_warehouse_prepare();
                """
            )
        )

    await connection.run_sync(setup_trigger)

    company_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO companies (id, name, inn, kpp, ogrn, legal_address, is_active, company_type)
            VALUES (:cid, 'Dealer Co', '7700000001', '770001001', '1027700000001', 'Moscow', true, 'dealer')
            """
        ),
        {"cid": company_id},
    )

    prefix = uuid4().hex[:8]
    mark_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_marks (id, code, name, slug, is_active)
            VALUES (:mid, :code, 'Test Mark', :code, true)
            """
        ),
        {"mid": mark_id, "code": f"mark-{prefix}"},
    )

    model_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_models (id, mark_id, code, name, slug, is_active)
            VALUES (:mod_id, :mid, :code, 'Test Model', :code, true)
            """
        ),
        {"mod_id": model_id, "mid": mark_id, "code": f"model-{prefix}"},
    )

    category_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_categories (id, code, name, slug, usage_metric, sort_order, is_active)
            VALUES (:cat_id, :code, 'Cat', :code, 'engine_hours', 0, true)
            """
        ),
        {"cat_id": category_id, "code": f"cat-{prefix}"},
    )

    modification_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_modifications (id, model_id, code, name, slug, is_active)
            VALUES (:moid, :mod_id, :code, 'Test Mod', :code, true)
            """
        ),
        {"moid": modification_id, "mod_id": model_id, "code": f"mod-{prefix}"},
    )

    await db_session.execute(
        sa.text(
            """
            INSERT INTO special_equipment_modification_categories (modification_id, category_id)
            VALUES (:moid, :cat_id)
            """
        ),
        {"moid": modification_id, "cat_id": category_id},
    )

    active_wh_id = uuid4()
    inactive_wh_id = uuid4()
    await db_session.execute(
        sa.text(
            """
            INSERT INTO warehouses (id, name, owner_company_id, owner_company_type, address, is_active)
            VALUES (:aid, 'Active WH', :cid, 'dealer', 'Address Active', true),
                   (:iid, 'Inactive WH', :cid, 'dealer', 'Address Inactive', false)
            """
        ),
        {
            "aid": active_wh_id,
            "iid": inactive_wh_id,
            "cid": company_id,
        },
    )
    await db_session.flush()

    return {
        "company_id": company_id,
        "modification_id": modification_id,
        "category_id": category_id,
        "active_wh_id": active_wh_id,
        "inactive_wh_id": inactive_wh_id,
        "prefix": prefix,
    }


async def test_admin_create_product_with_active_warehouse_succeeds(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    data = await _setup_scenario_entities(db_session)
    prefix = data["prefix"]

    response = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={
            "Authorization": f"Bearer {employee_token}",
            "Idempotency-Key": f"key-{prefix}-active",
        },
        json={
            "code": f"2_0T_AT_FWD_{prefix}",
            "modification_id": str(data["modification_id"]),
            "warehouse_id": str(data["active_wh_id"]),
            "seller_company_id": str(data["company_id"]),
            "category_ids": [str(data["category_id"])],
            "condition": "new",
            "currency_code": "RUB",
            "manufacture_year": 2025,
            "no_vin": False,
            "vin": f"VIN{prefix.upper()}0001",
            "price": "3453000",
            "special_price": "2403000",
            "publication_status": "draft",
            "sale_status": "available",
        },
    )
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["warehouse_id"] == str(data["active_wh_id"])


async def test_admin_create_product_with_inactive_warehouse_rejected(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    data = await _setup_scenario_entities(db_session)
    prefix = data["prefix"]

    response = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={
            "Authorization": f"Bearer {employee_token}",
            "Idempotency-Key": f"key-{prefix}-inactive",
        },
        json={
            "code": f"2_0T_AT_FWD_{prefix}_inact",
            "modification_id": str(data["modification_id"]),
            "warehouse_id": str(data["inactive_wh_id"]),
            "seller_company_id": str(data["company_id"]),
            "category_ids": [str(data["category_id"])],
            "condition": "new",
            "currency_code": "RUB",
            "manufacture_year": 2025,
            "no_vin": False,
            "vin": f"VIN{prefix.upper()}0002",
            "price": "3453000",
            "publication_status": "draft",
            "sale_status": "available",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "WAREHOUSE_INACTIVE"


async def test_admin_create_product_with_no_vin_and_warehouse_rejected(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    data = await _setup_scenario_entities(db_session)
    prefix = data["prefix"]

    response = await client.post(
        "/api/v1/admin/special-equipment/products",
        headers={
            "Authorization": f"Bearer {employee_token}",
            "Idempotency-Key": f"key-{prefix}-novin",
        },
        json={
            "code": f"2_0T_AT_FWD_{prefix}_novin",
            "modification_id": str(data["modification_id"]),
            "warehouse_id": str(data["active_wh_id"]),
            "seller_company_id": str(data["company_id"]),
            "category_ids": [str(data["category_id"])],
            "condition": "new",
            "currency_code": "RUB",
            "manufacture_year": 2025,
            "no_vin": True,
            "vin": None,
            "price": "3453000",
            "publication_status": "draft",
            "sale_status": "available",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "WAREHOUSE_NOT_ALLOWED"
