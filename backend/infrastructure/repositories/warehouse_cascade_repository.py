"""Warehouse cascade delete repository — plan computation and deletion execution."""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    WarehouseCascadeConfirmationInvalidError,
    WarehouseCascadeDeleteBlockedError,
    WarehouseCascadePreviewStaleError,
    WarehouseNotFoundError,
)
from infrastructure.models import Base
from infrastructure.models.companies import Company, DistributorBrand
from infrastructure.models.exchange import (
    ExchangeCartItem,
    ExchangeCartItemWarehouse,
    ExchangeRequestWarehouse,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentCatalogDeletionLog,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
    SpecialEquipmentProductCategory,
    SpecialEquipmentProductImage,
    SpecialEquipmentTrim,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentCartItem,
    SpecialEquipmentFavorite,
)
from infrastructure.models.special_equipment_import import SpecialEquipmentImportJob
from infrastructure.models.storefronts import StorefrontWarehouse
from infrastructure.models.support import SupportProgramMark
from infrastructure.models.users import UserFavorite
from infrastructure.models.vehicles import (
    VehicleWarehouseTransfer,
    Warehouse,
    WarehouseAccessRule,
    WarehouseMark,
)
from infrastructure.repositories import (
    special_equipment_cascade_delete_repository as cascade_repo,
)
from infrastructure.repository_timing import timed_repository


async def _load_other_mark_references(
    session: AsyncSession, mark_ids: set[UUID]
) -> set[UUID]:
    """Keep marks referenced outside the warehouse/catalogue being pruned."""
    referenced: set[UUID] = set()
    handled_tables = {"special_equipment_models", "warehouse_marks", "warehouse_access_rules"}
    for table in Base.metadata.tables.values():
        if table.name in handled_tables:
            continue
        for foreign_key in table.foreign_keys:
            if foreign_key.target_fullname == "special_equipment_marks.id":
                column = foreign_key.parent
                referenced.update(
                    (await session.execute(select(column).where(column.in_(mark_ids)))).scalars().all()
                )
    return referenced


