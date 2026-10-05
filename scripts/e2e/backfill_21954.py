from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

CATEGORY_ID = "21954000-0000-5000-8000-000000000001"
MARK_ID = "21954000-0000-5000-8000-000000000002"
MODEL_ID = "21954000-0000-5000-8000-000000000003"
MODIFICATION_ID = "21954000-0000-5000-8000-000000000004"
PRODUCT_ID = "21954000-0000-5000-8000-000000000005"
USER_ID = "21954000-0000-5000-8000-000000000006"
CART_ITEM_ID = "21954000-0000-5000-8000-000000000007"
COMPANY_ID = "21954000-0000-5000-8000-000000000008"


def _database_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        raise RuntimeError("DATABASE_URL is required")
    return raw.replace("postgresql://", "postgresql+asyncpg://", 1)


def _expected_head_revision() -> str:
    repository_root = Path(__file__).resolve().parents[2]
    config = Config(str(repository_root / "backend" / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, got {heads!r}")
    return heads[0]


async def seed_legacy_rows() -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_categories
                        (id, code, name, slug, is_active, usage_metric, sort_order)
                    VALUES
                        (:id, 'E2E_21954_LEGACY', 'E2E legacy category',
                         'e2e-21954-legacy', true, 'mileage_km', 0)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": CATEGORY_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_marks (id, code, name, slug)
                    VALUES (:id, 'E2E_21954_MARK', 'E2E 21954 Mark', 'e2e-21954-mark')
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": MARK_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_models
                        (id, code, name, slug, mark_id)
                    VALUES
                        (:id, 'E2E_21954_MODEL', 'E2E 21954 Model',
                         'e2e-21954-model', :mark_id)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": MODEL_ID, "mark_id": MARK_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_modifications
                        (id, code, name, slug, model_id)
                    VALUES
                        (:id, 'E2E_21954_MODIFICATION', 'E2E 21954 Modification',
                         'e2e-21954-modification', :model_id)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": MODIFICATION_ID, "model_id": MODEL_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO companies
                        (id, name, inn, company_type, legal_address, is_active)
                    VALUES
                        (:id, 'E2E 21954 legacy seller', '219540000008',
                         'dealer', 'E2E legacy address', true)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": COMPANY_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_products
                        (id, code, modification_id, seller_company_id, slug,
                         description, price, manufacture_year, condition,
                         publication_status, sale_status, published_at, no_vin)
                    VALUES
                        (:id, 'E2E_21954_PRODUCT', :modification_id, :seller_id,
                         'e2e-21954-product', 'E2E migrated legacy product',
                         2195400, 2026, 'new', 'published', 'available', now(), true)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": PRODUCT_ID,
                    "modification_id": MODIFICATION_ID,
                    "seller_id": COMPANY_ID,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_product_categories
                        (product_id, category_id)
                    VALUES (:product_id, :category_id)
                    ON CONFLICT (product_id, category_id) DO NOTHING
                    """
                ),
                {"product_id": PRODUCT_ID, "category_id": CATEGORY_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO users
                        (id, phone, role, is_active, phone_verified, mfa_enabled)
                    VALUES (:id, '+76669999999', 'client', true, true, false)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": USER_ID},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO special_equipment_cart_items
                        (id, user_id, product_id, is_selected)
                    VALUES (:id, :user_id, :product_id, true)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": CART_ITEM_ID,
                    "user_id": USER_ID,
                    "product_id": PRODUCT_ID,
                },
            )
    finally:
        await engine.dispose()


def _write_artifact(artifact: Path, payload: dict[str, object]) -> None:
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


async def verify_backfill(artifact: Path) -> None:
    engine = create_async_engine(_database_url())
    try:
        async with engine.connect() as connection:
            revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            attachment_value = (
                await connection.execute(
                    text(
                        "SELECT is_attachment_category "
                        "FROM special_equipment_categories WHERE id = :id"
                    ),
                    {"id": CATEGORY_ID},
                )
            ).scalar_one()
            quantity = (
                await connection.execute(
                    text(
                        "SELECT quantity FROM special_equipment_cart_items "
                        "WHERE id = :id"
                    ),
                    {"id": CART_ITEM_ID},
                )
            ).scalar_one()
            public_product = (
                await connection.execute(
                    text(
                        "SELECT publication_status, sale_status "
                        "FROM special_equipment_products WHERE id = :id"
                    ),
                    {"id": PRODUCT_ID},
                )
            ).one()
            category_is_active = (
                await connection.execute(
                    text(
                        "SELECT is_active FROM special_equipment_categories "
                        "WHERE id = :id"
                    ),
                    {"id": CATEGORY_ID},
                )
            ).scalar_one()
            category_link_exists = bool(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM special_equipment_product_categories "
                            "WHERE product_id = :product_id AND category_id = :category_id"
                        ),
                        {"product_id": PRODUCT_ID, "category_id": CATEGORY_ID},
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()

    expected_revision = _expected_head_revision()
    if revision != expected_revision:
        raise RuntimeError(f"Expected Alembic revision {expected_revision}, got {revision!r}")
    if attachment_value is not False:
        raise RuntimeError("Legacy category was not backfilled to false")
    if quantity != 1:
        raise RuntimeError("Legacy cart quantity was not backfilled to 1")
    if tuple(public_product) != ("published", "available"):
        raise RuntimeError("Migrated legacy product is not publicly available")
    if category_is_active is not True or not category_link_exists:
        raise RuntimeError("Migrated legacy product lost its active category")

    await asyncio.to_thread(
        _write_artifact,
        artifact,
        {
            "revision": revision,
            "category_id": CATEGORY_ID,
            "is_attachment_category": attachment_value,
            "cart_item_id": CART_ITEM_ID,
            "quantity": quantity,
            "catalog_product_id": PRODUCT_ID,
            "catalog_product_code": "E2E_21954_PRODUCT",
            "legacy_rows_retained": True,
        },
    )


async def cleanup_legacy_rows() -> None:
    """Remove the exact disposable rows used only by the backfill smoke check."""

    engine = create_async_engine(_database_url())
    try:
        async with engine.begin() as connection:
            for statement, entity_id in (
                ("DELETE FROM special_equipment_cart_items WHERE id = :id", CART_ITEM_ID),
                (
                    "DELETE FROM special_equipment_product_categories "
                    "WHERE product_id = :id",
                    PRODUCT_ID,
                ),
                ("DELETE FROM special_equipment_products WHERE id = :id", PRODUCT_ID),
                ("DELETE FROM special_equipment_modifications WHERE id = :id", MODIFICATION_ID),
                ("DELETE FROM special_equipment_models WHERE id = :id", MODEL_ID),
                ("DELETE FROM special_equipment_marks WHERE id = :id", MARK_ID),
                ("DELETE FROM special_equipment_categories WHERE id = :id", CATEGORY_ID),
                ("DELETE FROM users WHERE id = :id", USER_ID),
                ("DELETE FROM companies WHERE id = :id", COMPANY_ID),
            ):
                await connection.execute(text(statement), {"id": entity_id})
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "verify", "cleanup"))
    parser.add_argument(
        "--artifact",
        type=Path,
        default=Path("artifacts/e2e/backfill-21954.json"),
    )
    arguments = parser.parse_args()

    if arguments.action == "seed":
        asyncio.run(seed_legacy_rows())
    elif arguments.action == "verify":
        asyncio.run(verify_backfill(arguments.artifact))
    else:
        asyncio.run(cleanup_legacy_rows())


if __name__ == "__main__":
    main()