@timed_repository
async def get_warehouse_cascade_preview(  # noqa: PLR0912, PLR0915
    session: AsyncSession, warehouse_id: UUID
) -> dict[str, Any]:
    """Calculate cascade delete plan, blockers, retained items, and preview token."""
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise WarehouseNotFoundError(warehouse_id)

    owner_company_name: str | None = None
    if warehouse.owner_company_id is not None:
        company = await session.get(Company, warehouse.owner_company_id)
        if company is not None:
            owner_company_name = company.name

    warehouse_info = {
        "id": warehouse.id,
        "name": warehouse.name,
        "address": warehouse.address,
        "owner_company_id": warehouse.owner_company_id,
        "owner_company_name": owner_company_name,
        "owner_company_type": warehouse.owner_company_type,
    }

    # Initial candidate products on this warehouse
    prod_stmt = select(
        SpecialEquipmentProduct.id,
        SpecialEquipmentProduct.model_id,
        SpecialEquipmentProduct.modification_id,
        SpecialEquipmentProduct.trim_id,
    ).where(SpecialEquipmentProduct.warehouse_id == warehouse_id)
    products_rows = (await session.execute(prod_stmt)).all()
    product_ids = {r[0] for r in products_rows}

    # Check active import jobs
    active_imports_stmt = select(func.count(SpecialEquipmentImportJob.id)).where(
        SpecialEquipmentImportJob.target_warehouse_id == warehouse_id,
        SpecialEquipmentImportJob.status.not_in(
            ["completed", "completed_with_warnings", "failed", "cancelled", "validation_failed"]
        ),
    )
    active_imports = int((await session.scalar(active_imports_stmt)) or 0)

    # Check blockers
    blockers: list[dict[str, Any]] = []
    if active_imports > 0:
        blockers.append({
            "type": "import",
            "title": "Активный импорт",
            "detail": f"Для склада выполняется {active_imports} процесс(ов) импорта",
            "count": active_imports,
        })

    if product_ids:
        product_blockers = await cascade_repo.load_product_blockers(
            session, product_ids, lock=False
        )
        blockers.extend(
            {
                "type": "product_document",
                "title": "Связанные документы",
                "detail": f"Объявление {pb.product.id} связано с активными документами ({len(pb.documents)} шт.)",
                "count": len(pb.documents),
            }
            for pb in product_blockers
        )

        kit_blockers = await cascade_repo.load_kit_source_blockers(
            session, product_ids, lock=False
        )
        blockers.extend(
            {
                "type": "kit_source",
                "title": "Шасси в комплекте",
                "detail": f"Объявление {kb.product.id} используется как компонент комплекта",
                "count": len(kb.kits),
            }
            for kb in kit_blockers
        )

    can_delete = (len(blockers) == 0)

    # Candidates for catalog dictionary deletion
    candidate_mod_ids = {r[2] for r in products_rows if r[2] is not None}
    candidate_model_ids = {r[1] for r in products_rows if r[1] is not None}
    candidate_trim_ids = {r[3] for r in products_rows if r[3] is not None}

    if candidate_mod_ids:
        mod_model_rows = (
            await session.execute(
                select(SpecialEquipmentModification.model_id).where(
                    SpecialEquipmentModification.id.in_(candidate_mod_ids)
                )
            )
        ).scalars().all()
        candidate_model_ids.update(m for m in mod_model_rows if m is not None)

    candidate_mark_ids = set((await session.execute(
        select(WarehouseMark.mark_id).where(WarehouseMark.warehouse_id == warehouse_id)
    )).scalars().all())
    if candidate_model_ids:
        model_mark_rows = (
            await session.execute(
                select(SpecialEquipmentModel.mark_id).where(
                    SpecialEquipmentModel.id.in_(candidate_model_ids)
                )
            )
        ).scalars().all()
        candidate_mark_ids.update(m for m in model_mark_rows if m is not None)

    # Evaluate survival vs deletion (§5.2 of spec)
    # Trims
    surviving_trim_ids: set[UUID] = set()
    if candidate_trim_ids:
        surviving_trim_ids = {
            x
            for x in (
                await session.execute(
                    select(SpecialEquipmentProduct.trim_id).where(
                        SpecialEquipmentProduct.warehouse_id != warehouse_id,
                        SpecialEquipmentProduct.trim_id.in_(candidate_trim_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }
    deleted_trim_ids = candidate_trim_ids - surviving_trim_ids

    # Modifications
    surviving_mod_ids: set[UUID] = set()
    if candidate_mod_ids:
        surviving_mod_ids = {
            x
            for x in (
                await session.execute(
                    select(SpecialEquipmentProduct.modification_id).where(
                        SpecialEquipmentProduct.warehouse_id != warehouse_id,
                        SpecialEquipmentProduct.modification_id.in_(candidate_mod_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }
    deleted_mod_ids = candidate_mod_ids - surviving_mod_ids

    # Models
    surviving_model_ids: set[UUID] = set()
    if candidate_model_ids:
        used_by_products = {
            x
            for x in (
                await session.execute(
                    select(SpecialEquipmentProduct.model_id).where(
                        SpecialEquipmentProduct.warehouse_id != warehouse_id,
                        SpecialEquipmentProduct.model_id.in_(candidate_model_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }
        mods_query = select(SpecialEquipmentModification.model_id).where(
            SpecialEquipmentModification.model_id.in_(candidate_model_ids)
        )
        if deleted_mod_ids:
            mods_query = mods_query.where(
                SpecialEquipmentModification.id.not_in(deleted_mod_ids)
            )
        used_by_mods = {
            x
            for x in (await session.execute(mods_query)).scalars().all()
            if x is not None
        }
        surviving_model_ids = (used_by_products | used_by_mods) & candidate_model_ids
    deleted_model_ids = candidate_model_ids - surviving_model_ids

    # Marks
    surviving_mark_ids: set[UUID] = set()
    if candidate_mark_ids:
        models_query = select(SpecialEquipmentModel.mark_id).where(
            SpecialEquipmentModel.mark_id.in_(candidate_mark_ids)
        )
        if deleted_model_ids:
            models_query = models_query.where(
                SpecialEquipmentModel.id.not_in(deleted_model_ids)
            )
        used_by_models = {
            x
            for x in (await session.execute(models_query)).scalars().all()
            if x is not None
        }

        used_by_dist = {
            x
            for x in (
                await session.execute(
                    select(DistributorBrand.brand_id).where(
                        DistributorBrand.brand_id.in_(candidate_mark_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }

        used_by_sp = {
            x
            for x in (
                await session.execute(
                    select(SupportProgramMark.mark_id).where(
                        SupportProgramMark.mark_id.in_(candidate_mark_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }

        used_by_wh = {
            x
            for x in (
                await session.execute(
                    select(WarehouseMark.mark_id).where(
                        WarehouseMark.warehouse_id != warehouse_id,
                        WarehouseMark.mark_id.in_(candidate_mark_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }

        used_by_rules = {
            x
            for x in (
                await session.execute(
                    select(WarehouseAccessRule.brand_id).where(
                        WarehouseAccessRule.warehouse_id != warehouse_id,
                        WarehouseAccessRule.brand_id.in_(candidate_mark_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }

        other_references = await _load_other_mark_references(session, candidate_mark_ids)
        surviving_mark_ids = (
            used_by_models | used_by_dist | used_by_sp | used_by_wh | used_by_rules | other_references
        ) & candidate_mark_ids
    deleted_mark_ids = candidate_mark_ids - surviving_mark_ids

    # Retained list
    retained: list[dict[str, Any]] = []
    if surviving_mark_ids:
        mark_rows = (
            await session.execute(
                select(SpecialEquipmentMark.name)
                .where(SpecialEquipmentMark.id.in_(surviving_mark_ids))
                .order_by(SpecialEquipmentMark.name.asc())
            )
        ).scalars().all()
        retained.extend(
            {
                "type": "mark",
                "name": name,
                "reason": f"Марка {name} используется другими складами или дистрибьюторами",
            }
            for name in mark_rows
        )

    if surviving_model_ids:
        model_rows = (
            await session.execute(
                select(SpecialEquipmentModel.name)
                .where(SpecialEquipmentModel.id.in_(surviving_model_ids))
                .order_by(SpecialEquipmentModel.name.asc())
            )
        ).scalars().all()
        retained.extend(
            {
                "type": "model",
                "name": name,
                "reason": f"Модель {name} используется другими складами",
            }
            for name in model_rows
        )

    if surviving_mod_ids:
        mod_rows = (
            await session.execute(
                select(SpecialEquipmentModification.name)
                .where(SpecialEquipmentModification.id.in_(surviving_mod_ids))
                .order_by(SpecialEquipmentModification.name.asc())
            )
        ).scalars().all()
        retained.extend(
            {
                "type": "modification",
                "name": name,
                "reason": f"Модификация {name} используется другими объявлениями",
            }
            for name in mod_rows
        )

    # Auxiliary counts
    images_count = 0
    cart_count = 0
    fav_count = 0
    if product_ids:
        images_count = int(
            (
                await session.scalar(
                    select(func.count(SpecialEquipmentProductImage.id)).where(
                        SpecialEquipmentProductImage.product_id.in_(product_ids)
                    )
                )
            )
            or 0
        )
        cart_count = int(
            (
                await session.scalar(
                    select(func.count(SpecialEquipmentCartItem.id)).where(
                        SpecialEquipmentCartItem.product_id.in_(product_ids)
                    )
                )
            )
            or 0
        ) + int(
            (
                await session.scalar(
                    select(func.count(ExchangeCartItem.id)).where(
                        ExchangeCartItem.product_id.in_(product_ids)
                    )
                )
            )
            or 0
        )
        fav_count = int(
            (
                await session.scalar(
                    select(func.count(SpecialEquipmentFavorite.product_id)).where(
                        SpecialEquipmentFavorite.product_id.in_(product_ids)
                    )
                )
            )
            or 0
        ) + int(
            (
                await session.scalar(
                    select(func.count(UserFavorite.product_id)).where(
                        UserFavorite.product_id.in_(product_ids)
                    )
                )
            )
            or 0
        )

    rules_count = int(
        (
            await session.scalar(
                select(func.count(WarehouseAccessRule.id)).where(
                    WarehouseAccessRule.warehouse_id == warehouse_id
                )
            )
        )
        or 0
    )

    storefront_bindings_count = int(
        (
            await session.scalar(
                select(func.count(StorefrontWarehouse.storefront_id)).where(
                    StorefrontWarehouse.warehouse_id == warehouse_id
                )
            )
        )
        or 0
    )

    attr_values_count = 0
    if deleted_mod_ids:
        attr_values_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(SpecialEquipmentModificationAttributeValue)
                    .where(
                        SpecialEquipmentModificationAttributeValue.modification_id.in_(
                            deleted_mod_ids
                        )
                    )
                )
            )
            or 0
        )

    counts = {
        "products": len(product_ids),
        "marks": len(deleted_mark_ids),
        "models": len(deleted_model_ids),
        "modifications": len(deleted_mod_ids),
        "characteristics": 0,
        "characteristic_groups": 0,
        "trims": len(deleted_trim_ids),
        "characteristic_values": attr_values_count,
        "images": images_count,
        "cart_items": cart_count,
        "favorites": fav_count,
        "access_rules": rules_count,
        "storefront_bindings": storefront_bindings_count,
    }

    catalog_revision = await cascade_repo.get_catalog_revision(session)

    payload = {
        "warehouse_id": str(warehouse_id),
        "catalog_revision": catalog_revision,
        "selected_marks": sorted(str(m) for m in candidate_mark_ids),
        "category_id": str(warehouse.category_id) if warehouse.category_id else None,
        "product_ids": sorted(str(p) for p in product_ids),
        "deleted_marks": sorted(str(m) for m in deleted_mark_ids),
        "deleted_models": sorted(str(m) for m in deleted_model_ids),
        "deleted_modifications": sorted(str(m) for m in deleted_mod_ids),
        "deleted_trims": sorted(str(t) for t in deleted_trim_ids),
        "counts": counts,
    }
    raw_token = json.dumps(payload, sort_keys=True).encode("utf-8")
    preview_token = hashlib.sha256(raw_token).hexdigest()

    return {
        "warehouse": warehouse_info,
        "counts": counts,
        "retained": retained,
        "blockers": blockers,
        "can_delete": can_delete,
        "catalog_revision": catalog_revision,
        "preview_token": preview_token,
    }


@timed_repository
async def execute_warehouse_cascade_delete(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    warehouse_id: UUID,
    confirmation: str,
    preview_token: str,
    user_id: UUID | None,
) -> dict[str, Any]:
    """Execute confirmed warehouse cascade deletion atomically."""
    if confirmation != "УДАЛИТЬ":
        raise WarehouseCascadeConfirmationInvalidError()

    # 1. Exclusive advisory lock for catalog mutations
    await cascade_repo.lock_catalog_for_mutation(session)

    # 2. Lock warehouse row
    warehouse = await session.get(Warehouse, warehouse_id, with_for_update=True)
    if warehouse is None:
        raise WarehouseNotFoundError(warehouse_id)

    # 3. Recalculate preview under lock
    preview = await get_warehouse_cascade_preview(session, warehouse_id)

    if preview["preview_token"] != preview_token:
        raise WarehouseCascadePreviewStaleError()

    if not preview["can_delete"]:
        blocker_titles = ", ".join(b["title"] for b in preview["blockers"])
        raise WarehouseCascadeDeleteBlockedError(
            f"Каскадное удаление склада заблокировано: {blocker_titles}"
        )

    # 4. Perform deletions
    prod_stmt = select(
        SpecialEquipmentProduct.id,
        SpecialEquipmentProduct.model_id,
        SpecialEquipmentProduct.modification_id,
        SpecialEquipmentProduct.trim_id,
    ).where(SpecialEquipmentProduct.warehouse_id == warehouse_id)
    products_rows = (await session.execute(prod_stmt)).all()
    product_ids = {r[0] for r in products_rows}

    # Decouple transfers history snapshots (nullable FK)
    await session.execute(
        sa.update(VehicleWarehouseTransfer)
        .where(VehicleWarehouseTransfer.source_warehouse_id == warehouse_id)
        .values(source_warehouse_id=None)
    )
    await session.execute(
        sa.update(VehicleWarehouseTransfer)
        .where(VehicleWarehouseTransfer.destination_warehouse_id == warehouse_id)
        .values(destination_warehouse_id=None)
    )
    if product_ids:
        await session.execute(
            sa.update(VehicleWarehouseTransfer)
            .where(VehicleWarehouseTransfer.product_id.in_(product_ids))
            .values(product_id=None)
        )

    # Decouple import jobs
    await session.execute(
        sa.update(SpecialEquipmentImportJob)
        .where(SpecialEquipmentImportJob.target_warehouse_id == warehouse_id)
        .values(target_warehouse_id=None)
    )

    # Storefront bindings
    await session.execute(
        sa.delete(StorefrontWarehouse).where(
            StorefrontWarehouse.warehouse_id == warehouse_id
        )
    )

    # Exchange warehouse links
    await session.execute(
        sa.delete(ExchangeCartItemWarehouse).where(
            ExchangeCartItemWarehouse.warehouse_id == warehouse_id
        )
    )
    await session.execute(
        sa.delete(ExchangeRequestWarehouse).where(
            ExchangeRequestWarehouse.warehouse_id == warehouse_id
        )
    )

    # Access rules
    await session.execute(
        sa.delete(WarehouseAccessRule).where(
            WarehouseAccessRule.warehouse_id == warehouse_id
        )
    )

    media_storage_keys: set[str] = set()
    if product_ids:
        img_stmt = select(SpecialEquipmentProductImage.storage_key).where(
            SpecialEquipmentProductImage.product_id.in_(product_ids)
        )
        keys = (await session.execute(img_stmt)).scalars().all()
        for k in keys:
            if k:
                media_storage_keys.add(k)
                await cascade_repo.enqueue_media_cleanup(session, k)

        await session.execute(
            sa.delete(SpecialEquipmentProductImage).where(
                SpecialEquipmentProductImage.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentCartItem).where(
                SpecialEquipmentCartItem.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(ExchangeCartItem).where(
                ExchangeCartItem.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentFavorite).where(
                SpecialEquipmentFavorite.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(UserFavorite).where(
                UserFavorite.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentProductCategory).where(
                SpecialEquipmentProductCategory.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentProductAttachment).where(
                SpecialEquipmentProductAttachment.product_id.in_(product_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.id.in_(product_ids)
            )
        )

    # Re-evaluate candidate dictionary items to delete
    candidate_mod_ids = {r[2] for r in products_rows if r[2] is not None}
    candidate_model_ids = {r[1] for r in products_rows if r[1] is not None}
    candidate_trim_ids = {r[3] for r in products_rows if r[3] is not None}

    if candidate_mod_ids:
        mod_model_rows = (
            await session.execute(
                select(SpecialEquipmentModification.model_id).where(
                    SpecialEquipmentModification.id.in_(candidate_mod_ids)
                )
            )
        ).scalars().all()
        candidate_model_ids.update(m for m in mod_model_rows if m is not None)

    candidate_mark_ids = set((await session.execute(
        select(WarehouseMark.mark_id).where(WarehouseMark.warehouse_id == warehouse_id)
    )).scalars().all())
    if candidate_model_ids:
        model_mark_rows = (
            await session.execute(
                select(SpecialEquipmentModel.mark_id).where(
                    SpecialEquipmentModel.id.in_(candidate_model_ids)
                )
            )
        ).scalars().all()
        candidate_mark_ids.update(m for m in model_mark_rows if m is not None)

    # Trims
    surviving_trim_ids: set[UUID] = set()
    if candidate_trim_ids:
        surviving_trim_ids = {
            x
            for x in (
                await session.execute(
                    select(SpecialEquipmentProduct.trim_id).where(
                        SpecialEquipmentProduct.trim_id.in_(candidate_trim_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }
    deleted_trim_ids = candidate_trim_ids - surviving_trim_ids

    # Modifications
    surviving_mod_ids: set[UUID] = set()
    if candidate_mod_ids:
        surviving_mod_ids = {
            x
            for x in (
                await session.execute(
                    select(SpecialEquipmentProduct.modification_id).where(
                        SpecialEquipmentProduct.modification_id.in_(candidate_mod_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }
    deleted_mod_ids = candidate_mod_ids - surviving_mod_ids

    # Models
    surviving_model_ids: set[UUID] = set()
    if candidate_model_ids:
        used_by_products = {
            x
            for x in (
                await session.execute(
                    select(SpecialEquipmentProduct.model_id).where(
                        SpecialEquipmentProduct.model_id.in_(candidate_model_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }
        mods_query = select(SpecialEquipmentModification.model_id).where(
            SpecialEquipmentModification.model_id.in_(candidate_model_ids)
        )
        if deleted_mod_ids:
            mods_query = mods_query.where(
                SpecialEquipmentModification.id.not_in(deleted_mod_ids)
            )
        used_by_mods = {
            x
            for x in (await session.execute(mods_query)).scalars().all()
            if x is not None
        }
        surviving_model_ids = (used_by_products | used_by_mods) & candidate_model_ids
    deleted_model_ids = candidate_model_ids - surviving_model_ids

    # Marks
    surviving_mark_ids: set[UUID] = set()
    if candidate_mark_ids:
        models_query = select(SpecialEquipmentModel.mark_id).where(
            SpecialEquipmentModel.mark_id.in_(candidate_mark_ids)
        )
        if deleted_model_ids:
            models_query = models_query.where(
                SpecialEquipmentModel.id.not_in(deleted_model_ids)
            )
        used_by_models = {
            x
            for x in (await session.execute(models_query)).scalars().all()
            if x is not None
        }

        used_by_dist = {
            x
            for x in (
                await session.execute(
                    select(DistributorBrand.brand_id).where(
                        DistributorBrand.brand_id.in_(candidate_mark_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }

        used_by_sp = {
            x
            for x in (
                await session.execute(
                    select(SupportProgramMark.mark_id).where(
                        SupportProgramMark.mark_id.in_(candidate_mark_ids)
                    )
                )
            ).scalars().all()
            if x is not None
        }

        used_by_wh = {
            x
            for x in (
                await session.execute(
                    select(WarehouseMark.mark_id).where(
                        WarehouseMark.warehouse_id != warehouse_id,
                        WarehouseMark.mark_id.in_(candidate_mark_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }

        used_by_rules = {
            x
            for x in (
                await session.execute(
                    select(WarehouseAccessRule.brand_id).where(
                        WarehouseAccessRule.warehouse_id != warehouse_id,
                        WarehouseAccessRule.brand_id.in_(candidate_mark_ids),
                    )
                )
            ).scalars().all()
            if x is not None
        }

        other_references = await _load_other_mark_references(session, candidate_mark_ids)
        surviving_mark_ids = (
            used_by_models | used_by_dist | used_by_sp | used_by_wh | used_by_rules | other_references
        ) & candidate_mark_ids
    deleted_mark_ids = candidate_mark_ids - surviving_mark_ids

    # Remove this warehouse's selections before pruning selected marks.
    await session.execute(sa.delete(WarehouseMark).where(WarehouseMark.warehouse_id == warehouse_id))

    # Delete dictionary items bottom-up
    if deleted_trim_ids:
        await session.execute(
            sa.delete(SpecialEquipmentTrim).where(
                SpecialEquipmentTrim.id.in_(deleted_trim_ids)
            )
        )
    if deleted_mod_ids:
        await session.execute(
            sa.delete(SpecialEquipmentModificationAttributeValue).where(
                SpecialEquipmentModificationAttributeValue.modification_id.in_(deleted_mod_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentModification).where(
                SpecialEquipmentModification.id.in_(deleted_mod_ids)
            )
        )
    if deleted_model_ids:
        await session.execute(
            sa.delete(SpecialEquipmentModel).where(
                SpecialEquipmentModel.id.in_(deleted_model_ids)
            )
        )
    if deleted_mark_ids:
        await session.execute(
            sa.delete(SpecialEquipmentMark).where(
                SpecialEquipmentMark.id.in_(deleted_mark_ids)
            )
        )

    # Delete warehouse
    warehouse_name = warehouse.name
    await session.delete(warehouse)

    # Increment catalog revision
    new_revision = await cascade_repo.increment_catalog_revision(session)

    # Write immutable deletion log
    log_entry = SpecialEquipmentCatalogDeletionLog(
        user_id=user_id,
        root_type="warehouse",
        root_id=warehouse_id,
        root_code=None,
        root_name=warehouse_name,
        catalog_revision=new_revision,
        counts=preview["counts"],
        items=[{"type": "product", "count": len(product_ids)}],
    )
    session.add(log_entry)
    await session.flush()

    return {
        "warehouse_id": warehouse_id,
        "deleted": preview["counts"],
        "retained": preview["retained"],
        "catalog_revision": new_revision,
        "media_cleanup": {
            "enqueued_storage_keys_count": len(media_storage_keys),
            "status": "scheduled",
        },
        "message": "Склад и связанные данные успешно удалены",
    }


get_warehouse_delete_preview = get_warehouse_cascade_preview
